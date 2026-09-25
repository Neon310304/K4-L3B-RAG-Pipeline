"""Offline generation, citation and UI-boundary tests."""

from copy import deepcopy

import pytest

from src.contracts import validate_generation_result
from src import task10_generation as generation


def source(identifier="chunk-0", score=.8, method="hybrid", content=None):
    return {"id": identifier, "content": content or "Password verifiers SHALL require a minimum of 15 characters for single-factor authentication.",
            "score": score, "retrieval_method": method,
            "metadata": {"source": "nist_sp_800_63b_4.md", "title": "NIST Password Policy",
                         "doc_type": "legal", "url": "https://example.org/nist.pdf",
                         "chunk_index": 114, "pdf_page": 25}}


def trace(chunks, confident=True):
    return {"results": chunks, "dense_confident": confident, "best_dense_score": .8,
            "fallback_attempted": False, "fallback_status": "not_attempted", "rrf_calls": 1}


def model_payload(identifier="chunk-0", quote=None):
    return {"answerable": True, "claims": [{"text": "Mật khẩu dùng cho xác thực một yếu tố phải có ít nhất 15 ký tự.",
        "evidence": [{"id": identifier, "quote": quote or "Password verifiers SHALL require a minimum of 15 characters"}]}]}


def test_reorder_deep_copies_and_uses_lost_middle_order():
    chunks = [source(f"chunk-{i}", 1 - i / 10) for i in range(5)]
    original = deepcopy(chunks)
    reordered = generation.reorder_for_llm(chunks)
    assert [c["id"] for c in reordered] == ["chunk-0", "chunk-2", "chunk-4", "chunk-3", "chunk-1"]
    reordered[0]["metadata"]["pdf_page"] = 99
    assert chunks == original


def test_context_contains_stable_id_title_source_url_page_and_not_mutated():
    chunk = source()
    before = deepcopy(chunk)
    context = generation.format_context([chunk])
    assert '"id": "chunk-0"' in context
    assert "NIST Password Policy" in context and "nist_sp_800_63b_4.md" in context
    assert "pdf_page" in context and "https://example.org/nist.pdf" in context
    assert chunk == before


def test_call_llm_dispatches_openai_and_returns_only_output_text(monkeypatch):
    class Response:
        status = "completed"
        output_text = " plain text "
    class Responses:
        def create(self, **kwargs):
            assert kwargs["model"] == "test-model"
            assert kwargs["store"] is False
            return Response()
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.responses = Responses()
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(generation, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(generation, "LLM_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    import openai
    monkeypatch.setattr(openai, "OpenAI", Client)
    assert generation.call_llm("system", "user") == "plain text"


@pytest.mark.parametrize("provider,key", [("openai", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")])
def test_missing_provider_configuration_is_explicit_and_secret_free(monkeypatch, provider, key):
    monkeypatch.setattr(generation, "LLM_PROVIDER", provider)
    monkeypatch.setattr(generation, "LLM_MODEL", "")
    monkeypatch.delenv(key, raising=False)
    status = generation.llm_configuration_status()
    assert status["ready"] is False and key in status["missing"] and "test" not in str(status)
    with pytest.raises(generation.LLMNotConfigured):
        generation.call_llm("system", "user")


def test_generate_refuses_without_retrieval_or_provider(monkeypatch):
    monkeypatch.setattr(generation, "retrieve_with_trace", lambda query, top_k: trace([]))
    validate_generation_result(generation.generate_with_citation("outside", 5))
    assert generation.generate_with_citation("outside", 5)["retrieval_source"] == "none"


def test_generate_refuses_weak_hybrid_even_when_provider_configured(monkeypatch):
    monkeypatch.setattr(generation, "retrieve_with_trace", lambda query, top_k: trace([source()], confident=False))
    monkeypatch.setattr(generation, "call_llm", lambda *args: pytest.fail("weak evidence must not reach LLM"))
    result = generation.generate_with_citation("outside", 5)
    assert result == generation.safe_refusal()


def test_generate_validates_quotes_verifier_and_maps_only_cited_sources(monkeypatch):
    chunks = [source("chunk-0"), source("chunk-1", .7, content="MFA can protect accounts when a password is exposed.")]
    monkeypatch.setattr(generation, "retrieve_with_trace", lambda query, top_k: trace(chunks))
    calls = iter([json_text(model_payload()), json_text({"supported": True})])
    monkeypatch.setattr(generation, "call_llm", lambda *args: next(calls))
    result = generation.generate_with_citation("Mật khẩu?", 5)
    validate_generation_result(result)
    assert result["retrieval_source"] == "hybrid"
    assert [s["id"] for s in result["sources"]] == ["chunk-0"]
    assert "[1]" in result["answer"] and "[2]" not in result["answer"]
    assert result["sources"][0]["evidence_quotes"]


def json_text(value):
    import json
    return json.dumps(value, ensure_ascii=False)


def test_generate_rejects_fabricated_quote_and_verifier_failure(monkeypatch):
    chunk = source()
    monkeypatch.setattr(generation, "retrieve_with_trace", lambda query, top_k: trace([chunk]))
    monkeypatch.setattr(generation, "call_llm", lambda *args: json_text(model_payload(quote="fabricated statement absent from source")))
    result = generation.generate_with_citation("MFA?", 5)
    assert result["sources"] == [] and result["retrieval_source"] == "none"
    monkeypatch.setattr(generation, "call_llm", lambda *args: json_text(model_payload()))
    calls = iter([json_text(model_payload()), json_text({"supported": False})])
    monkeypatch.setattr(generation, "call_llm", lambda *args: next(calls))
    assert generation.generate_with_citation("MFA?", 5)["sources"] == []


def test_pageindex_generation_source_matches_route(monkeypatch):
    chunk = source("pageindex-page", 1., "pageindex")
    monkeypatch.setattr(generation, "retrieve_with_trace", lambda query, top_k: trace([chunk]))
    monkeypatch.setattr(generation, "call_llm", lambda *args: json_text(model_payload("pageindex-page")) if "PROPOSED_CLAIMS" not in args[1] else json_text({"supported": True}))
    result = generation.generate_with_citation("MFA?", 5)
    assert result["retrieval_source"] == "pageindex"
