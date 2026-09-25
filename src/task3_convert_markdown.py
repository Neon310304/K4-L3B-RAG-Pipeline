"""Convert landing snapshots to Markdown with verifiable provenance.

PDF text is extracted locally page by page with pdfplumber. Original page
numbers remain available for source checks. DOCX uses MarkItDown; legacy DOC
requires conversion to DOCX first. No LLM, translation or API key is used.
"""

import unicodedata
from pathlib import Path

import pdfplumber
import yaml

from .corpus_io import read_json, sha256, validate_article, write_bytes, write_json
from .corpus_sources import TOPIC

ROOT = Path(__file__).resolve().parent.parent
LANDING_DIR = ROOT / "data" / "landing"
OUTPUT_DIR = ROOT / "data" / "standardized"
MANIFEST_PATH = ROOT / "data" / "corpus_manifest.json"


def page_to_markdown(page) -> str:
    """Keep ruled tables in columns instead of interleaving their row text."""
    tables = [table for table in page.find_tables()
              if len(table.rows) >= 2 and len(table.columns) >= 2]
    sections = []
    cursor = 0.0
    for table in sorted(tables, key=lambda item: item.bbox[1]):
        top, bottom = table.bbox[1], table.bbox[3]
        if top < cursor:
            raise ValueError(f"Overlapping tables on PDF page {page.page_number}; manual review required")
        if top > cursor:
            sections.append(page.crop((0, cursor, page.width, top)).extract_text(x_tolerance=2) or "")
        rows = table.extract(x_tolerance=2)
        width = max(len(row) for row in rows)
        def cell(value):
            return (value or "").strip().replace("|", "\\|").replace("\n", "<br>")
        rendered = ["| " + " | ".join(cell(value) for value in row + [None] * (width - len(row))) + " |" for row in rows]
        rendered.insert(1, "| " + " | ".join(["---"] * width) + " |")
        sections.append("\n".join(rendered))
        cursor = bottom
    if cursor < page.height:
        sections.append(page.crop((0, cursor, page.width, page.height)).extract_text(x_tolerance=2) or "")
    text = "\n\n".join(section for section in sections if section.strip())
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def pdf_to_markdown(path: Path) -> tuple[str, int]:
    pages = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            text = page_to_markdown(page)
            if not text:
                text = "[No extractable text on this PDF page; consult the original PDF.]"
            pages.append(f"## PDF page {number}\n\n{text}")
        page_count = len(pdf.pages)
    return "\n\n".join(pages) + "\n", page_count


def render_markdown(metadata: dict, content: str) -> bytes:
    if len(content.strip()) < 200:
        raise ValueError(f"Insufficient body text in {metadata.get('landing_file')}")
    header = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{header}\n---\n\n# {metadata['title']}\n\n{content.strip()}\n".encode("utf-8")


def provenance(metadata: dict, path: Path) -> dict:
    for key in ("id", "title", "url", "date_crawled", "license", "license_url"):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise ValueError(f"Missing {key} in metadata for {path.name}")
    return {
        **{key: value for key, value in metadata.items()
           if key not in {"content_markdown", "html_sha256", "filename", "sha256"}},
        "source": path.name,
        "landing_file": f"data/landing/{path.parent.name}/{path.name}",
        "landing_sha256": sha256(path.read_bytes()),
    }


def convert_legal_docs() -> None:
    output_dir = OUTPUT_DIR / "legal"
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = sorted(path for path in (LANDING_DIR / "legal").iterdir()
                   if path.suffix.lower() in {".pdf", ".doc", ".docx"})
    if len({path.stem for path in paths}) != len(paths):
        raise ValueError("Legal documents have colliding stems; use distinct filenames")
    for path in paths:
        metadata = read_json(path.with_suffix(".metadata.json"))
        if metadata.get("sha256") != sha256(path.read_bytes()):
            raise ValueError(f"Landing PDF/DOCX hash mismatch: {path.name}")
        details = provenance(metadata, path)
        if path.suffix.lower() == ".pdf":
            content, pages = pdf_to_markdown(path)
            details.update(page_count=pages, extraction="pdfplumber; PDF page markers; ruled tables as Markdown; no images")
        elif path.suffix.lower() == ".docx":
            from markitdown import MarkItDown
            content = MarkItDown().convert(str(path)).text_content
            details["extraction"] = "MarkItDown DOCX"
        else:
            raise ValueError(f"Convert legacy DOC to DOCX before normalization: {path.name}")
        details["doc_type"] = "legal"
        details["content_sha256"] = sha256(content.strip().encode("utf-8"))
        output = output_dir / f"{path.stem}.md"
        write_bytes(output, render_markdown(details, content))
        print(f"Converted: legal/{output.name} ({len(content):,} characters)", flush=True)


def convert_news_articles() -> None:
    output_dir = OUTPUT_DIR / "news"
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted((LANDING_DIR / "news").glob("*.json")):
        article = read_json(path)
        validate_article(article)
        details = provenance(article, path)
        details["doc_type"] = "news"
        output = output_dir / f"{path.stem}.md"
        write_bytes(output, render_markdown(details, article["content_markdown"]))
        print(f"Converted: news/{output.name}", flush=True)


def build_manifest() -> None:
    documents = []
    for path in sorted(OUTPUT_DIR.glob("*/*.md")):
        raw = path.read_bytes()
        parts = raw.decode("utf-8").split("---\n", 2)
        if len(parts) != 3 or parts[0]:
            raise ValueError(f"Missing provenance front matter: {path}")
        metadata = yaml.safe_load(parts[1])
        landing = ROOT / metadata["landing_file"]
        if not landing.is_file() or sha256(landing.read_bytes()) != metadata["landing_sha256"]:
            raise ValueError(f"Stale or untraceable Markdown: {path}")
        documents.append({
            **metadata,
            "standardized_file": f"data/standardized/{path.parent.name}/{path.name}",
            "standardized_sha256": sha256(raw),
            "standardized_bytes": len(raw),
        })
    identities = [document["id"] for document in documents]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate source IDs in corpus")
    digest = sha256("\n".join(f"{d['id']}:{d['landing_sha256']}:{d['standardized_sha256']}" for d in documents).encode())
    write_json(MANIFEST_PATH, {"schema_version": 1, "topic": TOPIC, "corpus_sha256": digest, "documents": documents})


def convert_all() -> None:
    convert_legal_docs()
    convert_news_articles()
    build_manifest()
    print(f"Manifest: {MANIFEST_PATH}", flush=True)


if __name__ == "__main__":
    convert_all()
