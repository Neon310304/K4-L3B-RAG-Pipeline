"""Dense retrieval using Task 4's exact encoder and Chroma cosine distance."""

import argparse
import json
import math

from .contracts import validate_search_results
from .task4_chunking_indexing import embed_texts, ensure_ready, get_collection


def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k must be an integer")
    if not query.strip() or top_k <= 0:
        return []
    collection = get_collection()
    ensure_ready(collection)
    count = collection.count() if hasattr(collection, "count") else top_k
    if not count:
        return []
    response = collection.query(query_embeddings=embed_texts([query.strip()]),
        n_results=min(top_k, count), include=["documents", "metadatas", "distances"])
    unique = {}
    for identifier, content, raw_metadata, distance in zip(
        response["ids"][0], response["documents"][0], response["metadatas"][0],
        response["distances"][0], strict=True,
    ):
        if not math.isfinite(float(distance)):
            raise ValueError("Chroma returned a non-finite cosine distance")
        metadata = dict(raw_metadata)
        metadata.setdefault("url", None)
        # Preserve the true cosine range [-1, 1] for later threshold calibration.
        score = max(-1.0, min(1.0, 1.0 - float(distance)))
        item = {"id": identifier, "content": content, "metadata": metadata,
                "score": score, "retrieval_method": "dense"}
        if identifier not in unique or score > unique[identifier]["score"]:
            unique[identifier] = item
    results = sorted(unique.values(), key=lambda item: (-item["score"], item["id"]))[:top_k]
    validate_search_results(results, top_k=top_k, expected_method="dense")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="How long must a password be when used as the only authentication factor?")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(semantic_search(args.query, args.top_k), ensure_ascii=False, indent=2))
