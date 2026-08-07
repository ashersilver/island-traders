"""The AI Bank's insurance book (#196 follow-up, toward #235).

Three things had to be true before the AI could sell equipment cover at all:

  * the per-line Actuary rule must apply to **both** AI paths — the leak in the
    buyer-initiated path let a one-Actuary Bank write two lines;
  * the AI Bank must be able to **grow** past its single seeded Actuary, or the
    rule strands it on one line forever;
  * it must actually offer the equipment line.
"""
from __future__ import annotations

import pytest

from island_traders.constants import (
    AI_BANKER_TARGET_ACTUARIES,
    INSURANCE_DURATION_SEASONS,
)
from island_traders.engine.ai import AI_REPLACEMENT_TRAINING_ROLES, AIStrategy
from island_traders.models.insurance import InsurancePolicy
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.role import ROLES


def _bank(actuaries: int = 1, dollops: float = 2_000.0) -> Player:
    bank = Player(9, "Bank", [ROLES["Banker"]], dollops, is_human=False)
    if actuaries:
        bank.workforce.add_workers(actuaries, profession=Profession.ACTUARY.value)
    bank.workforce.add_workers(1, profession=Profession.INSURANCE_ADJUSTER.value)
    return bank


def _client(dollops: float = 2_000.0) -> Player:
    return Player(0, "Mine", [ROLES["Miner"]], dollops, is_human=False)


def _write(holder: Player, bank: Player, policy_type: str) -> None:
    holder.add_insurance_policy(InsurancePolicy(
        policy_id=len(holder.insurance_policies) + 1,
        policy_type=policy_type,
        holder_player_id=holder.player_id,
        banker_player_id=bank.player_id,
        premium_paid=50.0,
        purchased_tick=0,
        expires_at_tick=INSURANCE_DURATION_SEASONS,
    ))


# ---------------------------------------------------------------------------
# The per-line rule reaches both AI paths
# ---------------------------------------------------------------------------

def test_one_actuary_cannot_open_a_second_line_however_it_is_initiated():
    """The buyer-initiated path used to bypass this entirely."""
    ai = AIStrategy()
    bank, client = _bank(actuaries=1), _client()
    _write(client, bank, "life")
    open_lines = ai._ai_open_lines(bank, [client, bank], 0, 0)

    assert open_lines == {"life"}
    assert ai._ai_can_write_line(bank, "life", open_lines)        # more of an open line
    assert not ai._ai_can_write_line(bank, "medical", open_lines)  # a new one
    assert not ai._ai_can_write_line(bank, "equipment", open_lines)


def test_capacity_scales_with_actuaries():
    ai = AIStrategy()
    bank, client = _bank(actuaries=3), _client()
    _write(client, bank, "life")
    _write(client, bank, "medical")
    open_lines = ai._ai_open_lines(bank, [client, bank], 0, 0)

    assert ai._ai_can_write_line(bank, "equipment", open_lines)


def test_another_banks_book_does_not_consume_your_capacity():
    ai = AIStrategy()
    ours, rival = _bank(actuaries=1), Player(8, "Rival", [ROLES["Banker"]], 500.0)
    client = _client()
    _write(client, rival, "life")

    assert ai._ai_open_lines(ours, [client, ours, rival], 0, 0) == set()


# ---------------------------------------------------------------------------
# The Bank can grow its actuarial capacity
# ---------------------------------------------------------------------------

def test_the_ai_bank_trains_replacements_at_all():
    """It was absent from the training roles, so a lost Actuary was never rehired."""
    assert "Banker" in AI_REPLACEMENT_TRAINING_ROLES


def test_the_ai_bank_wants_one_actuary_per_line():
    ai = AIStrategy()
    bank = _bank(actuaries=1)

    deficits = ai._ai_training_skill_deficits(bank, training_registry=None)

    assert deficits.get(Profession.ACTUARY.value) == AI_BANKER_TARGET_ACTUARIES - 1
    assert AI_BANKER_TARGET_ACTUARIES >= 3, "life, medical and equipment"


def test_a_fully_staffed_bank_wants_no_more_actuaries():
    ai = AIStrategy()
    bank = _bank(actuaries=AI_BANKER_TARGET_ACTUARIES)

    deficits = ai._ai_training_skill_deficits(bank, training_registry=None)

    assert Profession.ACTUARY.value not in deficits


# ---------------------------------------------------------------------------
# Equipment cover
# ---------------------------------------------------------------------------

def test_equipment_cover_needs_a_free_actuary():
    ai = AIStrategy()
    bank, client = _bank(actuaries=1), _client()
    client.add_capital("miner.excavator", 1)
    _write(client, bank, "life")
    open_lines = {"life"}

    actions = ai._ai_offer_equipment_cover(
        bank, client, open_lines, purchased_tick=0,
        expires_at=INSURANCE_DURATION_SEASONS, year=0, season_index=0,
    )

    assert actions == []
    assert not any(p.policy_type == "equipment" for p in client.insurance_policies)


def test_equipment_cover_is_written_on_the_most_valuable_machine():
    ai = AIStrategy()
    bank, client = _bank(actuaries=3), _client()
    client.add_capital("miner.crusher", 1)       # 50 Dp
    client.add_capital("miner.oil_rig", 1)       # 110 Dp — dearest
    open_lines: set[str] = set()

    actions = ai._ai_offer_equipment_cover(
        bank, client, open_lines, purchased_tick=0,
        expires_at=INSURANCE_DURATION_SEASONS, year=0, season_index=0,
    )

    assert actions, "a solvent client with uninsured plant should get cover"
    policy = next(p for p in client.insurance_policies if p.policy_type == "equipment")
    assert policy.item_id == "miner.oil_rig"
    assert policy.insured_value == pytest.approx(110.0 * 0.9)
    assert "equipment" in open_lines


def test_the_same_machine_is_not_insured_twice():
    ai = AIStrategy()
    bank, client = _bank(actuaries=3), _client()
    client.add_capital("miner.oil_rig", 1)

    first = ai._ai_offer_equipment_cover(
        bank, client, set(), 0, INSURANCE_DURATION_SEASONS, 0, 0
    )
    second = ai._ai_offer_equipment_cover(
        bank, client, {"equipment"}, 0, INSURANCE_DURATION_SEASONS, 0, 0
    )

    assert first and not second
    equipment = [p for p in client.insurance_policies if p.policy_type == "equipment"]
    assert len(equipment) == 1


def test_a_client_who_cannot_afford_the_premium_is_not_sold_cover():
    ai = AIStrategy()
    bank, client = _bank(actuaries=3), _client(dollops=1.0)
    client.add_capital("miner.oil_rig", 1)

    actions = ai._ai_offer_equipment_cover(
        bank, client, set(), 0, INSURANCE_DURATION_SEASONS, 0, 0
    )

    assert actions == []
    assert client.dollops == pytest.approx(1.0)
