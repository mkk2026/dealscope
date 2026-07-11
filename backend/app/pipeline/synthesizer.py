"""Stage 2: turn sourced Facts into the deal screen.

Runs on Fireworks (AMD-hardware model). The model writes per-section summaries, a
risk matrix, and a verdict — all grounded in the facts we pass it. We do NOT let it
invent facts: the traceable Fact list is rendered as-is alongside its synthesis.
The 'market' summary is explicitly the model's opinion, not a sourced claim.

Testable against Fireworks once you have a key:
    python -m app.pipeline.synthesizer https://linear.app --fireworks
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass

import openai

from app.config import settings
from app.llm.client import Completion, LLMClient, extractor_client, synthesis_client
from app.pipeline.jsonparse import extract_json_object
from app.pipeline.models import CATEGORIES, SCORECARD_SIGNALS, Fact, Memo, Risk, Signal, Verdict

# One polite pause before retrying the premium model on a 429; if it is still
# throttled after that, the cheap extraction model finishes the screen instead
# of the whole run dying at the final stage.
_RATE_LIMIT_RETRY_DELAY_S = 5.0

# Evidence per signal is capped so the scorecard can't blow up the JSON output
# (truncated JSON = unparseable memo, the worst failure mode on a live screen).
_MAX_EVIDENCE = 3

_SIGNAL_IDS = ", ".join(SCORECARD_SIGNALS)

# Field order in the shape is deliberate: verdict and confidence FIRST, scorecard
# LAST. extract_json_object cannot repair truncated JSON, and a long reply that gets
# cut off should lose scorecard tail entries (which degrade to insufficient_data),
# never the verdict or confidence.
_SYSTEM = (
    "You are a startup deal-screen analyst. You are given atomic, sourced facts about "
    "a company, grouped by category; each fact ends with its [source: URL]. "
    "Produce a concise pre-meeting screen. Keep the whole reply under 2500 tokens. "
    "Return ONLY a JSON object with this shape, fields in this exact order: "
    '{"verdict": {"recommendation": "Worth a call"|"Borderline"|"Pass", '
    '"score": int 0-100, "bull": str, "bear": str}, '
    '"confidence": int 0-100 (REQUIRED — calibrate to fact coverage), '
    '"section_summaries": {<category>: one-sentence summary}, '
    '"risk_matrix": [{"category": str, "score": int 1-10, "reason": str}], '
    '"scorecard": [{"id": str, "score": int 0-10, "rationale": short phrase (max 12 words), '
    '"evidence": [up to 3 source URLs copied from the facts you used], '
    '"status": "scored"|"insufficient_data"}]}. '
    f"The scorecard is how an investor screens; produce one entry per id from: {_SIGNAL_IDS}. "
    "Score each signal 0-10 strictly from the provided facts and cite the exact source "
    "URLs of the facts you used in evidence. If the facts do not support a signal, use "
    'status "insufficient_data" with score 0 — never guess. For red_flags, higher score '
    "= more red flags found. "
    "Ground every statement in the provided facts. Do NOT invent facts. "
    "The 'market' summary is your opinion — hedge it. Higher risk score = riskier. "
    "If facts are thin, say so and lower confidence."
)


@dataclass
class SynthesisResult:
    memo: Memo
    prompt_tokens: int = 0
    completion_tokens: int = 0
    fallback_model: str | None = None   # set when the premium model was rate-limited

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _facts_payload(facts: list[Fact]) -> str:
    grouped: dict[str, list[Fact]] = defaultdict(list)
    for f in facts:
        grouped[f.category].append(f)
    lines = []
    for cat in CATEGORIES:
        if grouped[cat]:
            lines.append(f"## {cat}")
            # The [source: URL] suffix is what lets the model cite real evidence in the
            # scorecard — evidence URLs are validated against these exact strings.
            lines.extend(f"- ({f.confidence:.2f}) {f.claim} [source: {f.source_url}]"
                         for f in grouped[cat])
    return "\n".join(lines) if lines else "(no facts extracted)"


def _build_scorecard(obj: dict, valid_urls: set[str]) -> list[Signal]:
    """Validate the model's scorecard. Unknown ids are dropped, scores clamped, and
    evidence is checked against the source URLs of collected facts — a signal whose
    evidence doesn't trace back to a collected source is downgraded to
    insufficient_data, so hallucinated evidence is structurally impossible.
    A missing/malformed scorecard returns [] (the UI simply omits the section —
    this is also what keeps pre-scorecard replay recordings rendering cleanly)."""
    raw = obj.get("scorecard")
    if not isinstance(raw, list) or not raw:
        return []

    by_id: dict[str, Signal] = {}
    for s in raw:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id", "")).lower().strip()
        if sid not in SCORECARD_SIGNALS:
            continue
        evidence = [u for u in (s.get("evidence") or [])
                    if isinstance(u, str) and u in valid_urls][:_MAX_EVIDENCE]
        scored = bool(evidence) and s.get("status") != "insufficient_data"
        by_id[sid] = Signal(
            id=sid,
            name=SCORECARD_SIGNALS[sid],
            score=_clamp_int(s.get("score"), 0, 10, 0) if scored else 0,
            rationale=str(s.get("rationale", "")),
            evidence=evidence,
            status="scored" if scored else "insufficient_data",
        )

    # Every rubric signal appears exactly once, in rubric order; the ones the model
    # skipped are honest gaps, not silent omissions.
    return [by_id.get(sid) or Signal(id=sid, name=name, score=0, rationale="",
                                     status="insufficient_data")
            for sid, name in SCORECARD_SIGNALS.items()]


def _build_memo(url: str, facts: list[Fact], obj: dict | None) -> Memo:
    if obj is None:
        return Memo(url=url, facts=facts,
                    section_summaries={"overview": "Synthesis unavailable (model returned no parseable output)."},
                    confidence=0)

    summaries = {
        str(k).lower(): str(v)
        for k, v in (obj.get("section_summaries") or {}).items()
        if str(k).lower() in CATEGORIES
    }

    risks = []
    for r in obj.get("risk_matrix") or []:
        if isinstance(r, dict) and r.get("category"):
            risks.append(Risk(
                category=str(r["category"]),
                score=_clamp_int(r.get("score"), 1, 10, 5),
                reason=str(r.get("reason", "")),
            ))

    v = obj.get("verdict") or {}
    verdict = Verdict(
        recommendation=str(v.get("recommendation", "Borderline")),
        score=_clamp_int(v.get("score"), 0, 100, 50),
        bull=str(v.get("bull", "")),
        bear=str(v.get("bear", "")),
    )
    return Memo(
        url=url,
        section_summaries=summaries,
        facts=facts,
        risk_matrix=risks,
        verdict=verdict,
        confidence=_clamp_int(obj.get("confidence"), 0, 100, 0),
        scorecard=_build_scorecard(obj, {f.source_url for f in facts}),
    )


def _clamp_int(value, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


async def _complete_synthesis(client: LLMClient, user: str) -> Completion:
    # 6000, not 3000: the scorecard grew the JSON output and extract_json_object
    # cannot repair truncation — a cut-off reply degrades the whole memo to the
    # "synthesis unavailable" path. Headroom is cheap; a dead memo is not.
    return await client.complete(system=_SYSTEM, user=user, temperature=0.3,
                                 max_tokens=6000, json_mode=True)


async def _complete_with_fallback(client: LLMClient, user: str) -> tuple[Completion, str | None]:
    """Premium model first; on a 429, wait once and retry. If it is still throttled,
    finish the screen on the cheap extraction model — a verdict from the cheap model
    beats a dead run. If the fallback is throttled too, let the error propagate."""
    for attempt in (1, 2):
        try:
            return await _complete_synthesis(client, user), None
        except openai.RateLimitError:
            if attempt == 1:
                await asyncio.sleep(_RATE_LIMIT_RETRY_DELAY_S)
    fallback = extractor_client()
    return await _complete_synthesis(fallback, user), fallback.model


async def synthesize(url: str, facts: list[Fact], client: LLMClient | None = None) -> SynthesisResult:
    if not facts:
        # Nothing to synthesize — be honest rather than hallucinate a verdict.
        memo = Memo(url=url, facts=[],
                    section_summaries={"overview": "No public facts found — cannot screen."},
                    verdict=Verdict("Pass", 0, "", "No signal available from public sources."),
                    confidence=0)
        return SynthesisResult(memo=memo)

    client = client or synthesis_client()
    # Cap facts sent to the prompt (highest-confidence first) so a fact-rich company
    # can't overflow the model into an empty verdict. ALL facts still go into the memo.
    top_facts = sorted(facts, key=lambda f: f.confidence, reverse=True)[:settings.synth_max_facts]
    user = f"Company URL: {url}\n\nExtracted facts:\n{_facts_payload(top_facts)}"
    completion, fallback_model = await _complete_with_fallback(client, user)
    memo = _build_memo(url, facts, extract_json_object(completion.text))
    return SynthesisResult(memo=memo,
                           prompt_tokens=completion.prompt_tokens,
                           completion_tokens=completion.completion_tokens,
                           fallback_model=fallback_model)


if __name__ == "__main__":
    import sys

    from app.pipeline.collect import collect
    from app.pipeline.extractor import extract_facts

    async def _demo() -> None:
        target = next((a for a in sys.argv[1:] if not a.startswith("-")), "https://linear.app")
        client = synthesis_client() if "--fireworks" in sys.argv else None
        docs = await collect(target)
        facts = (await extract_facts(docs, client=client)).facts
        res = await synthesize(target, facts, client=client)
        m = res.memo
        print(f"\nVERDICT: {m.verdict.recommendation} ({m.verdict.score}/100), confidence {m.confidence}")
        print(f"  bull: {m.verdict.bull}\n  bear: {m.verdict.bear}")
        for cat, summ in m.section_summaries.items():
            print(f"  [{cat}] {summ}")
        for r in m.risk_matrix:
            print(f"  RISK {r.category}: {r.score}/10 — {r.reason}")

    asyncio.run(_demo())
