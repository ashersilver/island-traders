"""R1/R2/R7 baselining metrics (simulation-baselining review, 2026-07-04):
wealth-share variance, _SilentIO fallback telemetry, and concentration
(Gini/HHI) reporting in the simulation runner."""
from __future__ import annotations

import pytest

from island_traders.simulation.runner import (
    RoleStats,
    SimulationRunner,
    _SilentIO,
    gini_coefficient,
    hhi,
)


# ---- R7: concentration helpers ----

def test_gini_equal_distribution_is_zero():
    assert gini_coefficient([100.0, 100.0, 100.0, 100.0]) == 0.0


def test_gini_total_concentration_approaches_one():
    # One player holds everything among 7 → G = (n-1)/n ≈ 0.857.
    g = gini_coefficient([700.0, 0, 0, 0, 0, 0, 0])
    assert g == pytest.approx(6 / 7, abs=1e-3)


def test_gini_clamps_negative_wealth():
    # A bankrupt (negative) island counts as zero, not as negative mass.
    assert gini_coefficient([-50.0, 100.0]) == gini_coefficient([0.0, 100.0])


def test_gini_empty_and_zero_safe():
    assert gini_coefficient([]) == 0.0
    assert gini_coefficient([0.0, 0.0]) == 0.0


def test_hhi_balanced_seven_players():
    assert hhi([1.0] * 7) == pytest.approx(1 / 7, abs=1e-3)


def test_hhi_monopoly_is_one():
    assert hhi([500.0, 0.0, 0.0]) == 1.0


def test_hhi_normalises_raw_wealth():
    # 3:1 split → shares 0.75/0.25 → HHI 0.625 regardless of scale.
    assert hhi([300.0, 100.0]) == pytest.approx(0.625, abs=1e-4)
    assert hhi([3.0, 1.0]) == pytest.approx(0.625, abs=1e-4)


# ---- R1: share mean / stddev ----

def test_role_stats_share_mean_and_stddev():
    rs = RoleStats("Miner")
    rs.wealth_shares = [0.10, 0.20]
    assert rs.share_mean == pytest.approx(0.15)
    assert rs.share_stddev == pytest.approx(0.0707, abs=1e-3)


def test_role_stats_share_safe_when_empty_or_single():
    rs = RoleStats("Miner")
    assert rs.share_mean == 0.0
    assert rs.share_stddev == 0.0
    rs.wealth_shares = [0.14]
    assert rs.share_stddev == 0.0


# ---- R2: fallback telemetry ----

def test_silent_io_counts_decision_methods():
    io = _SilentIO()
    io.choose_quantity("q", 1, 10)
    io.choose_quantity("q", 1, 10)
    io.confirm("sure?")
    io.ask_dollop_amount("how much", 100.0)
    # Non-decision output methods are not counted.
    io.print("noise")
    io.input("prompt")
    assert io.fallback_counts == {
        "choose_quantity": 2,
        "confirm": 1,
        "ask_dollop_amount": 1,
    }


def test_silent_io_defaults_unchanged():
    io = _SilentIO()
    assert io.choose_quantity("q", 3, 10) == 3
    assert io.confirm("x") is True
    assert io.ask_dollop_amount("x", 50.0) == 0.0
    assert io.choose_resource("x", ["Oil", "Ore"]) == "Oil"


# ---- integration: one tiny sim run carries all three metrics ----

def test_runner_smoke_populates_new_metrics():
    runner = SimulationRunner(num_games=2, num_years=1, seed=42)
    stats = runner.run()
    # R7 aggregates exist and are sane.
    assert 0.0 <= stats.gini_mean < 1.0
    assert 0.0 < stats.hhi_mean <= 1.0
    # R1: every role logged one share per game, summing to ~1 per game.
    for rs in stats.role_stats.values():
        assert len(rs.wealth_shares) == 2
    per_game_total = sum(rs.wealth_shares[0] for rs in stats.role_stats.values())
    assert per_game_total == pytest.approx(1.0, abs=1e-6)
    # R2: dict exists (counts may legitimately be zero if AIStrategy covers
    # every prompt — the contract is presence, not a particular value).
    assert isinstance(stats.fallback_counts, dict)
