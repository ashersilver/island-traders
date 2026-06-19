from __future__ import annotations

import pytest

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import (
    BASE_PRICES,
    OIL_POLLUTION_SCALE,
    QOL_EMIGRATION_RATE,
    QOL_WEIGHT_FOOD,
    QOL_WEIGHT_FOREST,
    QOL_WEIGHT_HEALTH,
    QOL_WEIGHT_POLLUTION,
)
from island_traders.engine.ai import AIStrategy
from island_traders.engine import game as game_mod
from island_traders.engine.events import EventResult
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.production import ProductionEngine
from island_traders.engine.qol import (
    compute_qol,
    food_coverage,
    health_coverage,
    mitigated_pollution_index,
    raw_pollution_index,
)
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def _player(pid: int, role: str, *, dollops: float = 500.0) -> Player:
    player = Player(pid, f"Player{pid}", [ROLES[role]], dollops, is_human=False)
    workers = player.workforce.add_workers(8, training_level=3)
    for worker in workers:
        worker.experience_seasons = 20
    return player


def test_food_and_health_coverage_edge_cases():
    assert food_coverage(0, 0) == 1.0
    assert food_coverage(10, 0) == 0.0
    assert food_coverage(10, 4) == 0.4
    assert food_coverage(10, 12) == 1.0

    assert health_coverage(0, 0) == 1.0
    assert health_coverage(8, 0) == 0.0
    assert health_coverage(8, 2) == 0.25
    assert health_coverage(8, 12) == 1.0


def test_pollution_index_scales_with_oil_and_population():
    assert raw_pollution_index(0, 100) == 0.0
    assert raw_pollution_index(int(OIL_POLLUTION_SCALE * 50), 100) == 0.5
    assert raw_pollution_index(int(OIL_POLLUTION_SCALE * 100), 100) == 1.0
    assert raw_pollution_index(int(OIL_POLLUTION_SCALE * 200), 100) == 1.0
    assert raw_pollution_index(10, 0) == 0.0


def test_health_coverage_mitigates_pollution_impact():
    raw = raw_pollution_index(int(OIL_POLLUTION_SCALE * 50), 100)

    assert raw == 0.5
    assert mitigated_pollution_index(int(OIL_POLLUTION_SCALE * 50), 100, 0.0) == raw
    assert mitigated_pollution_index(int(OIL_POLLUTION_SCALE * 50), 100, 1.0) == 0.25


def test_compute_qol_uses_expected_weights():
    assert (
        QOL_WEIGHT_FOOD
        + QOL_WEIGHT_HEALTH
        + QOL_WEIGHT_POLLUTION
        + QOL_WEIGHT_FOREST
    ) == pytest.approx(1.0)
    score = compute_qol(
        food_cov=0.5,
        health_cov=0.25,
        pollution_idx=0.4,
        forest_coverage=0.0,
    )
    assert score == pytest.approx(0.4325)
    assert compute_qol(10.0, 10.0, -1.0, 10.0) == 1.0
    assert compute_qol(-1.0, -1.0, 2.0, -1.0) == 0.0


def test_production_and_consumer_demand_update_annual_accumulators():
    producer = Player(1, "Producer", [ROLES["Miner"]], 500.0, is_human=False)
    producer.add_capital("miner.crusher")
    producer.add_capital("miner.enhanced_crusher_smelter")
    producer.workforce.add_workers(1, training_level=1, profession=Profession.MINER.value)
    producer.workforce.add_workers(
        4, training_level=1, profession=Profession.MINING_TECHNICIAN.value
    )
    producer.workforce.add_workers(10, training_level=0, profession=Profession.UNSKILLED.value)
    producer.receive_resources(ResourceType.ORE, 20)
    producer.receive_resources(ResourceType.OIL, 20)
    produced = ProductionEngine().produce_product(
        producer,
        EventResult("Normal Operations"),
        "Spring",
        "Miner",
        ResourceType.METAL,
        40,
    )

    assert produced == {ResourceType.METAL: 40}
    assert producer._oil_consumed_this_year == 1

    buyer = _player(2, "Miner")
    seller = _player(3, "Doctor")
    buyer.population = 100
    buyer.household_cash = 100.0
    market = Market()
    seller.receive_resources(ResourceType.FOOD, 1)
    seller.receive_resources(ResourceType.HEALTH_SERVICES, 1)
    market.post_offer(seller, ResourceType.FOOD, 10.0, 1)
    market.post_offer(seller, ResourceType.HEALTH_SERVICES, 10.0, 1)
    turn_manager = TurnManager(
        players=[buyer, seller],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger(), [buyer, seller]),
        market=market,
        io_adapter=FakeIOAdapter(),
    )

    turn_manager._process_consumer_demand("Winter", [])

    assert buyer._food_demanded_this_year == 1
    assert buyer._food_bought_this_year == 1
    assert buyer._health_demanded_this_year == 1
    assert buyer._health_bought_this_year == 1


def test_year_end_qol_births_and_emigration_conserve_migrants(monkeypatch):
    monkeypatch.setattr(game_mod, "BASE_BIRTH_RATE", 0.0)
    game = Game(
        GameConfig(
            [
                PlayerSpec("Low", ["Miner"], is_human=False),
                PlayerSpec("High", ["Doctor"], is_human=False),
            ],
            num_years=1,
        ),
        FakeIOAdapter(),
    )
    game.setup()
    low, high = game.players
    low.population = 100
    high.population = 100
    low._food_demanded_this_year = 10
    low._health_demanded_this_year = 10
    low._oil_consumed_this_year = int(OIL_POLLUTION_SCALE * 100)
    high._food_demanded_this_year = 10
    high._food_bought_this_year = 10
    high._health_demanded_this_year = 10
    high._health_bought_this_year = 10
    before_total = low.population + high.population

    game._process_year_end_qol_and_population(0, game.market.current_prices(), 3)

    emigrants = round(100 * QOL_EMIGRATION_RATE)
    assert low._qol_score == pytest.approx(0.0)
    assert high._qol_score == pytest.approx(0.95)
    assert low.population == 100 - emigrants
    assert high.population == 100 + emigrants
    assert low.population + high.population == before_total


def test_game_run_computes_qol_fields_and_resets_accumulators(tmp_path):
    game = Game(
        GameConfig(
            [
                PlayerSpec("Farmer", ["Farmer"], is_human=False),
                PlayerSpec("Doctor", ["Doctor"], is_human=False),
            ],
            num_years=2,
        ),
        FakeIOAdapter(),
        save_path=str(tmp_path / "save.json"),
    )
    game.setup()
    observed = {"food_demand": 0}

    def after_season(year: int, season: int) -> None:
        if year == 0 and season == 0:
            observed["food_demand"] = max(
                getattr(player, "_food_demanded_this_year", 0)
                for player in game.players
            )

    game.after_season = after_season
    game.run()

    assert observed["food_demand"] > 0
    for player in game.players:
        assert 0.0 <= player._qol_score <= 1.0
        assert 0.0 <= player._food_coverage <= 1.0
        assert 0.0 <= player._health_coverage <= 1.0
        assert 0.0 <= player._pollution_index <= 1.0


def test_ai_buys_health_services_when_last_year_coverage_is_low():
    buyer = _player(1, "Banker", dollops=500.0)
    seller = _player(2, "Doctor", dollops=500.0)
    buyer.population = 250
    buyer._health_coverage = 0.25
    buyer._qol_observed_years = 1
    market = Market()
    trading = TradingEngine(market, DealLedger(), [buyer, seller])
    seller.receive_resources(ResourceType.HEALTH_SERVICES, 5)
    market.post_offer(
        seller,
        ResourceType.HEALTH_SERVICES,
        BASE_PRICES[ResourceType.HEALTH_SERVICES.value],
        5,
    )

    actions = AIStrategy().take_turn(
        buyer,
        market,
        [seller],
        ProductionEngine(),
        trading,
        EventResult("Normal Operations"),
        season_name="Spring",
        year=0,
        season_index=0,
    )

    assert buyer.inventory.get(ResourceType.HEALTH_SERVICES) == 3
    assert any("HealthServices" in action and "QoL" in action for action in actions)
