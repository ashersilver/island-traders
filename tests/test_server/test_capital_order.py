"""WebSocket capital-order endpoint (#185) — order conditions → delivery."""
from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.capacity import find_item
from island_traders.models.loan import CAPITAL_FINANCE_PREMIUM_PTS, posted_funding_rates
from island_traders.models.player import maintenance_contract_cost
from island_traders.models.resource import ResourceType
from island_traders.server.app import GameManager, GameRoom, LobbyPlayer


class _WS:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(json.loads(text))


def _bootstrap(role_names: list[str], *, human: bool = True):
    mgr = GameManager()
    room = GameRoom(
        room_id="cap-room", name="Cap Room", max_players=len(role_names),
        num_years=1, is_public=True, join_code="CAP1",
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
            [PlayerSpec(name=f"Player{idx}", role_names=[role], is_human=human)
             for idx, role in enumerate(role_names)],
            num_years=1, starting_dollops=100.0,
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


def _propose(mgr, room, lobby_id: str, msg: dict):
    ws = _WS()
    asyncio.run(mgr._handle_capital_order(room.room_id, lobby_id, msg, ws))
    ack = next(
        (m for m in ws.sent if m.get("type") == "capital_negotiation_ack"),
        None,
    )
    assert ack is not None, ws.sent
    return ws, ack["negotiation_id"]


def _respond(mgr, room, lobby_id: str, msg: dict):
    ws = _WS()
    asyncio.run(
        mgr._handle_capital_negotiation_respond(room.room_id, lobby_id, msg, ws)
    )
    return ws


def _accept_counter(mgr, room, lobby_id: str, negotiation_id: int):
    ws = _WS()
    asyncio.run(
        mgr._handle_capital_negotiation_accept(
            room.room_id,
            lobby_id,
            {"negotiation_id": negotiation_id},
            ws,
        )
    )
    return ws


def test_capital_order_propose_then_manufacturer_accept_delivers():
    mgr, room, players = _bootstrap(["Transporter", "Manufacturer"])
    buyer, manufacturer = players
    item = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    contract = maintenance_contract_cost(item.cost, 3, True)   # #188, predictive
    upfront = round(item.cost + contract + 0.15 * item.cost * 2, 2)
    buyer.dollops = item.cost * 5
    buyer_start = buyer.dollops
    mfr_start = manufacturer.dollops
    te_before = manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, item.capacity_units)

    _, negotiation_id = _propose(mgr, room, "p0", {
        "item_id": "transporter.cargo_plane",
        "maintenance_term_years": 3,
        "predictive_maintenance": True,
        "spares_kits": 2,
        "expedited_eligible": True,
    })
    assert buyer.dollops == buyer_start
    assert manufacturer.dollops == mfr_start
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == (
        te_before + item.capacity_units
    )

    ws = _respond(mgr, room, "p1", {
        "negotiation_id": negotiation_id,
        "action": "accept",
    })
    ack = next((m for m in ws.sent if m.get("type") == "capital_order_ack"), None)
    assert ack is not None, ws.sent
    assert ack["upfront"] == upfront
    assert ack["contract_cost"] == contract
    assert ack["spares_kits"] == 2
    assert ack["arrives_at_tick"] == item.delivery_seasons

    # Cash settled and proportional manufactured capacity consumed.
    assert buyer.dollops == buyer_start - upfront
    assert manufacturer.dollops == mfr_start + upfront
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == te_before

    # Order conditions ride on the transit entry...
    entry = buyer.capital_in_transit[0]
    assert entry["order"]["maintenance_term_years"] == 3
    assert entry["order"]["spares_kits"] == 2
    assert entry["order"]["purchase_value"] == item.cost

    # ...and land on the delivered unit.
    buyer.deliver_in_transit(
        current_tick=item.delivery_seasons, order_book=room.game.order_book
    )
    assert room.game.order_book.get(negotiation_id) is None
    unit = buyer.capital_units["transporter.cargo_plane"][0]
    assert unit.spares_attached == 2
    assert unit.maintenance_term_years == 3
    assert unit.predictive_maintenance is True
    assert unit.warranty is True
    assert unit.expedited_eligible is True
    assert unit.purchase_value == item.cost


def test_capital_order_backorders_when_manufacturer_capacity_units_short():
    mgr, room, players = _bootstrap(["Transporter", "Manufacturer"])
    buyer, manufacturer = players
    item = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    assert item.capacity_units == 4
    buyer.dollops = item.cost * 5
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 3)
    ws = _WS()

    asyncio.run(mgr._handle_capital_order(room.room_id, "p0", {
        "item_id": "transporter.cargo_plane",
    }, ws))

    ack = next(
        (m for m in ws.sent if m.get("type") == "capital_negotiation_ack"),
        None,
    )
    assert ack is not None, ws.sent
    assert ack["result"] == "backordered"
    assert "BACKORDERED" in ack["message"]
    negotiation = room.game.capital_negotiations.get(ack["negotiation_id"])
    assert negotiation.units_required == 4
    assert negotiation.units_short_at_order == 1

    response = _respond(mgr, room, "p1", {
        "negotiation_id": negotiation.negotiation_id,
        "action": "accept",
    })
    queued = next(
        m for m in response.sent if m.get("type") == "capital_negotiation_ack"
    )
    assert queued["result"] == "backordered"
    assert negotiation.status.value == "queued"
    entry = room.game.order_book.get(negotiation.negotiation_id)
    assert entry is not None and entry.locked is False
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == 3


def test_capital_backorder_drain_stops_at_first_unfillable_and_settles_in_order():
    mgr, room, players = _bootstrap(["Transporter", "Transporter", "Manufacturer"])
    first_buyer, second_buyer, manufacturer = players
    first_buyer.dollops = second_buyer.dollops = 10_000

    _, first_id = _propose(mgr, room, "p0", {"item_id": "transporter.cargo_plane"})
    _respond(mgr, room, "p2", {"negotiation_id": first_id, "action": "accept"})
    _, second_id = _propose(mgr, room, "p1", {"item_id": "transporter.cargo_ship"})
    _respond(mgr, room, "p2", {"negotiation_id": second_id, "action": "accept"})
    assert [e.negotiation_id for e in room.game.order_book.for_manufacturer(
        manufacturer.player_id
    )] == [first_id, second_id]

    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 3)
    assert mgr._drain_capital_order_books(room, 0, 0) == []
    assert room.game.capital_negotiations.get(second_id).status.value == "queued"
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == 3

    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 1)
    assert mgr._drain_capital_order_books(room, 0, 0) == [first_id]
    assert room.game.capital_negotiations.get(first_id).status.value == "accepted"
    assert room.game.capital_negotiations.get(second_id).status.value == "queued"
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == 0


def test_order_promises_use_manufacturer_durable_throughput():
    _, room, players = _bootstrap(["Manufacturer"])
    manufacturer = players[0]
    game = room.game
    slots = game.turn_manager.production.manufacturer_durable_allowance(manufacturer)
    assert slots > 1
    for negotiation_id in range(slots + 1):
        game.order_book.add(negotiation_id, manufacturer.player_id)

    game.refresh_order_promises(manufacturer.player_id, 2, 1)
    entries = game.order_book.for_manufacturer(manufacturer.player_id)
    assert all((e.promised_year, e.promised_season) == (2, 1) for e in entries[:slots])
    assert (entries[slots].promised_year, entries[slots].promised_season) == (2, 2)


def test_capital_order_counter_then_buyer_accept_finances_and_pays_referral():
    from island_traders.constants import MANUFACTURER_FINANCE_REFERRAL_RATE

    mgr, room, players = _bootstrap(["Transporter", "Manufacturer", "Banker"])
    buyer, manufacturer, banker = players
    item = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    upfront = round(item.cost, 2)  # no term, no spares
    # Buyer is too poor to pay cash — financing must carry the deal.
    buyer.dollops = 5.0
    buyer_start = buyer.dollops
    mfr_start = manufacturer.dollops
    banker_start = banker.dollops
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, item.capacity_units)

    _, negotiation_id = _propose(mgr, room, "p0", {
        "item_id": "transporter.cargo_plane",
        "financing": True,
        "buyer_offer": upfront - 25,
    })
    counter_ws = _respond(mgr, room, "p1", {
        "negotiation_id": negotiation_id,
        "action": "counter",
        "counter_total": upfront,
    })
    counter_ack = next(
        (m for m in counter_ws.sent if m.get("type") == "capital_negotiation_ack"),
        None,
    )
    assert counter_ack["result"] == "countered"

    ws = _accept_counter(mgr, room, "p0", negotiation_id)

    ack = next((m for m in ws.sent if m.get("type") == "capital_order_ack"), None)
    assert ack is not None, ws.sent
    assert ack["financed"] is True
    assert ack["loan_id"] is not None
    expected_rate = round(
        posted_funding_rates(0, 0, cycle=room.game.current_cycle)[3]
        + CAPITAL_FINANCE_PREMIUM_PTS,
        4,
    )
    assert ack["loan_rate"] == expected_rate
    assert ack["posted_3yr_rate"] == posted_funding_rates(
        0, 0, cycle=room.game.current_cycle
    )[3]
    assert ack["capital_finance_premium_pts"] == CAPITAL_FINANCE_PREMIUM_PTS
    fee = round(MANUFACTURER_FINANCE_REFERRAL_RATE * upfront, 2)
    assert ack["referral_fee"] == fee

    # Buyer treasury is flat (loan financed it); buyer now owes the loan.
    assert buyer.dollops == buyer_start
    assert room.game.loan_ledger.outstanding_debt(buyer.player_id) > 0
    # Manufacturer received full price plus the 2% referral kickback.
    assert manufacturer.dollops == mfr_start + upfront + fee
    # Banker funded the principal (less its reserve) and paid the referral.
    assert banker.dollops < banker_start
    # The order still delivers with the right purchase value.
    assert buyer.capital_in_transit[0]["order"]["purchase_value"] == item.cost


def test_capital_order_financing_falls_back_to_cash_without_banker():
    mgr, room, players = _bootstrap(["Transporter", "Manufacturer"])
    buyer, manufacturer = players
    item = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    upfront = round(item.cost, 2)
    buyer.dollops = item.cost * 5
    buyer_start = buyer.dollops
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, item.capacity_units)

    _, negotiation_id = _propose(mgr, room, "p0", {
        "item_id": "transporter.cargo_plane",
        "financing": True,
    })
    ws = _respond(mgr, room, "p1", {
        "negotiation_id": negotiation_id,
        "action": "accept",
    })

    ack = next((m for m in ws.sent if m.get("type") == "capital_order_ack"), None)
    assert ack is not None, ws.sent
    # No Bank → financing flag is honoured as cash.
    assert ack["financed"] is False
    assert ack["loan_id"] is None
    assert buyer.dollops == buyer_start - upfront


def test_capital_order_financing_rejected_when_bank_at_cap_and_buyer_broke():
    from island_traders.models.loan import LoanStatus

    mgr, room, players = _bootstrap(["Transporter", "Manufacturer", "Banker"])
    buyer, manufacturer, banker = players
    item = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    tm = room.game.turn_manager
    # Saturate the Bank's active-loan capacity.
    _, _, cap = tm._banker_can_issue_loan(banker)
    for _ in range(cap):
        room.game.loan_ledger.create_loan(
            borrower_id=buyer.player_id, lender_id=banker.player_id,
            principal=10.0, interest_rate=0.1, issued_year=5,
            issued_season=0, term_years=1,
        )
    assert not tm._banker_can_issue_loan(banker)[0]

    buyer.dollops = 1.0  # also can't pay cash
    te_before = manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, item.capacity_units)

    _, negotiation_id = _propose(mgr, room, "p0", {
        "item_id": "transporter.cargo_plane",
        "financing": True,
    })
    ws = _respond(mgr, room, "p1", {
        "negotiation_id": negotiation_id,
        "action": "accept",
    })

    assert any(m.get("type") == "error" for m in ws.sent)
    assert buyer.capital_in_transit == []
    # Nothing consumed — the saturating loans are the only ones on the ledger.
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == (
        te_before + item.capacity_units
    )
    assert all(
        l.status == LoanStatus.ACTIVE and l.principal == 10.0
        for l in room.game.loan_ledger.loans
    )


def test_capital_order_rejects_when_unaffordable():
    mgr, room, players = _bootstrap(["Transporter", "Manufacturer"])
    buyer, manufacturer = players
    item = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    buyer.dollops = 5.0
    te_before = manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, item.capacity_units)

    _, negotiation_id = _propose(mgr, room, "p0", {
        "item_id": "transporter.cargo_plane",
    })
    ws = _respond(mgr, room, "p1", {
        "negotiation_id": negotiation_id,
        "action": "accept",
    })

    assert any(m.get("type") == "error" for m in ws.sent)
    assert buyer.capital_in_transit == []
    # Nothing consumed or charged.
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == (
        te_before + item.capacity_units
    )


def test_capital_order_decline_does_not_charge_or_consume():
    mgr, room, players = _bootstrap(["Transporter", "Manufacturer"])
    buyer, manufacturer = players
    item = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    buyer.dollops = item.cost * 5
    buyer_start = buyer.dollops
    mfr_start = manufacturer.dollops
    te_before = manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, item.capacity_units)

    _, negotiation_id = _propose(mgr, room, "p0", {
        "item_id": "transporter.cargo_plane",
    })
    ws = _respond(mgr, room, "p1", {
        "negotiation_id": negotiation_id,
        "action": "decline",
    })

    ack = next((m for m in ws.sent if m.get("type") == "capital_negotiation_ack"), None)
    assert ack["result"] == "declined"
    assert buyer.dollops == buyer_start
    assert manufacturer.dollops == mfr_start
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == (
        te_before + item.capacity_units
    )
    assert buyer.capital_in_transit == []


def test_capital_order_ai_manufacturer_auto_accepts_at_recommended_total():
    mgr, room, players = _bootstrap(["Transporter", "Manufacturer"], human=False)
    buyer, manufacturer = players
    item = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    buyer.dollops = item.cost * 5
    buyer_start = buyer.dollops
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, item.capacity_units)
    ws = _WS()

    asyncio.run(mgr._handle_capital_order(room.room_id, "p0", {
        "item_id": "transporter.cargo_plane",
    }, ws))

    ack = next((m for m in ws.sent if m.get("type") == "capital_order_ack"), None)
    assert ack is not None, ws.sent
    assert ack["upfront"] == round(item.cost, 2)
    assert buyer.dollops == buyer_start - round(item.cost, 2)
    assert buyer.capital_in_transit


def test_capital_order_double_accept_settles_once():
    mgr, room, players = _bootstrap(["Transporter", "Manufacturer"])
    buyer, manufacturer = players
    item = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    buyer.dollops = item.cost * 5
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, item.capacity_units)
    _, negotiation_id = _propose(mgr, room, "p0", {
        "item_id": "transporter.cargo_plane",
    })
    first = _respond(mgr, room, "p1", {
        "negotiation_id": negotiation_id,
        "action": "accept",
    })
    second = _respond(mgr, room, "p1", {
        "negotiation_id": negotiation_id,
        "action": "accept",
    })

    assert any(m.get("type") == "capital_order_ack" for m in first.sent)
    assert any(m.get("type") == "error" for m in second.sent)
    assert len(buyer.capital_in_transit) == 1


def test_capital_order_self_build_settles_immediately_without_negotiation():
    # A Manufacturer ordering its own equipment has no counterparty to review the
    # order.  It must settle on the spot (consuming a manufactured unit, charging
    # the Wave-5.3 self-build cost, no referral) rather than parking a negotiation
    # that awaits — and can never clear — the manufacturer's own response, which
    # previously jammed the queue.
    from island_traders.constants import MANUFACTURER_SELF_ORDER_PRICE_FRACTION

    mgr, room, players = _bootstrap(["Manufacturer", "Transporter"])
    manufacturer, _other = players
    item = find_item(CAPITAL_CATALOGUE, "manufacturer.foundry")
    manufacturer.dollops = item.cost * 5
    start_dollops = manufacturer.dollops
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 1)
    te_before = manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)

    ws = _WS()
    asyncio.run(mgr._handle_capital_order(room.room_id, "p0", {
        "item_id": "manufacturer.foundry",
    }, ws))

    # Settles immediately: a capital_order_ack, never a 'proposed' negotiation.
    assert any(m.get("type") == "capital_order_ack" for m in ws.sent), ws.sent
    assert not any(
        m.get("type") == "capital_negotiation_ack" and m.get("result") == "proposed"
        for m in ws.sent
    ), ws.sent

    # Self-build: 20% of list price burned as a sunk cost (Wave 5.3),
    # proportional capacity consumed, equipment placed (foundry has 0-season
    # delivery, so it lands directly in capital_units).
    self_cost = round(MANUFACTURER_SELF_ORDER_PRICE_FRACTION * item.cost, 2)
    assert manufacturer.dollops == start_dollops - self_cost
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == te_before - 1
    assert manufacturer.capital_units.get("manufacturer.foundry")

    # Nothing is left awaiting the manufacturer — the queue stays clear.
    assert mgr.rooms[room.room_id].game.capital_negotiations.awaiting(
        manufacturer.player_id
    ) == []


def test_capital_order_self_build_warehouse_settles_immediately():
    mgr, room, players = _bootstrap(["Manufacturer", "Transporter"])
    manufacturer, _other = players
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 1)

    ws = _WS()
    asyncio.run(mgr._handle_capital_order(room.room_id, "p0", {
        "item_id": "manufacturer.warehouse",
    }, ws))

    ack = next((m for m in ws.sent if m.get("type") == "capital_order_ack"), None)
    assert ack is not None, ws.sent
    assert ack["item_id"] == "manufacturer.warehouse"
    assert manufacturer.capital_inventory.get("manufacturer.warehouse") == 1
    assert manufacturer.spares_capacity() == 22
    assert not any(
        m.get("type") == "capital_negotiation_ack" and m.get("result") == "proposed"
        for m in ws.sent
    ), ws.sent


def test_capital_order_self_order_charges_20pct_of_list_plus_spares_at_cost():
    # Wave 5.3: a self-order of a manufactured item used to settle at $0 cash.
    # It now costs 0.20 × list_price plus spares kits at cost, burned as a sunk
    # cost (no counterparty is paid); inputs are still consumed.
    from island_traders.constants import MANUFACTURER_SELF_ORDER_PRICE_FRACTION

    mgr, room, players = _bootstrap(["Manufacturer", "Transporter"])
    manufacturer, other = players
    item = find_item(CAPITAL_CATALOGUE, "manufacturer.foundry")
    manufacturer.dollops = item.cost * 5
    start_dollops = manufacturer.dollops
    other_start = other.dollops
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 1)
    te_before = manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)

    ws = _WS()
    asyncio.run(mgr._handle_capital_order(room.room_id, "p0", {
        "item_id": "manufacturer.foundry",
        "spares_kits": 2,
    }, ws))

    ack = next((m for m in ws.sent if m.get("type") == "capital_order_ack"), None)
    assert ack is not None, ws.sent
    expected = round(
        MANUFACTURER_SELF_ORDER_PRICE_FRACTION * item.cost
        + 0.15 * item.cost * 2,
        2,
    )
    assert ack["upfront"] == expected
    # Sunk cost: the manufacturer pays and nobody receives.
    assert manufacturer.dollops == start_dollops - expected
    assert other.dollops == other_start
    # The manufactured resource is still debited.
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == te_before - 1
    assert manufacturer.capital_units.get("manufacturer.foundry")


def test_capital_order_self_order_rejected_when_self_build_cost_unaffordable():
    mgr, room, players = _bootstrap(["Manufacturer", "Transporter"])
    manufacturer, _other = players
    manufacturer.dollops = 1.0
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 1)
    te_before = manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)

    ws = _WS()
    asyncio.run(mgr._handle_capital_order(room.room_id, "p0", {
        "item_id": "manufacturer.foundry",
    }, ws))

    error = next((m for m in ws.sent if m.get("type") == "error"), None)
    assert error is not None, ws.sent
    assert "20% of list price" in error["message"]
    # Nothing consumed or charged.
    assert manufacturer.dollops == 1.0
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == te_before
    assert not manufacturer.capital_units.get("manufacturer.foundry")


def test_game_state_exposes_spares_held_and_capacity():
    mgr, room, players = _bootstrap(["Manufacturer", "Transporter"])
    manufacturer, _other = players
    manufacturer.manufacture_spares(7)

    state = mgr.get_game_state(room.room_id, "p0")
    manufacturer_state = next(
        p for p in state["players"] if p["player_id"] == manufacturer.player_id
    )

    assert manufacturer_state["spares_held"] == 10
    assert manufacturer_state["spares_capacity"] == 10
