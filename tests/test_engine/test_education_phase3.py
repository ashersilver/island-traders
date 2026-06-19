"""Education Phase 3 — technical pipeline, course duration, settling ramp.

Covers the 2026-05-17 rulings now canonical in
requirements/education-model.md:

  * Manager-tier and Technician-tier courses are staffing-gated, with
    Courses and Expertise debited at approval.
  * Profession-dependent away duration (Doctor 4, other Managers 2,
    Nurse 1, Technicians 1 with a Technical Workshop).
  * Returning apprentices only settle after no-workshop training, at 50%
    productivity for one season; university (Manager) graduates do not.
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.capacity import technical_workshop_trainee_capacity
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import (
    TrainingRegistry, TrainingStatus, away_seasons,
    campus_has_technical_workshop, settling_seasons_on_return, training_duration,
)
from island_traders.models.workforce import Workforce
from island_traders.constants import STAFFING_FOOD_PER_STAFF_PER_SEASON
from island_traders.constants_capacity import CAPITAL_CATALOGUE

TECHNICAL_WORKSHOP_ITEM = "educator.technical_workshop"


def _player(pid: int, name: str, role: str) -> Player:
    return Player(pid, name, [ROLES[role]], 100.0, is_human=True)


def _turn_manager(players, training, io):
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
        training=training,
    )


def _propose_tech(training, farmer, educator, workers):
    has_workshop = campus_has_technical_workshop(educator)
    return training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=70.0,
        target_profession="FarmingTechnician",
        year=0, season=0, transport_mode="air_ticket",
        duration_seasons=training_duration(
            "FarmingTechnician",
            has_technical_workshop=has_workshop,
        ),
        settling_seasons_on_return=settling_seasons_on_return(
            "FarmingTechnician",
            has_technical_workshop=has_workshop,
        ),
    )


# --------------------------------------------------------------------------
# away_seasons mapping
# --------------------------------------------------------------------------

def test_away_seasons_by_profession():
    assert away_seasons("Doctor") == 4
    assert away_seasons("Nurse") == 1
    assert away_seasons("Engineer") == 3
    assert away_seasons("FarmingTechnician") == 1   # Technician away
    assert away_seasons("NotARealProfession") == 1   # safe fallback


def test_technical_workshop_trainee_capacity_helper():
    """Each workshop holds 6 trainees at a time (per-trainee headcount cap,
    independent of how many courses they're split across)."""
    assert technical_workshop_trainee_capacity(CAPITAL_CATALOGUE, {}) == 0
    assert technical_workshop_trainee_capacity(
        CAPITAL_CATALOGUE, {TECHNICAL_WORKSHOP_ITEM: 1}
    ) == 6
    assert technical_workshop_trainee_capacity(
        CAPITAL_CATALOGUE, {TECHNICAL_WORKSHOP_ITEM: 2}
    ) == 12


# --------------------------------------------------------------------------
# Technician gate: Technical Director + Instructor + Technical Workshop
# --------------------------------------------------------------------------

def test_technician_pending_without_instructor():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    educator.receive_resources(ResourceType.COURSES, 5)
    educator.receive_resources(ResourceType.EXPERTISE, 5)
    educator.workforce.add_workers(1, training_level=1, profession="TechnicalDirector")
    educator.capital_inventory[TECHNICAL_WORKSHOP_ITEM] = 1
    training = TrainingRegistry()
    req = _propose_tech(training, farmer, educator, workers)

    io = FakeIOAdapter()
    tm = _turn_manager([farmer, educator], training, io)
    tm._action_review_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )

    assert req.status == TrainingStatus.AWAITING_EDUCATOR
    assert "Instructor" in "\n".join(io.printed)
    # Resources are untouched on a capacity-peek failure.
    assert educator.inventory.get(ResourceType.COURSES) == 5
    assert educator.inventory.get(ResourceType.EXPERTISE) == 5
    # Air tickets not burned on a capacity-peek failure.
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 2


def test_technician_without_technical_workshop_uses_longer_settling_track():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    educator.receive_resources(ResourceType.COURSES, 5)
    educator.receive_resources(ResourceType.EXPERTISE, 5)
    educator.workforce.add_workers(1, training_level=1, profession="TechnicalDirector")
    educator.workforce.add_workers(1, training_level=1, profession="Instructor")
    training = TrainingRegistry()
    req = _propose_tech(training, farmer, educator, workers)

    io = FakeIOAdapter()
    tm = _turn_manager([farmer, educator], training, io)
    tm._action_review_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )

    assert req.status == TrainingStatus.DISPATCHED
    assert req.duration_seasons == 2
    assert req.settling_seasons_on_return == 1
    assert (req.return_year, req.return_season) == (0, 2)


def test_technician_dispatches_with_staff_workshop_courses_and_expertise():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    educator.receive_resources(ResourceType.COURSES, 2)
    educator.receive_resources(ResourceType.EXPERTISE, 3)
    educator.workforce.add_workers(1, training_level=1, profession="TechnicalDirector")
    educator.workforce.add_workers(1, training_level=1, profession="Instructor")
    educator.capital_inventory[TECHNICAL_WORKSHOP_ITEM] = 1
    training = TrainingRegistry()
    req = _propose_tech(training, farmer, educator, workers)

    io = FakeIOAdapter()
    tm = _turn_manager([farmer, educator], training, io)
    tm._action_review_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )

    assert req.status == TrainingStatus.DISPATCHED
    assert educator.inventory.get(ResourceType.COURSES) == 1
    assert educator.inventory.get(ResourceType.EXPERTISE) == 2
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 0
    assert farmer.workforce.training_count == 2
    assert training.technical_courses_in_flight(educator.player_id) == 1


def test_technical_course_staffing_blocks_overbooking():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    first = farmer.workforce.add_workers(3)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 10)
    educator.receive_resources(ResourceType.COURSES, 10)
    educator.receive_resources(ResourceType.EXPERTISE, 10)
    educator.workforce.add_workers(1, training_level=1, profession="TechnicalDirector")
    educator.workforce.add_workers(1, training_level=1, profession="Instructor")
    educator.capital_inventory[TECHNICAL_WORKSHOP_ITEM] = 1
    training = TrainingRegistry()
    r1 = _propose_tech(training, farmer, educator, first)

    io = FakeIOAdapter()
    tm = _turn_manager([farmer, educator], training, io)
    tm._action_review_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )
    assert r1.status == TrainingStatus.DISPATCHED

    # A second batch can't be admitted until the first returns.
    second = farmer.workforce.add_workers(1)
    r2 = _propose_tech(training, farmer, educator, second)
    io2 = FakeIOAdapter()
    tm._action_review_training(
        educator, TurnResult(educator.player_id, season=1, year=0),
        season_name="Summer", year=0,
    )
    assert r2.status == TrainingStatus.AWAITING_EDUCATOR
    # Staffing gate fires first (1 TD * 2, 1 Instructor → 1 concurrent course
    # max; one already in flight).  Workshop trainee-cap is a separate gate
    # checked after staffing.
    log = "\n".join(io2.printed) + "\n".join(io.printed)
    assert "Technical-course staffing full" in log


# --------------------------------------------------------------------------
# Course duration wired into dispatch
# --------------------------------------------------------------------------

def test_doctor_course_is_four_seasons_away():
    training = TrainingRegistry()
    req = training.propose(
        requester_id=0, worker_ids=[1, 2], educator_id=9,
        dollops_to_educator=0.0, target_profession="Doctor",
        year=0, season=0, transport_mode="air_ticket",
    )
    training.educator_approve(req.batch_id)
    training.dispatch(req.batch_id, year=0, season=0, num_seasons=4)
    # Spring (0) + 4 = Spring of the next year.
    assert (req.return_year, req.return_season) == (1, 0)


def test_technician_apprenticeship_is_one_season_away():
    training = TrainingRegistry()
    req = training.propose(
        requester_id=0, worker_ids=[1], educator_id=9,
        dollops_to_educator=0.0, target_profession="FarmingTechnician",
        year=0, season=3, transport_mode="air_ticket",
    )
    training.educator_approve(req.batch_id)
    training.dispatch(req.batch_id, year=0, season=3, num_seasons=4)
    # Winter (3) + 1 → Spring of the next year.
    assert (req.return_year, req.return_season) == (1, 0)


# --------------------------------------------------------------------------
# Post-return settling ramp (50% for one season) — no-workshop Technician only
# --------------------------------------------------------------------------

def test_technician_trained_with_workshop_returns_without_settling():
    wf = Workforce()
    w = wf.add_workers(1, profession="Unskilled")[0]

    wf.dispatch_for_training([w.worker_id])
    wf.return_from_training([w.worker_id], "FarmingTechnician")

    assert w.profession == "FarmingTechnician"
    assert w.settling_seasons == 0


def test_technician_trained_without_workshop_returns_with_one_settling_season():
    wf = Workforce()
    w = wf.add_workers(1, profession="Unskilled")[0]
    full_unskilled_eff = w.efficiency

    wf.dispatch_for_training([w.worker_id])
    wf.return_from_training(
        [w.worker_id],
        "FarmingTechnician",
        settling_seasons_on_return=1,
    )

    assert w.profession == "FarmingTechnician"
    assert w.settling_seasons == 1
    # During the settling season efficiency is throttled to 50%.
    settling_eff = w.efficiency
    assert settling_eff < full_unskilled_eff or w.training_level == 1
    base_no_settle = min(0.20 + w.experience_seasons * 0.05, w.plateau)
    assert abs(settling_eff - base_no_settle * 0.50) < 1e-9

    # One worked season clears the settling penalty.
    wf.apply_season_work()
    assert w.settling_seasons == 0
    assert abs(w.efficiency - min(
        0.20 + w.experience_seasons * 0.05, w.plateau
    )) < 1e-9


def test_training_duration_and_settling_follow_workshop_presence():
    assert training_duration(
        "FarmingTechnician",
        has_technical_workshop=True,
    ) == 1
    assert settling_seasons_on_return(
        "FarmingTechnician",
        has_technical_workshop=True,
    ) == 0
    assert training_duration(
        "FarmingTechnician",
        has_technical_workshop=False,
    ) == 2
    assert settling_seasons_on_return(
        "FarmingTechnician",
        has_technical_workshop=False,
    ) == 1


def test_campus_load_raises_education_island_sustenance_demand():
    """Phase 3 ↔ sustenance-basket seam: visiting trainees feed
    extra_residents into Educator.meals_needed, raising the Education
    Island's sustenance demand basket. Under the 2026-05-25 model every
    resident demands meals (no self-fed baseline), so the campus load
    shows up on top of the Education Island's own resident demand."""
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id, worker_ids=[1, 2, 3],
        educator_id=educator.player_id, dollops_to_educator=0.0,
        target_profession="FarmingTechnician", year=0, season=0,
        transport_mode="air_ticket",
    )
    training.educator_approve(req.batch_id)
    training.dispatch(req.batch_id, year=0, season=0, num_seasons=4)
    assert training.visiting_trainees(educator.player_id) == 3

    tm = _turn_manager([farmer, educator], training, FakeIOAdapter())

    # Compare Educator demand WITH vs. WITHOUT the visiting trainees.
    educator_base_meals = educator.meals_needed()
    educator_with_visitors = educator.meals_needed(extra_residents=3)
    # 3 extra residents → +1 meal under PEOPLE_PER_MEAL=10 rounding
    # (ceil(103/10) - ceil(100/10) = 11 - 10 = 1).
    assert educator_with_visitors - educator_base_meals == 1

    # The engine's per-season hook posts shortfall demand for both
    # islands (Farmer + Educator).  We strip their starting inventory so
    # both run at full shortfall and the Educator's extra-resident meal
    # is visible as a delta in the market basket.
    for p in (farmer, educator):
        for r in (ResourceType.FOOD, ResourceType.GRAIN,
                  ResourceType.PRODUCE, ResourceType.FISH,
                  ResourceType.MEAT):
            qty = p.inventory.get(r)
            if qty > 0:
                p.give_resources(r, qty)

    tm._consume_and_post_sustenance()

    # Total Food basket demand = farmer_meals + educator_meals_with_visitors.
    farmer_meals = farmer.meals_needed()
    expected_food_demand = farmer_meals + educator_with_visitors
    assert tm.market.demand.get(ResourceType.FOOD, 0) == expected_food_demand


def test_campus_food_load_is_near_per_capita_base_rate():
    assert 0.1 <= STAFFING_FOOD_PER_STAFF_PER_SEASON <= 0.25


def test_manager_returns_without_settling():
    wf = Workforce()
    w = wf.add_workers(1, profession="Unskilled")[0]
    wf.dispatch_for_training([w.worker_id])
    wf.return_from_training([w.worker_id], "Nurse")   # Manager band

    assert w.profession == "Nurse"
    assert w.settling_seasons == 0
    assert abs(w.efficiency - min(
        0.20 + w.experience_seasons * 0.05, w.plateau
    )) < 1e-9
