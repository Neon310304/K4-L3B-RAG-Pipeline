"""Offline data integrity and collection failure regressions."""

import asyncio
import re
from pathlib import Path

import pytest
import requests
import yaml

from src import task2_crawl_news as crawler
from src import task3_convert_markdown as converter
from src.corpus_io import read_json, sha256, validate_article, write_json
from src.task1_collect_legal_docs import validate_pdf

ROOT = Path(__file__).resolve().parent.parent


def example_article():
    url = crawler.ARTICLE_URLS[0]
    html = f'''<html><h1>Account protection</h1>
    <nav>DO NOT INDEX NAVIGATION</nav>
    <div class="text-with-summary"><h2>Use MFA</h2>
    <p>{'Protect your account with an additional authentication factor. ' * 8}</p>
    <figure><img src="copyrighted.jpg"><figcaption>Shutterstock</figcaption></figure>
    <a href="/help">Read more</a></div>
    <div class="text-with-summary">DO NOT INDEX BIOGRAPHY</div></html>'''
    return crawler.extract_article(html.encode(), url)


def test_article_excludes_non_article_content_and_resolves_links():
    article = example_article()
    content = article["content_markdown"]
    assert "## Use MFA" in content
    assert "https://www.nist.gov/help" in content
    assert "DO NOT INDEX" not in content
    assert "Shutterstock" not in content
    assert "copyrighted.jpg" not in content
    validate_article(article)


def test_http_failure_does_not_silently_produce_a_document(monkeypatch):
    def blocked(url):
        raise requests.HTTPError("403 Forbidden")
    monkeypatch.setattr(crawler, "fetch", blocked)
    with pytest.raises(requests.HTTPError):
        asyncio.run(crawler.crawl_article(crawler.ARTICLE_URLS[0]))


def test_pdf_validator_rejects_an_html_download():
    with pytest.raises(ValueError, match="real PDF"):
        validate_pdf(b"<html>Access denied</html>" * 100)


def test_cached_crawl_is_offline_and_byte_stable(tmp_path, monkeypatch):
    article = example_article()
    path = tmp_path / f"{article['id']}.json"
    write_json(path, article)
    before = path.read_bytes()
    monkeypatch.setattr(crawler, "DATA_DIR", tmp_path)
    monkeypatch.setattr(crawler, "ARTICLE_URLS", [article["url"]])
    def forbidden_network(url):
        pytest.fail("Cached crawl must not contact the network")
    monkeypatch.setattr(crawler, "fetch", forbidden_network)
    asyncio.run(crawler.crawl_all())
    assert path.read_bytes() == before
    assert list(tmp_path.glob("*.json")) == [path]


def test_convert_news_is_traceable_repeatable_and_preserves_valid_output(tmp_path, monkeypatch):
    landing = tmp_path / "landing"
    output = tmp_path / "standardized"
    article = example_article()
    path = landing / "news" / "example.json"
    write_json(path, article)
    monkeypatch.setattr(converter, "LANDING_DIR", landing)
    monkeypatch.setattr(converter, "OUTPUT_DIR", output)
    converter.convert_news_articles()
    result = output / "news" / "example.md"
    before = result.read_bytes()
    text = before.decode()
    metadata = yaml.safe_load(text.split("---\n", 2)[1])
    assert metadata["url"] == article["url"]
    assert metadata["landing_file"] == "data/landing/news/example.json"
    assert metadata["landing_sha256"] == sha256(path.read_bytes())
    assert article["content_markdown"].strip() in text
    converter.convert_news_articles()
    assert result.read_bytes() == before
    article["content_markdown"] = "Truncated or corrupted body"
    write_json(path, article)
    with pytest.raises(ValueError):
        converter.convert_news_articles()
    assert result.read_bytes() == before


def test_all_corpus_documents_have_verifiable_provenance():
    manifest = read_json(ROOT / "data" / "corpus_manifest.json")
    documents = manifest["documents"]
    assert len([d for d in documents if d["doc_type"] == "legal"]) >= 3
    assert len([d for d in documents if d["doc_type"] == "news"]) >= 5
    actual_paths = {p.relative_to(ROOT).as_posix() for p in (ROOT / "data/standardized").glob("*/*.md")}
    assert actual_paths == {d["standardized_file"] for d in documents}
    assert len({d["id"] for d in documents}) == len(documents)
    for document in documents:
        landing = ROOT / document["landing_file"]
        standardized = ROOT / document["standardized_file"]
        assert sha256(landing.read_bytes()) == document["landing_sha256"]
        assert sha256(standardized.read_bytes()) == document["standardized_sha256"]
        metadata, body = standardized.read_text(encoding="utf-8").split("---\n", 2)[1:]
        assert yaml.safe_load(metadata)["url"] == document["url"]
        assert len(body.split("\n\n", 2)[-1].strip()) >= 200
        if document["doc_type"] == "news":
            validate_article(read_json(landing))
            assert "![" not in body
            assert "Shutterstock" not in body
        else:
            assert validate_pdf(landing.read_bytes()) == document["page_count"]
            for page in range(1, document["page_count"] + 1):
                assert f"## PDF page {page}\n" in body


def test_sampled_normative_content_and_table_columns_survive_conversion():
    directory = ROOT / "data/standardized/legal"
    overview = (directory / "nist_sp_800_63_4.md").read_text(encoding="utf-8")
    assert "| AAL | Control Objectives | User Profile |" in overview
    row = next(line for line in overview.splitlines() if line.startswith("| AAL2 | Require multifactor"))
    cells = row.split("|")
    assert len(cells) == 5
    assert "Individual personal information" in cells[3]
    passwords = (directory / "nist_sp_800_63b_4.md").read_text(encoding="utf-8")
    page = passwords.split("## PDF page 25\n", 1)[1].split("## PDF page 26\n", 1)[0]
    text = re.sub(r"\s+", " ", page)
    assert "minimum of 15 characters" in text
    assert "minimum of eight characters" in text
    assert "SHALL NOT require subscribers to change passwords periodically" in text
