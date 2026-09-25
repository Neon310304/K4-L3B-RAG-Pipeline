"""Hybrid retrieval with one RRF pass and fallback driven by original cosine."""

import argparse
import copy
import json
import logging
import math
import os

from .contracts import validate_search_results
from .task5_semantic_search import semantic_search
from .task6_lexical_search import lexical_search
from .task7_reranking import rerank_rrf
from .task8_pageindex_vectorless import pageindex_search

logger = logging.getLogger(__name__)
# Baseline is calibrated by src.calibrate_retrieval; an empty .env uses it.
SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD") or "0.60")
DEFAULT_TOP_K = 5


def retrieve_with_trace(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    score_threshold: float = SCORE_THRESHOLD,
    use_reranking: bool = True,
) -> dict:
    """Return results plus routing evidence for reports and the future UI.

    Dense-only mode disables both BM25 and fallback for an honest A/B baseline.
    A low-confidence hybrid result is preserved on provider failure; its presence
    does not establish sufficient evidence for generation to answer the question.
    """
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k must be an integer")
    if isinstance(score_threshold, bool) or not isinstance(score_threshold, (float, int)):
        raise TypeError("score_threshold must be numeric")
    if not math.isfinite(score_threshold) or not -1 <= score_threshold <= 1:
        raise ValueError("score_threshold must be a finite cosine in [-1, 1]")
    if not isinstance(use_reranking, bool):
        raise TypeError("use_reranking must be a bool")
    trace = {"mode": "hybrid" if use_reranking else "dense_only",
             "score_threshold": score_threshold, "best_dense_score": None,
             "dense_confident": False, "dense_count": 0, "bm25_count": 0,
             "rrf_calls": 0, "fallback_attempted": False,
             "fallback_status": "not_attempted", "fallback_error_type": None,
             "results": []}
    if not query.strip() or top_k <= 0:
        return trace
    dense = semantic_search(query.strip(), top_k=top_k * 2 if use_reranking else top_k)
    validate_search_results(dense, expected_method="dense")
    best_dense = max((item["score"] for item in dense), default=None)
    trace.update(best_dense_score=best_dense, dense_count=len(dense),
                 dense_confident=best_dense is not None and best_dense >= score_threshold)
    if not use_reranking:
        trace["results"] = copy.deepcopy(dense[:top_k])
        return trace

    sparse = lexical_search(query.strip(), top_k=top_k * 2)
    validate_search_results(sparse, expected_method="bm25")
    hybrid = rerank_rrf([dense, sparse], top_k=top_k)
    validate_search_results(hybrid, top_k=top_k, expected_method="hybrid")
    trace.update(bm25_count=len(sparse), rrf_calls=1)
    results = hybrid
    if not trace["dense_confident"]:
        trace["fallback_attempted"] = True
        try:
            fallback = pageindex_search(query.strip(), top_k=top_k)
            # Malformed provider output is a provider failure too.
            validate_search_results(fallback, top_k=top_k, expected_method="pageindex")
            if fallback:
                results = fallback
                trace["fallback_status"] = "used"
            else:
                trace["fallback_status"] = "empty"
        except Exception as exc:
            # Do not log exception text: some SDKs include request bodies/secrets.
            trace["fallback_status"] = "error"
            trace["fallback_error_type"] = type(exc).__name__
            logger.warning("PageIndex unavailable (%s); keeping hybrid results", type(exc).__name__)
    trace["results"] = copy.deepcopy(results)
    return trace


def retrieve(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    score_threshold: float = SCORE_THRESHOLD,
    use_reranking: bool = True,
) -> list[dict]:
    """Return SearchResults while keeping the starter's public interface."""
    return retrieve_with_trace(query, top_k, score_threshold, use_reranking)["results"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="How can I protect my account against phishing?")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--threshold", type=float, default=SCORE_THRESHOLD)
    parser.add_argument("--dense-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(retrieve_with_trace(args.query, args.top_k, args.threshold,
                                       not args.dense_only), ensure_ascii=False, indent=2))
