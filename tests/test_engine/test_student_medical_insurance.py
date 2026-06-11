"""Student medical insurance (2026-06-02).

Students travelling to the Education island must be covered by medical
insurance paid for by the Education island. Coverage is consumed from
pre-bought sized policies first; any shortfall is auto-provisioned (Education
pays a per-head premium, to a Banker if one exists). Dispatch is held only when
the Educator can't afford the shortfall.
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.models.deal import DealLedger
from island_traders.models.insurance import InsurancePolicy
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.role import ROLES
from island_traders.models.training import TrainingRegistry, TrainingStatus
from island_traders.constants import MEDICAL_PREMIUM_PER_HEAD, INSURANCE_DURATION_SEASONS


def _player(pid, name, role, dollops=500.0, is_human=True):
    return Player(pid, name, [ROLES[role]], dollops, is_human=is_human)


def _tm(players, training):
    market = Market()
    return TurnManager(
        players=players, production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()), market=market,
        io_adapter=FakeIOAdapter(), training=training,
    )


def _ready_educator(educator, courses=10, expertise=20):
    educator.receive_resources(__import__("island_traders.models.resource",
                               fromlist=["ResourceType"]).ResourceType.COURSES, courses)
    from island_traders.models.resource import ResourceType
    educator.receive_resources(ResourceType.EXPERTISE, expertise)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 10)
    educator.workforce.add_workers(2, training_level=1, profession=Profession.PROFESSOR.value)
    educator.workforce.add_workers(2, training_level=1, profession=Profession.LECTURER.value)


def _nurse_req(training, requester, educator, count, fee=0.0):
    workers = requester.workforce.add_workers(count)
    return training.propose(
        requester_id=requester.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id, dollops_to_educator=fee,
        target_profession=Profession.NURSE.value, year=0, season=0,
        transport_mode="air_ticket",
    )


# ---- model ----------------------------------------------------------------

def test_covered_count_defaults_to_one():
    p = InsurancePolicy(1, "medical", 0, 1, 10.0, 0, 4)
    assert p.covered_count == 1


def test_medical_coverage_seats_sums_active_medical_policies():
    edu = _player(1, "Educator", "Educator")
    edu.add_insurance_policy(InsurancePolicy(1, "medical", 1, 9, 40.0, 0, 8, covered_count=5))
    edu.add_insurance_policy(InsurancePolicy(2, "medical", 1, 9, 24.0, 0, 8, covered_count=3))
    edu.add_insurance_policy(InsurancePolicy(3, "life", 1, 9, 10.0, 0, 8, covered_count=10))  # not medical
    assert edu.medical_coverage_seats(0, 0) == 8  # 5 + 3; life ignored


# ---- dispatch coverage gate ----------------------------------------------

def test_dispatch_auto_provisions_cover_and_charges_educator():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator", dollops=500.0)
    _ready_educator(educator)
    training = TrainingRegistry()
    req = _nurse_req(training, farmer, educator, count=3, fee=0.0)
    training.educator_approve(req.batch_id)
    tm = _tm([farmer, educator], training)

    ok = tm._dispatch_training(farmer, req, "Spring", 0)

    assert ok and req.status == TrainingStatus.DISPATCHED
    # 3 students × 8 = 24 charged to the Educator; a covering policy recorded.
    assert educator.dollops == 500.0 - MEDICAL_PREMIUM_PER_HEAD * 3
    assert educator.medical_coverage_seats(0, 0) >= 3


def test_pre_bought_coverage_avoids_extra_charge():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator", dollops=500.0)
    _ready_educator(educator)
    # Educator already holds cover for 5 students.
    educator.add_insurance_policy(InsurancePolicy(
        1, "medical", educator.player_id, 9, 40.0, 0, INSURANCE_DURATION_SEASONS,
        covered_count=5))
    training = TrainingRegistry()
    req = _nurse_req(training, farmer, educator, count=3, fee=0.0)
    training.educator_approve(req.batch_id)
    tm = _tm([farmer, educator], training)

    ok = tm._dispatch_training(farmer, req, "Spring", 0)

    assert ok and req.status == TrainingStatus.DISPATCHED
    assert educator.dollops == 500.0  # pre-bought cover used, no extra charge


def test_dispatch_held_when_educator_cannot_afford_cover():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator", dollops=10.0)  # too poor
    _ready_educator(educator)
    training = TrainingRegistry()
    req = _nurse_req(training, farmer, educator, count=3, fee=0.0)
    training.educator_approve(req.batch_id)
    tm = _tm([farmer, educator], training)

    ok = tm._dispatch_training(farmer, req, "Spring", 0)

    assert not ok
    assert req.status != TrainingStatus.DISPATCHED
    assert educator.dollops == 10.0  # nothing charged


def test_banker_receives_the_student_premium():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator", dollops=500.0)
    banker = _player(2, "Banker", "Banker", dollops=0.0)
    _ready_educator(educator)
    training = TrainingRegistry()
    req = _nurse_req(training, farmer, educator, count=2, fee=0.0)
    training.educator_approve(req.batch_id)
    tm = _tm([farmer, educator, banker], training)

    tm._dispatch_training(farmer, req, "Spring", 0)

    assert banker.dollops == MEDICAL_PREMIUM_PER_HEAD * 2  # premium routed to Banker


def test_self_training_needs_no_student_cover():
    """Educator training its own residents — they don't travel, so no cover."""
    educator = _player(1, "Educator", "Educator", dollops=500.0)
    _ready_educator(educator)
    training = TrainingRegistry()
    workers = educator.workforce.add_workers(2)
    req = training.propose(
        requester_id=educator.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id, dollops_to_educator=0.0,
        target_profession=Profession.NURSE.value, year=0, season=0,
        transport_mode="self_training",
    )
    training.educator_approve(req.batch_id)
    tm = _tm([educator], training)

    tm._dispatch_training(educator, req, "Spring", 0)

    assert educator.dollops == 500.0  # no student cover charged for self-training
