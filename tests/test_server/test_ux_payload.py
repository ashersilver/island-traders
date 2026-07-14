from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.events import EventResult
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.turn import TurnAction
from island_traders.constants import (
    EQUIPMENT_FAILURE_REPAIR_FRACTION,
    EQUIPMENT_REPAIR_SHIP_FREIGHT,
    EQUIPMENT_SPARES_REPAIR_DISCOUNT,
)
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.models.capacity import find_item
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


def test_game_state_exposes_winter_flu_payload():
    mgr, room, players = _bootstrap_game(["Farmer", "Doctor"])
    farmer = players[0]
    room.game._last_event_results = {
        farmer.player_id: EventResult(
            "Normal Operations + Winter Flu",
            yield_modifier=0.96,
            flu_strain_loss=0.20,
            flu_doses_needed=5,
            flu_doses_administered=5,
            flu_effective_loss=0.04,
        )
    }

    state = mgr.get_game_state(room.room_id, "p0")
    player_state = next(
        p for p in state["players"] if p["player_id"] == farmer.player_id
    )

    assert state["flu"] == {
        "season": "Winter",
        "strain_loss": 0.2,
        "active": True,
    }
    assert player_state["flu_strain_loss"] == 0.2
    assert player_state["flu_doses_needed"] == 5
    assert player_state["flu_doses_administered"] == 5
    assert player_state["flu_effective_loss"] == 0.04


def test_game_state_exposes_qol_payload():
    mgr, room, players = _bootstrap_game(["Farmer", "Doctor"])
    farmer = players[0]
    farmer._qol_score = 0.725
    farmer._food_coverage = 0.8
    farmer._health_coverage = 0.5
    farmer._pollution_index = 0.125

    state = mgr.get_game_state(room.room_id, "p0")
    player_state = next(
        p for p in state["players"] if p["player_id"] == farmer.player_id
    )

    assert player_state["qol_score"] == 0.725
    assert player_state["food_coverage"] == 0.8
    assert player_state["health_coverage"] == 0.5
    assert player_state["pollution_index"] == 0.125


def test_game_state_capital_owned_failed_units_include_repair_cost():
    mgr, room, players = _bootstrap_game(["Educator", "Manufacturer", "Transporter"])
    educator = players[0]
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    assert item is not None
    educator.add_capital(item.item_id, 1, acquired_tick=-4)
    educator.capital_units[item.item_id][0].status = "failed"
    educator.receive_resources(ResourceType.FREIGHT, EQUIPMENT_REPAIR_SHIP_FREIGHT)
    educator.receive_resources(ResourceType.SPARES, item.capacity_units)

    state = mgr.get_game_state(room.room_id, "p0")
    educator_data = next(p for p in state["players"] if p["player_id"] == educator.player_id)
    lab = next(
        c for c in educator_data["capacity"]["capital_owned"]
        if c["item_id"] == item.item_id
    )

    assert lab["repairable_failed"] == 1
    assert lab["repair_cost"] == {
        "dp": round(
            item.cost * EQUIPMENT_FAILURE_REPAIR_FRACTION
            * EQUIPMENT_SPARES_REPAIR_DISCOUNT,
            2,
        ),
        "freight": EQUIPMENT_REPAIR_SHIP_FREIGHT,
        "spares": item.capacity_units,
        "repairable": True,
        "reason": "",
    }


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
        "student_loan_requested",
        "loan_financed",
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
    assert batch["student_loan_requested"] is False
    assert batch["return_year"] == 1
    assert batch["return_season"] == "Summer"
    assert batch["seasons_remaining"] == 1
    assert batch["counter_message"] is None


def test_server_local_faculty_training_skips_passenger_seats_and_fee():
    mgr, room, players = _bootstrap_game(["Educator", "Farmer"])
    educator = players[0]

    result = mgr._submit_training_batch_row(
        room,
        educator,
        {
            "profession": Profession.LECTURER.value,
            "count": 1,
            "campus_player_id": "p0",
            "transport_mode": "air_ticket",
            "tickets_supplied_by_requester": 1,
            "dollops_to_educator": 50,
        },
        index=0,
        year=0,
        season=0,
    )

    assert result["status"] == "submitted"
    req = room.game.training.request_by_id(result["batch_id"])
    assert req.transport_mode == "self_training"
    assert req.tickets_supplied_by_requester == 0
    assert req.dollops_to_educator == 0.0


def test_server_cross_island_faculty_training_keeps_passenger_seats():
    mgr, room, players = _bootstrap_game(["Educator", "Farmer"])
    farmer = players[1]

    result = mgr._submit_training_batch_row(
        room,
        farmer,
        {
            "profession": Profession.LECTURER.value,
            "count": 1,
            "campus_player_id": "p0",
            "transport_mode": "air_ticket",
            "tickets_supplied_by_requester": 1,
            "dollops_to_educator": 50,
        },
        index=0,
        year=0,
        season=0,
    )

    assert result["status"] == "submitted"
    req = room.game.training.request_by_id(result["batch_id"])
    assert req.transport_mode == "air_ticket"
    assert req.tickets_supplied_by_requester == 1
    assert req.dollops_to_educator == 50.0


def test_server_training_batch_records_student_loan_flag():
    mgr, room, players = _bootstrap_game(["Educator", "Farmer"])
    farmer = players[1]

    result = mgr._submit_training_batch_row(
        room,
        farmer,
        {
            "profession": Profession.LECTURER.value,
            "count": 1,
            "campus_player_id": "p0",
            "dollops_to_educator": 50,
            "financing": True,
        },
        index=0,
        year=0,
        season=0,
    )

    assert result["status"] == "submitted"
    req = room.game.training.request_by_id(result["batch_id"])
    assert req.student_loan_requested is True

    state = mgr.get_game_state(room.room_id, "p1")
    farmer_data = next(p for p in state["players"] if p["player_id"] == farmer.player_id)
    assert farmer_data["training_pipeline"][0]["student_loan_requested"] is True


def test_personnel_training_counts_group_by_target_profession():
    mgr, room, players = _bootstrap_game(["Educator", "Farmer"])
    educator, farmer = players
    worker = farmer.workforce.add_workers(1)[0]
    worker_id = worker.worker_id
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
    farmer.workforce.dispatch_for_training([worker_id])

    state = mgr.get_game_state(room.room_id, "p1")
    farmer_data = next(p for p in state["players"] if p["player_id"] == farmer.player_id)
    professions = farmer_data["workforce_professions"]

    assert professions[Profession.FARMING_TECHNICIAN.value]["training"] == 1
    assert professions.get(Profession.UNSKILLED.value, {}).get("training", 0) == 0
    assert farmer_data["workforce_training_bands"]["Technician"] == 1


def test_training_pipeline_empty():
    mgr, room, players = _bootstrap_game(["Educator", "Farmer"])

    state = mgr.get_game_state(room.room_id, "p1")
    farmer_data = next(p for p in state["players"] if p["player_id"] == players[1].player_id)

    assert farmer_data["training_pipeline"] == []


def test_pending_actions_contains_review_training_for_educator():
    mgr, room, players = _bootstrap_game(["Educator", "Farmer"])
    educator, farmer = players
    worker_id = farmer.workforce.active_workers[0].worker_id
    room.game.training.propose(
        requester_id=farmer.player_id,
        worker_ids=[worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=25.0,
        target_profession=Profession.FARMING_TECHNICIAN.value,
        year=0,
        season=0,
        transport_mode="air_ticket",
    )

    educator_state = mgr.get_game_state(room.room_id, "p0")
    farmer_state = mgr.get_game_state(room.room_id, "p1")

    assert "review_training" in educator_state["pending_actions"]
    assert "review_training" not in farmer_state["pending_actions"]


def test_pending_actions_contains_arrange_transport_for_transporter_only():
    mgr, room, players = _bootstrap_game(["Educator", "Farmer", "Transporter"])
    educator, farmer, _transporter = players
    worker_id = farmer.workforce.active_workers[0].worker_id
    req = room.game.training.propose(
        requester_id=farmer.player_id,
        worker_ids=[worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=25.0,
        target_profession=Profession.FARMING_TECHNICIAN.value,
        year=0,
        season=0,
        transport_mode="cargo",
    )
    room.game.training.educator_approve(req.batch_id)

    transporter_state = mgr.get_game_state(room.room_id, "p2")
    farmer_state = mgr.get_game_state(room.room_id, "p1")

    assert "arrange_transport" in transporter_state["pending_actions"]
    assert "arrange_transport" not in farmer_state["pending_actions"]


def test_pending_actions_contains_review_staffing_for_provider_only():
    mgr, room, players = _bootstrap_game(["Doctor", "Farmer"])
    doctor, farmer = players
    room.game.staffing.propose(
        requester_id=farmer.player_id,
        provider_id=doctor.player_id,
        profession=Profession.NURSE.value,
        staff_count=1,
        duration_seasons=1,
        fee_total=20.0,
        year=0,
        season=0,
    )

    doctor_state = mgr.get_game_state(room.room_id, "p0")
    farmer_state = mgr.get_game_state(room.room_id, "p1")

    assert "review_staffing_requests" in doctor_state["pending_actions"]
    assert "review_staffing_requests" not in farmer_state["pending_actions"]


def test_pending_actions_contains_repair_capital_for_repairable_failed_unit():
    mgr, room, players = _bootstrap_game(["Educator", "Manufacturer", "Transporter"])
    educator = players[0]
    educator.add_capital("educator.research_lab", 1, acquired_tick=-4)
    educator.capital_units["educator.research_lab"][0].status = "failed"

    state = mgr.get_game_state(room.room_id, "p0")

    assert "repair_capital" in state["pending_actions"]


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


def test_game_state_includes_revenue_opportunities():
    mgr, room, players = _bootstrap_game(["Manufacturer", "Farmer"])
    manufacturer = players[0]

    state = mgr.get_game_state(room.room_id, "p0")
    manufacturer_data = next(
        p for p in state["players"] if p["player_id"] == manufacturer.player_id
    )
    opportunities = manufacturer_data["revenue_opportunities"]
    farm = next(
        opp for opp in opportunities
        if opp["output"] == ResourceType.FARM_MACHINERY.value
    )

    assert farm["product_line"] == "FarmMachinery"
    assert farm["structural_demand_units"] >= 1
    assert farm["inputs_to_stockpile"]["Metal"] > 0
    assert farm["required_professions"]
