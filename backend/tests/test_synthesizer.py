from app.pipeline.models import Fact
from app.pipeline.synthesizer import _build_memo, _clamp_int


def _facts():
    return [Fact("Free $0", "overview", "https://x/pricing", 0.9),
            Fact("892 repos", "engineering", "https://github.com/x", 0.8)]


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
