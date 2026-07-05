from __future__ import annotations

import random

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import (
    PANDEMIC_DURATION_SEASONS,
    REBUILD_LEVY_INSTALLMENTS,
    SEVERITY_PROFILES,
    UNTREATED_RECOVERY_SEASONS,
)
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.consumer import consumer_demand_plan
from island_traders.engine.cycle import BusinessCycle, BusinessCycleSnapshot, PHASES
from island_traders.engine.events import EventChart, EventResult
from island_traders.engine.game import Game, GameConfig
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager
from island_traders.engine.flu import vaccine_doses_needed
from island_traders.models.capacity import find_item
from island_traders.models.deal import DealLedger
from island_traders.models.loan import posted_funding_rates
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


class ChoiceOne(random.Random):
    def choice(self, seq):
        return seq[0]


class SequenceRandom(random.Random):
    def __init__(self, values: list[float]):
        super().__init__(0)
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0)


def _snapshot(phase: str) -> BusinessCycleSnapshot:
    info = PHASES[phase]
    return BusinessCycleSnapshot(
        phase=phase,
        seasons_remaining=1,
        rate_modifier=info.rate_modifier,
        consumer_demand_multiplier=info.consumer_demand_multiplier,
        stability_delta=info.stability_delta,
        note=info.note,
    )


def test_cycle_advances_through_phase_table_and_rates_match_snapshot():
    cycle = BusinessCycle(rng=ChoiceOne())

    phases = [cycle.advance_season().phase for _ in range(7)]

    assert phases == [
        "Expansion",
        "Expansion",
        "Boom",
        "Contraction",
        "Contraction",
        "Trough",
        "Expansion",
    ]
    assert posted_funding_rates(0, 0, cycle=_snapshot("Expansion")) == {
        1: 0.0425,
        2: 0.05,
        3: 0.0575,
    }
    assert posted_funding_rates(0, 0, cycle=_snapshot("Boom"))[3] == 0.08
    assert posted_funding_rates(0, 0, cycle=_snapshot("Contraction"))[1] == 0.0575
    assert posted_funding_rates(0, 0, cycle=_snapshot("Trough"))[2] == 0.0525


def test_cycle_demand_multiplier_changes_consumer_plan_size():
    player = Player(0, "Farmer", [ROLES["Farmer"]], dollops=500.0, population=500)
    base = consumer_demand_plan(player, "Spring").units
    boom = consumer_demand_plan(
        player,
        "Spring",
        demand_multiplier=PHASES["Boom"].consumer_demand_multiplier,
    ).units

    assert boom[ResourceType.FOOD] > base[ResourceType.FOOD]
    assert boom[ResourceType.GOODS] > base[ResourceType.GOODS]


def test_catastrophic_earthquake_sets_failure_multiplier_and_rebuild_levy():
    chart = EventChart.from_entries("Miner", [{
        "name": "Earthquake",
        "weight": 1.0,
        "yield_modifier": 0.0,
        "outage": True,
        "damage_seasons": 2,
        "natural_disaster": True,
        "severity": True,
    }])

    event = chart.draw(SequenceRandom([0.0, 0.99]))

    assert event.severity == "Catastrophic"
    assert event.yield_modifier <= 0.2
    assert event.capital_failure_multiplier == 4.0
    assert event.rebuild_levy_fraction == SEVERITY_PROFILES["Catastrophic"]["rebuild_levy_fraction"]

    player = Player(0, "Miner", [ROLES["Miner"]], dollops=0.0)
    player.add_capital("miner.excavator", 1)
    game = Game(GameConfig([]), FakeIOAdapter())
    game.players = [player]
    game._apply_rebuild_levy(player, event.rebuild_levy_fraction, event.event_name)

    item = find_item(CAPITAL_CATALOGUE, "miner.excavator")
    total = max(20.0, round(item.cost * event.rebuild_levy_fraction, 2))
    assert player._rebuild_levy_installments == [
        round(total / REBUILD_LEVY_INSTALLMENTS, 2),
        round(total / REBUILD_LEVY_INSTALLMENTS, 2),
    ]
    game._process_rebuild_levy_payments(player)
    assert player._rebuild_levy_remaining == total

    player.capital_units["miner.excavator"][0].status = "failed"
    assert not game.capital_repair_preview(player, "miner.excavator")["repairable"]
    assert not game._attempt_capital_repair(player, item, current_tick=0)


def test_minor_pandemic_persists_for_exactly_two_seasons():
    chart = EventChart.from_entries("Doctor", [{
        "name": "Pandemic",
        "weight": 1.0,
        "yield_modifier": 0.0,
        "outage": True,
        "damage_seasons": 2,
        "natural_disaster": True,
        "severity": True,
        "pandemic": True,
    }])

    event = chart.draw(SequenceRandom([0.0, 0.10]))

    assert event.severity == "Minor"
    assert event.yield_modifier == 0.50
    assert event.outage is False
    assert event.damage_seasons == PANDEMIC_DURATION_SEASONS - 1
    assert event.workforce_sidelined_fraction == 0.20


def test_pandemic_vaccine_coverage_reduces_sidelined_workers():
    player = Player(0, "Doctor", [ROLES["Doctor"]], dollops=100.0, population=100)
    player.workforce.add_workers(10)
    player.inventory = player.inventory.add(
        ResourceType.VACCINE,
        vaccine_doses_needed(player.population),
    )
    manager = TurnManager(
        players=[player],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(Market(), DealLedger()),
        market=Market(),
        io_adapter=FakeIOAdapter(),
    )

    reports = manager._event_sidelining_reports({
        player.player_id: EventResult(
            "Pandemic",
            pandemic=True,
            workforce_sidelined_fraction=0.50,
        )
    }, year=0, season_index=0)

    assert len(reports) == 1
    assert len(reports[0].injured_worker_ids) == 1
    assert player.inventory.get(ResourceType.VACCINE) == 0
    assert sum(w.absent_seasons == UNTREATED_RECOVERY_SEASONS for w in player.workforce.workers) == 1
