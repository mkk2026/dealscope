# Investor rubric — research-weighted roll-up over the scorecard.
# Weights cite Gompers et al. (JFE 2020) and CB Insights post-mortems; see rubric.py.

from app.pipeline.models import SCORECARD_SIGNALS, Signal
from app.pipeline.rubric import (MIN_SCORED_SIGNALS, RUBRIC_WEIGHTS,
                                 compute_rubric)


def _signal(sid, score=8, status="scored"):
    return Signal(id=sid, name=SCORECARD_SIGNALS[sid], score=score,
                  rationale="r", evidence=["https://x"] if status == "scored" else [],
                  status=status)


def _full_scorecard(score=8):
    return [_signal(sid, score=score) for sid in SCORECARD_SIGNALS]


def test_weights_cover_every_signal_except_red_flags():
    assert set(RUBRIC_WEIGHTS) == set(SCORECARD_SIGNALS) - {"red_flags"}
    assert sum(RUBRIC_WEIGHTS.values()) == 100


def test_uniform_scores_map_to_expected_scale():
    r = compute_rubric(_full_scorecard(score=8), model_score=80)
    assert r.score == 80                       # 8/10 across the board = 80/100
    assert r.scored_signals == 9 and r.total_signals == 9
    assert not r.diverges_from_model


def test_insufficient_signals_are_renormalized_not_zeroed():
    sc = [_signal("technical_team", 10), _signal("customer_evidence", 10),
          _signal("market_timing", 10), _signal("revenue_signals", 10)]
    sc += [_signal(sid, 0, status="insufficient_data")
           for sid in SCORECARD_SIGNALS if sid not in
           {"technical_team", "customer_evidence", "market_timing", "revenue_signals"}]
    r = compute_rubric(sc, model_score=None)
    assert r.score == 100                      # gaps don't drag the average down
    assert r.scored_signals == 4


def test_too_thin_coverage_returns_none():
    sc = [_signal("technical_team", 9), _signal("customer_evidence", 9),
          _signal("moat_evidence", 9)]        # 3 scored < MIN_SCORED_SIGNALS
    sc += [_signal(sid, 0, status="insufficient_data")
           for sid in SCORECARD_SIGNALS if sid not in
           {"technical_team", "customer_evidence", "moat_evidence"}]
    assert MIN_SCORED_SIGNALS == 4
    assert compute_rubric(sc, model_score=50) is None


def test_empty_or_missing_scorecard_returns_none():
    assert compute_rubric([], model_score=80) is None
    assert compute_rubric(None, model_score=80) is None


def test_red_flags_cap_is_a_veto_not_an_average():
    sc = _full_scorecard(score=9)
    sc = [s if s.id != "red_flags" else _signal("red_flags", 9) for s in sc]
    r = compute_rubric(sc, model_score=90)
    assert r.red_flag_capped                   # 9/10 red flags caps the verdict
    assert r.score == 90                       # ...but does NOT dilute the weighted score


def test_divergence_flag_fires_over_20_points():
    r = compute_rubric(_full_scorecard(score=4), model_score=90)   # rubric 40 vs model 90
    assert r.score == 40 and r.diverges_from_model
    r2 = compute_rubric(_full_scorecard(score=8), model_score=90)  # 80 vs 90
    assert not r2.diverges_from_model
