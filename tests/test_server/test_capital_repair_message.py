"""_handle_capital_repair surfaces the ACTUAL repair blocker (e.g. missing
Spares — repairs need capacity_units worth per the manufacturer-capacity-
scaling brief) instead of a generic "Dollops and Freight" message that
predates that requirement. Regression for the reported defect: Banker tries
to repair an underwriting_desk with plenty of cash and Freight but 0 Spares,
and got a misleading message pointing at the wrong resources."""
from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.capacity import find_item
from island_traders.models.resource import ResourceType
from island_traders.server.app import GameManager, GameRoom, LobbyPlayer


class _WS:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(json.loads(text))


def _bootstrap(role_names: list[str]):
    mgr = GameManager()
    room = GameRoom(
        room_id="repair-room", name="Repair Room", max_players=len(role_names),
        num_years=1, is_public=True, join_code="REP1",
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
            [PlayerSpec(name=f"Player{idx}", role_names=[role], is_human=True)
             for idx, role in enumerate(role_names)],
            num_years=1, starting_dollops=1000.0,
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


def _repair(mgr, room, lobby_id, item_id):
    ws = _WS()
    asyncio.run(mgr._handle_capital_repair(
        room.room_id, lobby_id, {"item_id": item_id}, ws
    ))
    return next(m for m in ws.sent if m.get("type") == "capital_repair_ack")


def test_repair_blocked_by_missing_spares_names_spares_not_dollops_freight():
    mgr, room, players = _bootstrap(["Banker", "Farmer"])
    banker = players[0]
    item = find_item(CAPITAL_CATALOGUE, "banker.underwriting_desk")
    assert item is not None

    banker.add_capital(item.item_id, 1, acquired_tick=-4)
    banker.capital_units[item.item_id][0].status = "failed"
    # Plenty of cash and Freight (matches the reported repro: 270 Dp, 4 Freight
    # both comfortably clear the repair fee/freight quote) but zero Spares —
    # the actual, sole blocker.  Clear the bootstrap-seeded Spares so the
    # missing-Spares path is the one under test.
    banker.inventory.amounts[ResourceType.SPARES] = 0
    assert banker.inventory.get(ResourceType.SPARES) == 0

    ack = _repair(mgr, room, "p0", item.item_id)

    assert ack["ok"] is False
    assert "Spares" in ack["message"]
    assert "Dollops and Freight" not in ack["message"]


def test_repair_succeeds_once_spares_are_stocked():
    mgr, room, players = _bootstrap(["Banker", "Farmer"])
    banker = players[0]
    item = find_item(CAPITAL_CATALOGUE, "banker.underwriting_desk")

    banker.add_capital(item.item_id, 1, acquired_tick=-4)
    banker.capital_units[item.item_id][0].status = "failed"
    banker.receive_resources(ResourceType.SPARES, item.capacity_units)
    banker.receive_resources(ResourceType.FREIGHT, 5)

    ack = _repair(mgr, room, "p0", item.item_id)

    assert ack["ok"] is True


def test_repair_blocked_by_rebuild_levy_still_names_levy():
    mgr, room, players = _bootstrap(["Banker", "Farmer"])
    banker = players[0]
    item = find_item(CAPITAL_CATALOGUE, "banker.underwriting_desk")

    banker.add_capital(item.item_id, 1, acquired_tick=-4)
    banker.capital_units[item.item_id][0].status = "failed"
    banker.receive_resources(ResourceType.SPARES, item.capacity_units)
    banker.receive_resources(ResourceType.FREIGHT, 5)
    banker._rebuild_levy_remaining = 10.0

    ack = _repair(mgr, room, "p0", item.item_id)

    assert ack["ok"] is False
    assert "levy" in ack["message"].lower()
