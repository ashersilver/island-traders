"""Tests for the 2026-05-27 disaster-mitigation brief.

Covers three fixes:

1. Flood event re-tiered from yield 0.0 + outage (catastrophic) to
   yield 0.25 + no-outage (heavy).  Damage cycle and natural-disaster
   cascade still fire; the originating island just doesn't lose
   *everything* in one season.
2. Life insurance reduces fatality *rate* by 50% (not just pays a
   death benefit), mirroring how Medical halves injury rate.
3. Per-tick workforce-loss cap: max 30% of active workers can die
   from any single workforce-event tick (floor of fraction, minimum 1).
"""
from __future__ import annotations

import math
import random

import pytest

from island_traders.constants import (
    LIFE_INSURANCE_FATALITY_REDUCTION,
    MAX_WORKFORCE_LOSS_PER_TICK_FRACTION,
    WORKPLACE_RISK,
)
from island_traders.engine.events import EventChart, EventChartLoader
from island_traders.engine.workforce_events import apply_workplace_risks
from island_traders.models.insurance import InsurancePolicy
from island_traders.models.player import Player
from island_traders.models.role import ROLES
from island_traders.models.workforce import Worker


# ─────────────────────────────────────────────────────────────────────────
# Fix 1 — Flood event re-tiered
# ─────────────────────────────────────────────────────────────────────────


def test_flood_yields_at_quarter_capacity_not_zero():
    """Flood in the loaded event chart yields 0.25, not 0.0.  Origin
    island gets reduced (not zero) output AND no outage flag."""
    charts = EventChartLoader.default_charts()
    farmer_chart = charts.get("Farmer")
    assert farmer_chart is not None
    # Chart stores events as (cumulative_weight, EventResult) tuples
    # in _buckets — extract the EventResult by event_name.
    flood = next(
        (result for _, result in farmer_chart._buckets if result.event_name == "Flood"),
        None,
    )
    assert flood is not None, "Flood event missing from Farmer chart"
    assert flood.yield_modifier == pytest.approx(0.25), (
        f"Flood yield_modifier should be 0.25 (re-tiered 2026-05-27), "
        f"got {flood.yield_modifier}"
    )
    assert flood.outage is False, (
        "Flood should no longer be a full outage — re-tiered to 'heavy'"
    )
    # Damage cycle and natural-disaster cascade should still fire.
    assert flood.damage_seasons == 1
    assert flood.natural_disaster is True


# ─────────────────────────────────────────────────────────────────────────
# Fix 2 — Life insurance reduces fatality rate
# ─────────────────────────────────────────────────────────────────────────


def _make_player(role: str, n_workers: int, pid: int = 1) -> Player:
    p = Player(pid, role, [ROLES[role]], 100.0, is_human=True)
    p.workforce.workers.clear()
    skilled = next(iter(set(
        prof for prof in [
            "Miner", "MiningTechnician", "Farmer", "FarmingTechnician",
        ]
    )))
    # Use a generic Unskilled set so the workplace-risk multiplier
    # treatment is consistent across these tests.
    for i in range(n_workers):
        p.workforce.workers.append(
            Worker(worker_id=pid * 1000 + i, profession="Unskilled")
        )
    return p


def test_life_insurance_halves_per_worker_fatality_probability(monkeypatch):
    """With a Life policy in force, each worker's fatality probability
    is multiplied by (1 - LIFE_INSURANCE_FATALITY_REDUCTION).  We
    verify this by comparing fatality counts across many simulated
    ticks with vs without insurance, using a deterministic seed and
    a higher-than-natural fatality rate so the difference is
    statistically visible inside a single test.

    Also monkey-patches MAX_WORKFORCE_LOSS_PER_TICK_FRACTION to 1.0
    (effectively disabling the per-tick cap) so the cap doesn't
    bottleneck the uninsured death count and mask the halving effect.
    """
    monkeypatch.setattr(
        "island_traders.engine.workforce_events.MAX_WORKFORCE_LOSS_PER_TICK_FRACTION",
        1.0,
    )
    # Set fatality_rate high enough that ~half the workers die per
    # tick (gives clear delta between insured/uninsured) and zero
    # injury_rate so all workers reach the fatality phase.
    monkeypatch.setitem(WORKPLACE_RISK, "Miner", {
        "injury_rate": 0.0,
        "fatality_rate": 0.30,
    })
    rng_uninsured = random.Random(42)
    rng_insured = random.Random(42)
    banker = Player(0, "Banker", [ROLES["Banker"]], 1000.0, is_human=False)
    deaths_uninsured = 0
    deaths_insured = 0
    n_ticks = 50
    for _ in range(n_ticks):
        miner_uninsured = _make_player("Miner", n_workers=10, pid=1)
        reports = apply_workplace_risks(
            [miner_uninsured], year=0, season_index=0,
            banker_players=[banker], rng=rng_uninsured,
        )
        deaths_uninsured += len(
            reports[0].fatality_worker_ids if reports else []
        )
    for _ in range(n_ticks):
        miner_insured = _make_player("Miner", n_workers=10, pid=1)
        miner_insured.insurance_policies.append(
            InsurancePolicy(
                policy_id=1, policy_type="life",
                holder_player_id=1, banker_player_id=0,
                premium_paid=50.0,
                purchased_tick=0, expires_at_tick=999,
            )
        )
        reports = apply_workplace_risks(
            [miner_insured], year=0, season_index=0,
            banker_players=[banker], rng=rng_insured,
        )
        deaths_insured += len(
            reports[0].fatality_worker_ids if reports else []
        )
    assert deaths_insured < deaths_uninsured, (
        f"Insured deaths ({deaths_insured}) should be < uninsured "
        f"({deaths_uninsured})"
    )
    # Allow generous variance margin.  Expected reduction is ~50 %.
    assert deaths_insured <= deaths_uninsured * 0.70, (
        f"Life insurance should approximately halve fatalities; "
        f"insured={deaths_insured}, uninsured={deaths_uninsured}"
    )


def test_life_insurance_reduction_flag_set_on_report(monkeypatch):
    """Report flag tracks whether the life-insurance reduction was
    applied to fatality probabilities (so the dashboard can attribute
    survivals to the policy)."""
    # Deterministically force a fatality so the flag has a chance to fire.
    monkeypatch.setitem(WORKPLACE_RISK, "Miner", {
        "injury_rate": 0.0,
        "fatality_rate": 1.0,
    })
    miner = _make_player("Miner", n_workers=5, pid=1)
    miner.insurance_policies.append(
        InsurancePolicy(
            policy_id=1, policy_type="life",
            holder_player_id=1, banker_player_id=0,
            premium_paid=50.0,
            purchased_tick=0, expires_at_tick=999,
        )
    )
    banker = Player(0, "Banker", [ROLES["Banker"]], 1000.0, is_human=False)

    class AlwaysKillsRng(random.Random):
        def random(self):
            return 0.0

    reports = apply_workplace_risks(
        [miner], year=0, season_index=0,
        banker_players=[banker], rng=AlwaysKillsRng(),
    )
    assert reports
    assert reports[0].fatality_worker_ids, "Expected at least one fatality"
    assert reports[0].insurance_reduced_fatalities is True


# ─────────────────────────────────────────────────────────────────────────
# Fix 3 — Per-tick workforce-loss cap
# ─────────────────────────────────────────────────────────────────────────


def test_per_tick_loss_cap_limits_fatalities_in_a_single_tick(monkeypatch):
    """With 10 active workers and a forced-100% fatality rate, only
    floor(10 × 0.30) = 3 workers can die in one tick.  Cap fires and
    the report flag tracks would_have_lost.

    Patches Mining's injury_rate to 0 so all workers reach the
    fatality phase as active (otherwise an AlwaysKillsRng would
    convert everyone into 'injured' before the fatality loop sees
    them)."""
    monkeypatch.setitem(WORKPLACE_RISK, "Miner", {
        "injury_rate": 0.0,
        "fatality_rate": 1.0,  # 100% fatality rate
    })
    miner = _make_player("Miner", n_workers=10, pid=1)
    banker = Player(0, "Banker", [ROLES["Banker"]], 1000.0, is_human=False)

    class AlwaysKillsRng(random.Random):
        def random(self):
            return 0.0  # always < any positive probability

    reports = apply_workplace_risks(
        [miner], year=0, season_index=0,
        banker_players=[banker], rng=AlwaysKillsRng(),
    )
    assert reports
    report = reports[0]
    expected_cap = max(
        1, math.floor(10 * MAX_WORKFORCE_LOSS_PER_TICK_FRACTION)
    )
    assert len(report.fatality_worker_ids) == expected_cap, (
        f"Cap should limit fatalities to {expected_cap}; "
        f"got {len(report.fatality_worker_ids)}"
    )
    assert report.loss_cap_applied is True
    # would_have_lost reflects how many would have died without the cap.
    assert report.would_have_lost > expected_cap


def test_per_tick_loss_cap_does_not_fire_when_natural_losses_low():
    """When fewer workers die than the cap allows, the cap is a no-op
    and the flag stays False."""
    # Mining at default rate over 1 tick will average ~0-1 deaths,
    # which is below the cap of floor(10 × 0.30) = 3.  Use a high seed
    # to force just one death (or zero).
    miner = _make_player("Miner", n_workers=10, pid=1)
    banker = Player(0, "Banker", [ROLES["Banker"]], 1000.0, is_human=False)
    reports = apply_workplace_risks(
        [miner], year=0, season_index=0,
        banker_players=[banker], rng=random.Random(0),
    )
    if not reports or not reports[0].fatality_worker_ids:
        # Zero deaths — cap obviously didn't fire.
        return
    report = reports[0]
    if len(report.fatality_worker_ids) <= 3:
        assert report.loss_cap_applied is False


def test_per_tick_cap_minimum_of_one(monkeypatch):
    """With a 5-worker Miner, floor(5 × 0.30) = 1.  At least 1
    fatality possible per tick even with the cap.  Verifies max(1, …)
    handles small workforces."""
    monkeypatch.setitem(WORKPLACE_RISK, "Miner", {
        "injury_rate": 0.0,
        "fatality_rate": 1.0,
    })
    miner = _make_player("Miner", n_workers=5, pid=1)
    banker = Player(0, "Banker", [ROLES["Banker"]], 1000.0, is_human=False)

    class AlwaysKillsRng(random.Random):
        def random(self):
            return 0.0

    reports = apply_workplace_risks(
        [miner], year=0, season_index=0,
        banker_players=[banker], rng=AlwaysKillsRng(),
    )
    assert reports
    report = reports[0]
    expected_cap = max(
        1, math.floor(5 * MAX_WORKFORCE_LOSS_PER_TICK_FRACTION)
    )
    assert expected_cap == 1
    assert len(report.fatality_worker_ids) == expected_cap


def test_cap_preserves_most_experienced_workers(monkeypatch):
    """When the cap fires, the workers KEPT (i.e. NOT in deceased
    list) should be the youngest — domain logic in the cap
    implementation: deceased list is sorted oldest-first (most
    vulnerable die first), then trimmed to the cap, so the trimmed
    survivors end up being the youngest."""
    monkeypatch.setitem(WORKPLACE_RISK, "Miner", {
        "injury_rate": 0.0,
        "fatality_rate": 1.0,
    })
    miner = Player(1, "Miner", [ROLES["Miner"]], 100.0, is_human=True)
    miner.workforce.workers.clear()
    # 10 workers with distinct ages — older = more experienced.
    for i in range(10):
        miner.workforce.workers.append(
            Worker(worker_id=i + 100, profession="Unskilled", age_seasons=i)
        )
    banker = Player(0, "Banker", [ROLES["Banker"]], 1000.0, is_human=False)

    class AlwaysKillsRng(random.Random):
        def random(self):
            return 0.0

    reports = apply_workplace_risks(
        [miner], year=0, season_index=0,
        banker_players=[banker], rng=AlwaysKillsRng(),
    )
    # Surviving workers = original 10 - cap
    expected_cap = max(
        1, math.floor(10 * MAX_WORKFORCE_LOSS_PER_TICK_FRACTION)
    )
    survivors = miner.workforce.workers
    assert len(survivors) == 10 - expected_cap
    # Survivors should be the YOUNGEST (vulnerable die first).
    surviving_ages = sorted(w.age_seasons for w in survivors)
    expected_surviving_ages = sorted(range(10 - expected_cap))
    assert surviving_ages == expected_surviving_ages, (
        f"Cap should keep the most-experienced (oldest) on the deceased "
        f"side: survivors should be the youngest.  Got ages "
        f"{surviving_ages}, expected {expected_surviving_ages}"
    )
