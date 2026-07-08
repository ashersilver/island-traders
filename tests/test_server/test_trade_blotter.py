"""Trade Blotter (#210) server wiring: order_batch layering + my_fills tape."""
from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.resource import ResourceType
from island_traders.server.app import GameManager, GameRoom, LobbyPlayer


class _WS:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(json.loads(text))


def _bootstrap_game(role_names: list[str]):
    mgr = GameManager()
    room = GameRoom(
        room_id="blotter-room",
        name="Blotter Room",
        max_players=len(role_names),
        num_years=1,
        is_public=True,
        join_code="BLOT01",
    )
    room.players = [
        LobbyPlayer(player_id=f"p{idx}", name=f"Player{idx}", role_names=[role])
        for idx, role in enumerate(role_names)
    ]
    room.status = "running"
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}
    game = Game(
        GameConfig(
            [
                PlayerSpec(name=f"Player{idx}", role_names=[role], is_human=True)
                for idx, role in enumerate(role_names)
            ],
            num_years=1,
            starting_dollops=100.0,
        ),
        FakeIOAdapter(),
    )
    game.setup()
    room.game = game
    room.lobby_to_engine_id = {
        lobby.player_id: player.player_id
        for lobby, player in zip(room.players, game.players)
    }
    return mgr, room, game.players


def test_order_batch_layers_resting_bids_with_replace_false():
    mgr, room, _players = _bootstrap_game(["Farmer", "Miner"])

    asyncio.run(mgr._handle_order_batch(
        room.room_id,
        "p0",
        {
            "batch_ref": "layer",
            "orders": [
                {"side": "buy", "resource": "Oil", "quantity": 2,
                 "limit_price": 10.0, "replace": False},
                {"side": "buy", "resource": "Oil", "quantity": 3,
                 "limit_price": 9.0, "replace": False},
            ],
        },
        _WS(),
    ))

    live = room.game.market.available_bids(ResourceType.OIL)
    assert sorted(b.remaining for b in live) == [2, 3]


def test_order_batch_supersedes_resting_bids_by_default():
    mgr, room, _players = _bootstrap_game(["Farmer", "Miner"])

    asyncio.run(mgr._handle_order_batch(
        room.room_id,
        "p0",
        {
            "batch_ref": "supersede",
            "orders": [
                {"side": "buy", "resource": "Oil", "quantity": 2, "limit_price": 10.0},
                {"side": "buy", "resource": "Oil", "quantity": 3, "limit_price": 9.0},
            ],
        },
        _WS(),
    ))

    live = room.game.market.available_bids(ResourceType.OIL)
    assert [b.remaining for b in live] == [3]


def test_game_state_exposes_my_fills_per_viewer():
    mgr, room, players = _bootstrap_game(["Farmer", "Miner"])
    buyer, seller = players
    seller.receive_resources(ResourceType.OIL, 2)
    room.game.market.post_offer(seller, ResourceType.OIL, 10.0, 2)

    # p0 (Farmer) buys immediately from p1's (Miner) resting ask.
    asyncio.run(mgr._handle_order_batch(
        room.room_id,
        "p0",
        {"batch_ref": "fill", "orders": [
            {"side": "buy", "resource": "Oil", "quantity": 2},
        ]},
        _WS(),
    ))

    buyer_state = mgr.get_game_state(room.room_id, "p0")
    seller_state = mgr.get_game_state(room.room_id, "p1")
    assert "my_fills" in buyer_state
    assert buyer_state["my_fills"][0]["side"] == "buy"
    assert buyer_state["my_fills"][0]["counterparty"] == "Player1"
    assert seller_state["my_fills"][0]["side"] == "sell"
    assert seller_state["my_fills"][0]["counterparty"] == "Player0"
