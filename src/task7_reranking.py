"""Reciprocal Rank Fusion: combine ranks, never cosine and BM25 magnitudes."""

import copy
import json

from .contracts import validate_search_results


def rerank_rrf(
    ranked_lists: list[list[dict]],
    top_k: int = 5,
    k: int = 60,
) -> list[dict]:
    """Fuse independent rankings, preserving the source items and metadata."""
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k must be an integer")
    if isinstance(k, bool) or not isinstance(k, int) or k < 0:
        raise ValueError("RRF k must be a non-negative integer")
    if top_k <= 0:
        return []
    scores, items = {}, {}
    for ranked_list in ranked_lists:
        # Duplicate IDs inside one ranking are an upstream bug, not extra votes.
        validate_search_results(ranked_list)
        for rank, item in enumerate(ranked_list, start=1):
            identifier = item["id"]
            if identifier in items and (
                items[identifier]["content"] != item["content"]
                or items[identifier]["metadata"] != item["metadata"]
            ):
                raise ValueError(f"Conflicting content/metadata for shared ID: {identifier}")
            items.setdefault(identifier, item)
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (k + rank)
    results = []
    for identifier in sorted(scores, key=lambda key: (-scores[key], key))[:top_k]:
        fused = copy.deepcopy(items[identifier])
        fused["score"] = scores[identifier]
        fused["retrieval_method"] = "hybrid"
        results.append(fused)
    validate_search_results(results, top_k=top_k, expected_method="hybrid")
    return results


if __name__ == "__main__":
    def example(identifier, score, method):
        return {"id": identifier, "content": "Example evidence: use MFA.",
                "metadata": {"source": "example.md", "title": "RRF demo",
                             "doc_type": "news", "url": None, "chunk_index": 0},
                "score": score, "retrieval_method": method}

    dense = [example("a", 0.9, "dense"), example("b", 0.8, "dense")]
    sparse = [example("b", 7.0, "bm25"), example("c", 5.0, "bm25")]
    print(json.dumps({"demo": "b receives 1/62 + 1/61",
                      "results": rerank_rrf([dense, sparse], top_k=3)}, indent=2))
