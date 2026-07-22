from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.capacity import find_item
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
    cargo_plane = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    maker.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, cargo_plane.capacity_units)
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


def test_delivered_order_leaves_the_book():
    """Landmine 1: order_book.remove() had no callers, so delivered entries
    piled up locked at the head of every queue and permanently blocked both
    manual reordering and any price-based priority."""
    mgr, room, buyer, maker = _bootstrap()
    ack = _propose(mgr, room)
    ws = _WS()
    asyncio.run(mgr._handle_capital_negotiation_respond(
        room.room_id, "maker",
        {"negotiation_id": ack["negotiation_id"], "action": "accept"}, ws,
    ))
    assert len(room.game.order_book.for_manufacturer(maker.player_id)) == 1

    # cargo_plane has delivery_seasons > 0, so it rides capital_in_transit.
    plane = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    assert plane.delivery_seasons > 0
    assert buyer.capital_in_transit, "expected the unit to be in transit"

    buyer.deliver_in_transit(
        current_tick=999, order_book=room.game.order_book,
    )

    assert not buyer.capital_in_transit
    assert room.game.order_book.for_manufacturer(maker.player_id) == [], \
        "a delivered order must leave the manufacturer's book"


def test_backorder_drain_never_double_spends_manufactured_units():
    """Landmine 2: several queued orders can each pass an independent stock
    check against the same units. Only the ordered drain may consume them."""
    from island_traders.models.capital_negotiation import CapitalNegotiationStatus

    mgr, room, buyer, maker = _bootstrap()
    plane = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    per_order = plane.capacity_units

    # Empty the shop so BOTH orders are backordered and land in the queue.
    held = maker.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    if held:
        maker.give_resources(ResourceType.TRANSPORT_EQUIPMENT, held)

    first = _propose(mgr, room)["negotiation_id"]
    second = _propose(mgr, room)["negotiation_id"]
    for nid in (first, second):
        ws = _WS()
        asyncio.run(mgr._handle_capital_negotiation_respond(
            room.room_id, "maker",
            {"negotiation_id": nid, "action": "accept"}, ws,
        ))
    ledger = room.game.capital_negotiations
    assert ledger.get(first).status is CapitalNegotiationStatus.QUEUED
    assert ledger.get(second).status is CapitalNegotiationStatus.QUEUED

    # Enough equipment for exactly ONE of the two queued orders.
    maker.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, per_order)
    before = maker.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)

    fulfilled = mgr._drain_capital_order_books(room, 0, 0)
    consumed = before - maker.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)

    # Exactly one settles, units are conserved, and the loser stays queued
    # at the head rather than being skipped or double-filled.
    assert fulfilled == [first]
    assert consumed == per_order
    assert ledger.get(second).status is CapitalNegotiationStatus.QUEUED


def test_unaffordable_head_order_does_not_freeze_the_whole_queue():
    """Units-short must block the queue (it is a build order), but a buyer who
    simply cannot pay must not stall everyone behind them indefinitely."""
    from island_traders.models.capital_negotiation import CapitalNegotiationStatus

    mgr, room, buyer, maker = _bootstrap()
    plane = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    held = maker.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    if held:
        maker.give_resources(ResourceType.TRANSPORT_EQUIPMENT, held)

    first = _propose(mgr, room)["negotiation_id"]
    second = _propose(mgr, room)["negotiation_id"]
    for nid in (first, second):
        ws = _WS()
        asyncio.run(mgr._handle_capital_negotiation_respond(
            room.room_id, "maker",
            {"negotiation_id": nid, "action": "accept"}, ws,
        ))

    # Plenty of equipment for both, but the buyer is broke for the first.
    maker.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, plane.capacity_units * 2)
    ledger = room.game.capital_negotiations
    ledger.get(first).buyer_offer = 10_000_000.0
    ledger.get(first).counter_total = None

    fulfilled = mgr._drain_capital_order_books(room, 0, 0)

    assert second in fulfilled, "a payable order behind a broke one must settle"
    assert ledger.get(first).status is CapitalNegotiationStatus.QUEUED
