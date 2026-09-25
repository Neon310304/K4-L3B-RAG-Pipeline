"""Optional PageIndex adapter for the starter's pinned 0.2.8 API.

Uploads are explicit (Task 8 CLI), never triggered by a user search. Only the
original legal PDFs are uploaded. API-selected pages are resolved to the local
corpus so provider-generated prose cannot become source evidence.
"""

import argparse
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from .contracts import validate_search_results
from .corpus_io import read_json, sha256, write_json
from .task4_chunking_indexing import load_documents

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE_URL = "https://api.pageindex.ai"
CACHE_PATH = ROOT / "pageindex_doc_ids.json"
SEARCH_TIMEOUT_SECONDS = 30.0
UPLOAD_TIMEOUT_SECONDS = 90.0
POLL_INTERVAL_SECONDS = 1.0


class PageIndexUnavailable(RuntimeError):
    """Optional provider is not configured, unavailable, or has invalid output."""


class PageIndexNotConfigured(PageIndexUnavailable):
    pass


class PageIndexNotReady(PageIndexUnavailable):
    pass


def _api_key() -> str:
    key = os.getenv("PAGEINDEX_API_KEY", "").strip()
    if not key:
        raise PageIndexNotConfigured("Set PAGEINDEX_API_KEY before enabling PageIndex")
    return key


def _request(method: str, path: str, key: str, deadline: float, **kwargs) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("PageIndex time budget exhausted")
    # SDK 0.2.8 has no request timeout option. Match its REST endpoints using
    # a bounded transport instead of monkeypatching requests globally.
    try:
        response = requests.request(method, BASE_URL + path, headers={"api_key": key},
            timeout=(min(5.0, remaining), min(10.0, remaining)),
            allow_redirects=False, **kwargs)
        try:
            if response.status_code != 200:
                raise PageIndexUnavailable(f"PageIndex HTTP {response.status_code}")
            payload = response.json()
        finally:
            response.close()
    except requests.Timeout:
        raise TimeoutError("PageIndex request timed out") from None
    except (requests.RequestException, ValueError):
        raise PageIndexUnavailable("PageIndex transport or JSON error") from None
    if not isinstance(payload, dict):
        raise PageIndexUnavailable("PageIndex response must be an object")
    return payload


def _identifier(payload: dict, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PageIndexUnavailable(f"PageIndex response missing {field}")
    return value


def _pdf_documents() -> list[dict]:
    documents = []
    legal_root = (ROOT / "data/landing/legal").resolve()
    for document in load_documents():
        metadata = document["metadata"]
        if metadata["doc_type"] != "legal":
            continue
        path = (ROOT / metadata["landing_file"]).resolve()
        if not path.is_relative_to(legal_root) or path.suffix.lower() != ".pdf":
            raise PageIndexUnavailable("PageIndex adapter requires original landing/legal PDFs")
        if sha256(path.read_bytes()) != metadata["landing_sha256"]:
            raise PageIndexUnavailable("Landing PDF changed; rebuild the corpus before upload")
        documents.append(document)
    if not documents:
        raise PageIndexNotReady("No legal PDFs in the corpus")
    return documents


def _cache(key: str) -> dict:
    # A key change must not reuse document IDs belonging to another account.
    scope = sha256(key.encode("utf-8"))
    cache = read_json(CACHE_PATH) if CACHE_PATH.exists() else {}
    if cache.get("version") != 1 or cache.get("account_fingerprint") != scope:
        return {"version": 1, "account_fingerprint": scope, "documents": {}}
    if not isinstance(cache.get("documents"), dict):
        raise PageIndexUnavailable("Invalid document ID cache")
    return cache


def _cached_id(cache: dict, document: dict) -> str | None:
    entry = cache["documents"].get(document["id"], {})
    if entry.get("landing_sha256") == document["metadata"]["landing_sha256"]:
        return _identifier(entry, "doc_id")
    return None


def upload_documents() -> None:
    """Explicitly submit legal PDFs; save each returned ID atomically for reuse."""
    key = _api_key()
    documents = _pdf_documents()
    cache = _cache(key)
    for document in documents:
        if _cached_id(cache, document):
            continue
        path = ROOT / document["metadata"]["landing_file"]
        with path.open("rb") as handle:
            payload = _request("POST", "/doc/", key, time.monotonic() + UPLOAD_TIMEOUT_SECONDS,
                               files={"file": (path.name, handle, "application/pdf")},
                               data={"if_retrieval": True})
        cache["documents"][document["id"]] = {
            "doc_id": _identifier(payload, "doc_id"),
            "landing_sha256": document["metadata"]["landing_sha256"]}
        write_json(CACHE_PATH, cache)


def _parse_pages(payload: dict, document: dict) -> list[dict]:
    nodes = payload.get("retrieved_nodes")
    if not isinstance(nodes, list):
        raise PageIndexUnavailable("PageIndex response missing retrieved_nodes")
    # Physical PDF page numbers in standardized Markdown are one-based.
    markers = list(re.finditer(r"^## PDF page (\d+)\s*$", document["content"], re.MULTILINE))
    pages = {int(marker.group(1)): document["content"][marker.end():
             markers[i + 1].start() if i + 1 < len(markers) else len(document["content"])].strip()
             for i, marker in enumerate(markers)}
    results, seen = [], set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("relevant_contents"), list):
            raise PageIndexUnavailable("Invalid PageIndex node")
        for reference in node["relevant_contents"]:
            page = reference.get("page_index") if isinstance(reference, dict) else None
            if type(page) is not int or page not in pages or not pages[page]:
                raise PageIndexUnavailable("PageIndex selected a page outside the local PDF")
            if page in seen:
                continue
            seen.add(page)
            results.append({"id": f"{document['id']}::pageindex-page-{page}",
                "content": pages[page], "score": 1.0 / (len(results) + 1),
                "metadata": {**document["metadata"], "document_id": document["id"],
                             "chunk_index": page - 1, "pdf_page": page,
                             "score_kind": "reciprocal_page_rank_within_document"},
                "retrieval_method": "pageindex"})
    return results


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """Search already-uploaded PDFs with bounded requests and polling."""
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k must be an integer")
    if not query.strip() or top_k <= 0:
        return []
    key = _api_key()
    documents, cache = _pdf_documents(), _cache(key)
    bindings = [(document, _cached_id(cache, document)) for document in documents]
    if any(doc_id is None for _, doc_id in bindings):
        raise PageIndexNotReady("Run Task 8 upload explicitly for the current PDFs first")
    deadline = time.monotonic() + SEARCH_TIMEOUT_SECONDS
    results = []
    for document, doc_id in bindings:
        ready = _request("GET", f"/doc/{quote(doc_id, safe='')}/?type=tree&summary=False", key, deadline)
        if ready.get("retrieval_ready") is not True:
            raise PageIndexNotReady("PageIndex PDF processing has not finished")
        submitted = _request("POST", "/retrieval/", key, deadline,
                             json={"doc_id": doc_id, "query": query.strip(), "thinking": False})
        retrieval_id = _identifier(submitted, "retrieval_id")
        while True:
            payload = _request("GET", f"/retrieval/{quote(retrieval_id, safe='')}/", key, deadline)
            if payload.get("status") == "completed":
                results.extend(_parse_pages(payload, document))
                break
            if payload.get("status") not in {"pending", "processing", "queued", "running"}:
                raise PageIndexUnavailable("PageIndex retrieval failed or returned an unknown status")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("PageIndex polling timed out")
            time.sleep(min(POLL_INTERVAL_SECONDS, remaining))
    results.sort(key=lambda item: (-item["score"], item["id"]))
    results = results[:top_k]
    validate_search_results(results, top_k=top_k, expected_method="pageindex")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload", action="store_true", help="Submit legal PDFs explicitly")
    parser.add_argument("--query", help="Search PDFs already uploaded to PageIndex")
    args = parser.parse_args()
    try:
        if args.upload:
            upload_documents()
            print("Document IDs cached; processing may still be pending.")
        if args.query:
            print(json.dumps(pageindex_search(args.query), ensure_ascii=False, indent=2))
        if not args.upload and not args.query:
            parser.print_help()
    except (PageIndexUnavailable, TimeoutError) as exc:
        parser.exit(1, f"PageIndex unavailable ({type(exc).__name__}). Check configuration/status.\n")
