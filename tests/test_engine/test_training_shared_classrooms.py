from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import TrainingRegistry, TrainingRequest


def _player(pid: int = 1) -> Player:
    return Player(pid, "Educator", [ROLES["Educator"]], 100.0, is_human=True)


def _turn_manager(training: TrainingRegistry) -> TurnManager:
    market = Market()
    return TurnManager(
        players=[],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=FakeIOAdapter(),
        training=training,
    )


def _staff_manager_course(educator: Player) -> None:
    educator.workforce.add_workers(3, training_level=1, profession=Profession.PROFESSOR.value)
    educator.workforce.add_workers(6, training_level=1, profession=Profession.LECTURER.value)


def _staff_technical_course(educator: Player) -> None:
    educator.workforce.add_workers(
        3, training_level=1, profession=Profession.TECHNICAL_DIRECTOR.value
    )
    educator.workforce.add_workers(6, training_level=1, profession=Profession.INSTRUCTOR.value)
    educator.capital_inventory["educator.technical_workshop"] = 3


def _fund_training(educator: Player, courses: int = 20, expertise: int = 20) -> None:
    educator.receive_resources(ResourceType.COURSES, courses)
    educator.receive_resources(ResourceType.EXPERTISE, expertise)


def _request(
    batch_id: int,
    profession: str,
    worker_count: int,
    *,
    year: int = 0,
    season: int = 0,
    educator_id: int = 1,
) -> TrainingRequest:
    return TrainingRequest(
        batch_id=batch_id,
        requester_id=10 + batch_id,
        worker_ids=list(range(batch_id * 100, batch_id * 100 + worker_count)),
        educator_id=educator_id,
        transporter_id=None,
        dollops_to_educator=0.0,
        dollops_to_transporter=0.0,
        target_profession=profession,
        proposed_year=year,
        proposed_season=season,
    )


def _add_and_approve(training: TrainingRegistry, req: TrainingRequest) -> None:
    training._requests.append(req)
    training.educator_approve(req.batch_id)


def test_same_profession_same_season_shares_one_classroom_and_one_course_slot():
    training = TrainingRegistry()
    tm = _turn_manager(training)
    educator = _player()
    _staff_manager_course(educator)
    _fund_training(educator, courses=2, expertise=4)

    first = _request(1, Profession.ENGINEER.value, 1)
    second = _request(2, Profession.ENGINEER.value, 1)

    tm._consume_training_capacity(educator, first, 0, 0)
    _add_and_approve(training, first)
    assert educator.inventory.get(ResourceType.COURSES) == 1
    assert educator.inventory.get(ResourceType.EXPERTISE) == 2
    assert training.manager_courses_in_flight(educator.player_id) == 1

    ok, msg = tm._training_capacity_status(educator, second, 0, 0)
    assert ok, msg
    tm._consume_training_capacity(educator, second, 0, 0)
    _add_and_approve(training, second)

    assert educator.inventory.get(ResourceType.COURSES) == 1
    assert educator.inventory.get(ResourceType.EXPERTISE) == 2
    assert training.manager_courses_in_flight(educator.player_id) == 1


def test_thirteenth_trainee_opens_second_classroom_and_charges_expertise():
    training = TrainingRegistry()
    tm = _turn_manager(training)
    educator = _player()
    _staff_manager_course(educator)
    _fund_training(educator, courses=3, expertise=6)

    full_class = _request(1, Profession.ENGINEER.value, 12)
    thirteenth = _request(2, Profession.ENGINEER.value, 1)

    tm._consume_training_capacity(educator, full_class, 0, 0)
    _add_and_approve(training, full_class)
    assert training.manager_courses_in_flight(educator.player_id) == 1

    ok, msg = tm._training_capacity_status(educator, thirteenth, 0, 0)
    assert ok, msg
    tm._consume_training_capacity(educator, thirteenth, 0, 0)
    _add_and_approve(training, thirteenth)

    assert educator.inventory.get(ResourceType.COURSES) == 1
    assert educator.inventory.get(ResourceType.EXPERTISE) == 2
    assert training.manager_courses_in_flight(educator.player_id) == 2


def test_different_professions_or_seasons_do_not_share_classrooms():
    training = TrainingRegistry()
    tm = _turn_manager(training)
    educator = _player()
    _staff_manager_course(educator)
    _fund_training(educator, courses=5, expertise=10)

    engineer = _request(1, Profession.ENGINEER.value, 1, season=0)
    nurse = _request(2, Profession.NURSE.value, 1, season=0)
    next_season_engineer = _request(3, Profession.ENGINEER.value, 1, season=1)

    for req in (engineer, nurse, next_season_engineer):
        ok, msg = tm._training_capacity_status(educator, req)
        assert ok, msg
        tm._consume_training_capacity(educator, req)
        _add_and_approve(training, req)
        if req is engineer:
            training.dispatch(req.batch_id, year=0, season=0)

    assert educator.inventory.get(ResourceType.COURSES) == 2
    assert educator.inventory.get(ResourceType.EXPERTISE) == 4
    assert training.manager_courses_in_flight(educator.player_id) == 3


def test_awaiting_transport_batches_share_the_current_processing_season():
    training = TrainingRegistry()
    tm = _turn_manager(training)
    educator = _player()
    _staff_manager_course(educator)
    _fund_training(educator, courses=3, expertise=6)

    old_pending = _request(1, Profession.ENGINEER.value, 1, season=0)
    later_pending = _request(2, Profession.ENGINEER.value, 1, season=1)
    _add_and_approve(training, old_pending)
    _add_and_approve(training, later_pending)

    assert training.manager_courses_in_flight(educator.player_id) == 2
    assert training.manager_courses_in_flight(educator.player_id, 0, 2) == 1

    new_current = _request(3, Profession.ENGINEER.value, 1, season=2)
    assert tm._incremental_courses_for_request(new_current, 0, 2) == 0


def test_manager_and_technician_expertise_charged_per_incremental_classroom():
    training = TrainingRegistry()
    tm = _turn_manager(training)
    educator = _player()
    _staff_manager_course(educator)
    _staff_technical_course(educator)
    _fund_training(educator, courses=6, expertise=12)

    manager_first = _request(1, Profession.ENGINEER.value, 1)
    manager_second = _request(2, Profession.ENGINEER.value, 1)
    tech_first = _request(3, Profession.FARMING_TECHNICIAN.value, 1)
    tech_second = _request(4, Profession.FARMING_TECHNICIAN.value, 1)

    tm._consume_training_capacity(educator, manager_first, 0, 0)
    _add_and_approve(training, manager_first)
    assert educator.inventory.get(ResourceType.EXPERTISE) == 10

    tm._consume_training_capacity(educator, manager_second, 0, 0)
    _add_and_approve(training, manager_second)
    assert educator.inventory.get(ResourceType.EXPERTISE) == 10

    tm._consume_training_capacity(educator, tech_first, 0, 0)
    _add_and_approve(training, tech_first)
    assert educator.inventory.get(ResourceType.EXPERTISE) == 9

    tm._consume_training_capacity(educator, tech_second, 0, 0)
    _add_and_approve(training, tech_second)
    assert educator.inventory.get(ResourceType.EXPERTISE) == 9


def test_single_large_batch_still_needs_two_classrooms():
    training = TrainingRegistry()
    tm = _turn_manager(training)
    educator = _player()
    _staff_manager_course(educator)
    _fund_training(educator, courses=3, expertise=6)

    large = _request(1, Profession.ENGINEER.value, 13)

    ok, msg = tm._training_capacity_status(educator, large, 0, 0)
    assert ok, msg
    tm._consume_training_capacity(educator, large, 0, 0)
    _add_and_approve(training, large)

    assert educator.inventory.get(ResourceType.COURSES) == 1
    assert educator.inventory.get(ResourceType.EXPERTISE) == 2
    assert training.manager_courses_in_flight(educator.player_id) == 2
