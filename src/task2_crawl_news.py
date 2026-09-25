"""Collect the main text of five public NIST articles without an API key.

Requests + BeautifulSoup + Markdownify are sufficient for these static pages.
Do not bypass blocked sites. Existing snapshots are reused unless --refresh.
"""

import argparse
import asyncio
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from markdownify import markdownify

from .corpus_io import fetch, read_json, sha256, utc_now, validate_article, write_json
from .corpus_sources import ARTICLE_SOURCES, RIGHTS, RIGHTS_URL

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "landing" / "news"
ARTICLE_URLS = [url for _, url in ARTICLE_SOURCES]
ARTICLE_IDS = {url: identifier for identifier, url in ARTICLE_SOURCES}


def extract_article(html: bytes, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("h1")
    # The FIRST text-with-summary block is the article. Later ones are bios
    # and related posts, which must not leak into the retrieval corpus.
    body = soup.select_one(".text-with-summary")
    if title is None or body is None:
        raise ValueError(f"Expected NIST article structure is missing: {url}")
    body = BeautifulSoup(str(body), "html.parser")
    for element in body.select(
        "script, style, nav, footer, form, figure, .nist-image, .nist-video, "
        ".video-embed-field, img, picture, video, audio, iframe"
    ):
        element.decompose()
    for link in body.find_all("a", href=True):
        target = urljoin(url, link["href"])
        if urlsplit(target).scheme in {"https", "http"}:
            link["href"] = target
        elif not link["href"].startswith("#"):
            link.unwrap()
    content = markdownify(str(body), heading_style="ATX", bullets="-", strip=["img"])
    content = re.sub(r"\n[ \t]+\n", "\n\n", content)
    content = re.sub(r"\n{3,}", "\n\n", content).strip() + "\n"

    def meta(name: str) -> str | None:
        element = soup.find("meta", attrs={"property": name})
        return element.get("content") if element else None

    article = {
        "id": ARTICLE_IDS[url],
        "url": url,
        "title": title.get_text(" ", strip=True),
        "date_crawled": utc_now(),
        "date_published": meta("article:published_time"),
        "date_modified": meta("article:modified_time"),
        "doc_type": "news",
        "publisher": "NIST",
        "language": "en",
        "content_markdown": content,
        "content_sha256": sha256(content.encode("utf-8")),
        "html_sha256": sha256(html),
        "license": RIGHTS,
        "license_url": RIGHTS_URL,
        "extraction": "First .text-with-summary; no navigation, bios, comments, images or embedded media",
    }
    validate_article(article)
    return article


async def crawl_article(url: str) -> dict:
    if url not in ARTICLE_IDS:
        raise ValueError("Add the source to ARTICLE_SOURCES before crawling it")
    response = await asyncio.to_thread(fetch, url)
    if "html" not in response.headers.get("Content-Type", "").lower():
        raise ValueError(f"Expected an HTML article: {url}")
    article = extract_article(response.content, url)
    article["resolved_url"] = response.url
    return article


async def crawl_all(*, refresh: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Serial requests: no need to put load on the publisher for five pages.
    for url in ARTICLE_URLS:
        output = DATA_DIR / f"{ARTICLE_IDS[url]}.json"
        if output.exists() and not refresh:
            cached = read_json(output)
            validate_article(cached)
            if cached["url"] != url:
                raise ValueError(f"Source mismatch in {output}")
            print(f"Reused: {output.name}", flush=True)
            continue
        article = await crawl_article(url)
        if output.exists():
            previous = read_json(output)
            if all(previous.get(key) == value for key, value in article.items() if key != "date_crawled"):
                article["date_crawled"] = previous["date_crawled"]
        write_json(output, article)
        print(f"Saved: {output.name} ({len(article['content_markdown']):,} characters)", flush=True)
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Explicitly update existing snapshots")
    asyncio.run(crawl_all(refresh=parser.parse_args().refresh))
