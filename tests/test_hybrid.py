"""Offline invariants for rank fusion and confidence routing."""

from copy import deepcopy

import pytest

from src.contracts import validate_search_results
from src.task7_reranking import rerank_rrf
from src import task9_retrieval_pipeline as pipeline


def item(identifier, score, method="dense"):
    return {"id": identifier, "content": f"Evidence for {identifier}",
            "score": score, "retrieval_method": method,
            "metadata": {"source": "policy.md", "title": "Account policy",
                         "doc_type": "legal", "url": "https://example.org/policy",
                         "chunk_index": 0, "pdf_page": 2}}


@pytest.mark.parametrize("k", [0, 60, 100])
def test_shared_rank_sum_and_deep_copy(k):
    inputs = [[item("a", .9), item("b", .8)],
              [item("b", 700, "bm25"), item("c", 1, "bm25")]]
    before = deepcopy(inputs)
    fused = rerank_rrf(inputs, top_k=3, k=k)
    assert [r["id"] for r in fused] == ["b", "a", "c"]
    assert fused[0]["score"] == pytest.approx(1 / (k + 2) + 1 / (k + 1))
    validate_search_results(fused, top_k=3, expected_method="hybrid")
    fused[0]["metadata"]["pdf_page"] = 99
    assert inputs == before


def test_rrf_ignores_score_magnitudes_and_uses_deterministic_ties():
    rankings = [[item("z", .9), item("a", .8)], [item("a", 50, "bm25"), item("z", 10, "bm25")]]
    baseline = rerank_rrf(rankings)
    rankings[0][0]["score"], rankings[0][1]["score"] = .2, -.1
    rankings[1][0]["score"], rankings[1][1]["score"] = 50000, 49999
    assert rerank_rrf(rankings) == baseline
    assert [x["id"] for x in baseline] == ["a", "z"]
    assert len(rerank_rrf(rankings, top_k=1)) == 1
    assert rerank_rrf([[], []]) == []
    assert rerank_rrf(rankings, top_k=0) == []


def test_rrf_rejects_duplicate_within_ranking_and_identity_conflict():
    a = item("a", .9)
    with pytest.raises(ValueError, match="unique"):
        rerank_rrf([[a, a]])
    b = item("a", 10, "bm25")
    b["content"] = "Different snapshot"
    with pytest.raises(ValueError, match="Conflicting"):
        rerank_rrf([[a], [b]])
    with pytest.raises(ValueError, match="sorted"):
        rerank_rrf([[item("a", .1), item("b", .9)]])
    with pytest.raises(ValueError, match="non-negative"):
        rerank_rrf([], k=-1)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_scores_fail_contract(score):
    with pytest.raises(ValueError, match="finite"):
        validate_search_results([item("a", score)])


def setup_pipeline(monkeypatch, dense, sparse, fallback):
    calls = {"dense": 0, "bm25": 0, "rrf": 0, "fallback": 0}

    def search(query, top_k):
        calls["dense"] += 1
        return dense[:top_k]

    def lexical(query, top_k):
        calls["bm25"] += 1
        return sparse[:top_k]

    def fuse(lists, top_k):
        calls["rrf"] += 1
        return rerank_rrf(lists, top_k=top_k)

    def alternate(query, top_k):
        calls["fallback"] += 1
        if isinstance(fallback, Exception):
            raise fallback
        return fallback

    monkeypatch.setattr(pipeline, "semantic_search", search)
    monkeypatch.setattr(pipeline, "lexical_search", lexical)
    monkeypatch.setattr(pipeline, "rerank_rrf", fuse)
    monkeypatch.setattr(pipeline, "pageindex_search", alternate)
    return calls


@pytest.mark.parametrize("cosine,expected_calls", [(.6, 0), (.9, 0), (.5999, 1), (-.3, 1)])
def test_boundary_uses_original_cosine_and_fuses_exactly_once(monkeypatch, cosine, expected_calls):
    dense, sparse = [item("a", cosine)], [item("a", 1e9, "bm25")]
    before = deepcopy([dense, sparse])
    calls = setup_pipeline(monkeypatch, dense, sparse, [])
    trace = pipeline.retrieve_with_trace("MFA", score_threshold=.6)
    assert calls == {"dense": 1, "bm25": 1, "rrf": 1, "fallback": expected_calls}
    assert trace["best_dense_score"] == cosine
    assert trace["results"][0]["score"] == pytest.approx(2 / 61)
    assert [dense, sparse] == before


@pytest.mark.parametrize("bad_fallback", [
    TimeoutError("secret-like-provider-message"), [],
    [item("x", .5)],
    [item("x", .5, "pageindex"), item("x", .5, "pageindex")],
    [item("x", float("inf"), "pageindex")],
    [item("x", 1, "pageindex"), item("y", .5, "pageindex")],
])
def test_provider_error_empty_or_malformed_preserves_hybrid(monkeypatch, caplog, bad_fallback):
    dense = [item("a", .2)]
    calls = setup_pipeline(monkeypatch, dense, [], bad_fallback)
    trace = pipeline.retrieve_with_trace("MFA", top_k=1, score_threshold=.6)
    assert trace["results"] == rerank_rrf([dense], top_k=1)
    assert calls["fallback"] == calls["rrf"] == 1
    assert "secret-like-provider-message" not in caplog.text + str(trace)


def test_successful_fallback_not_refused_or_fused_twice(monkeypatch):
    fallback = [item("page", 1, "pageindex")]
    calls = setup_pipeline(monkeypatch, [item("a", .2)], [], fallback)
    trace = pipeline.retrieve_with_trace("MFA")
    assert trace["results"] == fallback
    assert trace["fallback_status"] == "used"
    assert calls["rrf"] == calls["fallback"] == 1
    trace["results"][0]["metadata"]["pdf_page"] = 55
    assert fallback[0]["metadata"]["pdf_page"] == 2


def test_no_dense_results_always_attempts_fallback_even_at_negative_threshold(monkeypatch):
    calls = setup_pipeline(monkeypatch, [], [], TimeoutError())
    trace = pipeline.retrieve_with_trace("missing", score_threshold=-1)
    assert trace["best_dense_score"] is None
    assert trace["results"] == []
    assert calls["fallback"] == 1


def test_dense_baseline_skips_bm25_fusion_and_fallback(monkeypatch):
    dense = [item("a", .1)]
    calls = setup_pipeline(monkeypatch, dense, [], TimeoutError())
    assert pipeline.retrieve("MFA", use_reranking=False) == dense
    assert calls == {"dense": 1, "bm25": 0, "rrf": 0, "fallback": 0}


def test_empty_query_limits_and_invalid_threshold_do_no_work(monkeypatch):
    calls = setup_pipeline(monkeypatch, [], [], [])
    assert pipeline.retrieve("  ") == pipeline.retrieve("MFA", top_k=0) == []
    for threshold in (float("nan"), 2, -2):
        with pytest.raises(ValueError):
            pipeline.retrieve("MFA", score_threshold=threshold)
    assert sum(calls.values()) == 0
