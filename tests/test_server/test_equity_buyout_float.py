"""Equity Phase 3: issue unissued shares.

See requirements/equity-phase3-buyout-float-2026-06-02.md.
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager, GameRoom, LobbyPlayer
from island_traders.models.equity import (
    AUCTIONED_SHARES, share_price, fair_value,
)
from island_traders.constants_capacity import CAPITAL_CATALOGUE


class _WS:
    """Minimal async websocket stub capturing sent JSON."""
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        import json
        self.sent.append(json.loads(text))


def _running_room(mgr: GameManager) -> str:
    room = GameRoom(
        room_id="testroom", name="Test", max_players=7, num_years=1,
        is_public=True, join_code="ZZZZZZ", starting_capital=1500.0,
    )
    room.players.append(LobbyPlayer(player_id="h1", name="Solo"))
    room.players[0].role_names = ["Farmer"]
    mgr.rooms["testroom"] = room
    mgr._loop = None
    mgr._launch_game("testroom", bids={"h1": 400.0}, capital_spend={"h1": 0.0})
    return "testroom"


def _price(mgr, room_id):
    room = mgr.rooms[room_id]
    p = room.game.players[0]
    prices = room.game.market.current_prices()
    from island_traders.constants import SEASONS
    liq = p.total_wealth(prices, room.game.loan_ledger, CAPITAL_CATALOGUE, 0)
    return share_price(fair_value(liq, p.wealth_history))


def test_owner_buys_some_float_shares():
    mgr = GameManager()
    rid = _running_room(mgr)
    p = mgr.rooms[rid].game.players[0]
    cash0 = p.personal_cash
    treasury0 = p.dollops
    money0 = round(p.personal_cash + p.dollops, 1)
    price = _price(mgr, rid)
    ws = _WS()

    asyncio.run(mgr._handle_buy_out_float(rid, "h1", {"shares": 10}, ws))

    assert p.cap_table.held_by("0") == AUCTIONED_SHARES + 10
    assert p.cap_table.unissued() == (100 - AUCTIONED_SHARES) - 10
    assert sum(p.cap_table.shares.values()) == 100
    assert p.holdings["0"] == AUCTIONED_SHARES + 10
    cost = round(10 * price, 1)
    assert p.personal_cash == round(cash0 - cost, 1)
    assert (p.dollops - treasury0) == pytest.approx(cash0 - p.personal_cash, abs=0.1)
    assert round(p.personal_cash + p.dollops, 1) == money0


def test_buy_is_clamped_to_available_float():
    mgr = GameManager()
    rid = _running_room(mgr)
    p = mgr.rooms[rid].game.players[0]
    ws = _WS()

    # Ask for way more than the 40 unissued shares -> clamped to available.
    asyncio.run(mgr._handle_buy_out_float(rid, "h1", {"shares": 999}, ws))

    assert p.cap_table.held_by("0") == 100
    assert p.cap_table.unissued() == 0


def test_cannot_buy_without_enough_cash():
    mgr = GameManager()
    rid = _running_room(mgr)
    p = mgr.rooms[rid].game.players[0]
    p.personal_cash = 0.0
    ws = _WS()

    asyncio.run(mgr._handle_buy_out_float(rid, "h1", {"shares": 5}, ws))

    # Nothing bought; an error was returned.
    assert p.cap_table.unissued() == 100 - AUCTIONED_SHARES
    assert any(m.get("type") == "error" for m in ws.sent)


def test_primary_issuance_converts_personal_cash_to_island_treasury():
    mgr = GameManager()
    rid = _running_room(mgr)
    state0 = mgr.get_game_state(rid, "h1")
    pdata0 = next(p for p in state0["players"] if p["player_id"] == 0)
    nw0 = next(p for p in state0["players"] if p["player_id"] == 0)["net_worth"]
    ws = _WS()

    asyncio.run(mgr._handle_buy_out_float(rid, "h1", {"shares": 10}, ws))

    state1 = mgr.get_game_state(rid, "h1")
    pdata1 = next(p for p in state1["players"] if p["player_id"] == 0)
    assert pdata1["treasury"] > pdata0["treasury"]
    assert pdata1["personal_cash"] < pdata0["personal_cash"]
    assert pdata1["net_worth"] >= nw0


def test_payload_reports_unissued_shares_not_public_float():
    mgr = GameManager()
    rid = _running_room(mgr)

    state = mgr.get_game_state(rid, "h1")
    pdata = next(p for p in state["players"] if p["player_id"] == 0)

    assert pdata["unissued_pct"] == 40.0
    assert pdata["unissued_shares"] == 40
    assert "public_float_pct" not in pdata
    assert "public_float_shares" not in pdata
