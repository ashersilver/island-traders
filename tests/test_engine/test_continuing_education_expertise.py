from __future__ import annotations

import pytest

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import (
    CE_MAX,
    CE_PENALTY_PER_SEASON,
    CE_RECOVERY_PER_SEASON,
)
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def _player() -> Player:
    return Player(
        player_id=0,
        name="Educator",
        roles=[ROLES["Educator"]],
        dollops=500.0,
        is_human=False,
    )


def _turn_manager(player: Player) -> TurnManager:
    market = Market()
    return TurnManager(
        players=[player],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=FakeIOAdapter(),
    )


def _add_managers(player: Player, count: int) -> None:
    player.workforce.add_workers(
        count,
        training_level=3,
        profession=Profession.LECTURER.value,
    )


def test_shortfall_accrues_fractional_penalty_from_rolling_annual_coverage():
    player = _player()
    _add_managers(player, 7)
    player.ce_history = [0.0, 2.0, 2.0, 1.0]

    _turn_manager(player)._process_continuing_education(season_index=0)

    assert player.ce_ytd() == 5.0
    assert player._ce_uncovered_fraction_this_season == pytest.approx(2 / 7)
    assert player.ce_penalty == pytest.approx(CE_PENALTY_PER_SEASON * (2 / 7))


def test_full_coverage_recovers_and_consumes_needed_expertise():
    player = _player()
    _add_managers(player, 7)
    player.ce_history = [0.0, 2.0, 2.0, 1.0]
    player.ce_penalty = 0.10
    player.receive_resources(ResourceType.EXPERTISE, 2)

    _turn_manager(player)._process_continuing_education(season_index=0)

    assert player.inventory.get(ResourceType.EXPERTISE) == 0
    assert player.ce_ytd() == 7.0
    assert player._ce_uncovered_fraction_this_season == 0.0
    assert player.ce_penalty == pytest.approx(0.10 - CE_RECOVERY_PER_SEASON)


def test_neglected_managers_cap_then_recover_at_five_points_per_season():
    player = _player()
    _add_managers(player, 3)
    manager = _turn_manager(player)

    for season in range(8):
        manager._process_continuing_education(season_index=season)

    assert player.ce_penalty == pytest.approx(CE_MAX)
    assert player.ce_manager_efficiency_multiplier() == pytest.approx(1.0 - CE_MAX)

    player.receive_resources(ResourceType.EXPERTISE, 12)
    for season in range(4):
        manager._process_continuing_education(season_index=season)

    assert player.ce_penalty == pytest.approx(0.0)


def test_even_balanced_state_is_island_level_not_per_worker():
    player = _player()
    _add_managers(player, 2)

    _turn_manager(player)._process_continuing_education(season_index=0)

    factors = [
        player.ce_manager_efficiency_multiplier()
        for worker in player.workforce.active_workers
        if worker.profession == Profession.LECTURER.value
    ]
    assert factors == [pytest.approx(0.95), pytest.approx(0.95)]
    assert all(not hasattr(worker, "ce_penalty") for worker in player.workforce.workers)
    assert all(not hasattr(worker, "ce_history") for worker in player.workforce.workers)


def test_manager_efficiency_multiplier_only_affects_manager_band_workers():
    manager_player = _player()
    manager_player.workforce.add_workers(
        1,
        training_level=3,
        profession=Profession.LECTURER.value,
    )
    technician_player = _player()
    technician_player.workforce.add_workers(
        1,
        training_level=3,
        profession=Profession.INSTRUCTOR.value,
    )

    manager_factor = manager_player.workforce.labour_productivity_factor(
        1,
        0,
        [Profession.LECTURER.value],
        manager_efficiency_multiplier=0.80,
    )
    manager_baseline = manager_player.workforce.labour_productivity_factor(
        1,
        0,
        [Profession.LECTURER.value],
    )
    technician_factor = technician_player.workforce.labour_productivity_factor(
        1,
        0,
        [Profession.INSTRUCTOR.value],
        manager_efficiency_multiplier=0.80,
    )
    technician_baseline = technician_player.workforce.labour_productivity_factor(
        1,
        0,
        [Profession.INSTRUCTOR.value],
    )

    assert manager_factor == pytest.approx(manager_baseline * 0.80)
    assert technician_factor == pytest.approx(technician_baseline)
