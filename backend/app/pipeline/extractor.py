"""Stage 1: turn raw SourceDocuments into atomic, traceable Facts.

Runs on the AMD-hosted model (the cost engine). For each page we ask the model
for a JSON array of {claim, category, confidence}; we attach the source URL
ourselves from the SourceDocument so a claim can never point at the wrong place.

Token usage is summed across every call so the cost-race (app/cost.py) is fed by
real numbers, not a slide.

Testable against Fireworks before the pod exists:
    python -m app.pipeline.extractor https://linear.app --fireworks
"""

import asyncio
from dataclasses import dataclass, field

import openai

from app.config import settings
from app.llm.client import LLMClient, extractor_client
from app.pipeline.jsonparse import extract_json_object
from app.pipeline.models import CATEGORIES, Fact, SourceDocument

# Same armor as the synthesis stage: one polite pause before retrying a page
# that got a 429 — the retry happens while holding the concurrency semaphore,
# which also naturally slows the whole stage down when the provider is throttling.
_RATE_LIMIT_RETRY_DELAY_S = 5.0

_SYSTEM = (
    "You extract atomic, verifiable facts from a single web page for a startup deal "
    'screen. Return ONLY a JSON object: {"facts": [ {"claim": str, "category": one of '
    f"{list(CATEGORIES)}, "
    '"confidence": number 0-1} ]}. '
    "Rules: one fact per element; only claims directly supported by the page text; "
    "no speculation; prefer specific numbers, names, prices, role titles. "
    'If the page has no useful facts, return {"facts": []}.'
)


@dataclass
class ExtractionResult:
    facts: list[Fact] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _build_user(doc: SourceDocument, max_chars: int) -> str:
    body = doc.text[:max_chars]
    return f"PAGE TITLE: {doc.title}\nPAGE URL: {doc.url}\n\nPAGE TEXT:\n{body}"


def _coerce_facts(raw_text: str, source_url: str) -> list[Fact]:
    """Pull facts out of the model's {"facts": [...]} reply, tolerant of wrap."""
    obj = extract_json_object(raw_text)
    arr = obj.get("facts") if isinstance(obj, dict) else None
    if not isinstance(arr, list):
        return []
    facts: list[Fact] = []
    for item in arr:
        if not isinstance(item, dict) or "claim" not in item:
            continue
        category = str(item.get("category", "")).lower().strip()
        if category not in CATEGORIES:
            category = "overview"
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        claim = str(item["claim"]).strip()
        if claim:
            facts.append(Fact(claim=claim, category=category,
                              source_url=source_url, confidence=confidence))
    return facts


async def extract_facts(
    docs: list[SourceDocument],
    client: LLMClient | None = None,
    on_event=None,
) -> ExtractionResult:
    """Extract facts from every doc. If on_event is given (async callable), emit a
    'fact' event per fact and a 'page' event per page as they complete — that's what
    drives the live demo stream."""
    client = client or extractor_client()
    sem = asyncio.Semaphore(settings.extract_concurrency)

    async def _one(doc: SourceDocument):
        async with sem:
            for attempt in (1, 2):
                try:
                    completion = await client.complete(
                        system=_SYSTEM,
                        user=_build_user(doc, settings.extract_max_chars),
                        temperature=0.1,
                        max_tokens=2500,
                        json_mode=True,
                        # Keep gpt-oss in low-reasoning mode: fast, cheap, and it stops
                        # leaking chain-of-thought so the JSON lands cleanly on the
                        # high-volume stage.
                        reasoning_effort="low",
                    )
                    break
                except openai.RateLimitError:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(_RATE_LIMIT_RETRY_DELAY_S)
        facts = _coerce_facts(completion.text, doc.url)
        if on_event:
            for f in facts:
                await on_event({"type": "fact", "category": f.category, "claim": f.claim,
                                "source_url": f.source_url, "confidence": f.confidence})
            await on_event({"type": "page", "url": doc.url, "facts": len(facts),
                            "tokens_in": completion.prompt_tokens,
                            "tokens_out": completion.completion_tokens})
        return facts, completion

    result = ExtractionResult()
    failures = 0
    last_exc: Exception | None = None
    for outcome in await asyncio.gather(*(_one(d) for d in docs), return_exceptions=True):
        if isinstance(outcome, Exception):
            print(f"[extractor] page failed: {type(outcome).__name__}: {outcome}")
            failures += 1
            last_exc = outcome
            continue
        facts, completion = outcome
        result.facts.extend(facts)
        result.prompt_tokens += completion.prompt_tokens
        result.completion_tokens += completion.completion_tokens
    if docs and failures == len(docs) and last_exc is not None:
        # Every single page failed for the same class of reason (throttled key,
        # dead provider). Surfacing the real error beats returning 0 facts and
        # letting the screen degrade into a misleading "Pass — 0/100".
        raise last_exc
    return result


if __name__ == "__main__":
    import sys

    from app.llm.client import synthesis_client
    from app.pipeline.collect import collect

    async def _demo() -> None:
        target = next((a for a in sys.argv[1:] if not a.startswith("-")), "https://linear.app")
        # --fireworks lets you test extraction before the AMD pod exists.
        client = synthesis_client() if "--fireworks" in sys.argv else None
        docs = await collect(target)
        print(f"Collected {len(docs)} pages. Extracting facts...")
        res = await extract_facts(docs, client=client)
        print(f"\n{len(res.facts)} facts ({res.total_tokens} tokens):\n")
        for f in res.facts:
            print(f"  [{f.category:11} {f.confidence:.2f}] {f.claim}\n      ↳ {f.source_url}")

    asyncio.run(_demo())
