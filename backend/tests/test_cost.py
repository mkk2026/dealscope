import pytest

from app.cost import FRONTIER_8B_PER_1M, amd_rate_per_1m, compute_race, cost_usd


def test_cost_usd():
    assert cost_usd(1_000_000, 0.2) == pytest.approx(0.2)
    assert cost_usd(0, 5.0) == 0.0


def test_amd_rate_derived_from_throughput():
    # $1/hr at 1000 tok/s -> 3.6M tok/hr -> ~$0.2778 / 1M
    assert amd_rate_per_1m(1.0, 1000) == pytest.approx(1_000_000 / 3_600_000, rel=1e-6)
    assert amd_rate_per_1m(1.0, 0) == 0.0  # guard against div-by-zero


def test_compute_race_savings_is_frontier_over_amd():
    race = compute_race(extraction_tokens=1_000_000, synth_tokens=0,
                        pod_hourly_usd=1.0, tokens_per_sec=1000)
    assert race.frontier_usd == pytest.approx(FRONTIER_8B_PER_1M)  # 1M tokens at frontier rate
    assert race.savings_x == pytest.approx(race.frontier_usd / race.amd_usd, rel=1e-6)


def test_high_throughput_makes_amd_cheaper():
    # The whole thesis: saturate the pod -> AMD wins.
    slow = compute_race(1_000_000, 0, 2.0, 500)
    fast = compute_race(1_000_000, 0, 2.0, 5000)
    assert fast.amd_usd < slow.amd_usd
    assert fast.savings_x > slow.savings_x
