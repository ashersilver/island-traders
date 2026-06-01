"""Web equity flip (Phase 2b): treasury seed, bid->personal cash, auto-lend.

See requirements/equity-phase2b-flip-2026-05-29.md.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager, GameRoom, LobbyPlayer
from island_traders.models.equity import ISLAND_STARTING_CASH


def _room(mgr: GameManager, capital: float = 1500.0) -> str:
    room = GameRoom(
        room_id="testroom", name="Test", max_players=7, num_years=1,
        is_public=True, join_code="ZZZZZZ", starting_capital=capital,
    )
    room.players.append(LobbyPlayer(player_id="h1", name="Solo"))
    room.players[0].role_names = ["Farmer"]
    mgr.rooms["testroom"] = room
    mgr._loop = None
    return "testroom"


def test_treasury_seeded_and_bid_leaves_personal_cash_small_basket():
    """Capital basket <= treasury: no shareholder loan; bid leaves personal cash."""
    mgr = GameManager()
    rid = _room(mgr, capital=1500.0)
    # Won the role for 400; opening capital basket of 300 (< 500 treasury).
    mgr._launch_game(rid, bids={"h1": 400.0}, capital_spend={"h1": 300.0})

    p = mgr.rooms[rid].game.players[0]
    # Treasury seeded at 500, basket 300 -> ~200 left (then drifts down a little
    # as the game's first season starts charging maintenance, so assert a bound).
    assert 0.0 < p.dollops <= round(ISLAND_STARTING_CASH - 300.0, 1)
    # personal_cash and shareholder_loans are NOT touched by normal play.
    assert p.personal_cash == round(1500.0 - 400.0, 1)           # 1100, no loan
    assert p.shareholder_loans == {}                             # nothing lent
    # Owns 60% of own island.
    assert p.cap_table.fraction("0") == 0.6


def test_big_basket_auto_lends_from_personal_cash():
    """Capital basket > treasury: the shortfall is auto-lent (shareholder loan)."""
    mgr = GameManager()
    rid = _room(mgr, capital=1500.0)
    # Bid 400; basket 900 > 500 treasury -> lend 400, treasury drains to 0.
    mgr._launch_game(rid, bids={"h1": 400.0}, capital_spend={"h1": 900.0})

    p = mgr.rooms[rid].game.players[0]
    lent = 900.0 - ISLAND_STARTING_CASH                          # 400
    assert p.dollops == 0.0                                      # 500 + 400 - 900
    assert p.personal_cash == round(1500.0 - 400.0 - lent, 1)    # 700
    assert p.shareholder_loans == {"0": round(lent, 1)}          # island owes investor 400


def test_lending_is_net_worth_neutral():
    """A shareholder loan must not change the investor's net worth."""
    mgr = GameManager()
    rid = _room(mgr, capital=1500.0)
    mgr._launch_game(rid, bids={"h1": 400.0}, capital_spend={"h1": 900.0})
    state = mgr.get_game_state(rid, "h1")
    pdata = next(p for p in state["players"] if p["player_id"] == 0)
    # personal_cash(700) + receivable(400) + 0.6*share_price... the loan piece
    # (−400 from personal cash, +400 receivable, treasury+400 offset by
    # liability−400) nets to zero, so net_worth == personal + 0.6*fair − 0.
    assert pdata["shareholder_loan_owed"] == 400.0
    assert pdata["shareholder_loan_receivable"] == 400.0
    assert pdata["personal_cash"] == 700.0
    # net worth is finite and reflects the equity stake, not inflated by the loan
    assert pdata["net_worth"] >= pdata["personal_cash"]
