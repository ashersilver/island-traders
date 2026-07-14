from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import (
    BROWNOUT_CAPACITY_PENALTY,
    BROWNOUT_QOL_PENALTY,
)
from island_traders.engine.events import EventResult
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.deal import DealLedger
from island_traders.models.loan import LoanLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import TrainingRegistry


def _player(player_id: int, role_name: str, dollops: float = 500.0) -> Player:
    return Player(
        player_id=player_id,
        name=role_name,
        roles=[ROLES[role_name]],
        dollops=dollops,
        is_human=False,
    )


def _turn_manager(
    players: list[Player],
    *,
    training: TrainingRegistry | None = None,
    loan_ledger: LoanLedger | None = None,
) -> TurnManager:
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=FakeIOAdapter(),
        training=training,
        loan_ledger=loan_ledger,
    )


def test_energy_floor_counts_only_energy_intensive_units_and_prorates_brownout():
    manufacturer = _player(0, "Manufacturer")
    manufacturer.add_capital("manufacturer.shipyard")
    assert manufacturer.energy_intensive_capacity_units() == 4
    assert manufacturer.energy_floor_oil_required() == 2

    manufacturer.receive_resources(ResourceType.OIL, 2)
    manager = _turn_manager([manufacturer])
    manager._process_energy_floor()
    assert manufacturer.inventory.get(ResourceType.OIL) == 0
    assert manufacturer._energy_floor_oil_consumed_this_season == 2
    assert manufacturer._brownout_capacity_multiplier == 1.0

    farmer = _player(1, "Farmer")
    farmer.add_capital("farmer.fishing_boat")
    farmer.add_capital("farmer.storage_building")
    assert farmer.owned_capital_capacity_units() == 2
    assert farmer.energy_intensive_capacity_units() == 0
    assert farmer.energy_floor_oil_required() == 1

    partial = _player(2, "Manufacturer")
    partial.add_capital("manufacturer.shipyard")
    partial.receive_resources(ResourceType.OIL, 1)
    manager = _turn_manager([partial])
    manager._process_energy_floor()
    unmet_fraction = 0.5
    assert partial._energy_floor_oil_required_this_season == 2
    assert partial._energy_floor_oil_consumed_this_season == 1
    assert partial._brownout_capacity_multiplier == 1.0 - (
        BROWNOUT_CAPACITY_PENALTY * unmet_fraction
    )
    assert partial._brownout_qol_stability_delta == -BROWNOUT_QOL_PENALTY * unmet_fraction

    banker = _player(3, "Banker")
    manager = _turn_manager([banker])
    manager._process_energy_floor()
    assert banker._energy_floor_oil_required_this_season == 1
    assert banker._energy_floor_oil_consumed_this_season == 0
    assert banker._brownout_capacity_multiplier == 1.0 - BROWNOUT_CAPACITY_PENALTY
    assert banker._brownout_qol_stability_delta == -BROWNOUT_QOL_PENALTY

    baseline_banker = _player(4, "Banker")
    baseline = ProductionEngine().produce(
        baseline_banker, EventResult("Normal"), "Spring"
    )[ResourceType.FINANCE]
    produced = ProductionEngine().produce(banker, EventResult("Normal"), "Spring")
    assert produced[ResourceType.FINANCE] < baseline
    assert produced[ResourceType.FINANCE] == int(baseline * (1.0 - BROWNOUT_CAPACITY_PENALTY))


def test_educator_feeds_visiting_students_and_home_excludes_away_trainees():
    farmer = _player(0, "Farmer")
    educator = _player(1, "Educator")
    farmer.population = 10
    educator.population = 10
    farmer.receive_resources(ResourceType.FOOD, 1)
    educator.receive_resources(ResourceType.FOOD, 2)
    farmer.workforce.add_workers(4)
    worker_ids = [worker.worker_id for worker in farmer.workforce.active_workers[:4]]

    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=worker_ids,
        educator_id=educator.player_id,
        dollops_to_educator=10.0,
        target_profession=Profession.NURSE.value,
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    training.educator_approve(req.batch_id)
    training.arrange_transport(req.batch_id, transporter_id=educator.player_id)
    training.dispatch(req.batch_id, year=0, season=0)
    farmer.workforce.dispatch_for_training(worker_ids)

    manager = _turn_manager([farmer, educator], training=training)
    manager._consume_and_post_sustenance()

    assert training.visiting_trainees(educator.player_id) == 4
    assert training.trainees_away_from_home(farmer.player_id) == 4
    assert educator._qol_meals_needed_this_season == 2  # ceil((10 + 4) / 10)
    assert farmer._qol_meals_needed_this_season == 1  # ceil((10 - 4) / 10)
    assert educator.inventory.get(ResourceType.FOOD) == 0
    assert farmer.inventory.get(ResourceType.FOOD) == 0


def test_educator_lab_step_inputs_for_courses_and_expertise():
    engine = ProductionEngine()

    assert engine._output_inputs_for_quantity(
        "Educator", ResourceType.EXPERTISE, 20
    ) == {ResourceType.REAGENTS: 2, ResourceType.OIL: 2}
    assert engine._output_inputs_for_quantity(
        "Educator", ResourceType.COURSES, 20
    ) == {ResourceType.REAGENTS: 2, ResourceType.OIL: 2}
    assert engine._output_inputs_for_quantity(
        "Educator", ResourceType.EXPERTISE, 8
    ) == {}


def test_banker_active_loan_consumes_office_goods():
    banker = _player(0, "Banker")
    borrower = _player(1, "Farmer")
    banker.receive_resources(ResourceType.GOODS, 1)
    loans = LoanLedger()
    loans.create_loan(
        borrower_id=borrower.player_id,
        lender_id=banker.player_id,
        principal=100.0,
        interest_rate=0.05,
        issued_year=0,
        issued_season=0,
        term_years=1,
    )

    manager = _turn_manager([banker, borrower], loan_ledger=loans)
    manager._process_banker_office_goods(year=0, season_index=0)

    assert banker.inventory.get(ResourceType.GOODS) == 0
    assert banker._banker_office_goods_consumed_this_season == 1
