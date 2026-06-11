from __future__ import annotations

import pytest

from island_traders.models.equity import (
    AUCTIONED_SHARES,
    MIN_SHARE_PRICE,
    TOTAL_SHARES,
    UNISSUED_HOLDER,
    CapTable,
    fair_value,
    liquidation_value,
    share_price,
)


def test_new_with_majority_seats_owner_and_unissued_shares():
    cap_table = CapTable.new_with_majority("player-1")

    assert cap_table.held_by("player-1") == AUCTIONED_SHARES
    assert cap_table.unissued() == TOTAL_SHARES - AUCTIONED_SHARES
    assert sum(cap_table.shares.values()) == TOTAL_SHARES


def test_fraction_held_by_and_unissued_handle_absent_holders():
    cap_table = CapTable.new_with_majority("player-1")

    assert cap_table.fraction("player-1") == 0.6
    assert cap_table.fraction("missing") == 0.0
    assert cap_table.held_by("missing") == 0
    assert cap_table.unissued() == 40


def test_transfer_moves_shares_drops_zeroed_holders_and_preserves_total():
    cap_table = CapTable.new_with_majority("seller")

    cap_table.transfer(UNISSUED_HOLDER, "buyer", 40)

    assert cap_table.held_by(UNISSUED_HOLDER) == 0
    assert UNISSUED_HOLDER not in cap_table.shares
    assert cap_table.held_by("buyer") == 40
    assert cap_table.held_by("seller") == 60
    assert sum(cap_table.shares.values()) == TOTAL_SHARES
    assert cap_table.player_holders() == {"seller": 60, "buyer": 40}


def test_transfer_raises_when_holder_lacks_shares():
    cap_table = CapTable.new_with_majority("seller")

    with pytest.raises(ValueError):
        cap_table.transfer(UNISSUED_HOLDER, "buyer", 41)

    assert sum(cap_table.shares.values()) == TOTAL_SHARES


def test_transfer_rejects_non_positive_share_counts():
    cap_table = CapTable.new_with_majority("seller")

    with pytest.raises(ValueError):
        cap_table.transfer("seller", "buyer", 0)


def test_to_dict_and_from_dict_round_trip_cap_table():
    cap_table = CapTable.new_with_majority("seller")
    cap_table.transfer(UNISSUED_HOLDER, "buyer", 5)

    rebuilt = CapTable.from_dict(cap_table.to_dict())

    assert rebuilt.shares == cap_table.shares


def test_from_dict_migrates_legacy_public_holder_to_unissued():
    rebuilt = CapTable.from_dict({"seller": 60, "public": 40})

    assert rebuilt.held_by("seller") == 60
    assert rebuilt.unissued() == 40
    assert "public" not in rebuilt.shares


def test_cap_table_rejects_invalid_totals_and_counts():
    with pytest.raises(ValueError):
        CapTable({"owner": 99})
    with pytest.raises(ValueError):
        CapTable({"owner": 100, "ghost": 0})


def test_liquidation_value_arithmetic_including_insolvent_case():
    assert liquidation_value(500.0, 120.0, 300.0, 100.0) == 820.0
    assert liquidation_value(50.0, 25.0, 0.0, 100.0) == -25.0


def test_fair_value_thin_history_falls_back_to_liquidation_value():
    assert fair_value(250.0, []) == 250.0
    assert fair_value(250.0, [240.0]) == 250.0


def test_fair_value_steady_growth_applies_premium():
    value = fair_value(500.0, [100.0, 120.0, 140.0, 160.0])

    assert value > 500.0
    assert value == pytest.approx(560.0)


def test_fair_value_same_growth_with_higher_volatility_is_discounted():
    steady = fair_value(500.0, [100.0, 120.0, 140.0, 160.0])
    volatile = fair_value(500.0, [100.0, 150.0, 110.0, 160.0])

    assert volatile < steady
    assert volatile > 500.0


def test_fair_value_negative_growth_falls_back_to_liquidation_value():
    assert fair_value(500.0, [160.0, 140.0, 120.0, 100.0]) == 500.0


def test_share_price_divides_by_total_shares_and_applies_floor():
    assert share_price(250.0) == 2.5
    assert share_price(0.0) == MIN_SHARE_PRICE
    assert share_price(-100.0) == MIN_SHARE_PRICE
