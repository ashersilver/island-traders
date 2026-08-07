"""Doctor-certified insurance effects (#19).

Two of the three mechanics in the issue:

  * an insured island loses **no productivity** to injuries — the worker is
    treated at the insurer's expense rather than being sidelined;
  * the life-insurance death benefit pays the cost of **replacing** the
    worker, which depends on how long that worker took to train.

The third (an annual physical halving the premium) is gated on Laboratory
Tests, which are deferred to Phase B of requirements/medical-laboratory.md.

Note on the scripted RNG: `apply_workplace_risks` rolls once per active
worker for injuries and then once per still-active worker for fatalities.
An RNG that always returns 0.0 injures everyone, which empties the active
pool so no fatality roll ever happens — that is why the pre-existing
death-benefit assertion in test_workforce_events.py never actually ran. The
sequences below drive the two phases independently.
"""
from __future__ import annotations

import pytest

from island_traders.constants import (
    INSURED_INJURY_RECOVERY_SEASONS,
    LIFE_INSURANCE_DEATH_BENEFIT_BY_BAND,
    INSURANCE_DURATION_SEASONS,
    MAX_WORKFORCE_LOSS_PER_TICK_FRACTION,
    UNTREATED_RECOVERY_SEASONS,
)
from island_traders.engine.workforce_events import apply_workplace_risks
from island_traders.models.insurance import InsurancePolicy
from island_traders.models.player import Player
from island_traders.models.profession import Profession, band_of
from island_traders.models.role import ROLES


class ScriptedRNG:
    """Returns each queued value in turn, then `tail` forever."""

    def __init__(self, queued: list[float], tail: float = 1.0):
        self._queued = list(queued)
        self._tail = tail

    def random(self) -> float:
        return self._queued.pop(0) if self._queued else self._tail


def _island(role: str = "Miner", professions: list[str] | None = None) -> Player:
    player = Player(2, "Carol", [ROLES[role]], 100.0, is_human=False)
    for profession in (professions or [Profession.UNSKILLED.value] * 8):
        worker = player.workforce.add_workers(1, training_level=3, profession=profession)[0]
        worker.experience_seasons = 20
    return player


def _banker(dollops: float = 10_000.0) -> Player:
    return Player(9, "Bank", [ROLES["Banker"]], dollops, is_human=False)


def _insure(player: Player, kind: str) -> None:
    """Give the island an active policy of `kind` for year 0 / season 0."""
    player.add_insurance_policy(InsurancePolicy(
        policy_id=1,
        policy_type=kind,
        holder_player_id=player.player_id,
        banker_player_id=9,
        premium_paid=25.0,
        purchased_tick=0,
        expires_at_tick=INSURANCE_DURATION_SEASONS,
    ))
    assert player.has_active_insurance(kind, 0, 0)


# ---------------------------------------------------------------------------
# Injuries cost an insured island nothing
# ---------------------------------------------------------------------------

def _injuries_only(worker_count: int) -> ScriptedRNG:
    """Injure everyone, then miss every fatality roll.

    Isolating the two phases matters here: with medical insurance the injured
    stay in the active pool, so they are still rolled for fatalities — a real
    consequence of the #19 change, and one that would otherwise be mistaken
    for the absence behaviour under test.
    """
    return ScriptedRNG([0.0] * worker_count, tail=1.0)


def test_uninsured_injuries_sideline_the_worker():
    island = _island()
    always_injure = _injuries_only(8)

    report = apply_workplace_risks(
        [island], year=0, season_index=0, banker_players=[], rng=always_injure
    )[0]

    assert report.injured_worker_ids
    assert not report.insurance_reduced_injuries
    absent = [w for w in island.workforce.workers if w.worker_id in set(report.injured_worker_ids)]
    assert all(w.absent_seasons == UNTREATED_RECOVERY_SEASONS for w in absent)
    # The whole workforce is off the line.
    assert island.workforce.active_count == 0


def test_medical_insurance_means_injuries_cost_no_productivity():
    """#19: 'if they are insured they have no loss of productivity'."""
    island = _island()
    _insure(island, "medical")
    before = island.workforce.active_count
    always_injure = _injuries_only(8)

    report = apply_workplace_risks(
        [island], year=0, season_index=0, banker_players=[], rng=always_injure
    )[0]

    # The injuries still happen and are still reported...
    assert report.injured_worker_ids
    assert report.insurance_reduced_injuries
    # ...but nobody is sidelined.
    assert island.workforce.active_count == before
    assert all(w.absent_seasons == 0 for w in island.workforce.workers)
    assert INSURED_INJURY_RECOVERY_SEASONS == 0


def test_insurance_no_longer_suppresses_the_injury_roll():
    """The injury happens either way — only its consequence differs."""
    uninsured, insured = _island(), _island()
    _insure(insured, "medical")

    reports = [
        apply_workplace_risks(
            [island], year=0, season_index=0, banker_players=[], rng=_injuries_only(8)
        )[0]
        for island in (uninsured, insured)
    ]

    assert len(reports[0].injured_worker_ids) == len(reports[1].injured_worker_ids)


# ---------------------------------------------------------------------------
# Death benefit tracks replacement cost
# ---------------------------------------------------------------------------

def _fatalities_only(worker_count: int) -> ScriptedRNG:
    """No injuries (so the active pool survives), then every fatality roll hits."""
    return ScriptedRNG([1.0] * worker_count, tail=0.0)


def test_death_benefit_is_paid_per_band_not_a_flat_rate():
    # 8 Managers: every payout should be the Manager rate.
    island = _island(professions=[Profession.DOCTOR.value] * 8)
    _insure(island, "life")
    banker = _banker()

    report = apply_workplace_risks(
        [island], year=0, season_index=0, banker_players=[banker],
        rng=_fatalities_only(8),
    )[0]

    deaths = len(report.fatality_worker_ids)
    assert deaths, "scripted RNG should force fatalities"
    assert report.death_benefit_paid == pytest.approx(
        LIFE_INSURANCE_DEATH_BENEFIT_BY_BAND["Manager"] * deaths
    )


def test_an_unskilled_death_pays_less_than_a_manager_death():
    """A Manager took seasons of university; a Worker was hired off the dock."""
    payouts = {}
    for profession in (Profession.DOCTOR.value, Profession.UNSKILLED.value):
        island = _island(professions=[profession] * 8)
        _insure(island, "life")
        banker = _banker()
        report = apply_workplace_risks(
            [island], year=0, season_index=0, banker_players=[banker],
            rng=_fatalities_only(8),
        )[0]
        assert report.fatality_worker_ids
        payouts[profession] = report.death_benefit_paid / len(report.fatality_worker_ids)

    assert payouts[Profession.DOCTOR.value] > payouts[Profession.UNSKILLED.value]
    assert payouts[Profession.DOCTOR.value] == LIFE_INSURANCE_DEATH_BENEFIT_BY_BAND["Manager"]
    assert payouts[Profession.UNSKILLED.value] == LIFE_INSURANCE_DEATH_BENEFIT_BY_BAND["Worker"]


def test_mixed_workforce_benefit_is_the_sum_of_each_band():
    island = _island(professions=[Profession.DOCTOR.value] * 4 + [Profession.UNSKILLED.value] * 4)
    _insure(island, "life")
    banker = _banker()
    # The deceased are removed from the roster, so record bands up front.
    bands_before = {
        w.worker_id: band_of(w.profession).value for w in island.workforce.workers
    }

    report = apply_workplace_risks(
        [island], year=0, season_index=0, banker_players=[banker],
        rng=_fatalities_only(8),
    )[0]

    cap = max(1, int(8 * MAX_WORKFORCE_LOSS_PER_TICK_FRACTION))
    assert len(report.fatality_worker_ids) == cap

    expected = sum(
        LIFE_INSURANCE_DEATH_BENEFIT_BY_BAND[bands_before[worker_id]]
        for worker_id in report.fatality_worker_ids
    )
    assert report.death_benefit_paid == pytest.approx(expected)


def test_no_life_policy_pays_nothing():
    island = _island(professions=[Profession.DOCTOR.value] * 8)
    banker = _banker()

    report = apply_workplace_risks(
        [island], year=0, season_index=0, banker_players=[banker],
        rng=_fatalities_only(8),
    )[0]

    assert report.fatality_worker_ids
    assert report.death_benefit_paid == 0.0
