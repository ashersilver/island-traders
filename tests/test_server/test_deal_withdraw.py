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


def _bootstrap_game(role_names=None):
    role_names = role_names or ["Farmer", "Miner"]
    mgr = GameManager()
    room = GameRoom(
        room_id="withdrawroom",
        name="Withdraw",
        max_players=len(role_names),
        num_years=1,
        is_public=True,
        join_code="WD0001",
        creator_id="p0",
    )
    room.players = [
        LobbyPlayer(player_id=f"p{i}", name=f"Player{i}", role_names=[r])
        for i, r in enumerate(role_names)
    ]
    room.status = "running"
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}
    game = Game(
        GameConfig(
            player_specs=[
                PlayerSpec(name=f"Player{i}", role_names=[r], is_human=True)
                for i, r in enumerate(role_names)
            ],
            num_years=1,
            starting_dollops=100.0,
        ),
        FakeIOAdapter(),
    )
    game.setup()
    room.game = game
    room.lobby_to_engine_id = {
        lobby.player_id: engine.player_id
        for lobby, engine in zip(room.players, game.players)
    }
    return mgr, room, game.players


def _propose(room, farmer, miner):
    farmer.receive_resources(ResourceType.FOOD, 2)
    return room.game.turn_manager.trading.propose_deal(
        farmer, miner, ResourceType.FOOD, 2, ResourceType.OIL, 1
    )


def test_proposer_withdraws_pending_deal_and_counterparty_is_notified(monkeypatch):
    mgr, room, players = _bootstrap_game()
    farmer, miner = players
    deal = _propose(room, farmer, miner)
    food_before = (farmer.inventory.get(ResourceType.FOOD),
                   miner.inventory.get(ResourceType.FOOD))

    sent = []
    monkeypatch.setattr(mgr, "_thread_safe_send",
                        lambda rid, lid, msg: sent.append((lid, msg)))
    ws = FakeWebSocket()
    asyncio.run(mgr._handle_deal_withdraw(
        room.room_id, "p0", {"deal_id": deal.deal_id}, ws))

    ack = next(m for m in ws.messages if m.get("type") == "deal_response_ack")
    assert ack["result"] == "withdrawn"
    assert deal.status is DealStatus.WITHDRAWN
    assert deal.awaiting_id is None
    # Counterparty (p1) gets a withdrawn push and no longer sees it awaiting.
    push = next(m for lid, m in sent if lid == "p1" and m["type"] == "deal_response")
    assert push["result"] == "withdrawn"
    state = next(m for lid, m in sent if lid == "p1" and m["type"] == "game_state")
    assert all(d["deal_id"] != deal.deal_id for d in state["deals_awaiting_me"])
    # Nothing was escrowed, so inventories are untouched.
    assert (farmer.inventory.get(ResourceType.FOOD),
            miner.inventory.get(ResourceType.FOOD)) == food_before


def test_withdraw_after_accept_is_rejected(monkeypatch):
    mgr, room, players = _bootstrap_game()
    farmer, miner = players
    deal = _propose(room, farmer, miner)
    miner.receive_resources(ResourceType.OIL, 1)
    room.game.turn_manager.trading.accept_deal(
        deal, acceptor=miner, proposer=farmer, acquired_tick=0,
        players=room.game.players,
    )
    ws = FakeWebSocket()
    asyncio.run(mgr._handle_deal_withdraw(
        room.room_id, "p0", {"deal_id": deal.deal_id}, ws))
    err = ws.messages[-1]
    assert err["type"] == "error"
    assert "cannot withdraw" in err["message"] or "already" in err["message"]
    assert deal.status is DealStatus.ACCEPTED


def test_non_proposer_cannot_withdraw(monkeypatch):
    mgr, room, players = _bootstrap_game()
    farmer, miner = players
    deal = _propose(room, farmer, miner)
    ws = FakeWebSocket()
    # p1 is the target, not the proposer.
    asyncio.run(mgr._handle_deal_withdraw(
        room.room_id, "p1", {"deal_id": deal.deal_id}, ws))
    err = ws.messages[-1]
    assert err["type"] == "error"
    assert deal.status is DealStatus.PENDING
