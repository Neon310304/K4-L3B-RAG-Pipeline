"""Offline adapter tests using the starter 0.2.8 response shape, no live API."""

from copy import deepcopy

import pytest
import requests

from src import task8_pageindex_vectorless as pageindex
from src.contracts import validate_search_results
from src.corpus_io import sha256


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not call a live provider")
    monkeypatch.setattr(requests, "request", forbidden)


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(pageindex, "ROOT", tmp_path)
    monkeypatch.setattr(pageindex, "CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setenv("PAGEINDEX_API_KEY", "offline-test-key")
    pdf = tmp_path / "data/landing/legal/policy.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-offline-fixture")
    document = {"id": "policy", "content": "## PDF page 1\nOriginal first page.\n## PDF page 2\nOriginal MFA evidence.",
                "metadata": {"source": "policy.md", "title": "Policy", "doc_type": "legal",
                             "url": "https://example.org/policy.pdf", "document_id": "policy",
                             "landing_file": "data/landing/legal/policy.pdf",
                             "landing_sha256": sha256(pdf.read_bytes())}}
    monkeypatch.setattr(pageindex, "load_documents", lambda: [document])
    return document, pdf


def test_missing_key_never_starts_network_or_upload(monkeypatch):
    monkeypatch.delenv("PAGEINDEX_API_KEY", raising=False)
    with pytest.raises(pageindex.PageIndexNotConfigured):
        pageindex.upload_documents()
    with pytest.raises(pageindex.PageIndexNotConfigured):
        pageindex.pageindex_search("MFA")
    assert pageindex.pageindex_search(" ") == []


def test_upload_cache_reuses_digest_refreshes_changes_and_scopes_account(corpus, monkeypatch):
    document, pdf = corpus
    handles = []

    def submit(method, path, key, deadline, **kwargs):
        assert method == "POST" and path == "/doc/"
        handle = kwargs["files"]["file"][1]
        assert handle.read() == pdf.read_bytes()
        handles.append(handle)
        return {"doc_id": f"remote-{len(handles)}"}

    monkeypatch.setattr(pageindex, "_request", submit)
    pageindex.upload_documents()
    pageindex.upload_documents()
    assert len(handles) == 1 and handles[0].closed
    pdf.write_bytes(b"%PDF-new-snapshot")
    with pytest.raises(pageindex.PageIndexUnavailable, match="changed"):
        pageindex.upload_documents()
    document["metadata"]["landing_sha256"] = sha256(pdf.read_bytes())
    pageindex.upload_documents()
    assert len(handles) == 2
    monkeypatch.setenv("PAGEINDEX_API_KEY", "different-offline-key")
    pageindex.upload_documents()
    assert len(handles) == 3 and all(handle.closed for handle in handles)


def test_query_requires_explicit_upload(corpus):
    with pytest.raises(pageindex.PageIndexNotReady, match="explicitly"):
        pageindex.pageindex_search("MFA")


def test_parsing_keeps_local_evidence_provenance_stable_ids_and_unique_pages(corpus):
    document, _ = corpus
    payload = {"retrieved_nodes": [{"title": "node", "relevant_contents": [
        {"page_index": 2, "relevant_content": "Provider prose must not become evidence"},
        {"page_index": 2, "relevant_content": "Duplicate page"}, {"page_index": 1}]}]}
    before = deepcopy(payload)
    results = pageindex._parse_pages(payload, document)
    validate_search_results(results, expected_method="pageindex")
    assert [r["id"] for r in results] == ["policy::pageindex-page-2", "policy::pageindex-page-1"]
    assert results[0]["content"] == "Original MFA evidence."
    assert results[0]["metadata"]["pdf_page"] == 2
    assert results[0]["metadata"]["url"] == document["metadata"]["url"]
    assert payload == before
    payload["retrieved_nodes"][0]["relevant_contents"][0]["page_index"] = 99
    with pytest.raises(pageindex.PageIndexUnavailable, match="outside"):
        pageindex._parse_pages(payload, document)


def test_query_polls_then_parses_completed_results(corpus, monkeypatch):
    replies = iter([{"doc_id": "doc-1"}, {"retrieval_ready": True},
                    {"retrieval_id": "r-1"}, {"status": "processing"},
                    {"status": "completed", "retrieved_nodes": [
                        {"relevant_contents": [{"page_index": 2}, {"page_index": 1}]}]}])
    calls, waits = [], []

    def request(method, path, key, deadline, **kwargs):
        calls.append((method, path))
        return next(replies)

    monkeypatch.setattr(pageindex, "_request", request)
    monkeypatch.setattr(pageindex.time, "sleep", waits.append)
    pageindex.upload_documents()
    results = pageindex.pageindex_search("MFA", top_k=1)
    validate_search_results(results, top_k=1, expected_method="pageindex")
    assert results[0]["metadata"]["pdf_page"] == 2
    assert len(waits) == 1 and len(calls) == 5


def test_polling_stops_at_budget(corpus, monkeypatch):
    monkeypatch.setattr(pageindex, "_request", lambda *args, **kwargs: {"doc_id": "doc-1"})
    pageindex.upload_documents()
    replies = iter([{"retrieval_ready": True}, {"retrieval_id": "r-1"}, {"status": "processing"}])
    monkeypatch.setattr(pageindex, "_request", lambda *args, **kwargs: next(replies))
    times = iter([0., 31.])
    monkeypatch.setattr(pageindex.time, "monotonic", lambda: next(times))
    with pytest.raises(TimeoutError, match="polling"):
        pageindex.pageindex_search("MFA")


def test_transport_has_timeouts_and_sanitizes_provider_errors(monkeypatch):
    calls = []

    class Response:
        status_code = 401
        def close(self):
            pass
        def json(self):
            raise AssertionError("Do not parse an HTTP error body")

    def request(method, url, **kwargs):
        calls.append(kwargs)
        return Response()

    monkeypatch.setattr(requests, "request", request)
    monkeypatch.setattr(pageindex.time, "monotonic", lambda: 1.)
    with pytest.raises(pageindex.PageIndexUnavailable, match="HTTP 401"):
        pageindex._request("GET", "/doc/x/", "private-key", 20.)
    assert calls[0]["timeout"] == (5., 10.)
    assert calls[0]["allow_redirects"] is False
    with pytest.raises(TimeoutError, match="budget"):
        pageindex._request("GET", "/doc/x/", "private-key", 0.)
    assert len(calls) == 1
