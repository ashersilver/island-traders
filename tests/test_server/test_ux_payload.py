from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.turn import TurnAction
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.server.app import GameManager, GameRoom, LobbyPlayer
from island_traders.server.ws_adapter import action_option_payload


def _bootstrap_game(role_names: list[str] | None = None):
    role_names = role_names or ["Banker", "Farmer"]
    mgr = GameManager()
    room = GameRoom(
        room_id="r1",
        name="Test",
        max_players=len(role_names),
        num_years=1,
        is_public=True,
        join_code="GS0001",
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

    config = GameConfig(
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
    )
    game = Game(config, FakeIOAdapter())
    game.setup()
    room.game = game
    room.lobby_to_engine_id = {
        lobby.player_id: engine_player.player_id
        for lobby, engine_player in zip(room.players, game.players)
    }
    return mgr, room, game.players


def test_action_payload_grouping():
    _, _, players = _bootstrap_game(["Banker", "Farmer"])
    farmer = players[1]
    options = {
        action.value: action_option_payload(action, farmer)
        for action in TurnAction
    }

    assert options["produce"]["group"] == "Production"
    assert options["apply_patent"]["group"] == "Production"
    assert options["market_buy"]["group"] == "Trade"
    assert options["propose_deal"]["group"] == "Trade"
    assert options["request_training"]["group"] == "People"
    assert options["arrange_transport"]["group"] == "People"
    assert options["purchase_capital"]["group"] == "Capital"
    assert options["invest"]["group"] == "Capital"
    assert options["take_loan"]["group"] == "Finance"
    assert options["manage_insurance"]["group"] == "Finance"
    assert options["view_market"]["group"] == "Info"
    assert options["inventory"]["group"] == "Info"
    assert all("recommended" in option for option in options.values())


def test_action_payload_finance_gated():
    _, _, players = _bootstrap_game(["Banker", "Farmer"])
    farmer = players[1]

    sell_policy = action_option_payload(TurnAction.SELL_INSURANCE, farmer)
    offer_loan = action_option_payload(TurnAction.OFFER_LOAN, farmer)

    assert sell_policy["enabled"] is False
    assert "Banking" in sell_policy["disabled_reason"]
    assert offer_loan["enabled"] is False
    assert "Banking" in offer_loan["disabled_reason"]


def test_training_pipeline_shape():
    mgr, room, players = _bootstrap_game(["Educator", "Farmer"])
    educator, farmer = players
    worker_id = farmer.workforce.active_workers[0].worker_id
    req = room.game.training.propose(
        requester_id=farmer.player_id,
        worker_ids=[worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=25.0,
        target_profession=Profession.FARMING_TECHNICIAN.value,
        year=0,
        season=0,
        transport_mode="transporter",
    )
    room.game.training.educator_approve(req.batch_id)
    room.game.training.arrange_transport(req.batch_id, transporter_id=educator.player_id)
    room.game.training.dispatch(req.batch_id, year=0, season=0)

    state = mgr.get_game_state(room.room_id, "p1")
    farmer_data = next(p for p in state["players"] if p["player_id"] == farmer.player_id)
    pipeline = farmer_data["training_pipeline"]

    assert len(pipeline) == 1
    batch = pipeline[0]
    assert set(batch) == {
        "batch_id",
        "worker_count",
        "target_profession",
        "engineer_specialty",
        "duration_seasons",
        "status",
        "educator_player_id",
        "educator_name",
        "transport_mode",
        "tickets_supplied_by_requester",
        "dollops_to_educator",
        "return_year",
        "return_season",
        "seasons_remaining",
        "counter_message",
        # 2026-05-27 training-expertise-deadlock brief Layer 3 fields.
        "blocker_reason",
        "seasons_blocked",
        "can_supply_expertise",
    }
    assert batch["batch_id"] == req.batch_id
    assert batch["worker_count"] == 1
    assert batch["target_profession"] == "Farming Technician"
    assert batch["status"] == "dispatched"
    assert batch["educator_player_id"] == educator.player_id
    assert batch["educator_name"] == educator.name
    assert batch["transport_mode"] == "transporter"
    assert batch["tickets_supplied_by_requester"] == 0
    assert batch["dollops_to_educator"] == 25.0
    assert batch["return_year"] == 1
    assert batch["return_season"] == "Summer"
    assert batch["seasons_remaining"] == 1
    assert batch["counter_message"] is None


def test_training_pipeline_empty():
    mgr, room, players = _bootstrap_game(["Educator", "Farmer"])

    state = mgr.get_game_state(room.room_id, "p1")
    farmer_data = next(p for p in state["players"] if p["player_id"] == players[1].player_id)

    assert farmer_data["training_pipeline"] == []


def test_finance_hidden_from_market_data():
    mgr, room, _ = _bootstrap_game(["Banker", "Farmer"])

    state = mgr.get_game_state(room.room_id, "p0")

    assert ResourceType.FINANCE.value not in state["market"]
    for snapshot in state["price_history"]:
        assert ResourceType.FINANCE.value not in snapshot["prices"]


def test_decision_hint_target_structured():
    mgr, room, players = _bootstrap_game(["Banker", "Farmer"])
    farmer = players[1]
    farmer.inventory.amounts[ResourceType.OIL] = 0

    state = mgr.get_game_state(room.room_id, "p1")
    farmer_data = next(p for p in state["players"] if p["player_id"] == farmer.player_id)
    hints = farmer_data["decision_hints"]
    oil_hint = next(
        hint for hint in hints
        if hint["target"]["type"] == "resource_shortfall"
        and hint["target"]["resource"] == ResourceType.OIL.value
    )

    assert oil_hint["text"]
    assert oil_hint["target"] == {
        "type": "resource_shortfall",
        "resource": ResourceType.OIL.value,
    }
