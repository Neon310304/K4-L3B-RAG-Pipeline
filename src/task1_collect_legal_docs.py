"""Download reviewed NIST guidance PDFs and preserve source metadata.

Existing snapshots are verified and reused. Use --refresh deliberately when
updating the corpus, then rebuild the index and evaluation results.
"""

import argparse
import io
from pathlib import Path

import pdfplumber

from .corpus_io import fetch, read_json, sha256, utc_now, write_bytes, write_json
from .corpus_sources import LEGAL_SOURCES, RIGHTS, RIGHTS_URL

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "landing" / "legal"


def setup_directory() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def validate_pdf(data: bytes) -> int:
    if len(data) <= 1024 or not data.startswith(b"%PDF-"):
        raise ValueError("Expected a real PDF, not HTML or an empty download")
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if not pdf.pages or not any((p.extract_text() or "").strip() for p in pdf.pages[:3]):
            raise ValueError("PDF has no usable text; OCR/manual review is required")
        return len(pdf.pages)


def download_documents(*, refresh: bool = False) -> None:
    setup_directory()
    for source in LEGAL_SOURCES:
        output = DATA_DIR / source["filename"]
        sidecar = output.with_suffix(".metadata.json")
        if output.exists() and sidecar.exists() and not refresh:
            metadata = read_json(sidecar)
            if metadata.get("url") != source["url"] or metadata.get("sha256") != sha256(output.read_bytes()):
                raise ValueError(f"Changed snapshot: {output}; review it or use --refresh")
            validate_pdf(output.read_bytes())
            print(f"Reused: {output.name}", flush=True)
            continue
        response = fetch(source["url"])
        pages = validate_pdf(response.content)
        digest = sha256(response.content)
        metadata = {
            **source,
            "doc_type": "legal",
            "publisher": "NIST",
            "language": "en",
            "edition": "Revision 4, final, July 2025",
            "date_published": "2025-07-31",
            "date_crawled": utc_now(),
            "resolved_url": response.url,
            "sha256": digest,
            "page_count": pages,
            "license": RIGHTS,
            "license_url": RIGHTS_URL,
        }
        if sidecar.exists():
            previous = read_json(sidecar)
            if previous.get("sha256") == digest and previous.get("url") == source["url"]:
                metadata["date_crawled"] = previous["date_crawled"]
        write_bytes(output, response.content)
        write_json(sidecar, metadata)
        print(f"Saved: {output.name} ({pages} pages, {len(response.content):,} bytes)", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Explicitly update existing snapshots")
    download_documents(refresh=parser.parse_args().refresh)
