from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.order_book import ManufacturerOrderBook, compute_promise_dates
from island_traders.models.resource import ResourceType
from island_traders.server.app import GameManager, GameRoom, LobbyPlayer


class _WS:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(json.loads(text))


def test_order_book_add_reorder_remove_and_promise_dates():
    book = ManufacturerOrderBook()
    entries = [book.add(n, 7) for n in (10, 11, 12, 13, 14)]

    assert [e.queue_position for e in entries] == [0, 1, 2, 3, 4]

    book.reorder(7, [12, 10, 11, 13, 14])
    assert [e.negotiation_id for e in book.for_manufacturer(7)] == [12, 10, 11, 13, 14]

    with pytest.raises(ValueError):
        book.reorder(7, [12, 10])

    book.for_manufacturer(7)[0].locked = True
    with pytest.raises(ValueError):
        book.reorder(7, [10, 12, 11, 13, 14])

    book.remove(11)
    assert [e.queue_position for e in book.for_manufacturer(7)] == [0, 1, 2, 3]

    compute_promise_dates(book, 7, slots_per_season=2, current_year=0, current_season=3)
    promises = [
        (e.promised_year, e.promised_season)
        for e in book.for_manufacturer(7)
    ]
    assert promises == [(0, 3), (0, 3), (1, 0), (1, 0)]


def _bootstrap():
    mgr = GameManager()
    room = GameRoom(
        room_id="order-book-room",
        name="Order Book",
        max_players=2,
        num_years=1,
        is_public=True,
        join_code="OB1",
    )
    room.players = [
        LobbyPlayer(player_id="buyer", name="Buyer", role_names=["Transporter"]),
        LobbyPlayer(player_id="maker", name="Maker", role_names=["Manufacturer"]),
    ]
    room.status = "running"
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}
    game = Game(
        GameConfig([
            PlayerSpec("Buyer", ["Transporter"]),
            PlayerSpec("Maker", ["Manufacturer"]),
        ]),
        FakeIOAdapter(),
    )
    game.setup()
    buyer, maker = game.players
    buyer.dollops = 10000.0
    maker.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 3)
    room.game = game
    room.lobby_to_engine_id = {"buyer": buyer.player_id, "maker": maker.player_id}
    return mgr, room, buyer, maker


def _propose(mgr, room):
    ws = _WS()
    asyncio.run(mgr._handle_capital_order(
        room.room_id,
        "buyer",
        {"item_id": "transporter.cargo_plane"},
        ws,
    ))
    return next(m for m in ws.sent if m.get("type") == "capital_negotiation_ack")


def test_accepted_capital_order_appears_in_manufacturer_order_book():
    mgr, room, _buyer, maker = _bootstrap()
    ack = _propose(mgr, room)

    ws = _WS()
    asyncio.run(mgr._handle_capital_negotiation_respond(
        room.room_id,
        "maker",
        {"negotiation_id": ack["negotiation_id"], "action": "accept"},
        ws,
    ))

    rows = room.game.order_book.for_manufacturer(maker.player_id)
    assert len(rows) == 1
    assert rows[0].negotiation_id == ack["negotiation_id"]
    assert rows[0].queue_position == 0
    assert rows[0].locked is True

    state = mgr.get_game_state(room.room_id, "maker")
    maker_state = next(p for p in state["players"] if p["player_id"] == maker.player_id)
    assert maker_state["order_book"][0]["negotiation_id"] == ack["negotiation_id"]


def test_manufacturer_reorder_queue_updates_only_that_manufacturer():
    mgr, room, _buyer, maker = _bootstrap()
    first = _propose(mgr, room)["negotiation_id"]
    second = _propose(mgr, room)["negotiation_id"]
    room.game.order_book.add(first, maker.player_id)
    room.game.order_book.add(second, maker.player_id)

    ws = _WS()
    asyncio.run(mgr._handle_manufacturer_reorder_queue(
        room.room_id,
        "maker",
        {"negotiation_ids": [second, first]},
        ws,
    ))

    ack = next(m for m in ws.sent if m.get("type") == "manufacturer_reorder_ack")
    assert ack["ok"] is True
    assert [
        e.negotiation_id for e in room.game.order_book.for_manufacturer(maker.player_id)
    ] == [second, first]
