"""Education Phase 3 — apprenticeship pipeline, course duration, settling ramp.

Covers the 2026-05-17 rulings now canonical in
requirements/education-model.md:

  * Manager-tier = Course-gated; Technician-tier = Educator
    apprenticeship-slot-pool + Instructor gated (NOT Course-gated).
  * Profession-dependent away duration (Doctor 3, other Managers 2,
    Nurse 1, Technicians 1).
  * Returning apprentices work one 75%-productivity settling season;
    university (Manager) graduates do not.
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.capacity import apprenticeship_slot_capacity
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import (
    TrainingRegistry, TrainingStatus, away_seasons,
)
from island_traders.models.workforce import Workforce
from island_traders.constants_capacity import CAPITAL_CATALOGUE

APPRENTICESHIP_ITEM = "educator.apprenticeship_programme"


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
    return training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=70.0,
        target_profession="FarmingTechnician",
        year=0, season=0, transport_mode="air_ticket",
    )


# --------------------------------------------------------------------------
# away_seasons mapping
# --------------------------------------------------------------------------

def test_away_seasons_by_profession():
    assert away_seasons("Doctor") == 3
    assert away_seasons("Nurse") == 1
    assert away_seasons("Engineer") == 2
    assert away_seasons("FarmingTechnician") == 1   # Technician away
    assert away_seasons("NotARealProfession") == 1   # safe fallback


def test_apprenticeship_slot_capacity_helper():
    assert apprenticeship_slot_capacity(CAPITAL_CATALOGUE, {}) == 0
    assert apprenticeship_slot_capacity(
        CAPITAL_CATALOGUE, {APPRENTICESHIP_ITEM: 1}
    ) == 3
    assert apprenticeship_slot_capacity(
        CAPITAL_CATALOGUE, {APPRENTICESHIP_ITEM: 2}
    ) == 6


# --------------------------------------------------------------------------
# Technician gate: Instructor + apprenticeship slot pool, NOT Courses
# --------------------------------------------------------------------------

def test_technician_pending_without_instructor():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    educator.receive_resources(ResourceType.COURSES, 5)          # irrelevant for Technicians
    educator.capital_inventory[APPRENTICESHIP_ITEM] = 1           # slots, but no Instructor
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
    # Courses are untouched — Technicians are not Course-gated.
    assert educator.inventory.get(ResourceType.COURSES) == 5
    # Air tickets not burned on a capacity-peek failure.
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 2


def test_technician_pending_without_slot_pool():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    educator.workforce.add_workers(1, training_level=1, profession="Instructor")
    # Instructor present but NO apprenticeship_programme capital → 0 slots.
    training = TrainingRegistry()
    req = _propose_tech(training, farmer, educator, workers)

    io = FakeIOAdapter()
    tm = _turn_manager([farmer, educator], training, io)
    tm._action_review_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )

    assert req.status == TrainingStatus.AWAITING_EDUCATOR
    assert "apprenticeship slot pool full" in "\n".join(io.printed)


def test_technician_dispatches_with_instructor_and_slots_without_courses():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    educator.workforce.add_workers(1, training_level=1, profession="Instructor")
    educator.capital_inventory[APPRENTICESHIP_ITEM] = 1           # 3 slots
    # Deliberately ZERO Courses — Technician training must not need them.
    training = TrainingRegistry()
    req = _propose_tech(training, farmer, educator, workers)

    io = FakeIOAdapter()
    tm = _turn_manager([farmer, educator], training, io)
    tm._action_review_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )

    assert req.status == TrainingStatus.DISPATCHED
    assert educator.inventory.get(ResourceType.COURSES) == 0       # none needed
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 0
    assert farmer.workforce.training_count == 2
    # Two trainees now occupy the slot pool (3 slots → 1 free).
    assert training.technician_trainees_in_flight(educator.player_id) == 2


def test_apprenticeship_slot_pool_blocks_overbooking():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    first = farmer.workforce.add_workers(3)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 10)
    educator.workforce.add_workers(1, training_level=1, profession="Instructor")
    educator.capital_inventory[APPRENTICESHIP_ITEM] = 1           # exactly 3 slots
    training = TrainingRegistry()
    r1 = _propose_tech(training, farmer, educator, first)

    io = FakeIOAdapter()
    tm = _turn_manager([farmer, educator], training, io)
    tm._action_review_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )
    assert r1.status == TrainingStatus.DISPATCHED   # 3/3 slots now occupied

    # A second batch can't be admitted until the first returns.
    second = farmer.workforce.add_workers(1)
    r2 = _propose_tech(training, farmer, educator, second)
    io2 = FakeIOAdapter()
    tm._action_review_training(
        educator, TurnResult(educator.player_id, season=1, year=0),
        season_name="Summer", year=0,
    )
    assert r2.status == TrainingStatus.AWAITING_EDUCATOR
    assert "apprenticeship slot pool full" in "\n".join(io2.printed) or \
           "apprenticeship slot pool full" in "\n".join(io.printed)


# --------------------------------------------------------------------------
# Course duration wired into dispatch
# --------------------------------------------------------------------------

def test_doctor_course_is_three_seasons_away():
    training = TrainingRegistry()
    req = training.propose(
        requester_id=0, worker_ids=[1, 2], educator_id=9,
        dollops_to_educator=0.0, target_profession="Doctor",
        year=0, season=0, transport_mode="air_ticket",
    )
    training.educator_approve(req.batch_id)
    training.dispatch(req.batch_id, year=0, season=0, num_seasons=4)
    # Spring (0) + 3 = Winter (3) of the same year.
    assert (req.return_year, req.return_season) == (0, 3)


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
# Post-return settling ramp (75% for one season) — Technician only
# --------------------------------------------------------------------------

def test_technician_returns_with_one_settling_season():
    wf = Workforce()
    w = wf.add_workers(1, profession="Unskilled")[0]
    full_unskilled_eff = w.efficiency

    wf.dispatch_for_training([w.worker_id])
    wf.return_from_training([w.worker_id], "FarmingTechnician")

    assert w.profession == "FarmingTechnician"
    assert w.settling_seasons == 1
    # During the settling season efficiency is throttled to 75%.
    settling_eff = w.efficiency
    assert settling_eff < full_unskilled_eff or w.training_level == 1
    base_no_settle = min(0.20 + w.experience_seasons * 0.05, w.plateau)
    assert abs(settling_eff - base_no_settle * 0.75) < 1e-9

    # One worked season clears the settling penalty.
    wf.apply_season_work()
    assert w.settling_seasons == 0
    assert abs(w.efficiency - min(
        0.20 + w.experience_seasons * 0.05, w.plateau
    )) < 1e-9


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
