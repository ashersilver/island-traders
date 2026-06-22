from __future__ import annotations

from island_traders.constants import (
    OUTPUT_PRODUCTION_INPUTS,
    PRODUCTION_INPUTS,
    SKILLED_PROFESSIONS,
    UNIVERSITY_CAPACITY,
)
from island_traders.constants_capacity import PRODUCTION_RECIPES
from island_traders.engine.events import EventResult
from island_traders.engine.production import ProductionEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.player import Player
from island_traders.models.profession import (
    PROFESSION_LABEL,
    ROLE_PROFESSIONS,
    SCIENCE_TRAINING_PROFESSIONS,
    Profession,
)
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import TrainingRegistry


def test_new_science_set_professions_are_trainable_and_classified():
    assert Profession.ACTUARY not in SCIENCE_TRAINING_PROFESSIONS
    assert Profession.TRADESMAN not in SCIENCE_TRAINING_PROFESSIONS
    assert Profession.MEDICAL_RESEARCHER in SCIENCE_TRAINING_PROFESSIONS
    assert Profession.MEDICAL_TECHNICIAN in SCIENCE_TRAINING_PROFESSIONS

    for profession in (
        Profession.ACTUARY,
        Profession.TRADESMAN,
        Profession.MEDICAL_RESEARCHER,
        Profession.MEDICAL_TECHNICIAN,
    ):
        assert profession in PROFESSION_LABEL
        assert profession.value in UNIVERSITY_CAPACITY

    assert Profession.ACTUARY in ROLE_PROFESSIONS["Banker"]
    assert Profession.TRADESMAN in ROLE_PROFESSIONS["Manufacturer"]
    assert Profession.MEDICAL_RESEARCHER in ROLE_PROFESSIONS["Doctor"]
    assert Profession.MEDICAL_TECHNICIAN in ROLE_PROFESSIONS["Doctor"]

    assert Profession.ACTUARY.value in SKILLED_PROFESSIONS["Banker"]
    assert Profession.TRADESMAN.value in SKILLED_PROFESSIONS["Manufacturer"]
    assert Profession.MEDICAL_RESEARCHER.value in SKILLED_PROFESSIONS["Doctor"]
    assert Profession.MEDICAL_TECHNICIAN.value in SKILLED_PROFESSIONS["Doctor"]


def test_educator_reagents_gate_patents_but_not_expertise_or_courses():
    assert PRODUCTION_INPUTS["Educator"] == {}
    assert OUTPUT_PRODUCTION_INPUTS["Educator"] == {
        "Patents": {"Reagents": 1},
    }

    recipes = {
        recipe.output: recipe
        for recipe in PRODUCTION_RECIPES
        if recipe.role == "Educator"
    }
    assert recipes["Expertise"].inputs == {}
    assert "Reagents" not in recipes["Courses"].inputs
    assert recipes["Patents"].inputs.get("Reagents", 0) > 0

    educator = Player(0, "Edu", [ROLES["Educator"]], 100.0)
    educator.receive_resources(ResourceType.EXPERTISE, 10)
    educator.workforce.add_workers(2, training_level=1, profession=Profession.PROFESSOR.value)
    educator.workforce.add_workers(4, training_level=1, profession=Profession.INSTRUCTOR.value)

    produced = ProductionEngine().produce(
        educator,
        EventResult("Normal Operations"),
        season_name="Spring",
    )

    assert produced.get(ResourceType.EXPERTISE, 0) > 0
    assert produced.get(ResourceType.COURSES, 0) > 0
    assert ResourceType.PATENTS not in produced


def _educator_with_course_capacity(reagents: int) -> Player:
    educator = Player(1, "Educator", [ROLES["Educator"]], 100.0)
    educator.receive_resources(ResourceType.COURSES, 5)
    educator.receive_resources(ResourceType.EXPERTISE, 10)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 5)
    if reagents:
        educator.receive_resources(ResourceType.REAGENTS, reagents)
    educator.workforce.add_workers(2, training_level=1, profession=Profession.PROFESSOR.value)
    educator.workforce.add_workers(2, training_level=1, profession=Profession.LECTURER.value)
    educator.workforce.add_workers(1, training_level=1, profession=Profession.TECHNICAL_DIRECTOR.value)
    educator.workforce.add_workers(2, training_level=1, profession=Profession.INSTRUCTOR.value)
    educator.add_capital("educator.technical_workshop", 1)
    return educator


def _training_request(target_profession: Profession, educator: Player):
    requester = Player(0, "Requester", [ROLES["Doctor"]], 100.0)
    trainee = requester.workforce.add_workers(1)[0]
    training = TrainingRegistry()
    req = training.propose(
        requester_id=requester.player_id,
        worker_ids=[trainee.worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=0.0,
        target_profession=target_profession.value,
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    manager = TurnManager(
        players=[requester, educator],
        production_engine=ProductionEngine(),
        trading_engine=None,
        market=None,
        io_adapter=None,
        training=training,
    )
    return manager, req


def test_science_training_requires_reagents():
    educator = _educator_with_course_capacity(reagents=0)
    manager, req = _training_request(Profession.MEDICAL_RESEARCHER, educator)

    ok, reason = manager._training_capacity_status(educator, req, year=0, season=0)

    assert ok is False
    assert "Reagents" in reason


def test_non_science_training_does_not_require_reagents():
    educator = _educator_with_course_capacity(reagents=0)
    manager, req = _training_request(Profession.ACTUARY, educator)

    ok, reason = manager._training_capacity_status(educator, req, year=0, season=0)

    assert ok is True
    assert reason == ""


def test_science_training_consumes_reagents_on_approval():
    educator = _educator_with_course_capacity(reagents=2)
    manager, req = _training_request(Profession.MEDICAL_TECHNICIAN, educator)

    before = educator.inventory.get(ResourceType.REAGENTS)
    consumed = manager._consume_training_capacity(educator, req, year=0, season=0)

    assert educator.inventory.get(ResourceType.REAGENTS) == before - 1
    assert "Reagents" in consumed
