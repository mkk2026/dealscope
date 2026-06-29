"""Public job-board fetcher.

Hiring is a clean momentum signal and the big three ATS platforms (Greenhouse,
Lever, Ashby) all expose public JSON APIs — no scraping, no auth. We detect the
board token from links on the company's site, then pull open roles.
"""

import re

import httpx

from app.config import settings
from app.pipeline.models import SourceDocument, SourceKind

_PATTERNS = {
    "greenhouse": r"boards\.greenhouse\.io/([A-Za-z0-9_-]+)",
    "lever": r"jobs\.lever\.co/([A-Za-z0-9_-]+)",
    "ashby": r"jobs\.ashbyhq\.com/([A-Za-z0-9_-]+)",
}


def detect_boards(html: str) -> dict[str, str]:
    boards: dict[str, str] = {}
    for platform, pattern in _PATTERNS.items():
        m = re.search(pattern, html or "")
        if m:
            boards[platform] = m.group(1)
    return boards


_BOARD_URLS = {
    "greenhouse": "https://boards.greenhouse.io/{token}",
    "lever": "https://jobs.lever.co/{token}",
    "ashby": "https://jobs.ashbyhq.com/{token}",
}


async def fetch_jobs(boards: dict[str, str]) -> list[SourceDocument]:
    docs: list[SourceDocument] = []
    async with httpx.AsyncClient(timeout=settings.http_timeout,
                                 headers={"User-Agent": "DealScope/0.1"}) as client:
        for platform, token in boards.items():
            roles, ok = await _fetch_platform(client, platform, token)
            docs.append(_to_doc(platform, token, roles, ok))
    return docs


async def _fetch_platform(client, platform, token) -> tuple[list[str], bool]:
    """Returns (roles, ok). ok=False means the fetch failed — caller must NOT
    report that as 'zero open roles', which would be a false negative signal."""
    try:
        if platform == "greenhouse":
            r = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
            if r.status_code != 200:
                return [], False
            jobs = r.json().get("jobs", [])
            return [f"{j.get('title')} — {j.get('location', {}).get('name', '')}" for j in jobs], True
        if platform == "lever":
            r = await client.get(f"https://api.lever.co/v0/postings/{token}?mode=json")
            if r.status_code != 200:
                return [], False
            jobs = r.json()
            return [f"{j.get('text')} — {j.get('categories', {}).get('location', '')}" for j in jobs], True
        if platform == "ashby":
            r = await client.get(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
            if r.status_code != 200:
                return [], False
            jobs = r.json().get("jobs", [])
            return [f"{j.get('title')} — {j.get('location', '')}" for j in jobs], True
    except (httpx.HTTPError, ValueError):
        return [], False
    return [], False


def _to_doc(platform: str, token: str, roles: list[str], ok: bool) -> SourceDocument:
    url = _BOARD_URLS.get(platform, "").format(token=token)
    if not ok:
        # Fetch failed — say so. Never let it masquerade as a hiring-momentum signal.
        return SourceDocument(
            url=url, kind=SourceKind.JOBS,
            title=f"Open roles ({platform}): unavailable",
            text=f"Could not fetch {platform} board '{token}' — roles unavailable, not zero.",
            meta={"platform": platform, "token": token, "open_roles": None, "fetch_ok": False},
        )
    body = "\n".join(f"- {r}" for r in roles)
    return SourceDocument(
        url=url, kind=SourceKind.JOBS,
        title=f"Open roles ({platform}): {len(roles)}",
        text=f"{len(roles)} open roles via {platform}:\n{body}",
        meta={"platform": platform, "token": token, "open_roles": len(roles), "fetch_ok": True},
    )
