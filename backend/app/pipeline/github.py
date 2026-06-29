"""GitHub public-API fetcher.

The strongest, most reliable signal we have: it's free, public, and real.
Discovers the org from links on the company's site, then pulls top repos and
engineering-health stats. Optional GITHUB_TOKEN raises the rate limit.
"""

import re

import httpx

from app.config import settings
from app.pipeline.models import SourceDocument, SourceKind

_API = "https://api.github.com"
# github.com/<x> paths that are never an org/user we care about.
_NON_ORG = {
    "sponsors", "features", "about", "pricing", "enterprise", "login", "join",
    "topics", "collections", "marketplace", "apps", "explore", "settings",
    "notifications", "new", "orgs", "search",
}


def extract_github_org(html: str, domain_hint: str | None = None) -> str | None:
    """Pull the most plausible org/user handle from github.com links on a page.

    Prefers a handle that matches the company's domain (e.g. linear.app -> 'linear')
    so a stray link to a dependency's repo or a founder's personal account doesn't
    make us silently screen the wrong entity. Falls back to the first non-skip handle.
    """
    candidates = [
        h for h in re.findall(r"github\.com/([A-Za-z0-9][A-Za-z0-9-]*)", html or "")
        if h.lower() not in _NON_ORG
    ]
    if not candidates:
        return None
    if domain_hint:
        stem = domain_hint.split(".")[0].lower()
        for h in candidates:
            if h.lower() == stem or stem in h.lower() or h.lower() in stem:
                return h
    return candidates[0]


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "DealScope/0.1"}
    if settings.github_token:
        h["Authorization"] = f"Bearer {settings.github_token}"
    return h


async def fetch_github(org: str, max_repos: int = 6) -> list[SourceDocument]:
    async with httpx.AsyncClient(headers=_headers(), timeout=settings.http_timeout) as client:
        repos = await _list_repos(client, org)
        if not repos:
            return []
        repos = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:max_repos]
        total_stars = sum(r.get("stargazers_count", 0) for r in repos)
        langs = sorted({r.get("language") for r in repos if r.get("language")})

        lines = [f"GitHub org/user: {org}", f"Top repos by stars (total shown: {total_stars}):"]
        for r in repos:
            lines.append(
                f"- {r['full_name']}: {r.get('stargazers_count', 0)} stars, "
                f"{r.get('forks_count', 0)} forks, lang={r.get('language')}, "
                f"open_issues={r.get('open_issues_count', 0)}, last_push={r.get('pushed_at')}"
                + (f" — {r['description']}" if r.get("description") else "")
            )
        if langs:
            lines.append(f"Primary languages: {', '.join(langs)}")

        return [SourceDocument(
            url=f"https://github.com/{org}",
            kind=SourceKind.GITHUB,
            title=f"GitHub: {org}",
            text="\n".join(lines),
            meta={"org": org, "repos_shown": len(repos), "total_stars": total_stars},
        )]


async def _list_repos(client: httpx.AsyncClient, org: str) -> list[dict]:
    # Try org endpoint first, fall back to user endpoint. A 403 means rate-limited
    # (surface it — do NOT mistake it for "no repos"); 404 means not that kind, fall through.
    for kind in ("orgs", "users"):
        r = await client.get(f"{_API}/{kind}/{org}/repos",
                             params={"per_page": 100, "type": "public", "sort": "updated"})
        if r.status_code == 200:
            return r.json()
        if r.status_code == 403:
            raise RuntimeError(
                "GitHub API rate-limited (403). Set GITHUB_TOKEN to raise the limit to 5000/hr."
            )
    return []


if __name__ == "__main__":
    import asyncio
    import sys

    async def _demo() -> None:
        org = sys.argv[1] if len(sys.argv) > 1 else "linear"
        docs = await fetch_github(org)
        for d in docs:
            print(d.text)

    asyncio.run(_demo())
