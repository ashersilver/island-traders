"""Server-side test: structured loans_detail + policies_detail in game_state.

Verifies the dashboard payload exposes enough per-loan and per-policy detail
for the UI to render the Loans and Insurance side panels (Issues #5, #6).
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager, GameRoom, LobbyPlayer
from island_traders.models.insurance import InsurancePolicy


def _bootstrap_game(mgr, *, with_policy=False, with_loan=False):
    """Build a minimal running game without going through auction/investing."""
    from island_traders.engine.game import Game, GameConfig, PlayerSpec
    from island_traders.cli.prompts import FakeIOAdapter
    room = GameRoom(
        room_id="r1", name="Test", max_players=2, num_years=1,
        is_public=True, join_code="GS0001", creator_id="host",
    )
    room.players.append(LobbyPlayer(player_id="host", name="Host",
                                    role_names=["Banker"]))
    room.players.append(LobbyPlayer(player_id="p2", name="Player2",
                                    role_names=["Farmer"]))
    room.status = "running"
    mgr.rooms["r1"] = room
    mgr._ws_connections["r1"] = {}
    mgr._loop = None

    config = GameConfig(
        player_specs=[
            PlayerSpec(name="Host",     role_names=["Banker"], is_human=True),
            PlayerSpec(name="Player2",  role_names=["Farmer"], is_human=True),
        ],
        num_years=1,
        starting_dollops=100.0,
    )
    game = Game(config, FakeIOAdapter())
    game.setup()  # build players + workforce
    room.game = game
    banker, farmer = game.players[0], game.players[1]
    room.lobby_to_engine_id = {
        "host": banker.player_id,
        "p2":   farmer.player_id,
    }
    if with_loan:
        # farmer borrows 100 from banker at 10%, 1-year term
        game.loan_ledger.create_loan(
            borrower_id=farmer.player_id, lender_id=banker.player_id,
            principal=100.0, interest_rate=0.10,
            issued_year=0, issued_season=0, term_years=1,
        )
    if with_policy:
        pol = InsurancePolicy(
            policy_id=1, policy_type="life",
            holder_player_id=farmer.player_id, banker_player_id=banker.player_id,
            premium_paid=40.0, purchased_tick=0, expires_at_tick=4,
        )
        farmer.add_insurance_policy(pol)
    return room, banker, farmer


def test_game_state_includes_structured_loans_detail():
    mgr = GameManager()
    room, banker, farmer = _bootstrap_game(mgr, with_loan=True)
    room.current_year_index = 0
    room.current_season_index = 2  # 2 seasons into the year

    state = mgr.get_game_state(room.room_id, "p2")
    assert state is not None
    farmer_data = next(p for p in state["players"] if p["lobby_player_id"] == "p2")
    loans = farmer_data["loans_detail"]
    assert len(loans) == 1
    loan = loans[0]
    assert loan["role"] == "borrower"
    assert loan["principal"] == 100.0
    assert loan["interest_rate"] == 0.10
    assert loan["repayment_amount"] == 110.0
    assert loan["term_years"] == 1
    assert loan["seasons_to_maturity"] == 2  # matures Y1 S0, now Y0 S2 → 2 seasons
    # Banker should see the same loan as lender
    banker_data = next(p for p in state["players"] if p["lobby_player_id"] == "host")
    bank_loans = banker_data["loans_detail"]
    assert any(l["role"] == "lender" and l["loan_id"] == loan["loan_id"]
               for l in bank_loans)


def test_game_state_includes_structured_policies_detail():
    mgr = GameManager()
    room, banker, farmer = _bootstrap_game(mgr, with_policy=True)
    room.current_year_index = 0
    room.current_season_index = 1  # 3 seasons remaining on a 4-season policy

    state = mgr.get_game_state(room.room_id, "p2")
    assert state is not None
    farmer_data = next(p for p in state["players"] if p["lobby_player_id"] == "p2")
    pols = farmer_data["policies_detail"]
    assert len(pols) == 1
    pol = pols[0]
    assert pol["policy_type"] == "life"
    assert pol["premium_paid"] == 40.0
    assert pol["seasons_remaining"] == 3
    assert pol["cancel_refund"] == 30.0  # 3/4 of 40
    # Existing back-compat field still present
    assert farmer_data["policies"]
    assert "Life Insurance" in farmer_data["policies"][0]


def test_game_state_loans_and_policies_empty_lists_when_none():
    mgr = GameManager()
    room, banker, farmer = _bootstrap_game(mgr)  # no loans, no policies
    state = mgr.get_game_state(room.room_id, "p2")
    assert state is not None
    for p in state["players"]:
        assert p["loans_detail"] == []
        assert p["policies_detail"] == []
