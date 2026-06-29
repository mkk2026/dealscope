"""DealScope API — entry point.

For now: a health check and a /screen stub that returns the memo shape we'll
fill in stage by stage. Run from backend/:

    uvicorn app.main:app --reload
"""

import json
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

from app.pipeline.collect import collect
from app.pipeline.extractor import extract_facts
from app.pipeline.models import CATEGORIES
from app.pipeline.stream import replay_events, screen_events
from app.pipeline.synthesizer import synthesize

app = FastAPI(title="DealScope", version="0.1.0")

_STATIC = Path(__file__).resolve().parent / "static"
_STATIC.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


class ScreenRequest(BaseModel):
    url: HttpUrl


class FactOut(BaseModel):
    claim: str
    source_url: str
    confidence: float


class RiskOut(BaseModel):
    category: str
    score: int
    reason: str


class VerdictOut(BaseModel):
    recommendation: str
    score: int
    bull: str
    bear: str


class CostSummary(BaseModel):
    amd_tokens: int = 0          # Stage 1 extraction (the AMD pod)
    fireworks_tokens: int = 0    # Stage 2 synthesis (Fireworks)


class ScreenResponse(BaseModel):
    url: str
    status: str
    sources_collected: int
    facts_extracted: int
    section_summaries: dict[str, str]
    sections: dict[str, list[FactOut]]   # traceable facts, grouped by category
    risk_matrix: list[RiskOut]
    verdict: VerdictOut | None
    confidence: int
    cost: CostSummary


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/screen/stream")
async def screen_stream(url: str = "", replay: str = "", record: bool = False):
    """Server-Sent Events for the live instrument-panel demo. Pass ?url=... for a live
    run (optionally &record=true), or ?replay=events-host.jsonl to replay a capture."""
    async def gen():
        try:
            source = replay_events(replay) if replay else screen_events(url, record=record)
            async for ev in source:
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as exc:  # surface failures to the UI instead of a dead stream
            yield f"data: {json.dumps({'type': 'error', 'message': f'{type(exc).__name__}: {exc}'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/screen", response_model=ScreenResponse)
async def screen(req: ScreenRequest) -> ScreenResponse:
    url = str(req.url)
    # Stage 0: gather traceable sources → Stage 1: extract facts (AMD) → Stage 2: synthesize (Fireworks).
    docs = await collect(url)
    extraction = await extract_facts(docs)
    synthesis = await synthesize(url, extraction.facts)
    memo = synthesis.memo

    sections: dict[str, list[FactOut]] = {c: [] for c in CATEGORIES}
    grouped: dict[str, list] = defaultdict(list)
    for f in memo.facts:
        grouped[f.category].append(FactOut(claim=f.claim, source_url=f.source_url,
                                           confidence=f.confidence))
    sections.update(grouped)

    return ScreenResponse(
        url=url,
        status="screened",
        sources_collected=len(docs),
        facts_extracted=len(memo.facts),
        section_summaries=memo.section_summaries,
        sections=sections,
        risk_matrix=[RiskOut(category=r.category, score=r.score, reason=r.reason)
                     for r in memo.risk_matrix],
        verdict=(VerdictOut(**vars(memo.verdict)) if memo.verdict else None),
        confidence=memo.confidence,
        cost=CostSummary(amd_tokens=extraction.total_tokens,
                         fireworks_tokens=synthesis.total_tokens),
    )
