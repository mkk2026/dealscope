"""Stage 0: gather every public signal for a company into SourceDocuments.

Crawl the site once, then reuse the homepage HTML to discover GitHub and
job-board links and fetch those in parallel. The output is the raw, traceable
material the AMD-hosted extractor turns into structured facts.

Runnable on its own — no LLM, no keys required:

    python -m app.pipeline.collect https://linear.app
"""

import asyncio
from urllib.parse import urlparse

from app.pipeline.crawler import crawl_site
from app.pipeline.github import extract_github_org, fetch_github
from app.pipeline.jobs import detect_boards, fetch_jobs
from app.pipeline.models import SourceDocument


def normalize_url(url: str) -> str:
    """People paste bare domains ('stripe.com'); without a scheme the crawler
    collects nothing and the screen degrades to a bogus 'Pass — 0/100'."""
    url = url.strip()
    if url and not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


async def collect(url: str) -> list[SourceDocument]:
    url = normalize_url(url)
    pages, page_html = await crawl_site(url)
    # Discover from the combined raw HTML of every page (github/careers links live
    # in hrefs and often only on subpages, not the homepage).
    domain = urlparse(url).netloc.removeprefix("www.")

    tasks = []
    org = extract_github_org(page_html, domain_hint=domain)
    if org:
        tasks.append(fetch_github(org))

    boards = detect_boards(page_html)
    if boards:
        tasks.append(fetch_jobs(boards))

    extra: list[SourceDocument] = []
    for result in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(result, Exception):
            # Don't let a single source failure vanish — it makes "empty memo" undebuggable.
            print(f"[collect] source fetch failed: {type(result).__name__}: {result}")
        elif isinstance(result, list):
            extra.extend(result)

    return pages + extra


if __name__ == "__main__":
    import sys

    async def _demo() -> None:
        target = sys.argv[1] if len(sys.argv) > 1 else "https://linear.app"
        docs = await collect(target)
        print(f"\nCollected {len(docs)} source documents for {target}:\n")
        for d in docs:
            print(f"  [{d.kind.value:8}] {d.url}")
            print(f"             {d.title[:60]}")
            print(f"             {d.preview()}\n")

    asyncio.run(_demo())
