"""Capture real recorded screens for the gallery / demo reel.

Runs DealScope on a list of recognizable startups and records each to
demo/events-<host>.jsonl, which the gallery (/gallery) and replay (?replay=)
serve. Until the AMD pod is up, extraction runs on Fireworks too.

    CRAWL_MAX_PAGES=6 python capture_gallery.py
"""

import asyncio

from app.pipeline import stream

# Both stages run on AMD-hosted Fireworks models — no override needed.

COMPANIES = [
    "https://linear.app",
    "https://posthog.com",
    "https://www.cal.com",
    "https://supabase.com",
    "https://sentry.io",
    "https://n8n.io",
    "https://huggingface.co",
    "https://gitlab.com",
    "https://grafana.com",
    "https://railway.com",
]


PER_COMPANY_TIMEOUT = 200  # seconds — one slow site/LLM call can't stall the batch


def _rec_path(url: str):
    host = url.split("//")[-1].split("/")[0].replace(":", "_") or "run"
    return stream.DEMO_DIR / f"events-{host}.jsonl"


async def _capture_one(url: str):
    verdict, facts = None, 0
    async for ev in stream.screen_events(url, record=True):
        if ev["type"] == "memo":
            verdict, facts = ev.get("verdict"), ev.get("facts_extracted")
    return verdict, facts


async def main() -> None:
    for url in COMPANIES:
        path = _rec_path(url)
        if path.exists():
            print(f"SKIP {url:30}  (already recorded)", flush=True)
            continue
        try:
            verdict, facts = await asyncio.wait_for(_capture_one(url), timeout=PER_COMPANY_TIMEOUT)
            rec = verdict["recommendation"] if verdict else "—"
            score = verdict["score"] if verdict else "—"
            print(f"OK   {url:30}  {rec} {score}  | {facts} facts", flush=True)
        except Exception as exc:  # noqa: BLE001 — timeout or any failure: drop the partial file
            print(f"FAIL {url:30}  {type(exc).__name__}: {exc}", flush=True)
            if path.exists():
                path.unlink()
    print("done", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
