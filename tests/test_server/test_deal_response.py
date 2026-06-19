from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.deal import DealStatus
from island_traders.models.resource import ResourceType
from island_traders.server.app import GameManager, GameRoom, LobbyPlayer


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_text(self, text: str) -> None:
        self.messages.append(json.loads(text))


def _bootstrap_game(role_names: list[str] | None = None):
    role_names = role_names or ["Farmer", "Miner"]
    mgr = GameManager()
    room = GameRoom(
        room_id="dealroom",
        name="Deals",
        max_players=len(role_names),
        num_years=1,
        is_public=True,
        join_code="DL0001",
        creator_id="p0",
    )
    room.players = [
        LobbyPlayer(
            player_id=f"p{idx}",
            name=f"Player{idx}",
            role_names=[role_name],
        )
        for idx, role_name in enumerate(role_names)
    ]
    room.status = "running"
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}

    game = Game(
        GameConfig(
            player_specs=[
                PlayerSpec(
                    name=f"Player{idx}",
                    role_names=[role_name],
                    is_human=True,
                )
                for idx, role_name in enumerate(role_names)
            ],
            num_years=1,
            starting_dollops=100.0,
        ),
        FakeIOAdapter(),
    )
    game.setup()
    room.game = game
    room.lobby_to_engine_id = {
        lobby.player_id: engine_player.player_id
        for lobby, engine_player in zip(room.players, game.players)
    }
    return mgr, room, game.players


def test_game_state_exposes_deals_awaiting_me_and_my_deals():
    mgr, room, players = _bootstrap_game()
    farmer, miner = players
    farmer.receive_resources(ResourceType.FOOD, 2)
    deal = room.game.turn_manager.trading.propose_deal(
        farmer,
        miner,
        ResourceType.FOOD,
        2,
        ResourceType.OIL,
        1,
    )

    proposer_state = mgr.get_game_state(room.room_id, "p0")
    target_state = mgr.get_game_state(room.room_id, "p1")

    assert proposer_state["my_deals"][0]["deal_id"] == deal.deal_id
    assert proposer_state["my_deals"][0]["awaiting_id"] == miner.player_id
    assert target_state["deals_awaiting_me"][0]["deal_id"] == deal.deal_id
    assert target_state["deals_awaiting_me"][0]["offer"] == {
        "resource": "Food",
        "qty": 2,
    }


def test_deal_propose_notifies_target_with_actionable_state(monkeypatch):
    mgr, room, players = _bootstrap_game()
    farmer, _miner = players
    farmer.receive_resources(ResourceType.FOOD, 2)
    sent = []
    monkeypatch.setattr(
        mgr,
        "_thread_safe_send",
        lambda room_id, lobby_id, msg: sent.append((room_id, lobby_id, msg)),
    )
    ws = FakeWebSocket()

    asyncio.run(mgr._handle_deal_propose(
        room.room_id,
        "p0",
        {
            "target_player_id": players[1].player_id,
            "offer": {"resource": "Food", "qty": 2},
            "request": {"resource": "Oil", "qty": 1},
        },
        ws,
    ))

    push = next(msg for _, lobby_id, msg in sent if lobby_id == "p1" and msg["type"] == "deal_response")
    state = next(msg for _, lobby_id, msg in sent if lobby_id == "p1" and msg["type"] == "game_state")
    assert push["result"] == "proposed"
    assert push["deal"]["awaiting_id"] == players[1].player_id
    assert state["deals_awaiting_me"][0]["deal_id"] == push["deal_id"]
    assert state["deals_awaiting_me"][0]["awaiting_id"] == players[1].player_id


def test_deal_respond_return_updates_terms_and_notifies_proposer(monkeypatch):
    mgr, room, players = _bootstrap_game()
    farmer, miner = players
    farmer.receive_resources(ResourceType.FOOD, 2)
    deal = room.game.turn_manager.trading.propose_deal(
        farmer, miner, ResourceType.FOOD, 2, ResourceType.OIL, 1
    )
    sent = []
    monkeypatch.setattr(
        mgr,
        "_thread_safe_send",
        lambda room_id, lobby_id, msg: sent.append((room_id, lobby_id, msg)),
    )
    ws = FakeWebSocket()

    asyncio.run(mgr._handle_deal_respond(
        room.room_id,
        "p1",
        {
            "deal_id": deal.deal_id,
            "action": "return",
            "new_offer": {"resource": "Food", "qty": 1},
            "new_request": {"resource": "Oil", "qty": 2},
            "new_sweetener": -3,
            "message": "Need two Oil.",
        },
        ws,
    ))

    assert deal.status == DealStatus.RETURNED
    assert deal.awaiting_id == farmer.player_id
    assert ws.messages[0]["type"] == "deal_response_ack"
    assert ws.messages[0]["result"] == "returned"
    push = next(msg for _, lobby_id, msg in sent if lobby_id == "p0" and msg["type"] == "deal_response")
    assert push["result"] == "returned"
    assert push["from"] == miner.name
    assert push["deal"]["offer"] == {"resource": "Food", "qty": 1}
    assert push["deal"]["request"] == {"resource": "Oil", "qty": 2}
    assert push["deal"]["message"] == "Need two Oil."
    state = next(msg for _, lobby_id, msg in sent if lobby_id == "p0" and msg["type"] == "game_state")
    assert state["deals_awaiting_me"][0]["deal_id"] == deal.deal_id
    assert state["deals_awaiting_me"][0]["awaiting_id"] == farmer.player_id


def test_deal_respond_accept_returned_deal_moves_resources_once(monkeypatch):
    mgr, room, players = _bootstrap_game()
    farmer, miner = players
    farmer.receive_resources(ResourceType.FOOD, 2)
    miner.receive_resources(ResourceType.OIL, 2)
    deal = room.game.turn_manager.trading.propose_deal(
        farmer, miner, ResourceType.FOOD, 2, ResourceType.OIL, 1
    )
    room.game.turn_manager.trading.return_deal(
        deal,
        responder_id=miner.player_id,
        offer_resource=ResourceType.FOOD,
        offer_qty=1,
        request_resource=ResourceType.OIL,
        request_qty=2,
        message="Counter.",
    )
    sent = []
    farmer_food_before = farmer.inventory.get(ResourceType.FOOD)
    farmer_oil_before = farmer.inventory.get(ResourceType.OIL)
    miner_food_before = miner.inventory.get(ResourceType.FOOD)
    miner_oil_before = miner.inventory.get(ResourceType.OIL)
    monkeypatch.setattr(
        mgr,
        "_thread_safe_send",
        lambda room_id, lobby_id, msg: sent.append((room_id, lobby_id, msg)),
    )
    ws = FakeWebSocket()

    asyncio.run(mgr._handle_deal_respond(
        room.room_id,
        "p0",
        {"deal_id": deal.deal_id, "action": "accept"},
        ws,
    ))

    assert deal.status == DealStatus.ACCEPTED
    assert farmer.inventory.get(ResourceType.FOOD) == farmer_food_before - 1
    assert farmer.inventory.get(ResourceType.OIL) == farmer_oil_before + 2
    assert miner.inventory.get(ResourceType.FOOD) == miner_food_before + 1
    assert miner.inventory.get(ResourceType.OIL) == miner_oil_before - 2
    assert ws.messages[0]["result"] == "accepted"
    push = next(msg for _, lobby_id, msg in sent if lobby_id == "p1" and msg["type"] == "deal_response")
    assert push["result"] == "accepted"


def test_deal_respond_reject_sets_terminal_status(monkeypatch):
    mgr, room, players = _bootstrap_game()
    farmer, miner = players
    farmer.receive_resources(ResourceType.FOOD, 2)
    deal = room.game.turn_manager.trading.propose_deal(
        farmer, miner, ResourceType.FOOD, 2, None, 0
    )
    monkeypatch.setattr(mgr, "_thread_safe_send", lambda *args: None)
    ws = FakeWebSocket()

    asyncio.run(mgr._handle_deal_respond(
        room.room_id,
        "p1",
        {"deal_id": deal.deal_id, "action": "reject", "message": "No thanks."},
        ws,
    ))

    assert deal.status == DealStatus.REJECTED
    assert deal.awaiting_id is None
    assert deal.message == "No thanks."
    assert ws.messages[0]["result"] == "rejected"
