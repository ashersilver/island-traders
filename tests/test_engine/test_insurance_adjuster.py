"""Insurance Adjuster — claims processing (#196).

> "For claims to be processed there needs to be an 'Insurance Adjuster' to
> process the claim."

Underwriting and claims are different jobs: an Actuary prices the risk, an
Adjuster settles the loss. Holding one does not cover the other. The Banking
island starts with one Adjuster, so the rule bites only when the Adjuster is
lost or retrained away.
"""
from __future__ import annotations

import pytest

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import (
    INSURANCE_DURATION_SEASONS,
    SKILLED_PROFESSIONS,
    STARTING_WORKERS_BY_PROFESSION,
    UNIVERSITY_CAPACITY,
)
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.workforce_events import apply_workplace_risks
from island_traders.models.insurance import InsurancePolicy, banker_can_process_claims
from island_traders.models.player import Player
from island_traders.models.profession import (
    APPRENTICESHIP_SEASONS,
    PROFESSION_BAND,
    PROFESSION_LABEL,
    ROLE_PROFESSIONS,
    Profession,
    WorkerBand,
)
from island_traders.models.role import ROLES


ITEM_ID = "farmer.tractor"


class _Item:
    name = "Tractor"
    cost = 60.0


# ---------------------------------------------------------------------------
# Profession wiring
# ---------------------------------------------------------------------------

def test_adjuster_is_a_banker_technician():
    assert PROFESSION_BAND[Profession.INSURANCE_ADJUSTER] == WorkerBand.TECHNICIAN
    assert PROFESSION_LABEL[Profession.INSURANCE_ADJUSTER] == "Insurance Adjuster"
    assert Profession.INSURANCE_ADJUSTER in ROLE_PROFESSIONS["Banker"]
    assert "InsuranceAdjuster" in SKILLED_PROFESSIONS["Banker"]


def test_adjuster_is_trainable():
    assert APPRENTICESHIP_SEASONS[Profession.INSURANCE_ADJUSTER] == 1
    assert UNIVERSITY_CAPACITY["InsuranceAdjuster"] > 0


def test_the_bank_starts_with_a_claims_desk():
    """Otherwise the rule would silently stop every existing death benefit."""
    assert dict(STARTING_WORKERS_BY_PROFESSION["Banker"])["InsuranceAdjuster"] == 1

    game = Game(GameConfig([PlayerSpec("Bank", ["Banker"], is_human=False)]), FakeIOAdapter())
    game.setup()
    assert banker_can_process_claims(game.players[0])


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

def _bank(adjusters: int, actuaries: int = 1, dollops: float = 5_000.0) -> Player:
    bank = Player(1, "Bank", [ROLES["Banker"]], dollops, is_human=False)
    if adjusters:
        bank.workforce.add_workers(adjusters, profession=Profession.INSURANCE_ADJUSTER.value)
    if actuaries:
        bank.workforce.add_workers(actuaries, profession=Profession.ACTUARY.value)
    return bank


def test_an_actuary_does_not_double_as_an_adjuster():
    """Pricing risk and settling losses are different jobs."""
    assert not banker_can_process_claims(_bank(adjusters=0, actuaries=3))
    assert banker_can_process_claims(_bank(adjusters=1, actuaries=0))


def _equipment_claim_game(adjusters: int):
    game = Game(GameConfig([]), FakeIOAdapter())
    farmer = Player(0, "Farm", [ROLES["Farmer"]], 100.0, is_human=False)
    bank = _bank(adjusters=adjusters)
    game.players = [farmer, bank]
    farmer.add_insurance_policy(InsurancePolicy(
        policy_id=1,
        policy_type="equipment",
        holder_player_id=farmer.player_id,
        banker_player_id=bank.player_id,
        premium_paid=12.72,
        purchased_tick=0,
        expires_at_tick=INSURANCE_DURATION_SEASONS,
        item_id=ITEM_ID,
        insured_value=54.0,
    ))
    return game, farmer, bank


def test_no_adjuster_means_an_equipment_claim_cannot_be_settled():
    game, farmer, bank = _equipment_claim_game(adjusters=0)

    paid = game._settle_equipment_claim(farmer, ITEM_ID, _Item(), current_tick=1)

    assert paid == 0.0
    assert farmer.dollops == pytest.approx(100.0)
    assert bank.dollops == pytest.approx(5_000.0)


def test_an_unsettled_claim_leaves_the_policy_in_force():
    """The buyer paid for cover; a staffing gap at the Bank must not void it."""
    game, farmer, _ = _equipment_claim_game(adjusters=0)

    game._settle_equipment_claim(farmer, ITEM_ID, _Item(), current_tick=1)
    assert farmer.insurance_policies[0].active

    # Hire an Adjuster and the same claim now settles.
    game.players[1].workforce.add_workers(
        1, profession=Profession.INSURANCE_ADJUSTER.value
    )
    assert game._settle_equipment_claim(farmer, ITEM_ID, _Item(), 1) == pytest.approx(54.0)


def test_a_death_benefit_is_a_claim_and_needs_an_adjuster_too():
    miner = Player(0, "Mine", [ROLES["Miner"]], 100.0, is_human=False)
    for _ in range(8):
        worker = miner.workforce.add_workers(1, training_level=3)[0]
        worker.experience_seasons = 20
    miner.add_insurance_policy(InsurancePolicy(
        policy_id=1,
        policy_type="life",
        holder_player_id=miner.player_id,
        banker_player_id=1,
        premium_paid=50.0,
        purchased_tick=0,
        expires_at_tick=INSURANCE_DURATION_SEASONS,
    ))

    class _RNG:
        """No injuries (keeps the pool active), then every fatality roll hits."""
        def __init__(self):
            self._queued = [1.0] * 8

        def random(self):
            return self._queued.pop(0) if self._queued else 0.0

    report = apply_workplace_risks(
        [miner], year=0, season_index=0,
        banker_players=[_bank(adjusters=0)], rng=_RNG(),
    )[0]

    assert report.fatality_worker_ids, "scripted RNG should force fatalities"
    assert report.death_benefit_paid == 0.0
