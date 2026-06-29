"""Event stream for the live demo.

screen_events() runs the real pipeline (collect -> extract -> synthesize) and yields
demo events as each thing happens. The same event shape can be recorded to a JSONL
file and replayed with original timing — so a pod hiccup on stage can't kill the demo.

Event types: stage, fact, metric, cost, memo, done, error.
"""

import asyncio
import json
import time
from pathlib import Path

import httpx

from app.config import settings
from app.cost import compute_race
from app.pipeline.collect import collect
from app.pipeline.extractor import extract_facts
from app.pipeline.synthesizer import synthesize

# Recordings live here; replay only ever reads a basename from this dir (no traversal).
DEMO_DIR = Path(__file__).resolve().parents[2] / "demo"


async def _sample_gpu() -> tuple[float | None, float | None]:
    """Poll the pod's metrics endpoint if configured. Returns (gpu_util, tokens_per_sec)."""
    if not settings.amd_metrics_url:
        return None, settings.amd_assumed_tokens_per_sec
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            d = (await c.get(settings.amd_metrics_url)).json()
            return d.get("gpu_util"), d.get("tokens_per_sec", settings.amd_assumed_tokens_per_sec)
    except (httpx.HTTPError, ValueError):
        return None, settings.amd_assumed_tokens_per_sec


async def _run(url: str):
    yield {"type": "stage", "stage": "collect", "status": "start"}
    docs = await collect(url)
    yield {"type": "stage", "stage": "collect", "status": "done", "sources": len(docs)}

    yield {"type": "stage", "stage": "extract", "status": "start"}
    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(ev: dict) -> None:
        await queue.put(ev)

    task = asyncio.create_task(extract_facts(docs, on_event=on_event))
    cum_tokens = 0
    while not (task.done() and queue.empty()):
        try:
            ev = await asyncio.wait_for(queue.get(), timeout=0.15)
        except asyncio.TimeoutError:
            continue
        if ev["type"] == "page":
            cum_tokens += ev.get("tokens", 0)
            gpu_util, tps = await _sample_gpu()
            yield {"type": "metric", "cum_tokens": cum_tokens, "tokens_per_sec": tps,
                   "gpu_util": gpu_util}
            race = compute_race(cum_tokens, 0, settings.amd_pod_hourly_usd, tps or 1.0)
            yield {"type": "cost", "amd_usd": round(race.amd_usd, 4),
                   "frontier_usd": round(race.frontier_usd, 4),
                   "savings_x": round(race.savings_x, 1)}
        else:
            yield ev  # fact events

    extraction = task.result()
    yield {"type": "stage", "stage": "extract", "status": "done",
           "facts": len(extraction.facts), "tokens": extraction.total_tokens}

    yield {"type": "stage", "stage": "synthesize", "status": "start"}
    synth = await synthesize(url, extraction.facts)
    m = synth.memo
    _, tps = await _sample_gpu()
    race = compute_race(extraction.total_tokens, synth.total_tokens,
                        settings.amd_pod_hourly_usd, tps or settings.amd_assumed_tokens_per_sec)
    yield {"type": "cost", "final": True, "amd_usd": round(race.amd_usd, 4),
           "frontier_usd": round(race.frontier_usd, 4), "savings_x": round(race.savings_x, 1)}
    yield {"type": "stage", "stage": "synthesize", "status": "done"}
    yield {"type": "memo",
           "verdict": (vars(m.verdict) if m.verdict else None),
           "risk_matrix": [vars(r) for r in m.risk_matrix],
           "section_summaries": m.section_summaries,
           "confidence": m.confidence,
           "sources_collected": len(docs),
           "facts_extracted": len(m.facts)}
    yield {"type": "done"}


async def screen_events(url: str, record: bool = False):
    """Run the pipeline live. If record=True, also append each event (with a relative
    timestamp) to demo/events-<host>.jsonl for later replay."""
    writer = None
    if record:
        DEMO_DIR.mkdir(exist_ok=True)
        host = url.split("//")[-1].split("/")[0].replace(":", "_") or "run"
        writer = (DEMO_DIR / f"events-{host}.jsonl").open("w")
    t0 = time.monotonic()
    try:
        async for ev in _run(url):
            if writer:
                writer.write(json.dumps({**ev, "_t": round(time.monotonic() - t0, 3)}) + "\n")
                writer.flush()
            yield ev
    finally:
        if writer:
            writer.close()


async def replay_events(name: str):
    """Replay a recorded run with its original timing. `name` is a basename only."""
    path = DEMO_DIR / Path(name).name
    if not path.exists():
        yield {"type": "error", "message": f"recording not found: {path.name}"}
        return
    last_t = None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        t = rec.pop("_t", None)
        if last_t is not None and t is not None:
            await asyncio.sleep(min(max(t - last_t, 0.0), 2.0))
        last_t = t
        yield rec
