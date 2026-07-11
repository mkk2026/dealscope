"""Research-weighted rubric score over the investor scorecard.

The weights are not opinions — they are derived from published evidence on how
early-stage investors actually decide:

- Gompers, Gornall, Kaplan & Strebulaev, "How do venture capitalists make
  decisions?" (Journal of Financial Economics, 2020; 885 VCs surveyed): 47% rank
  the management team as the single most important factor (53% among early-stage
  VCs); importance mentions — team 95%, business model 83%, product 74%, market 68%.
- CB Insights startup post-mortems: "no market need" is the #1 cause of failure
  (~42%), bad timing ~29%, team breakdown 23% — so demand evidence and timing are
  the strongest negative screens.
- Angel screening practice: validated pilots/logos/revenue count as traction;
  vanity metrics are noise; red flags cap a deal rather than average into it.

Cluster view of the weights below (sums to 100):
  Team 28 · Traction/execution 35 · Business & moat 20 · Market timing 12 · Capital 5
red_flags is deliberately NOT in the weighted sum — it is a veto lane: a high
red-flag score caps the rubric verdict instead of being diluted by good signals.
"""

from dataclasses import dataclass

# signal id -> weight (percent). Keys must match models.SCORECARD_SIGNALS.
RUBRIC_WEIGHTS = {
    "technical_team": 20,
    "hiring_velocity": 8,
    "shipping_cadence": 10,
    "customer_evidence": 18,
    "revenue_signals": 10,
    "github_momentum": 7,
    "market_timing": 12,
    "moat_evidence": 10,
    "capital_efficiency": 5,
}

# Below this many evidence-backed signals the rubric stays silent — a score
# computed from 2-3 signals is fake precision, not analysis.
MIN_SCORED_SIGNALS = 4

# red_flags at or above this caps the rubric verdict at "Borderline".
RED_FLAG_CAP_THRESHOLD = 7


@dataclass
class RubricScore:
    score: int                  # 0-100, weighted over scored signals only
    scored_signals: int         # how many weighted signals had evidence
    total_signals: int          # how many weighted signals exist
    red_flag_capped: bool       # True when red_flags >= threshold
    diverges_from_model: bool   # |rubric - model verdict score| > 20


def compute_rubric(scorecard, model_score: int | None) -> RubricScore | None:
    """Weighted roll-up over evidence-backed signals, renormalized so honest
    "insufficient data" gaps don't drag the score to zero. Returns None when the
    scorecard is absent or too thin to score honestly."""
    if not scorecard:
        return None

    by_id = {s.id: s for s in scorecard}
    scored = [(RUBRIC_WEIGHTS[sid], by_id[sid].score)
              for sid in RUBRIC_WEIGHTS
              if sid in by_id and by_id[sid].status == "scored"]
    if len(scored) < MIN_SCORED_SIGNALS:
        return None

    weight_sum = sum(w for w, _ in scored)
    raw = sum(w * sig_score * 10 for w, sig_score in scored) / weight_sum

    red = by_id.get("red_flags")
    capped = bool(red and red.status == "scored" and red.score >= RED_FLAG_CAP_THRESHOLD)

    score = max(0, min(100, round(raw)))
    diverges = model_score is not None and abs(score - model_score) > 20
    return RubricScore(score=score,
                       scored_signals=len(scored),
                       total_signals=len(RUBRIC_WEIGHTS),
                       red_flag_capped=capped,
                       diverges_from_model=diverges)
