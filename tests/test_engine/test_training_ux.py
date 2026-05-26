from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import STARTING_INVENTORY
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.engine.events import EventResult
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import (
    TrainingCapacityError, TrainingRegistry, TrainingStatus,
)


def _player(pid: int, name: str, role: str, is_human: bool = True) -> Player:
    return Player(pid, name, [ROLES[role]], 500.0, is_human=is_human)


def _turn_manager(players, training, io=None) -> TurnManager:
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io or FakeIOAdapter(),
        training=training,
    )


def _prepare_manager_training(educator: Player, courses: int = 10, expertise: int = 20) -> None:
    educator.receive_resources(ResourceType.COURSES, courses)
    educator.receive_resources(ResourceType.EXPERTISE, expertise)
    educator.workforce.add_workers(2, training_level=1, profession=Profession.PROFESSOR.value)
    educator.workforce.add_workers(2, training_level=1, profession=Profession.LECTURER.value)


def _nurse_request(
    training: TrainingRegistry,
    requester: Player,
    educator: Player,
    count: int,
    tickets_supplied_by_requester: int = 0,
    fee: float = 0.0,
):
    workers = requester.workforce.add_workers(count)
    return training.propose(
        requester_id=requester.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=fee,
        target_profession=Profession.NURSE.value,
        year=0,
        season=0,
        transport_mode="air_ticket",
        tickets_supplied_by_requester=tickets_supplied_by_requester,
    )


def test_educator_starts_with_10_passenger_seats():
    assert STARTING_INVENTORY["Educator"]["PassengerSeats"] == 10


def test_request_with_zero_self_supplied_tickets_uses_educator_inventory():
    requester = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 5)
    _prepare_manager_training(educator)
    training = TrainingRegistry()
    req = _nurse_request(training, requester, educator, count=3)
    tm = _turn_manager([requester, educator], training)

    assert tm._approve_training_request(educator, requester, req, TurnResult(1, 0, 0), "Spring", 0)
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 2
    assert requester.inventory.get(ResourceType.PASSENGER_SEATS) == 0


def test_request_with_partial_self_supplied_tickets_splits_consumption():
    requester = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    requester.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 5)
    _prepare_manager_training(educator)
    training = TrainingRegistry()
    req = _nurse_request(training, requester, educator, count=5, tickets_supplied_by_requester=2)
    tm = _turn_manager([requester, educator], training)

    assert tm._approve_training_request(educator, requester, req, TurnResult(1, 0, 0), "Spring", 0)
    assert requester.inventory.get(ResourceType.PASSENGER_SEATS) == 0
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 2


def test_request_with_full_self_supplied_tickets_skips_educator_ticket_gate():
    requester = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    requester.receive_resources(ResourceType.PASSENGER_SEATS, 4)
    _prepare_manager_training(educator)
    training = TrainingRegistry()
    req = _nurse_request(training, requester, educator, count=4, tickets_supplied_by_requester=4)
    tm = _turn_manager([requester, educator], training)

    assert tm._approve_training_request(educator, requester, req, TurnResult(1, 0, 0), "Spring", 0)
    assert req.status == TrainingStatus.DISPATCHED
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 0
    assert requester.inventory.get(ResourceType.PASSENGER_SEATS) == 0


def test_ai_educator_fee_drops_when_requester_self_supplies_tickets():
    requester = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator", is_human=False)
    training = TrainingRegistry()
    tm = _turn_manager([requester, educator], training)
    no_self_supply = _nurse_request(training, requester, educator, count=3)
    full_self_supply = _nurse_request(
        training, requester, educator, count=3, tickets_supplied_by_requester=3
    )

    assert tm._ai_training_required_offer(no_self_supply) - tm._ai_training_required_offer(full_self_supply) == (
        3 * tm.market.current_price(ResourceType.PASSENGER_SEATS)
    )


def test_ai_educator_approves_lower_offer_when_requester_self_supplies():
    requester = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator", is_human=False)
    requester.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    _prepare_manager_training(educator)
    training = TrainingRegistry()
    req = _nurse_request(
        training,
        requester,
        educator,
        count=2,
        tickets_supplied_by_requester=2,
        fee=40.0,
    )
    tm = _turn_manager([requester, educator], training)

    tm._ai_educator_respond(educator, requester, req, "Spring", 0)

    assert req.status == TrainingStatus.DISPATCHED
    assert requester.inventory.get(ResourceType.PASSENGER_SEATS) == 0
    assert educator.dollops == 540.0


def test_dispatch_fails_when_requester_promises_tickets_but_lacks_inventory():
    requester = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    requester.receive_resources(ResourceType.PASSENGER_SEATS, 1)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 5)
    _prepare_manager_training(educator)
    training = TrainingRegistry()
    req = _nurse_request(training, requester, educator, count=3, tickets_supplied_by_requester=3)
    tm = _turn_manager([requester, educator], training)

    assert not tm._approve_training_request(educator, requester, req, TurnResult(1, 0, 0), "Spring", 0)
    assert req.status == TrainingStatus.AWAITING_EDUCATOR
    assert requester.inventory.get(ResourceType.PASSENGER_SEATS) == 1
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 5


def test_training_request_reserves_workers_until_terminal_status():
    requester = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    worker = requester.workforce.add_workers(1)[0]
    training = TrainingRegistry()
    req = training.propose(
        requester_id=requester.player_id,
        worker_ids=[worker.worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=40.0,
        target_profession=Profession.NURSE.value,
        year=0,
        season=0,
        transport_mode="air_ticket",
    )

    try:
        training.propose(
            requester_id=requester.player_id,
            worker_ids=[worker.worker_id],
            educator_id=educator.player_id,
            dollops_to_educator=40.0,
            target_profession=Profession.NURSE.value,
            year=0,
            season=0,
            transport_mode="air_ticket",
        )
    except TrainingCapacityError as exc:
        assert "already committed" in str(exc)
    else:  # pragma: no cover - assertion helper
        raise AssertionError("duplicate worker should be rejected while request is active")

    training.educator_reject(req.batch_id)
    replacement = training.propose(
        requester_id=requester.player_id,
        worker_ids=[worker.worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=40.0,
        target_profession=Profession.NURSE.value,
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    assert replacement.batch_id == 1


def test_ai_educator_revisits_pending_request_after_capacity_clears():
    requester = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator", is_human=False)
    requester.dollops = 500.0
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 1)
    _prepare_manager_training(educator, courses=0, expertise=4)
    training = TrainingRegistry()
    req = _nurse_request(training, requester, educator, count=1, fee=100.0)
    tm = _turn_manager([requester, educator], training)
    event = EventResult("Normal", 1.0)

    tm.execute_turn(educator, event, year=0, season_index=0)
    assert req.status == TrainingStatus.AWAITING_EDUCATOR
    assert requester.workforce.training_count == 0

    educator.receive_resources(ResourceType.COURSES, 1)
    educator.receive_resources(ResourceType.EXPERTISE, 2)
    tm.execute_turn(educator, event, year=0, season_index=1)

    assert req.status == TrainingStatus.DISPATCHED
    assert requester.workforce.training_count == 1


class SummaryCaptureIO(FakeIOAdapter):
    def __init__(self, confirm_value: bool):
        super().__init__()
        self.confirm_value = confirm_value
        self.request_summaries: list[dict] = []

    def confirm(self, prompt, request_summary=None):
        if request_summary is not None:
            self.request_summaries.append(request_summary)
        return self.confirm_value

    def ask_dollop_amount(self, prompt, max_dollops, prefill=0.0):
        return 0.0


def test_approve_prompt_payload_includes_request_summary():
    requester = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    _prepare_manager_training(educator)
    training = TrainingRegistry()
    _nurse_request(training, requester, educator, count=2, tickets_supplied_by_requester=1, fee=70.0)
    io = SummaryCaptureIO(confirm_value=False)
    tm = _turn_manager([requester, educator], training, io)

    tm._action_review_training(educator, TurnResult(1, 0, 0), "Spring", 0)

    summary = io.request_summaries[0]
    assert summary["trainee_count"] == 2
    assert summary["target_profession"] == "Nurse"
    assert summary["transport_mode"] == "air_ticket"
    assert summary["tickets_supplied_by_requester"] == 1
    assert summary["tickets_supplied_by_educator"] == 1
    assert summary["dollops_to_educator"] == 70.0


def test_counter_prompt_payload_includes_request_summary():
    requester = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    training = TrainingRegistry()
    req = _nurse_request(training, requester, educator, count=1, fee=50.0)
    training.educator_counter(req.batch_id, 80.0, "Need a better fee.")
    io = SummaryCaptureIO(confirm_value=False)
    tm = _turn_manager([requester, educator], training, io)

    tm._review_training_counteroffers(requester, TurnResult(0, 0, 0), "Spring", 0)

    summary = io.request_summaries[0]
    assert summary["trainee_count"] == 1
    assert summary["target_profession"] == "Nurse"
    assert summary["transport_mode"] == "air_ticket"
    assert summary["dollops_to_educator"] == 80.0
