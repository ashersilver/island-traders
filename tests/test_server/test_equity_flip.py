"""Web equity flip: treasury seed, bid->personal cash, secured setup loans.

See requirements/codex-tasks/capital-purchases-at-game-start-2026-06-16.md.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager, GameRoom, LobbyPlayer
from island_traders.models.equity import ISLAND_STARTING_CASH
from island_traders.models.loan import posted_funding_rates


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
    """Capital basket <= treasury: island capital pays, owner wallet is untouched."""
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
    assert mgr.rooms[rid].game.loan_ledger.all_loans() == []
    # Owns 60% of own island.
    assert p.cap_table.fraction("0") == 0.6


def test_big_basket_creates_secured_bank_loan_not_owner_loan():
    """Capital basket > treasury: the shortfall is a secured 3-year setup loan."""
    mgr = GameManager()
    rid = _room(mgr, capital=1500.0)
    # Bid 400; basket 900 > 500 treasury -> secured loan 400, treasury drains to 0.
    mgr._launch_game(
        rid,
        bids={"h1": 400.0},
        capital_spend={"h1": 900.0},
        capital_purchase_costs={"h1": {"farmer.tractor": 900.0}},
    )

    p = mgr.rooms[rid].game.players[0]
    shortfall = 900.0 - ISLAND_STARTING_CASH                      # 400
    assert p.dollops == 0.0
    assert p.personal_cash == round(1500.0 - 400.0, 1)            # owner wallet not drained
    assert p.shareholder_loans == {}
    loans = mgr.rooms[rid].game.loan_ledger.all_loans()
    assert len(loans) == 1
    loan = loans[0]
    assert loan.principal == shortfall
    assert loan.term_years == 3
    assert loan.interest_rate == posted_funding_rates(0, 0)[3]
    assert loan.secured is True
    assert loan.collateral_item_id == "farmer.tractor"


def test_secured_setup_loan_is_reported_without_owner_cash_leak():
    """Opening finance details surface as bank debt, not shareholder debt."""
    mgr = GameManager()
    rid = _room(mgr, capital=1500.0)
    mgr._launch_game(
        rid,
        bids={"h1": 400.0},
        capital_spend={"h1": 900.0},
        capital_purchase_costs={"h1": {"farmer.tractor": 900.0}},
    )
    state = mgr.get_game_state(rid, "h1")
    pdata = next(p for p in state["players"] if p["player_id"] == 0)
    assert pdata["shareholder_loan_owed"] == 0.0
    assert pdata["shareholder_loan_receivable"] == 0.0
    assert pdata["personal_cash"] == 1100.0
    assert pdata["loans_outstanding"] > 400.0
    loan = pdata["loans_detail"][0]
    assert loan["term_years"] == 3
    assert loan["secured"] is True
    assert loan["collateral_item_id"] == "farmer.tractor"
    assert pdata["net_worth"] >= pdata["personal_cash"]
