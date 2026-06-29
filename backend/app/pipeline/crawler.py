"""Polite same-domain crawler.

Fetches the homepage, ranks internal links by how likely they are to carry
screening signal (pricing, about, team, careers, product...), and pulls the top
few. Returns clean text per page as SourceDocuments. No JS rendering — fast and
good enough for the marketing/content pages we care about.
"""

import asyncio
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.pipeline.models import SourceDocument, SourceKind

_SIGNAL_WORDS = (
    "pricing", "price", "plans", "about", "team", "company", "career",
    "jobs", "product", "features", "customers", "solutions", "docs",
)
_HEADERS = {"User-Agent": "DealScope/0.1 (+hackathon deal screener)"}


async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url, headers=_HEADERS, follow_redirects=True, timeout=settings.http_timeout)
    except httpx.HTTPError:
        return None
    if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
        return r.text
    return None


def _clean(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title else ""
    text = " ".join(soup.get_text(separator=" ").split())
    return title, text


def _rank_internal_links(base_url: str, html: str, limit: int) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc
    scored: dict[str, int] = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#")[0].rstrip("/")
        p = urlparse(href)
        if p.scheme not in ("http", "https") or p.netloc != host or href == base_url.rstrip("/"):
            continue
        score = sum(w in href.lower() for w in _SIGNAL_WORDS)
        if score:
            scored[href] = max(scored.get(href, 0), score)
    return sorted(scored, key=lambda u: scored[u], reverse=True)[:limit]


async def crawl_site(url: str, max_pages: int | None = None) -> tuple[list[SourceDocument], str]:
    """Returns (documents, combined_html) — the raw HTML of every fetched page,
    so the orchestrator can discover GitHub/job-board links from hrefs on any page."""
    max_pages = max_pages or settings.crawl_max_pages
    docs: list[SourceDocument] = []
    async with httpx.AsyncClient() as client:
        sem = asyncio.Semaphore(settings.crawl_concurrency)

        async def bounded_fetch(link: str) -> str | None:
            async with sem:
                return await _fetch(client, link)

        home = await _fetch(client, url)
        if home is None:
            return docs, ""
        title, text = _clean(home)
        docs.append(SourceDocument(url=url, kind=SourceKind.WEBPAGE, title=title, text=text,
                                   meta={"page": "home"}))
        links = _rank_internal_links(url, home, max_pages - 1)
        pages = await asyncio.gather(*(bounded_fetch(link) for link in links))
        html_blobs = [home]
        for link, html in zip(links, pages):
            if html:
                t, tx = _clean(html)
                docs.append(SourceDocument(url=link, kind=SourceKind.WEBPAGE, title=t, text=tx))
                html_blobs.append(html)
    # Combined raw HTML of every fetched page — discovery scans hrefs across all of it.
    return docs, "\n".join(html_blobs)


if __name__ == "__main__":
    import sys

    async def _demo() -> None:
        target = sys.argv[1] if len(sys.argv) > 1 else "https://linear.app"
        docs, _ = await crawl_site(target)
        print(f"Crawled {len(docs)} pages from {target}:")
        for d in docs:
            print(f"  [{d.title[:50]!r}] {d.url}\n      {d.preview()}")

    asyncio.run(_demo())
