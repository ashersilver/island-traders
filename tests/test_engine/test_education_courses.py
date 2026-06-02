"""Tests for Education Model Phase 2 — Courses resource + Course-gated training.

Covers:
  * `ResourceType.COURSES` exists with a base price.
  * Educator has a Courses production recipe that consumes Expertise.
  * Patents recipe now consumes a small Expertise input.
  * `TurnManager.courses_needed` class-size (ceil) math.
  * Standard training approval is Course-gated: pending when the Educator
    has no Courses, consumes ceil(n/12) on approval.
  * Tutor → Instructor consolidation: enum/labels/capacity moved over.
"""
from __future__ import annotations

from island_traders.constants import (
    BASE_PRICES, MAX_CLASS_SIZE_PER_COURSE, UNIVERSITY_CAPACITY,
    STARTING_WORKFORCE, STARTING_WORKERS_BY_PROFESSION, STARTING_INVENTORY,
)
from island_traders.constants_capacity import PRODUCTION_RECIPES
from island_traders.models.resource import ResourceType
from island_traders.models.profession import (
    Profession, PROFESSION_BAND, WorkerBand, PROFESSION_LABEL,
)


# ---------------------------------------------------------------------------
# Resource + recipes
# ---------------------------------------------------------------------------

def test_courses_resource_exists_with_price():
    assert ResourceType.COURSES.value == "Courses"
    assert BASE_PRICES["Courses"] == 23.75
    assert BASE_PRICES["Expertise"] == 17.1


def test_educator_has_courses_recipe_consuming_expertise():
    edu = [r for r in PRODUCTION_RECIPES if r.role == "Educator"]
    outputs = {r.output for r in edu}
    assert "Courses" in outputs
    assert "Expertise" in outputs
    assert "Patents" in outputs
    courses = next(r for r in edu if r.output == "Courses")
    assert courses.inputs.get("Expertise", 0) > 0, "Courses must consume Expertise"
    patents = next(r for r in edu if r.output == "Patents")
    assert patents.inputs.get("Expertise", 0) > 0, "Patents now consume Expertise too"


# ---------------------------------------------------------------------------
# Class-size math
# ---------------------------------------------------------------------------

def test_courses_needed_class_size_ceiling():
    from island_traders.engine.turn import TurnManager
    cn = TurnManager.courses_needed
    assert MAX_CLASS_SIZE_PER_COURSE == 12
    assert cn(0) == 0
    assert cn(1) == 1
    assert cn(12) == 1
    assert cn(13) == 2
    assert cn(24) == 2
    assert cn(25) == 3


# ---------------------------------------------------------------------------
# Tutor → Instructor consolidation
# ---------------------------------------------------------------------------

def test_tutor_consolidated_into_instructor():
    assert not hasattr(Profession, "TUTOR")
    assert Profession.INSTRUCTOR.value == "Instructor"
    assert PROFESSION_BAND[Profession.INSTRUCTOR] == WorkerBand.TECHNICIAN
    assert PROFESSION_LABEL[Profession.INSTRUCTOR] == "Instructor"
    assert "Instructor" in UNIVERSITY_CAPACITY
    assert "Tutor" not in UNIVERSITY_CAPACITY


def test_educator_starting_workforce_bootstrap_shape():
    """Option-B faculty mix (2026-05-25 bootstrap follow-up): 2 Prof + 4 Lect
    + 1 TD + 4 Instructor.  Lecturers are required so Manager-tier training
    is viable from turn 1 — without them, training a first Lecturer is
    chicken-and-egg (Lecturer is itself Manager-band so it needs an
    existing Lecturer to teach the course).  The skilled faculty (11) is the
    bootstrap-critical part; the rest of the 50-worker roster fills as
    Unskilled (2026-06-02)."""
    assert STARTING_WORKFORCE["Educator"] == 50
    mix = dict(STARTING_WORKERS_BY_PROFESSION["Educator"])
    assert mix == {
        "Professor": 2,
        "Lecturer": 4,
        "TechnicalDirector": 1,
        "Instructor": 4,
    }
    # Sanity: starting Manager-course capacity = min(Prof*2, Lect) > 0.
    assert min(mix["Professor"] * 2, mix["Lecturer"]) == 4


def test_educator_starts_with_expertise_and_courses():
    inv = STARTING_INVENTORY["Educator"]
    assert inv.get("Expertise", 0) >= 6
    assert inv.get("Courses", 0) >= 5


# ---------------------------------------------------------------------------
# Course-gated standard training
# ---------------------------------------------------------------------------

def _turn_manager(players, training, io):
    from island_traders.engine.production import ProductionEngine
    from island_traders.engine.trading import TradingEngine
    from island_traders.engine.turn import TurnManager
    from island_traders.models.deal import DealLedger
    from island_traders.models.market import Market
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
        training=training,
    )


def _mk(player_id, name, role):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES
    return Player(player_id, name, [ROLES[role]], 100.0, is_human=True)


def test_standard_training_pending_without_courses():
    from island_traders.cli.prompts import FakeIOAdapter
    from island_traders.engine.turn import TurnResult
    from island_traders.models.training import TrainingRegistry, TrainingStatus

    farmer = _mk(0, "Farmer", "Farmer")
    educator = _mk(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    educator.receive_resources(ResourceType.EXPERTISE, 2)
    educator.workforce.add_workers(1, training_level=1, profession="Professor")
    educator.workforce.add_workers(1, training_level=1, profession="Lecturer")
    # NO Courses given to the Educator.
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=70.0,
        target_profession="Nurse",  # Manager-tier → Course-gated (Phase 3)
        year=0, season=0, transport_mode="air_ticket",
    )
    io = FakeIOAdapter()
    tm = _turn_manager([farmer, educator], training, io)
    tm._action_review_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )
    # Pending — no Course slots available
    assert req.status == TrainingStatus.AWAITING_EDUCATOR
    assert "Course slot" in "\n".join(io.printed)
    # No-leak: air tickets NOT consumed when the Course peek fails first
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 2


def test_standard_training_consumes_one_course_for_small_class():
    from island_traders.cli.prompts import FakeIOAdapter
    from island_traders.engine.turn import TurnResult
    from island_traders.models.training import TrainingRegistry, TrainingStatus

    farmer = _mk(0, "Farmer", "Farmer")
    educator = _mk(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(4)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 4)
    educator.receive_resources(ResourceType.COURSES, 3)
    educator.receive_resources(ResourceType.EXPERTISE, 3)
    educator.workforce.add_workers(1, training_level=1, profession="Professor")
    educator.workforce.add_workers(1, training_level=1, profession="Lecturer")
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=100.0,
        target_profession="Nurse",  # Manager-tier → Course-gated (Phase 3)
        year=0, season=0, transport_mode="air_ticket",
    )
    io = FakeIOAdapter()
    tm = _turn_manager([farmer, educator], training, io)
    tm._action_review_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )
    assert req.status == TrainingStatus.DISPATCHED
    # 4 trainees → ceil(4/12) = 1 Course consumed (3 → 2)
    assert educator.inventory.get(ResourceType.COURSES) == 2
