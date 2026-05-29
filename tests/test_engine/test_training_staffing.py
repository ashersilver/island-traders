from __future__ import annotations

from pathlib import Path

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.production import ProductionEngine
from island_traders.engine.game import (
    _migrate_capital_in_transit,
    _migrate_capital_inventory,
    _migrate_capital_ticks,
)
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.capacity import find_item
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import TrainingRegistry, TrainingRequest, TrainingStatus


def _player(pid: int, name: str, role: str = "Educator") -> Player:
    return Player(pid, name, [ROLES[role]], 100.0, is_human=True)


def _turn_manager(training: TrainingRegistry | None = None) -> TurnManager:
    market = Market()
    return TurnManager(
        players=[],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=FakeIOAdapter(),
        training=training or TrainingRegistry(),
    )


def _request(target: str, worker_count: int = 1, educator_id: int = 1) -> TrainingRequest:
    return TrainingRequest(
        batch_id=99,
        requester_id=0,
        worker_ids=list(range(worker_count)),
        educator_id=educator_id,
        transporter_id=None,
        dollops_to_educator=0.0,
        dollops_to_transporter=0.0,
        target_profession=target,
    )


def _staff(educator: Player, profession: Profession, count: int) -> None:
    educator.workforce.add_workers(
        count, training_level=1, profession=profession.value
    )


def _fund_training(educator: Player, courses: int = 20, expertise: int = 20) -> None:
    educator.receive_resources(ResourceType.COURSES, courses)
    educator.receive_resources(ResourceType.EXPERTISE, expertise)


def test_manager_capacity_min_of_2x_professor_and_lecturer():
    tm = _turn_manager()
    educator = _player(1, "Educator")
    _staff(educator, Profession.PROFESSOR, 3)
    _staff(educator, Profession.LECTURER, 5)
    assert tm._manager_course_capacity(educator) == 5

    educator = _player(1, "Educator")
    _staff(educator, Profession.PROFESSOR, 1)
    _staff(educator, Profession.LECTURER, 5)
    assert tm._manager_course_capacity(educator) == 2

    educator = _player(1, "Educator")
    _staff(educator, Profession.PROFESSOR, 2)
    assert tm._manager_course_capacity(educator) == 0


def test_technical_capacity_min_of_2x_td_and_instructors_staffing_only():
    """Technical-course staffing capacity is min(TD*2, Instructors).  The
    workshop is a SEPARATE per-trainee gate (see
    ``test_technical_workshop_caps_trainee_headcount``) so removing
    workshops does NOT change the staffing-only number — it just blocks
    admission via the prerequisite check."""
    tm = _turn_manager()
    educator = _player(1, "Educator")
    _staff(educator, Profession.TECHNICAL_DIRECTOR, 2)
    _staff(educator, Profession.INSTRUCTOR, 3)
    educator.capital_inventory["educator.technical_workshop"] = 2
    assert tm._technical_course_capacity(educator) == 3

    educator.capital_inventory.clear()
    # Staffing unchanged — workshop check happens separately.
    assert tm._technical_course_capacity(educator) == 3


def test_technical_course_requires_workshop_prerequisite():
    training = TrainingRegistry()
    tm = _turn_manager(training)
    educator = _player(1, "Educator")
    _staff(educator, Profession.TECHNICAL_DIRECTOR, 1)
    _staff(educator, Profession.INSTRUCTOR, 1)
    _fund_training(educator)

    ok, msg = tm._training_capacity_status(
        educator, _request(Profession.FARMING_TECHNICIAN.value)
    )

    assert not ok
    assert "no Technical Workshop" in msg


def test_manager_course_does_not_require_workshop():
    tm = _turn_manager()
    educator = _player(1, "Educator")
    _staff(educator, Profession.PROFESSOR, 1)
    _staff(educator, Profession.LECTURER, 1)
    _fund_training(educator)

    ok, msg = tm._training_capacity_status(educator, _request(Profession.NURSE.value))

    assert ok, msg


def test_staff_locked_for_course_duration():
    training = TrainingRegistry()
    educator = _player(1, "Educator")
    _staff(educator, Profession.PROFESSOR, 1)
    _staff(educator, Profession.LECTURER, 2)

    req1 = training.propose(
        0, [1], educator.player_id, 0.0, target_profession=Profession.BANKER.value
    )
    req2 = training.propose(
        0, [2], educator.player_id, 0.0, target_profession=Profession.BANKER.value
    )

    training.educator_approve(req1.batch_id)
    assert training.manager_courses_in_flight(educator.player_id) == 1
    training.educator_approve(req2.batch_id)
    assert training.manager_courses_in_flight(educator.player_id) == 2

    training.dispatch(req1.batch_id, year=0, season=0, num_seasons=4)
    training.dispatch(req2.batch_id, year=0, season=1, num_seasons=4)
    training.process_returns(year=0, season=1)
    assert training.manager_courses_in_flight(educator.player_id) == 2

    training.process_returns(year=req1.return_year, season=req1.return_season)
    assert req1.status == TrainingStatus.COMPLETED
    assert training.manager_courses_in_flight(educator.player_id) == 1


def test_expertise_debited_per_course():
    tm = _turn_manager()
    educator = _player(1, "Educator")
    _fund_training(educator, courses=4, expertise=4)

    tm._consume_training_capacity(educator, _request(Profession.NURSE.value))
    assert educator.inventory.get(ResourceType.EXPERTISE) == 2

    tm._consume_training_capacity(
        educator, _request(Profession.FARMING_TECHNICIAN.value)
    )
    assert educator.inventory.get(ResourceType.EXPERTISE) == 1


def test_course_slot_debited_per_course_unchanged():
    tm = _turn_manager()
    educator = _player(1, "Educator")
    _fund_training(educator, courses=5, expertise=5)

    tm._consume_training_capacity(
        educator, _request(Profession.NURSE.value, worker_count=13)
    )

    assert educator.inventory.get(ResourceType.COURSES) == 3


def test_capacity_blocks_third_manager_course_when_lecturers_pinned():
    training = TrainingRegistry()
    tm = _turn_manager(training)
    educator = _player(1, "Educator")
    _staff(educator, Profession.PROFESSOR, 1)
    _staff(educator, Profession.LECTURER, 2)
    _fund_training(educator)

    first = training.propose(0, [1], educator.player_id, 0.0, target_profession="Nurse")
    second = training.propose(0, [2], educator.player_id, 0.0, target_profession="Nurse")
    training.educator_approve(first.batch_id)
    training.educator_approve(second.batch_id)

    ok, msg = tm._training_capacity_status(educator, _request("Nurse"))

    assert not ok
    assert "Manager-course staffing full: 2/2" in msg


def test_technical_workshop_capital_item_renamed():
    item = find_item(CAPITAL_CATALOGUE, "educator.technical_workshop")
    assert item is not None
    assert item.name == "Technical Workshop"
    # Each workshop holds 6 trainees at a time (per-trainee headcount cap).
    assert item.effects["technical_workshop_trainees"] == 6
    assert find_item(CAPITAL_CATALOGUE, "educator.apprenticeship_programme") is None


def test_legacy_technical_workshop_save_keys_migrate():
    assert _migrate_capital_inventory(
        {"educator.apprenticeship_programme": 1, "educator.technical_workshop": 2}
    ) == {"educator.technical_workshop": 3}
    assert _migrate_capital_ticks(
        {"educator.apprenticeship_programme": [0], "educator.technical_workshop": [4]}
    ) == {"educator.technical_workshop": [0, 4]}
    assert _migrate_capital_in_transit(
        [{"item_id": "educator.apprenticeship_programme", "arrives_at_tick": 7}]
    ) == [{"item_id": "educator.technical_workshop", "arrives_at_tick": 7}]


def test_technical_workshop_caps_trainee_headcount():
    """Each Technical Workshop holds 6 trainees at a time across all
    concurrent technical batches (per-trainee, not per-course). Two
    workshops → 12 trainees. A batch that doesn't fit the remaining
    workshop seats should be rejected even when staffing is fully
    available."""
    training = TrainingRegistry()
    tm = _turn_manager(training)
    educator = _player(1, "Educator")
    # Plenty of staffing — 3 TD * 2 = 6 courses, 6 Instructors → 6 concurrent.
    _staff(educator, Profession.TECHNICAL_DIRECTOR, 3)
    _staff(educator, Profession.INSTRUCTOR, 6)
    _fund_training(educator)
    # 1 workshop = 6 trainee seats.
    educator.capital_inventory["educator.technical_workshop"] = 1

    # First batch of 4 trainees fits (6 - 0 = 6 seats free; uses 4).
    # Bypass propose() to avoid the annual university intake cap — this
    # test is about the workshop seat gate, not the intake cap.
    req1 = TrainingRequest(
        batch_id=101,
        requester_id=0,
        worker_ids=[10, 11, 12, 13],
        educator_id=educator.player_id,
        transporter_id=None,
        dollops_to_educator=0.0,
        dollops_to_transporter=0.0,
        target_profession=Profession.FARMING_TECHNICIAN.value,
    )
    training._requests.append(req1)
    training.educator_approve(req1.batch_id)   # status -> AWAITING_TRANSPORT (counts as in-flight)
    assert training.technical_trainees_in_flight(educator.player_id) == 4

    # Second batch of 3 trainees does NOT fit (6 - 4 = 2 seats free; needs 3).
    req2 = TrainingRequest(
        batch_id=102,
        requester_id=0,
        worker_ids=[20, 21, 22],
        educator_id=educator.player_id,
        transporter_id=None,
        dollops_to_educator=0.0,
        dollops_to_transporter=0.0,
        target_profession=Profession.FARMING_TECHNICIAN.value,
    )
    ok, msg = tm._training_capacity_status(educator, req2)
    assert ok is False
    assert "Technical Workshop capacity full" in msg
    assert "4/6 trainee seat(s)" in msg

    # With a second workshop the same batch fits (12 - 4 = 8 free; uses 3).
    educator.capital_inventory["educator.technical_workshop"] = 2
    ok2, _ = tm._training_capacity_status(educator, req2)
    assert ok2 is True


def test_technical_workshop_is_mandatory_minimum_for_educator():
    """Bootstrap follow-up (2026-05-25): without a starting Technical
    Workshop the Educator can't run any Technical course at game start
    (workshop is a hard prerequisite).  Mandatory-minimum keeps the
    Technical pipeline viable from turn 1; the player can deselect at
    the investing phase but is warned.

    Interim financing: until the proper Lease subsystem lands (see
    requirements/codex-tasks/capital-equipment-lease-2026-05.md when
    spec'd), players who can't afford the workshop outright can
    finance it via the existing 1/2/3-year Bank loans at the prevailing
    banker_quote_rate (posted funding + 2% margin + borrower risk)."""
    from island_traders.constants_capacity import MANDATORY_MINIMUM_INVESTMENT
    assert "educator.technical_workshop" in MANDATORY_MINIMUM_INVESTMENT["Educator"]


def test_legacy_apprenticeship_slot_callers_updated():
    """All legacy slot-pool names from before the technical-workshop
    redesign — and the earlier per-course `technical_workshop_slots`
    naming used in Codex's first cut — must be gone from the engine."""
    root = Path(__file__).resolve().parents[2] / "island_traders"
    source = "\n".join(
        path.read_text()
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )

    assert "apprenticeship_slot_capacity" not in source
    assert "apprenticeship_slots" not in source
    # The per-course `_slots` naming was superseded by the per-trainee
    # `_trainees` naming in the 2026-05-25 workshop-cap-6 follow-up.
    assert "technical_workshop_slot_capacity" not in source
    assert "technical_workshop_slots" not in source
