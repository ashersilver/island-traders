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
        room_id="xfer-room",
        name="Transfer Room",
        max_players=3,
        num_years=1,
        is_public=True,
        join_code="XFER01",
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


def _transfer(mgr, room, msg, lobby_id="owner"):
    ws = _WS()
    asyncio.run(mgr._handle_island_transfer(room.room_id, lobby_id, msg, ws))
    return ws.sent[0]


def test_transfer_moves_goods_cash_and_freight():
    mgr, room, players = _bootstrap()
    farm, mine, _ = players
    farm.receive_resources(ResourceType.FOOD, 10)
    farm.receive_resources(ResourceType.FREIGHT, 2)
    price = room.game.market.current_price(ResourceType.FOOD)

    food_before = (farm.inventory.get(ResourceType.FOOD),
                   mine.inventory.get(ResourceType.FOOD))
    cash_before = (farm.dollops, mine.dollops)
    freight_before = farm.inventory.get(ResourceType.FREIGHT)

    ack = _transfer(mgr, room, {
        "island_id": 0, "to_island_id": 1,
        "resource": "Food", "quantity": 4,
    })

    assert ack["ok"] is True
    deemed = round(price * 4, 2)
    assert ack["deemed_cost"] == deemed
    assert farm.inventory.get(ResourceType.FOOD) == food_before[0] - 4
    assert mine.inventory.get(ResourceType.FOOD) == food_before[1] + 4
    assert farm.inventory.get(ResourceType.FREIGHT) == freight_before - 1
    assert farm.dollops == pytest.approx(cash_before[0] + deemed)
    assert mine.dollops == pytest.approx(cash_before[1] - deemed)


def test_transfer_rejects_destination_not_owned():
    mgr, room, players = _bootstrap()
    farm = players[0]
    farm.receive_resources(ResourceType.FOOD, 5)
    farm.receive_resources(ResourceType.FREIGHT, 1)

    ack = _transfer(mgr, room, {
        "island_id": 0, "to_island_id": 2,
        "resource": "Food", "quantity": 1,
    })

    assert ack["ok"] is False
    assert "own" in ack["message"]


def test_transfer_rejects_without_freight():
    mgr, room, players = _bootstrap()
    farm = players[0]
    farm.receive_resources(ResourceType.FOOD, 5)
    freight = farm.inventory.get(ResourceType.FREIGHT)
    if freight:
        farm.give_resources(ResourceType.FREIGHT, freight)

    ack = _transfer(mgr, room, {
        "island_id": 0, "to_island_id": 1,
        "resource": "Food", "quantity": 1,
    })

    assert ack["ok"] is False
    assert "Freight" in ack["message"]


def test_transfer_rejects_insufficient_stock_and_funds():
    mgr, room, players = _bootstrap()
    farm, mine, _ = players
    farm.receive_resources(ResourceType.FREIGHT, 1)

    stock = farm.inventory.get(ResourceType.PRODUCE)
    ack = _transfer(mgr, room, {
        "island_id": 0, "to_island_id": 1,
        "resource": "Produce", "quantity": stock + 99,
    })
    assert ack["ok"] is False

    farm.receive_resources(ResourceType.FOOD, 10)
    mine.dollops = 0.0
    ack = _transfer(mgr, room, {
        "island_id": 0, "to_island_id": 1,
        "resource": "Food", "quantity": 10,
    })
    assert ack["ok"] is False
    assert "afford" in ack["message"]


def test_transferring_freight_itself_needs_extra_unit():
    mgr, room, players = _bootstrap()
    farm, mine, _ = players
    held = farm.inventory.get(ResourceType.FREIGHT)
    if held:
        farm.give_resources(ResourceType.FREIGHT, held)
    farm.receive_resources(ResourceType.FREIGHT, 3)

    ack = _transfer(mgr, room, {
        "island_id": 0, "to_island_id": 1,
        "resource": "Freight", "quantity": 3,
    })
    assert ack["ok"] is False

    ack = _transfer(mgr, room, {
        "island_id": 0, "to_island_id": 1,
        "resource": "Freight", "quantity": 2,
    })
    assert ack["ok"] is True
    assert farm.inventory.get(ResourceType.FREIGHT) == 0
