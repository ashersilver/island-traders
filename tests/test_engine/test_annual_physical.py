"""The annual physical halves insurance premiums (#19, third mechanic).

> "If employees undergo a physical their medical and life insurance premiums
> are halved. Employees covered by insurance need a physical once a year on
> the anniversary of the insurance to maintain reduced premiums."

The physical is a "Health Certificate" — a Lab Test from the Medical &
Laboratory Island — consumed when the policy is written. Policies run one
year, so renewal *is* the anniversary: a buyer who cannot produce a
certificate at renewal pays full rate again, which is the reversion the issue
describes without separate anniversary bookkeeping.

This mechanic was blocked until Lab Tests shipped in `0.1.6-dev.2026-08-07.7`.
"""
from __future__ import annotations

import pytest

from island_traders.constants import (
    INSURANCE_BASE_PREMIUM,
    PHYSICAL_PREMIUM_DISCOUNT,
)
from island_traders.models.insurance import (
    HEALTH_CERTIFICATE_TESTS,
    apply_physical_discount,
)
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def _island(lab_tests: int = 0) -> Player:
    player = Player(0, "Mine", [ROLES["Miner"]], 1_000.0, is_human=False)
    if lab_tests:
        player.receive_resources(ResourceType.LABORATORY_TESTS, lab_tests)
    return player


def test_a_certificate_halves_the_premium():
    island = _island(lab_tests=1)
    base = INSURANCE_BASE_PREMIUM["life"]

    premium, certified = apply_physical_discount(island, base)

    assert certified
    assert premium == pytest.approx(base * (1 - PHYSICAL_PREMIUM_DISCOUNT))
    assert premium < base


def test_the_certificate_is_consumed():
    island = _island(lab_tests=3)

    apply_physical_discount(island, 50.0)

    assert island.inventory.get(ResourceType.LABORATORY_TESTS) == 3 - HEALTH_CERTIFICATE_TESTS


def test_no_certificate_means_full_price():
    island = _island(lab_tests=0)

    premium, certified = apply_physical_discount(island, 50.0)

    assert not certified
    assert premium == 50.0


def test_nothing_is_consumed_when_the_island_cannot_pay_for_a_physical():
    """A near-miss must not silently eat the island's last test."""
    island = _island(lab_tests=0)
    island.receive_resources(ResourceType.LABORATORY_TESTS, 0)

    apply_physical_discount(island, 50.0)

    assert island.inventory.get(ResourceType.LABORATORY_TESTS) == 0


def test_each_policy_needs_its_own_certificate():
    """Renewal is the anniversary: cover lapses back to full rate without one."""
    island = _island(lab_tests=1)

    first, first_certified = apply_physical_discount(island, 50.0)
    second, second_certified = apply_physical_discount(island, 50.0)

    assert first_certified and first == 25.0
    assert not second_certified and second == 50.0, "the discount must not persist for free"


def test_a_zero_premium_is_left_alone():
    island = _island(lab_tests=1)

    premium, certified = apply_physical_discount(island, 0.0)

    assert premium == 0.0
    assert not certified
    assert island.inventory.get(ResourceType.LABORATORY_TESTS) == 1, "no test wasted"


def test_every_premium_path_offers_the_discount():
    """Two human paths and two AI paths mint policies; all must honour it."""
    import inspect

    from island_traders.engine.ai import AIStrategy
    from island_traders.engine.turn import TurnManager

    for owner, names in (
        (TurnManager, ("_action_sell_insurance", "_action_buy_insurance")),
        (AIStrategy, ("_ai_offer_insurance", "_ai_buy_workplace_insurance")),
    ):
        for name in names:
            source = inspect.getsource(getattr(owner, name))
            assert "apply_physical_discount" in source, f"{name} ignores the physical"
