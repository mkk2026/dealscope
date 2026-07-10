"""Event stream for the live demo.

screen_events() runs the real pipeline (collect -> extract -> synthesize) and yields
demo events as each thing happens. The same event shape can be recorded to a JSONL
file and replayed with original timing — so a pod hiccup on stage can't kill the demo.

Event types: stage, fact, cost, memo, done, error.
"""

import asyncio
import json
import time
from pathlib import Path

from app.cost import compute_race
from app.pipeline.collect import collect
from app.pipeline.extractor import extract_facts
from app.pipeline.synthesizer import synthesize

# Recordings live here; replay only ever reads a basename from this dir (no traversal).
DEMO_DIR = Path(__file__).resolve().parents[2] / "demo"


def _cost_event(ein: int, eout: int, sin: int = 0, sout: int = 0, final: bool = False) -> dict:
    race = compute_race(ein, eout, sin, sout)
    ev = {"type": "cost", "naive_usd": round(race.naive_usd, 4),
          "routed_usd": round(race.routed_usd, 4), "savings_x": round(race.savings_x, 1),
          "tokens": race.total_tokens}
    if final:
        ev["final"] = True
    return ev


async def _run(url: str):
    yield {"type": "stage", "stage": "collect", "status": "start"}
    docs = await collect(url)
    yield {"type": "stage", "stage": "collect", "status": "done", "sources": len(docs)}

    yield {"type": "stage", "stage": "extract", "status": "start"}
    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(ev: dict) -> None:
        await queue.put(ev)

    task = asyncio.create_task(extract_facts(docs, on_event=on_event))
    ein = eout = 0  # cumulative extraction input/output tokens
    while not (task.done() and queue.empty()):
        try:
            ev = await asyncio.wait_for(queue.get(), timeout=0.15)
        except asyncio.TimeoutError:
            continue
        if ev["type"] == "page":
            ein += ev.get("tokens_in", 0)
            eout += ev.get("tokens_out", 0)
            yield _cost_event(ein, eout)  # cost climbs live as extraction runs
        else:
            yield ev  # fact events

    extraction = task.result()
    yield {"type": "stage", "stage": "extract", "status": "done",
           "facts": len(extraction.facts), "tokens": extraction.total_tokens}

    yield {"type": "stage", "stage": "synthesize", "status": "start"}
    synth = await synthesize(url, extraction.facts)
    m = synth.memo
    yield _cost_event(extraction.prompt_tokens, extraction.completion_tokens,
                      synth.prompt_tokens, synth.completion_tokens, final=True)
    yield {"type": "stage", "stage": "synthesize", "status": "done"}
    yield {"type": "memo",
           "verdict": (vars(m.verdict) if m.verdict else None),
           "risk_matrix": [vars(r) for r in m.risk_matrix],
           "section_summaries": m.section_summaries,
           "confidence": m.confidence,
           "sources_collected": len(docs),
           "facts_extracted": len(m.facts),
           "synth_fallback_model": synth.fallback_model}
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
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # tolerate a truncated final line from an interrupted capture
        t = rec.pop("_t", None)
        if last_t is not None and t is not None:
            await asyncio.sleep(min(max(t - last_t, 0.0), 2.0))
        last_t = t
        yield rec
