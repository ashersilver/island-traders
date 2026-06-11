"""Phase-1 additive equity fields on Player (personal_cash, holdings, net_worth).

These are additive and default to empty/zero, so existing games are unchanged.
The cap-table / valuation math itself lives in equity.py (Codex-owned, separately
tested); here we only pin the Player-side helper.
"""
from __future__ import annotations

from island_traders.models.equity import CapTable
from island_traders.models.player import Player
from island_traders.models.role import ROLES


def _player(**kw) -> Player:
    return Player(0, "P", [ROLES["Farmer"]], dollops=100.0, is_human=True, **kw)


def test_defaults_are_inert():
    p = _player()
    assert p.personal_cash == 0.0
    assert p.holdings == {}
    assert p.cap_table is None
    # No holdings -> net worth is just personal cash.
    assert p.net_worth({}) == 0.0


def test_net_worth_sums_cash_plus_holdings_at_share_price():
    p = _player(personal_cash=1100.0, holdings={"0": 60, "3": 10})
    prices = {"0": 5.0, "3": 2.0}
    # 1100 + 60*5 + 10*2 = 1100 + 300 + 20
    assert p.net_worth(prices) == 1420.0


def test_net_worth_ignores_islands_without_a_price():
    p = _player(personal_cash=500.0, holdings={"9": 60})
    assert p.net_worth({}) == 500.0  # unknown island -> 0 contribution


def test_cap_table_field_round_trips_via_helper():
    p = _player(cap_table=CapTable.new_with_majority("0"))
    assert p.cap_table.held_by("0") == 60
    assert p.cap_table.public_float() == 40
