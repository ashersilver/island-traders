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


def test_unpayable_head_order_defaults_forfeits_deposit_and_frees_the_queue():
    """Wave 9 deposit rule: a buyer who cannot pay the balance once the build
    is ready forfeits their 50% deposit to the Manufacturer, who keeps the
    goods to resell. The order leaves the queue instead of freezing it."""
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

    ledger = room.game.capital_negotiations
    deposit = ledger.get(first).deposit_paid
    assert deposit > 0, "ordering should have taken a deposit"

    # Equipment for both, but the head buyer cannot cover the balance.
    maker.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, plane.capacity_units * 2)
    ledger.get(first).buyer_offer = 10_000_000.0
    ledger.get(first).counter_total = None
    maker_cash = maker.dollops

    fulfilled = mgr._drain_capital_order_books(room, 0, 0)

    assert ledger.get(first).status is CapitalNegotiationStatus.DEFAULTED
    assert room.game.order_book.get(first) is None, "defaulted order must leave the queue"
    assert maker.dollops >= maker_cash + deposit, "deposit forfeits to the builder"
    assert second in fulfilled, "the next buyer is not blocked by the default"


def test_deposit_is_refunded_when_the_order_ends_without_a_build():
    """The deposit secures payment on delivery. If nothing is ever built —
    here the Manufacturer declines — the buyer is made whole."""
    from island_traders.models.capital_negotiation import CapitalNegotiationStatus

    mgr, room, buyer, maker = _bootstrap()
    before = buyer.dollops
    nid = _propose(mgr, room)["negotiation_id"]
    deposit = room.game.capital_negotiations.get(nid).deposit_paid
    assert deposit > 0
    assert buyer.dollops == pytest.approx(before - deposit)

    ws = _WS()
    asyncio.run(mgr._handle_capital_negotiation_respond(
        room.room_id, "maker",
        {"negotiation_id": nid, "action": "decline"}, ws,
    ))

    assert room.game.capital_negotiations.get(nid).status \
        is CapitalNegotiationStatus.DECLINED
    assert buyer.dollops == pytest.approx(before), "deposit must come back"


def _queue_backordered_order(mgr, room, maker):
    ack = _propose(mgr, room)
    ws = _WS()
    asyncio.run(mgr._handle_capital_negotiation_respond(
        room.room_id, "maker",
        {"negotiation_id": ack["negotiation_id"], "action": "accept"}, ws,
    ))
    return ack["negotiation_id"]


def test_buyer_cancel_refunds_deposit_and_frees_queue():
    from island_traders.models.capital_negotiation import CapitalNegotiationStatus

    mgr, room, buyer, maker = _bootstrap()
    held = maker.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    maker.give_resources(ResourceType.TRANSPORT_EQUIPMENT, held)
    before = buyer.dollops
    nid = _queue_backordered_order(mgr, room, maker)
    deposit = room.game.capital_negotiations.get(nid).deposit_paid

    ws = _WS()
    asyncio.run(mgr._handle_capital_order_cancel(
        room.room_id, "buyer", {"negotiation_id": nid}, ws,
    ))

    negotiation = room.game.capital_negotiations.get(nid)
    assert negotiation.status is CapitalNegotiationStatus.CANCELLED
    assert negotiation.awaiting_id is None
    assert negotiation.deposit_paid == 0
    assert buyer.dollops == pytest.approx(before)
    assert room.game.order_book.get(nid) is None
    assert any(m.get("result") == "cancelled" for m in ws.sent)


def test_buyer_amend_resets_counter_and_reawaits_manufacturer():
    from island_traders.constants import CAPITAL_ORDER_DEPOSIT_FRACTION
    from island_traders.models.capital_negotiation import CapitalNegotiationStatus

    mgr, room, buyer, maker = _bootstrap()
    nid = _propose(mgr, room)["negotiation_id"]
    counter = _WS()
    asyncio.run(mgr._handle_capital_negotiation_respond(
        room.room_id, "maker",
        {"negotiation_id": nid, "action": "counter", "counter_total": 999.0},
        counter,
    ))
    amended_offer = 420.0
    ws = _WS()
    asyncio.run(mgr._handle_capital_order_amend(
        room.room_id, "buyer", {
            "negotiation_id": nid,
            "item_id": "transporter.cargo_plane",
            "maintenance_term_years": 1,
            "spares_kits": 1,
            "predictive_maintenance": False,
            "expedited_eligible": True,
            "buyer_offer": amended_offer,
        }, ws,
    ))

    negotiation = room.game.capital_negotiations.get(nid)
    assert negotiation.status is CapitalNegotiationStatus.PROPOSED
    assert negotiation.counter_total is None
    assert negotiation.awaiting_id == maker.player_id
    assert negotiation.spares_kits == 1
    assert negotiation.deposit_paid == pytest.approx(
        CAPITAL_ORDER_DEPOSIT_FRACTION * amended_offer
    )
    assert any(m.get("result") == "amended" for m in ws.sent)


def test_buyer_mutations_refuse_locked_and_settled_orders():
    mgr, room, _buyer, maker = _bootstrap()
    held = maker.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    maker.give_resources(ResourceType.TRANSPORT_EQUIPMENT, held)
    queued_id = _queue_backordered_order(mgr, room, maker)
    room.game.order_book.get(queued_id).locked = True
    locked = _WS()
    asyncio.run(mgr._handle_capital_order_cancel(
        room.room_id, "buyer", {"negotiation_id": queued_id}, locked,
    ))
    assert any(m.get("type") == "error" and "already settled" in m["message"]
               for m in locked.sent)

    maker.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 10)
    settled_id = _propose(mgr, room)["negotiation_id"]
    accepted = _WS()
    asyncio.run(mgr._handle_capital_negotiation_respond(
        room.room_id, "maker",
        {"negotiation_id": settled_id, "action": "accept"}, accepted,
    ))
    settled = _WS()
    asyncio.run(mgr._handle_capital_order_amend(
        room.room_id, "buyer", {
            "negotiation_id": settled_id,
            "item_id": "transporter.cargo_plane",
            "buyer_offer": 500.0,
        }, settled,
    ))
    assert any(m.get("type") == "error" and "already accepted" in m["message"]
               for m in settled.sent)


def test_sweetener_replaces_unlocked_order_without_passing_locked_entry():
    mgr, room, _buyer, maker = _bootstrap()
    held = maker.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    maker.give_resources(ResourceType.TRANSPORT_EQUIPMENT, held)
    first = _queue_backordered_order(mgr, room, maker)
    second = _queue_backordered_order(mgr, room, maker)
    offer = room.game.capital_negotiations.get(second).buyer_offer + 40.0

    ws = _WS()
    asyncio.run(mgr._handle_capital_order_sweeten(
        room.room_id, "buyer", {"negotiation_id": second, "buyer_offer": offer}, ws,
    ))
    assert [entry.negotiation_id for entry in room.game.order_book.for_manufacturer(
        maker.player_id
    )] == [second, first]
    assert room.game.order_book.get(second).premium > room.game.order_book.get(first).premium

    room.game.order_book.get(second).locked = True
    third = _queue_backordered_order(mgr, room, maker)
    ws = _WS()
    asyncio.run(mgr._handle_capital_order_sweeten(
        room.room_id, "buyer", {
            "negotiation_id": third,
            "buyer_offer": room.game.capital_negotiations.get(third).buyer_offer + 80.0,
        }, ws,
    ))
    assert [entry.negotiation_id for entry in room.game.order_book.for_manufacturer(
        maker.player_id
    )] == [second, third, first]


def test_sweetener_accepts_a_counter_when_it_meets_the_counter_total():
    from island_traders.models.capital_negotiation import CapitalNegotiationStatus

    mgr, room, _buyer, maker = _bootstrap()
    nid = _propose(mgr, room)["negotiation_id"]
    counter_total = room.game.capital_negotiations.get(nid).buyer_offer + 25.0
    asyncio.run(mgr._handle_capital_negotiation_respond(
        room.room_id, "maker", {
            "negotiation_id": nid,
            "action": "counter",
            "counter_total": counter_total,
        }, _WS(),
    ))

    ws = _WS()
    asyncio.run(mgr._handle_capital_order_sweeten(
        room.room_id, "buyer", {
            "negotiation_id": nid,
            "buyer_offer": counter_total,
        }, ws,
    ))
    assert room.game.capital_negotiations.get(nid).status \
        is CapitalNegotiationStatus.ACCEPTED
    assert any(m.get("type") == "capital_order_ack" for m in ws.sent)


def test_deposit_is_trued_up_on_sweeten_and_amendment_reduction():
    from island_traders.constants import CAPITAL_ORDER_DEPOSIT_FRACTION

    mgr, room, buyer, _maker = _bootstrap()
    nid = _propose(mgr, room)["negotiation_id"]
    negotiation = room.game.capital_negotiations.get(nid)
    initial_offer = negotiation.buyer_offer
    initial_deposit = negotiation.deposit_paid
    cash_after_initial_deposit = buyer.dollops

    raised_offer = initial_offer + 100.0
    asyncio.run(mgr._handle_capital_order_sweeten(
        room.room_id, "buyer", {"negotiation_id": nid, "buyer_offer": raised_offer}, _WS(),
    ))
    assert negotiation.deposit_paid == pytest.approx(
        CAPITAL_ORDER_DEPOSIT_FRACTION * raised_offer
    )
    assert buyer.dollops == pytest.approx(cash_after_initial_deposit - 50.0)

    asyncio.run(mgr._handle_capital_order_amend(
        room.room_id, "buyer", {
            "negotiation_id": nid,
            "item_id": "transporter.cargo_plane",
            "buyer_offer": initial_offer,
        }, _WS(),
    ))
    assert negotiation.deposit_paid == pytest.approx(initial_deposit)
    assert buyer.dollops == pytest.approx(cash_after_initial_deposit)


def test_amendment_is_refused_when_buyer_cannot_fund_larger_deposit():
    mgr, room, buyer, _maker = _bootstrap()
    nid = _propose(mgr, room)["negotiation_id"]
    negotiation = room.game.capital_negotiations.get(nid)
    original_offer = negotiation.buyer_offer
    original_deposit = negotiation.deposit_paid
    buyer.dollops = 1.0

    ws = _WS()
    asyncio.run(mgr._handle_capital_order_amend(
        room.room_id, "buyer", {
            "negotiation_id": nid,
            "item_id": "transporter.cargo_plane",
            "buyer_offer": original_offer + 100.0,
        }, ws,
    ))
    assert any(m.get("type") == "error" and "bring the deposit up" in m["message"]
               for m in ws.sent)
    assert negotiation.buyer_offer == original_offer
    assert negotiation.deposit_paid == original_deposit


def _queue_two_orders(mgr, room, maker):
    """Two accepted-but-unbuildable orders, so both sit unlocked in the book."""
    held = maker.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    if held:
        maker.give_resources(ResourceType.TRANSPORT_EQUIPMENT, held)
    ids = []
    for _ in range(2):
        nid = _propose(mgr, room)["negotiation_id"]
        ws = _WS()
        asyncio.run(mgr._handle_capital_negotiation_respond(
            room.room_id, "maker",
            {"negotiation_id": nid, "action": "accept"}, ws,
        ))
        ids.append(nid)
    return ids


def test_upgrading_an_amendment_keeps_the_queue_position():
    """Amending to the same or a higher total must not send the buyer to the
    back of the queue — only a downgrade forfeits the slot."""
    mgr, room, buyer, maker = _bootstrap()
    buyer.dollops = 100_000.0
    first, second = _queue_two_orders(mgr, room, maker)
    book = room.game.order_book
    assert [e.negotiation_id for e in book.for_manufacturer(maker.player_id)] == [first, second]

    negotiation = room.game.capital_negotiations.get(first)
    higher = round(negotiation.buyer_offer + 50.0, 2)
    ws = _WS()
    asyncio.run(mgr._handle_capital_order_amend(
        room.room_id, "buyer",
        {"negotiation_id": first, "item_id": negotiation.item_id,
         "buyer_offer": higher}, ws,
    ))

    assert not any(m.get("type") == "error" for m in ws.sent), ws.sent
    entry = book.get(first)
    assert entry is not None, "an upgrade must keep its slot in the book"
    assert entry.queue_position == 0
    assert room.game.capital_negotiations.get(first).buyer_offer == higher


def test_downgrading_an_amendment_forfeits_the_queue_position():
    mgr, room, buyer, maker = _bootstrap()
    buyer.dollops = 100_000.0
    first, _second = _queue_two_orders(mgr, room, maker)
    negotiation = room.game.capital_negotiations.get(first)
    lower = round(negotiation.buyer_offer - 20.0, 2)

    ws = _WS()
    asyncio.run(mgr._handle_capital_order_amend(
        room.room_id, "buyer",
        {"negotiation_id": first, "item_id": negotiation.item_id,
         "buyer_offer": lower}, ws,
    ))

    assert not any(m.get("type") == "error" for m in ws.sent), ws.sent
    assert room.game.order_book.get(first) is None, \
        "a downgrade gives up the slot"


def test_slot_held_during_re_review_does_not_block_the_drain():
    """The held entry is no longer QUEUED, so the drain must skip past it and
    still settle the order behind it."""
    from island_traders.models.capital_negotiation import CapitalNegotiationStatus

    mgr, room, buyer, maker = _bootstrap()
    buyer.dollops = 100_000.0
    first, second = _queue_two_orders(mgr, room, maker)
    negotiation = room.game.capital_negotiations.get(first)
    ws = _WS()
    asyncio.run(mgr._handle_capital_order_amend(
        room.room_id, "buyer",
        {"negotiation_id": first, "item_id": negotiation.item_id,
         "buyer_offer": round(negotiation.buyer_offer + 50.0, 2)}, ws,
    ))
    assert room.game.order_book.get(first).queue_position == 0

    plane = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    maker.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, plane.capacity_units)

    fulfilled = mgr._drain_capital_order_books(room, 0, 0)

    assert second in fulfilled, "the queued order behind must still settle"
    assert room.game.capital_negotiations.get(first).status \
        is CapitalNegotiationStatus.PROPOSED
