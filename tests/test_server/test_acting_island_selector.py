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


def _bootstrap():
    mgr = GameManager()
    room = GameRoom(
        room_id="acting-room",
        name="Acting Room",
        max_players=3,
        num_years=1,
        is_public=True,
        join_code="ACTING",
    )
    room.players = [
        LobbyPlayer(player_id="owner", name="Owner", role_names=["Farmer", "Miner"]),
        LobbyPlayer(player_id="other", name="Other", role_names=["Transporter"]),
    ]
    room.status = "running"
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}
    game = Game(
        GameConfig(
            [
                PlayerSpec(name="FarmCo", role_names=["Farmer"], is_human=True),
                PlayerSpec(name="MineCo", role_names=["Miner"], is_human=True),
                PlayerSpec(name="ShipCo", role_names=["Transporter"], is_human=True),
            ],
            num_years=1,
            starting_dollops=100.0,
        ),
        FakeIOAdapter(),
    )
    game.setup()
    room.game = game
    room.lobby_to_engine_id = {"owner": [0, 1], "other": [2]}
    room.acting_engine_id = {"owner": 0, "other": 2}
    return mgr, room, game.players


def _order_batch(mgr, room, msg):
    ws = _WS()
    asyncio.run(mgr._handle_order_batch(room.room_id, "owner", msg, ws))
    return ws.sent[0]


def test_action_rejects_island_id_not_owned_by_connection():
    mgr, room, _players = _bootstrap()

    result = _order_batch(mgr, room, {
        "batch_ref": "bad-island",
        "island_id": 2,
        "orders": [],
    })

    assert result["type"] == "order_batch_result"
    assert result["error"] == "Island 2 is not owned by this connection."


def test_action_with_owned_island_id_routes_to_that_engine_player():
    mgr, room, players = _bootstrap()
    miner = players[1]
    miner.receive_resources(ResourceType.OIL, 3)

    result = _order_batch(mgr, room, {
        "batch_ref": "owned-island",
        "island_id": miner.player_id,
        "orders": [
            {"side": "sell", "resource": "Oil", "quantity": 2, "limit_price": 11.0},
        ],
    })

    assert "error" not in result
    offers = room.game.market.available_offers(ResourceType.OIL)
    assert len(offers) == 1
    assert offers[0].seller_id == miner.player_id
    assert room.acting_engine_id["owner"] == miner.player_id


def test_action_without_island_id_uses_acting_default_for_back_compat():
    mgr, room, players = _bootstrap()
    farmer = players[0]
    farmer.receive_resources(ResourceType.OIL, 3)

    result = _order_batch(mgr, room, {
        "batch_ref": "default-island",
        "orders": [
            {"side": "sell", "resource": "Oil", "quantity": 1, "limit_price": 12.0},
        ],
    })

    assert "error" not in result
    offers = room.game.market.available_offers(ResourceType.OIL)
    assert len(offers) == 1
    assert offers[0].seller_id == farmer.player_id
