"""Small shared helpers for reproducible corpus snapshots."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(url: str) -> requests.Response:
    response = requests.get(
        url,
        headers={"User-Agent": "RAG-Lab08-Corpus/1.0 (educational source collection)"},
        timeout=(15, 90),
    )
    # Never turn an HTTP error / WAF response into a corpus document.
    response.raise_for_status()
    return response


def write_bytes(path: Path, data: bytes) -> None:
    """Replace a stable filename only after producing complete output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def write_json(path: Path, value: object) -> None:
    write_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_article(article: dict) -> None:
    for key in ("url", "title", "date_crawled", "content_markdown"):
        if not isinstance(article.get(key), str) or not article[key].strip():
            raise ValueError(f"Article is missing a non-empty {key}")
    if not article["url"].startswith("https://"):
        raise ValueError("Article source must be an HTTPS URL")
    if datetime.fromisoformat(article["date_crawled"]).tzinfo is None:
        raise ValueError("date_crawled must include a timezone")
    if len(article["content_markdown"].strip()) < 200:
        raise ValueError("Article body is too short (minimum 200 characters)")
    digest = sha256(article["content_markdown"].encode("utf-8"))
    if article.get("content_sha256") != digest:
        raise ValueError("Article content hash does not match its body")
