"""Equipment ("industrial") insurance — #196.

> "For equipment failures an insurance policy needs to be applied to a
> specific item of equipment, and its premium will be a flat rate with a 20%
> markup, over percentage (based on the actuarial tables in Issue #188) of the
> equipment replacement value per year ... and will pay out 90% of the value
> of the equipment."

Priced off the same #188 Weibull curve the engine rolls against, so the
premium tracks the hazard that causes the claim.
"""
from __future__ import annotations

import pytest

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import (
    EQUIPMENT_FAILURE_PROB_BY_QUARTER,
    EQUIPMENT_INSURANCE_MARKUP,
    EQUIPMENT_INSURANCE_PAYOUT_FRACTION,
    INSURANCE_DURATION_SEASONS,
)
from island_traders.engine.game import Game, GameConfig
from island_traders.models.insurance import (
    InsurancePolicy,
    annual_failure_probability,
    equipment_insurance_quote,
)
from island_traders.models.player import Player
from island_traders.models.role import ROLES


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def test_annual_probability_compounds_four_quarters_of_the_188_curve():
    expected = 1.0
    for quarter in (1, 2, 3, 4):
        expected *= 1.0 - EQUIPMENT_FAILURE_PROB_BY_QUARTER[quarter]

    assert annual_failure_probability(0) == pytest.approx(1.0 - expected)


def test_older_equipment_is_likelier_to_fail_and_costs_more_to_insure():
    young = equipment_insurance_quote(100.0, age_seasons=0)
    old = equipment_insurance_quote(100.0, age_seasons=16)

    assert old["failure_probability"] > young["failure_probability"]
    assert old["annual_premium"] > young["annual_premium"]
    # The payout is the value of the machine, so it does not move with age.
    assert old["payout"] == young["payout"]


def test_payout_is_ninety_percent_of_value():
    quote = equipment_insurance_quote(200.0)

    assert quote["payout"] == pytest.approx(200.0 * EQUIPMENT_INSURANCE_PAYOUT_FRACTION)
    assert quote["payout"] == pytest.approx(180.0)


def test_premium_is_expected_loss_plus_the_twenty_percent_markup():
    quote = equipment_insurance_quote(150.0, age_seasons=4)

    assert quote["expected_loss"] == pytest.approx(
        quote["payout"] * quote["failure_probability"], rel=1e-3
    )
    assert quote["annual_premium"] == pytest.approx(
        quote["expected_loss"] * (1 + EQUIPMENT_INSURANCE_MARKUP), rel=1e-3
    )


def test_the_bank_keeps_a_consistent_margin_at_every_age():
    """Loss ratio is 1/1.2 whatever the machine's age — that IS the markup."""
    for age in (0, 4, 12, 40):
        quote = equipment_insurance_quote(80.0, age)
        assert quote["loss_ratio"] == pytest.approx(1 / (1 + EQUIPMENT_INSURANCE_MARKUP), rel=1e-3)


def test_beyond_the_table_the_final_quarter_is_held():
    last = max(EQUIPMENT_FAILURE_PROB_BY_QUARTER)

    assert annual_failure_probability(1000) == pytest.approx(
        annual_failure_probability(last - 1)
    )


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

ITEM_ID = "farmer.tractor"


def _game_with_policy(banker_cash: float = 5_000.0, insured_value: float = 54.0):
    game = Game(GameConfig([]), FakeIOAdapter())
    farmer = Player(0, "Farm", [ROLES["Farmer"]], 100.0, is_human=False)
    banker = Player(1, "Bank", [ROLES["Banker"]], banker_cash, is_human=False)
    game.players = [farmer, banker]
    farmer.add_insurance_policy(InsurancePolicy(
        policy_id=1,
        policy_type="equipment",
        holder_player_id=farmer.player_id,
        banker_player_id=banker.player_id,
        premium_paid=12.72,
        purchased_tick=0,
        expires_at_tick=INSURANCE_DURATION_SEASONS,
        item_id=ITEM_ID,
        insured_value=insured_value,
    ))
    return game, farmer, banker


class _Item:
    name = "Tractor"
    cost = 60.0


def test_a_failure_pays_the_agreed_value_from_the_bank():
    game, farmer, banker = _game_with_policy()

    paid = game._settle_equipment_claim(farmer, ITEM_ID, _Item(), current_tick=1)

    assert paid == pytest.approx(54.0)
    assert farmer.dollops == pytest.approx(154.0)
    assert banker.dollops == pytest.approx(4_946.0)


def test_a_claim_closes_the_policy():
    """Total-loss settlement — the cover is spent, not reusable."""
    game, farmer, _ = _game_with_policy()

    game._settle_equipment_claim(farmer, ITEM_ID, _Item(), current_tick=1)
    assert not farmer.insurance_policies[0].active

    # A second failure on the same machine pays nothing more.
    assert game._settle_equipment_claim(farmer, ITEM_ID, _Item(), current_tick=1) == 0.0


def test_a_policy_on_a_different_machine_does_not_pay():
    game, farmer, _ = _game_with_policy()

    assert game._settle_equipment_claim(farmer, "farmer.harvester", _Item(), 1) == 0.0
    assert farmer.insurance_policies[0].active


def test_an_expired_policy_does_not_pay():
    game, farmer, _ = _game_with_policy()
    past_expiry = INSURANCE_DURATION_SEASONS + 4

    assert game._settle_equipment_claim(farmer, ITEM_ID, _Item(), past_expiry) == 0.0


def test_a_bank_short_of_cash_pays_what_it_has():
    game, farmer, banker = _game_with_policy(banker_cash=20.0)

    paid = game._settle_equipment_claim(farmer, ITEM_ID, _Item(), current_tick=1)

    assert paid == pytest.approx(20.0)
    assert banker.dollops == pytest.approx(0.0)
    assert farmer.dollops == pytest.approx(120.0)


def test_an_uninsured_island_claims_nothing():
    game = Game(GameConfig([]), FakeIOAdapter())
    farmer = Player(0, "Farm", [ROLES["Farmer"]], 100.0, is_human=False)
    game.players = [farmer]

    assert game._settle_equipment_claim(farmer, ITEM_ID, _Item(), 1) == 0.0
    assert farmer.dollops == pytest.approx(100.0)
