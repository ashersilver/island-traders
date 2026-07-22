from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.equity import CapTable
from island_traders.models.owner import (
    Owner, holdings_mirror_consistent, sync_holdings_mirror,
)
from island_traders.server.app import GameManager, GameRoom, LobbyPlayer


class _WS:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(json.loads(text))


def _bootstrap():
    manager = GameManager()
    room = GameRoom("equity", "Equity", num_years=1)
    room.players = [
        LobbyPlayer(player_id="seller", name="Seller", role_names=["Farmer"]),
        LobbyPlayer(player_id="buyer", name="Buyer", role_names=["Miner"]),
        LobbyPlayer(player_id="third", name="Third", role_names=["Transporter"]),
    ]
    room.status = "running"
    game = Game(GameConfig([
        PlayerSpec("Seller Farm", ["Farmer"], is_human=True),
        PlayerSpec("Buyer Mine", ["Miner"], is_human=True),
        PlayerSpec("Third Ship", ["Transporter"], is_human=True),
    ], num_years=1), FakeIOAdapter())
    game.setup()
    game.owners = {
        "seller": Owner("seller", "Seller", 200.0, {"0": 60}),
        "buyer": Owner("buyer", "Buyer", 200.0, {"1": 60}),
        "third": Owner("third", "Third", 200.0, {"2": 60}),
    }
    for player, owner_id in zip(game.players, game.owners):
        player.owner_id = owner_id
        player.owner = game.owners[owner_id]
        player.cap_table = CapTable.new_with_majority(owner_id)
    room.game = game
    room.lobby_to_engine_id = {"seller": [0], "buyer": [1], "third": [2]}
    room.acting_engine_id = {"seller": 0, "buyer": 1, "third": 2}
    manager.rooms[room.room_id] = room
    manager._ws_connections[room.room_id] = {}
    return manager, room


def _offer(manager, room, **overrides):
    msg = {"island_id": 0, "buyer_id": "buyer", "shares": 10, "price": 50}
    msg.update(overrides)
    ws = _WS()
    asyncio.run(manager._handle_equity_sale_offer(room.room_id, "seller", msg, ws))
    return ws.sent[0]


def _respond(manager, room, lobby_id, sale_id, action, **extra):
    ws = _WS()
    asyncio.run(manager._handle_equity_sale_respond(
        room.room_id, lobby_id, {"sale_id": sale_id, "action": action, **extra}, ws,
    ))
    return ws.sent[0]


def test_offer_accept_settles_personal_cash_not_treasury_and_syncs_mirrors():
    manager, room = _bootstrap()
    seller, buyer = room.game.owners["seller"], room.game.owners["buyer"]
    island = room.game.players[0]
    treasury = island.dollops
    ack = _offer(manager, room)
    assert ack["result"] == "offered"

    result = _respond(manager, room, "buyer", ack["sale"]["sale_id"], "accept")

    assert result["result"] == "settled"
    assert seller.personal_cash == 250.0
    assert buyer.personal_cash == 150.0
    assert island.dollops == treasury
    assert island.cap_table.held_by("seller") == 50
    assert island.cap_table.held_by("buyer") == 10
    assert holdings_mirror_consistent(0, island.cap_table, room.game.owners)


def test_single_counter_round_and_decline_lifecycle():
    manager, room = _bootstrap()
    sale = _offer(manager, room)["sale"]
    counter = _respond(manager, room, "buyer", sale["sale_id"], "counter", price=35)
    assert counter["result"] == "countered"
    assert counter["sale"]["awaiting_owner_id"] == "seller"
    rejected_counter = _respond(manager, room, "seller", sale["sale_id"], "counter", price=30)
    assert rejected_counter["ok"] is False
    declined = _respond(manager, room, "seller", sale["sale_id"], "decline")
    assert declined["result"] == "declined"


def test_control_flips_to_unique_largest_holder_but_tie_keeps_incumbent():
    manager, room = _bootstrap()
    island = room.game.players[0]
    tie = _offer(manager, room, shares=30, price=30)["sale"]
    _respond(manager, room, "buyer", tie["sale_id"], "accept")
    assert island.owner_id == "seller"
    assert room.lobby_to_engine_id["seller"] == [0]

    flip = _offer(manager, room, shares=1, price=1)["sale"]
    _respond(manager, room, "buyer", flip["sale_id"], "accept")
    assert island.owner_id == "buyer"
    assert 0 not in room.lobby_to_engine_id["seller"]
    assert 0 in room.lobby_to_engine_id["buyer"]
    assert island.name.startswith("Buyer — ")


def test_sale_below_fifty_can_leave_seller_as_controlling_minority():
    manager, room = _bootstrap()
    sale = _offer(manager, room, shares=11, price=11)["sale"]
    _respond(manager, room, "buyer", sale["sale_id"], "accept")
    assert room.game.players[0].cap_table.held_by("seller") == 49
    assert room.game.players[0].owner_id == "seller"


def test_minority_stake_appears_in_owner_payload_and_consolidated_position():
    manager, room = _bootstrap()
    before = manager.get_game_state(room.room_id, "buyer")
    prior = next(o for o in before["owners"] if o["owner_id"] == "buyer")["consolidated_position"]
    sale = _offer(manager, room, shares=10, price=10)["sale"]
    _respond(manager, room, "buyer", sale["sale_id"], "accept")
    state = manager.get_game_state(room.room_id, "buyer")
    owner = next(o for o in state["owners"] if o["owner_id"] == "buyer")
    assert owner["holdings"]["0"] == 10
    expected_delta = 10 * next(p for p in state["players"] if p["player_id"] == 0)["share_price"] - 10
    assert owner["consolidated_position"] == pytest.approx(prior + expected_delta, abs=0.2)


@pytest.mark.parametrize("overrides,error", [
    ({"buyer_id": "missing"}, "named player"),
    ({"price": 999}, "cannot afford"),
    ({"shares": 61}, "between 1 and 60"),
])
def test_invalid_offers(overrides, error):
    manager, room = _bootstrap()
    ack = _offer(manager, room, **overrides)
    assert ack["ok"] is False
    assert error in ack["error"]


def test_non_controlling_owner_cannot_offer_even_if_routing_map_is_stale():
    manager, room = _bootstrap()
    room.lobby_to_engine_id["buyer"].append(0)
    ws = _WS()
    asyncio.run(manager._handle_equity_sale_offer(room.room_id, "buyer", {
        "island_id": 0, "buyer_id": "third", "shares": 1, "price": 1,
    }, ws))
    assert ws.sent[0]["ok"] is False
    assert "controlling owner" in ws.sent[0]["error"]


def test_mirror_helper_repairs_both_sides_of_cross_owner_transfer():
    owners = {
        "a": Owner("a", "A", holdings={"7": 99}),
        "b": Owner("b", "B", holdings={}),
    }
    table = CapTable.new_with_majority("a")
    table.transfer("a", "b", 12)
    assert not holdings_mirror_consistent(7, table, owners)
    sync_holdings_mirror(7, table, owners)
    assert owners["a"].holdings["7"] == 48
    assert owners["b"].holdings["7"] == 12
    assert holdings_mirror_consistent(7, table, owners)


def test_ai_secondary_sale_is_strictly_gated_and_sells_one_share():
    manager, room = _bootstrap()
    for lobby_player in room.players:
        lobby_player.is_human = False
    island = room.game.players[0]
    island.cap_table.transfer("unissued", "seller", 1)
    sync_holdings_mirror(0, island.cap_table, room.game.owners)
    island.dollops = 0.0

    manager._run_ai_secondary_equity(room)

    assert island.cap_table.held_by("seller") == 60
    assert sum(
        island.cap_table.held_by(owner_id) for owner_id in ("buyer", "third")
    ) == 1
    assert holdings_mirror_consistent(0, island.cap_table, room.game.owners)
