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
from island_traders.models.player import maintenance_contract_cost
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
            [PlayerSpec(name=f"Player{idx}", role_names=[role], is_human=True)
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


def test_capital_order_charges_records_conditions_and_delivers():
    mgr, room, players = _bootstrap(["Transporter", "Manufacturer"])
    buyer, manufacturer = players
    item = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    contract = maintenance_contract_cost(item.cost, 3, True)   # #188, predictive
    upfront = round(item.cost + contract + 0.15 * item.cost * 2, 2)
    buyer.dollops = item.cost * 5
    buyer_start = buyer.dollops
    mfr_start = manufacturer.dollops
    te_before = manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 1)
    ws = _WS()

    asyncio.run(mgr._handle_capital_order(room.room_id, "p0", {
        "item_id": "transporter.cargo_plane",
        "maintenance_term_years": 3,
        "predictive_maintenance": True,
        "spares_kits": 2,
        "expedited_eligible": True,
    }, ws))

    ack = next((m for m in ws.sent if m.get("type") == "capital_order_ack"), None)
    assert ack is not None, ws.sent
    assert ack["upfront"] == upfront
    assert ack["contract_cost"] == contract
    assert ack["spares_kits"] == 2
    assert ack["arrives_at_tick"] == item.delivery_seasons

    # Cash settled and one manufactured unit consumed.
    assert buyer.dollops == buyer_start - upfront
    assert manufacturer.dollops == mfr_start + upfront
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == te_before

    # Order conditions ride on the transit entry...
    entry = buyer.capital_in_transit[0]
    assert entry["order"]["maintenance_term_years"] == 3
    assert entry["order"]["spares_kits"] == 2
    assert entry["order"]["purchase_value"] == item.cost

    # ...and land on the delivered unit.
    buyer.deliver_in_transit(current_tick=item.delivery_seasons)
    unit = buyer.capital_units["transporter.cargo_plane"][0]
    assert unit.spares_attached == 2
    assert unit.maintenance_term_years == 3
    assert unit.predictive_maintenance is True
    assert unit.warranty is True
    assert unit.expedited_eligible is True
    assert unit.purchase_value == item.cost


def test_capital_order_financed_creates_loan_and_pays_referral():
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
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 1)
    ws = _WS()

    asyncio.run(mgr._handle_capital_order(room.room_id, "p0", {
        "item_id": "transporter.cargo_plane",
        "financing": True,
    }, ws))

    ack = next((m for m in ws.sent if m.get("type") == "capital_order_ack"), None)
    assert ack is not None, ws.sent
    assert ack["financed"] is True
    assert ack["loan_id"] is not None
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
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 1)
    ws = _WS()

    asyncio.run(mgr._handle_capital_order(room.room_id, "p0", {
        "item_id": "transporter.cargo_plane",
        "financing": True,
    }, ws))

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
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 1)
    ws = _WS()

    asyncio.run(mgr._handle_capital_order(room.room_id, "p0", {
        "item_id": "transporter.cargo_plane",
        "financing": True,
    }, ws))

    assert any(m.get("type") == "error" for m in ws.sent)
    assert buyer.capital_in_transit == []
    # Nothing consumed — the saturating loans are the only ones on the ledger.
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == te_before + 1
    assert all(
        l.status == LoanStatus.ACTIVE and l.principal == 10.0
        for l in room.game.loan_ledger.loans
    )


def test_capital_order_rejects_when_unaffordable():
    mgr, room, players = _bootstrap(["Transporter", "Manufacturer"])
    buyer, manufacturer = players
    buyer.dollops = 5.0
    te_before = manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT)
    manufacturer.receive_resources(ResourceType.TRANSPORT_EQUIPMENT, 1)
    ws = _WS()

    asyncio.run(mgr._handle_capital_order(room.room_id, "p0", {
        "item_id": "transporter.cargo_plane",
    }, ws))

    assert any(m.get("type") == "error" for m in ws.sent)
    assert buyer.capital_in_transit == []
    # Nothing consumed or charged.
    assert manufacturer.inventory.get(ResourceType.TRANSPORT_EQUIPMENT) == te_before + 1
