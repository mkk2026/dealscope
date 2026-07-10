import httpx
import openai

from app.llm.client import Completion
from app.pipeline import synthesizer
from app.pipeline.models import Fact
from app.pipeline.synthesizer import _build_memo, _clamp_int, synthesize


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
