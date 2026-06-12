"""Server-side test: inventory visibility + is_ai flag in game_state.

UI v2 phase 1 (#114): the Trade Finder needs every seat's inventory —
including AI islands — and an `is_ai` flag so the UI can badge them.
Previously inventory was omitted from payloads built for AI requesters.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager, GameRoom, LobbyPlayer
from island_traders.models.resource import ResourceType


def _bootstrap_game(mgr):
    """Minimal running game: one human seat + one AI seat."""
    from island_traders.engine.game import Game, GameConfig, PlayerSpec
    from island_traders.cli.prompts import FakeIOAdapter
    room = GameRoom(
        room_id="r1", name="Test", max_players=2, num_years=1,
        is_public=True, join_code="INV001", creator_id="host",
    )
    room.players.append(LobbyPlayer(player_id="host", name="Host",
                                    role_names=["Farmer"]))
    room.players.append(LobbyPlayer(player_id="ai1", name="Robo",
                                    role_names=["Miner"], is_human=False))
    room.status = "running"
    mgr.rooms["r1"] = room
    mgr._ws_connections["r1"] = {}
    mgr._loop = None

    config = GameConfig(
        player_specs=[
            PlayerSpec(name="Host", role_names=["Farmer"], is_human=True),
            PlayerSpec(name="Robo", role_names=["Miner"], is_human=False),
        ],
        num_years=1,
        starting_dollops=100.0,
    )
    game = Game(config, FakeIOAdapter())
    game.setup()
    room.game = game
    farmer, miner = game.players[0], game.players[1]
    room.lobby_to_engine_id = {"host": farmer.player_id, "ai1": miner.player_id}
    # ResourceBundle is immutable — add() returns a new bundle.
    farmer.inventory = farmer.inventory.add(ResourceType.FOOD, 7)
    miner.inventory = miner.inventory.add(ResourceType.ORE, 11)
    return room, farmer, miner


def test_all_seats_expose_inventory_and_is_ai():
    mgr = GameManager()
    room, farmer, miner = _bootstrap_game(mgr)

    state = mgr.get_game_state(room.room_id, "host")
    assert state is not None
    human_data = next(p for p in state["players"] if p["lobby_player_id"] == "host")
    ai_data = next(p for p in state["players"] if p["lobby_player_id"] == "ai1")

    assert human_data["is_ai"] is False
    assert ai_data["is_ai"] is True
    assert human_data["inventory"]["Food"] == farmer.inventory.get(ResourceType.FOOD)
    # AI islands are discoverable trading partners: inventory included.
    assert ai_data["inventory"]["Ore"] == miner.inventory.get(ResourceType.ORE)
    assert ai_data["inventory"]["Ore"] >= 11


def test_ai_requester_also_receives_inventories():
    mgr = GameManager()
    room, farmer, miner = _bootstrap_game(mgr)

    state = mgr.get_game_state(room.room_id, "ai1")
    assert state is not None
    for pd in state["players"]:
        assert "inventory" in pd
