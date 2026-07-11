import httpx
import openai

from app.llm.client import Completion
from app.pipeline import synthesizer
from app.pipeline.models import SCORECARD_SIGNALS, Fact
from app.pipeline.synthesizer import _build_memo, _build_scorecard, _clamp_int, synthesize


def _facts():
    return [Fact("Free $0", "overview", "https://x/pricing", 0.9),
            Fact("892 repos", "engineering", "https://github.com/x", 0.8)]


def _rate_limit_error() -> openai.RateLimitError:
    req = httpx.Request("POST", "https://api.fireworks.ai/inference/v1/chat/completions")
    return openai.RateLimitError("rate limited", response=httpx.Response(429, request=req), body=None)


_GOOD_JSON = ('{"section_summaries": {"overview": "ok"}, "risk_matrix": [], '
              '"verdict": {"recommendation": "Borderline", "score": 50, "bull": "b", "bear": "r"}, '
              '"confidence": 42}')


class _FlakyClient:
    """Raises RateLimitError for the first `failures` calls, then succeeds."""

    def __init__(self, failures: int, model: str = "premium-model"):
        self.failures = failures
        self.model = model
        self.calls = 0

    async def complete(self, **kwargs) -> Completion:
        self.calls += 1
        if self.calls <= self.failures:
            raise _rate_limit_error()
        return Completion(text=_GOOD_JSON, prompt_tokens=10, completion_tokens=5)


def test_clamp_int():
    assert _clamp_int(99, 1, 10, 5) == 10
    assert _clamp_int("84", 0, 100, 50) == 84
    assert _clamp_int(None, 0, 100, 0) == 0
    assert _clamp_int("nope", 0, 100, 7) == 7


def test_build_memo_happy_path():
    obj = {
        "section_summaries": {"overview": "SaaS", "market": "crowded", "BOGUS": "drop"},
        "risk_matrix": [{"category": "market", "score": 99, "reason": "many"}, {"category": "team"}],
        "verdict": {"recommendation": "Worth a call", "score": "84", "bull": "b", "bear": "r"},
        "confidence": 77,
    }
    m = _build_memo("https://x", _facts(), obj)
    assert "BOGUS" not in m.section_summaries          # unknown category dropped
    assert m.section_summaries["market"] == "crowded"
    assert m.risk_matrix[0].score == 10               # 99 clamped
    assert m.risk_matrix[1].score == 5                # missing score defaulted
    assert m.verdict.score == 84                      # "84" coerced
    assert m.confidence == 77
    assert len(m.facts) == 2                           # sourced facts preserved


def test_build_memo_null_obj_is_graceful():
    m = _build_memo("https://x", _facts(), None)
    assert m.confidence == 0
    assert "unavailable" in m.section_summaries["overview"].lower()
    assert len(m.facts) == 2


# Investor Scorecard — validation is the trust boundary: the model proposes,
# _build_scorecard disposes. Evidence must trace to collected fact URLs.

_VALID_URLS = {"https://x/pricing", "https://github.com/x"}


def test_build_scorecard_validates_clamps_and_fills_all_signals():
    obj = {"scorecard": [
        {"id": "technical_team", "score": 99, "rationale": "strong",
         "evidence": ["https://github.com/x"]},                          # 99 → clamped 10
        {"id": "BOGUS_SIGNAL", "score": 5, "evidence": ["https://x/pricing"]},  # dropped
        {"id": "hiring_velocity", "score": 7, "rationale": "hiring",
         "evidence": ["https://fake.invented/url"]},                     # unverifiable → coerced
        {"id": "red_flags", "score": 3, "rationale": "stale blog",
         "evidence": ["https://x/pricing", "https://github.com/x",
                      "https://x/pricing", "https://github.com/x"]},     # capped at 3
        "not-a-dict",                                                    # tolerated
    ]}
    sc = _build_scorecard(obj, _VALID_URLS)
    assert [s.id for s in sc] == list(SCORECARD_SIGNALS)   # all 10, rubric order
    by = {s.id: s for s in sc}
    assert by["technical_team"].score == 10 and by["technical_team"].status == "scored"
    assert by["hiring_velocity"].status == "insufficient_data"   # fake evidence rejected
    assert by["hiring_velocity"].score == 0
    assert len(by["red_flags"].evidence) == 3
    assert by["market_timing"].status == "insufficient_data"     # model skipped it


def test_build_scorecard_absent_or_malformed_returns_empty():
    assert _build_scorecard({}, _VALID_URLS) == []
    assert _build_scorecard({"scorecard": {}}, _VALID_URLS) == []
    assert _build_scorecard({"scorecard": []}, _VALID_URLS) == []


def test_build_memo_wires_scorecard_with_fact_urls():
    obj = {"verdict": {"recommendation": "Borderline", "score": 50, "bull": "b", "bear": "r"},
           "confidence": 40,
           "scorecard": [{"id": "customer_evidence", "score": 6, "rationale": "logos",
                          "evidence": ["https://x/pricing"]}]}
    m = _build_memo("https://x", _facts(), obj)
    assert len(m.scorecard) == 10
    by = {s.id: s for s in m.scorecard}
    assert by["customer_evidence"].status == "scored"
    assert by["customer_evidence"].evidence == ["https://x/pricing"]


def test_build_memo_without_scorecard_key_keeps_memo_working():
    m = _build_memo("https://x", _facts(), {"verdict": {"score": 50}, "confidence": 10})
    assert m.scorecard == []          # old recordings / non-conforming models: section omitted
    assert m.verdict.score == 50


async def test_synthesize_no_facts_has_empty_scorecard():
    res = await synthesize("https://x", [])
    assert res.memo.scorecard == []


# Regression: ISSUE-003 — a Fireworks 429 on the premium model killed every live
# screen at the synthesize stage (the run died with a raw RateLimitError while
# recorded replays kept working, so the demo looked broken for any new URL).
# Found by /qa on 2026-07-10 against the deployed HF Space.
# Report: .gstack/qa-reports/qa-report-dealscope-2026-07-10.md

async def test_synthesize_retries_premium_on_rate_limit(monkeypatch):
    monkeypatch.setattr(synthesizer, "_RATE_LIMIT_RETRY_DELAY_S", 0)
    client = _FlakyClient(failures=1)
    res = await synthesize("https://x", _facts(), client=client)
    assert client.calls == 2                     # one 429, one successful retry
    assert res.fallback_model is None            # premium recovered — no fallback
    assert res.memo.confidence == 42


async def test_synthesize_falls_back_to_cheap_model_when_throttled(monkeypatch):
    monkeypatch.setattr(synthesizer, "_RATE_LIMIT_RETRY_DELAY_S", 0)
    cheap = _FlakyClient(failures=0, model="cheap-model")
    monkeypatch.setattr(synthesizer, "extractor_client", lambda: cheap)
    premium = _FlakyClient(failures=99)
    res = await synthesize("https://x", _facts(), client=premium)
    assert premium.calls == 2                    # retry once before giving up
    assert cheap.calls == 1
    assert res.fallback_model == "cheap-model"   # surfaced so the UI can label it
    assert res.memo.verdict.score == 50          # screen still completes


async def test_synthesize_fallback_rate_limit_still_raises(monkeypatch):
    monkeypatch.setattr(synthesizer, "_RATE_LIMIT_RETRY_DELAY_S", 0)
    monkeypatch.setattr(synthesizer, "extractor_client", lambda: _FlakyClient(failures=99))
    premium = _FlakyClient(failures=99)
    try:
        await synthesize("https://x", _facts(), client=premium)
        raise AssertionError("expected RateLimitError to propagate")
    except openai.RateLimitError:
        pass                                     # stream layer turns this into an error event
