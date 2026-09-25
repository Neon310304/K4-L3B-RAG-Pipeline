"""BM25 over the exact chunk snapshot in Chroma, with no embedding/model load."""

import argparse
import copy
import json
import math
import re
import unicodedata

from rank_bm25 import BM25Okapi

from .contracts import validate_document, validate_search_results
from .task4_chunking_indexing import chunk_fingerprint, ensure_ready, get_collection, stored_chunks

CORPUS: list[dict] = []  # Optional in-memory fixture; production reads Chroma.
_CACHE = None
TOKENIZER_VERSION = "unicode-compound-v1"


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).casefold()
    tokens = re.findall(r"[^\W_]+(?:[-.][^\W_]+)*", text, flags=re.UNICODE)
    # Keep exact publication identifiers as well as their searchable components.
    return tokens + [part for token in tokens if '-' in token or '.' in token
                     for part in re.split(r"[-.]", token)]


class PositiveBM25(BM25Okapi):
    """Okapi term frequency/length weighting with Lucene-style positive IDF.

    log(1 + (N - df + .5)/(df + .5)) avoids all-zero IDF in tiny corpora,
    including the starter's two-document contract fixture.
    """
    def _calc_idf(self, nd):
        self.idf = {word: math.log1p((self.corpus_size - freq + 0.5) / (freq + 0.5))
                    for word, freq in nd.items()}


def build_bm25_index(corpus: list[dict]):
    if not corpus:
        return None
    if len({chunk["id"] for chunk in corpus}) != len(corpus):
        raise ValueError("Duplicate BM25 chunk IDs")
    for chunk in corpus:
        validate_document(chunk, require_chunk=True)
    tokenized = [tokenize(chunk["metadata"]["title"] + "\n" + chunk["content"]) for chunk in corpus]
    if not any(tokenized):
        return None
    return PositiveBM25(tokenized, k1=1.5, b=0.75)


def _active_corpus():
    global _CACHE
    if CORPUS:
        return CORPUS, build_bm25_index(CORPUS)
    collection = get_collection()
    ensure_ready(collection)
    signature = (str(collection.id), collection.metadata.get("chunk_sha256"))
    if _CACHE is None or _CACHE[0] != signature:
        corpus = stored_chunks(collection)
        if chunk_fingerprint(corpus) != signature[1]:
            raise RuntimeError("Chroma corpus hash mismatch; rebuild the index")
        _CACHE = (signature, corpus, build_bm25_index(corpus))
    return _CACHE[1], _CACHE[2]


def lexical_search(query: str, top_k: int = 10) -> list[dict]:
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k must be an integer")
    tokens = tokenize(query)
    if not tokens or top_k <= 0:
        return []
    corpus, bm25 = _active_corpus()
    if bm25 is None:
        return []
    scores = bm25.get_scores(tokens)
    indices = sorted(range(len(corpus)), key=lambda i: (-float(scores[i]), corpus[i]["id"]))
    results = []
    for index in indices[:top_k]:
        score = float(scores[index])
        if score <= 0:
            continue
        results.append({**copy.deepcopy(corpus[index]), "score": score, "retrieval_method": "bm25"})
    validate_search_results(results, top_k=top_k, expected_method="bm25")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="password minimum 15 characters")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(lexical_search(args.query, args.top_k), ensure_ascii=False, indent=2))
