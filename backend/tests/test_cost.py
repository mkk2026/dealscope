import pytest

from app.cost import (
    EXTRACT_IN_PER_1M,
    SYNTH_IN_PER_1M,
    compute_race,
)


def test_routed_extraction_uses_cheap_rate_naive_uses_premium():
    # 1M extraction input tokens, nothing else.
    r = compute_race(extract_in=1_000_000, extract_out=0)
    assert r.routed_usd == pytest.approx(EXTRACT_IN_PER_1M)   # cheap model
    assert r.naive_usd == pytest.approx(SYNTH_IN_PER_1M)      # premium model for same work


def test_savings_is_naive_over_routed_and_routing_never_costs_more():
    r = compute_race(500_000, 200_000, 3_000, 4_000)
    assert r.savings_x == pytest.approx(r.naive_usd / r.routed_usd, rel=1e-9)
    assert r.naive_usd >= r.routed_usd


def test_extraction_heavy_workload_widens_the_gap():
    # The thesis: the more bulk extraction (routed to the cheap model), the bigger the win.
    light = compute_race(100_000, 50_000, 3_000, 4_000)
    heavy = compute_race(2_000_000, 1_000_000, 3_000, 4_000)
    assert heavy.savings_x > light.savings_x


def test_total_tokens_and_zero_safety():
    assert compute_race(10, 20, 30, 40).total_tokens == 100
    z = compute_race(0, 0, 0, 0)
    assert z.routed_usd == 0.0 and z.savings_x == 0.0
