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


def _bootstrap_game(role_names: list[str]):
    mgr = GameManager()
    room = GameRoom(
        room_id="batch-room",
        name="Batch Room",
        max_players=len(role_names),
        num_years=1,
        is_public=True,
        join_code="BATCH1",
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
            [
                PlayerSpec(
                    name=f"Player{idx}",
                    role_names=[role],
                    is_human=True,
                )
                for idx, role in enumerate(role_names)
            ],
            num_years=1,
            starting_dollops=100.0,
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


def test_order_batch_ws_handler_returns_per_row_results():
    mgr, room, players = _bootstrap_game(["Farmer", "Miner"])
    buyer, seller = players
    oil_before = buyer.inventory.get(ResourceType.OIL)
    seller.receive_resources(ResourceType.OIL, 2)
    room.game.market.post_offer(seller, ResourceType.OIL, 10.0, 2)
    ws = _WS()

    asyncio.run(mgr._handle_order_batch(
        room.room_id,
        "p0",
        {
            "batch_ref": "ob-1",
            "orders": [
                {"side": "buy", "resource": "Oil", "quantity": 1},
                {"side": "sell", "resource": "Oil", "quantity": 99},
            ],
        },
        ws,
    ))

    result = ws.sent[0]
    assert result["type"] == "order_batch_result"
    assert result["batch_ref"] == "ob-1"
    assert result["results"][0]["status"] == "filled"
    assert result["results"][1]["status"] == "rejected"
    assert buyer.inventory.get(ResourceType.OIL) == oil_before + 1


def test_training_batch_ws_handler_submits_and_rejects_independent_rows():
    mgr, room, players = _bootstrap_game(["Farmer", "Educator"])
    farmer, educator = players
    ws = _WS()

    asyncio.run(mgr._handle_training_batch(
        room.room_id,
        "p0",
        {
            "batch_ref": "tb-1",
            "requests": [
                {"profession": "Nurse", "count": 1, "campus_player_id": educator.player_id},
                {"profession": "Professor", "count": 2, "campus_player_id": educator.player_id},
            ],
        },
        ws,
    ))

    result = ws.sent[0]
    assert result["type"] == "training_batch_result"
    assert result["batch_ref"] == "tb-1"
    assert result["results"][0]["status"] == "submitted"
    assert result["results"][0]["batch_id"] >= 0
    assert result["results"][1]["status"] == "rejected"
    req = room.game.training.request_by_id(result["results"][0]["batch_id"])
    assert req.requester_id == farmer.player_id
    assert req.educator_id == educator.player_id
    room.game.training.educator_approve(req.batch_id)
    assert room.game.training.request_by_id(req.batch_id).status.value == "awaiting_transport"


def test_training_batch_server_computes_technician_duration_and_settling():
    mgr, room, players = _bootstrap_game(["Farmer", "Educator"])
    farmer, educator = players
    educator.capital_units.pop("educator.technical_workshop", None)
    ws = _WS()

    asyncio.run(mgr._handle_training_batch(
        room.room_id,
        "p0",
        {
            "batch_ref": "tb-tech",
            "requests": [
                {
                    "profession": "FarmingTechnician",
                    "count": 1,
                    "campus_player_id": educator.player_id,
                    "dollops_to_educator": 0,
                },
            ],
        },
        ws,
    ))

    result = ws.sent[0]
    assert result["results"][0]["status"] == "submitted"
    req = room.game.training.request_by_id(result["results"][0]["batch_id"])
    assert req.requester_id == farmer.player_id
    assert req.duration_seasons == 2
    assert req.settling_seasons_on_return == 1


def test_game_state_exposes_training_options_for_desk_dialog():
    # #158: the Training Desk dialog reads a read-only training_options field
    # (professions with remaining capacity + eligible-worker budget) so it can
    # build its dropdowns without a per-field round-trip.
    mgr, room, players = _bootstrap_game(["Farmer", "Educator"])

    state = mgr.get_game_state(room.room_id, "p0")
    assert state is not None
    farmer_pd = next(p for p in state["players"] if p["lobby_player_id"] == "p0")

    opts = farmer_pd["training_options"]
    assert set(opts) >= {"professions", "eligible_worker_count", "exhausted"}
    assert isinstance(opts["professions"], list)
    assert opts["eligible_worker_count"] >= 0
    # Every offered profession carries the fields the dialog renders.
    for prof in opts["professions"]:
        assert set(prof) >= {"value", "label", "remaining", "annual_cap", "suggested_count"}
        assert prof["remaining"] > 0
    # Offered and exhausted sets are disjoint.
    offered = {p["value"] for p in opts["professions"]}
    exhausted = {p["value"] for p in opts["exhausted"]}
    assert offered.isdisjoint(exhausted)
