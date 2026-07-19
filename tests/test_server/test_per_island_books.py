from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.models.equity import ISLAND_STARTING_CASH
from island_traders.models.resource import ResourceType
from island_traders.server.app import GameManager, GameRoom, LobbyPlayer
from island_traders.server.ws_adapter import WebSocketIOAdapter


def _room(manager: GameManager, *, num_years: int = 0) -> GameRoom:
    room = GameRoom(
        room_id="books",
        name="Books",
        max_players=7,
        num_years=num_years,
        is_public=True,
        join_code="BOOKS1",
        starting_capital=1500.0,
    )
    manager.rooms[room.room_id] = room
    manager._loop = None
    return room


def test_multi_island_owner_gets_independent_island_books():
    manager = GameManager()
    room = _room(manager)
    room.players.append(
        LobbyPlayer(
            player_id="h1",
            name="Owner",
            role_names=["Farmer", "Miner"],
            is_human=True,
        )
    )

    assert manager._launch_game(room.room_id, bids={"h1": 300.0})
    room.game_thread.join(timeout=2)

    assert room.lobby_to_engine_id == {"h1": [0, 1]}
    farmer, miner = room.game.players
    assert [r.name for r in farmer.roles] == ["Farmer"]
    assert [r.name for r in miner.roles] == ["Miner"]
    # Multi-island owners get disambiguated island names.
    assert farmer.name == "Owner — Agriculture"
    assert miner.name == "Owner — Mining"
    assert farmer.dollops == ISLAND_STARTING_CASH
    assert miner.dollops == ISLAND_STARTING_CASH

    farmer.dollops -= 125.0
    farmer.receive_resources(ResourceType.FOOD, 9)

    assert miner.dollops == ISLAND_STARTING_CASH
    assert miner.inventory.get(ResourceType.FOOD) == 0


def test_whole_island_acquisition_preserves_acquired_books():
    manager = GameManager()
    room = _room(manager)
    room.players.extend([
        LobbyPlayer(player_id="buyer", name="Buyer", role_names=["Farmer"]),
        LobbyPlayer(
            player_id="seller",
            name="Seller",
            role_names=["Miner"],
            is_human=False,
        ),
    ])
    assert manager._launch_game(room.room_id, bids={"buyer": 100.0, "seller": 50.0})
    room.game_thread.join(timeout=2)

    acquired = room.game.players[1]
    acquired.dollops = 321.0
    ore_before = acquired.inventory.get(ResourceType.ORE)
    acquired.receive_resources(ResourceType.ORE, 17)
    acquired.shareholder_loans["seller"] = 44.0
    buyer_cash = room.game.owners["buyer"].personal_cash
    seller_cash = room.game.owners["seller"].personal_cash

    manager._transfer_island_ownership(
        room,
        island_engine_id=acquired.player_id,
        buyer_lobby_id="buyer",
        seller_lobby_id="seller",
        price=200.0,
    )

    assert room.lobby_to_engine_id["buyer"] == [0, 1]
    assert room.lobby_to_engine_id["seller"] == []
    assert acquired.owner_id == "buyer"
    assert acquired.dollops == 321.0
    assert acquired.inventory.get(ResourceType.ORE) == ore_before + 17
    assert acquired.shareholder_loans == {"seller": 44.0}
    assert room.game.owners["buyer"].personal_cash == buyer_cash - 200.0
    assert room.game.owners["seller"].personal_cash == seller_cash + 200.0


def test_owner_consolidated_position_uses_cash_stakes_and_receivables():
    manager = GameManager()
    room = _room(manager)
    room.players.append(
        LobbyPlayer(
            player_id="h1",
            name="Owner",
            role_names=["Farmer", "Miner"],
        )
    )
    assert manager._launch_game(room.room_id, bids={"h1": 0.0})
    room.game_thread.join(timeout=2)

    room.game.players[1].shareholder_loans["h1"] = 25.0
    state = manager.get_game_state(room.room_id, "h1")
    owner = state["owners"][0]
    prices = {
        str(player["player_id"]): player["share_price"]
        for player in state["players"]
    }
    expected = round(
        owner["personal_cash"]
        + sum(shares * prices[island_id] for island_id, shares in owner["holdings"].items())
        + 25.0,
        1,
    )

    # payload share_price is rounded to 2dp for display; the server computes
    # the consolidated position from unrounded prices, so allow the rounding
    # drift (≤0.005 per share held).
    tolerance = 0.005 * sum(owner["holdings"].values()) + 0.05
    assert owner["shareholder_loan_receivable"] == 25.0
    assert abs(owner["consolidated_position"] - expected) <= tolerance
    assert all(
        p["owner_consolidated_position"] == owner["consolidated_position"]
        for p in state["players"]
    )


def test_owner_ready_requires_all_owned_islands_ready():
    manager = GameManager()
    room = _room(manager, num_years=1)
    room.players.append(
        LobbyPlayer(
            player_id="h1",
            name="Owner",
            role_names=["Farmer", "Miner"],
        )
    )
    room.status = "running"
    room.lobby_to_engine_id = {"h1": [0, 1]}
    room.acting_engine_id = {"h1": 0}
    room.season_active_humans = {"h1"}
    room.season_phase = "action"
    room.io_adapter = WebSocketIOAdapter(
        "books",
        broadcast_fn=lambda msg: None,
        player_send_fns={0: lambda msg: None, 1: lambda msg: None},
    )
    room.io_adapter.begin_season()

    result = manager.submit_ready(room.room_id, "h1", True)

    assert result == {"ok": True, "ready": True}
    assert room.season_ready_engine_ids == {0, 1}
    assert room.season_ready_set == {"h1"}
    assert 0 in room.io_adapter._player_ready_flags
    assert 1 in room.io_adapter._player_ready_flags
