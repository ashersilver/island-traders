from __future__ import annotations

import pytest

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.deal import DealLedger
from island_traders.models.capacity import find_item
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.storage_contract import (
    StorageContractLedger, StorageContractStatus,
)
from island_traders.constants_capacity import CAPITAL_CATALOGUE


def _player(pid: int, role: str, dollops: float = 100.0) -> Player:
    return Player(pid, role, [ROLES[role]], dollops, is_human=False)


def _manager(players: list[Player]) -> TurnManager:
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=FakeIOAdapter(),
        storage_contract_ledger=StorageContractLedger(),
    )


def _cold_contract(manager: TurnManager, renter: Player, transporter: Player, capacity: int):
    transporter.add_capital("transporter.cold_warehouse")
    return manager.create_storage_contract(
        renter, transporter, "transporter.cold_warehouse", ResourceType.FOOD,
        capacity, year=0, season=0,
    )


def test_transporter_warehouses_offer_scaled_rental_space_not_owner_storage():
    bulk = find_item(CAPITAL_CATALOGUE, "transporter.bulk_warehouse")
    cold = find_item(CAPITAL_CATALOGUE, "transporter.cold_warehouse")
    assert bulk.effects["storage_rental"]["capacity"] == 120
    assert cold.effects["storage_rental"]["capacity"] == 80

    transporter = _player(0, "Transporter")
    transporter.add_capital("transporter.cold_warehouse")
    assert transporter.owned_storage_capacity(ResourceType.FOOD) == 12


def test_rented_capacity_protects_the_renters_stock():
    renter = _player(0, "Farmer")
    transporter = _player(1, "Transporter")
    manager = _manager([renter, transporter])
    _cold_contract(manager, renter, transporter, 20)
    renter.receive_resources(ResourceType.FOOD, 32)

    assert renter.storage_capacity(ResourceType.FOOD) == 32
    assert renter.process_spoilage(0) == {}
    assert renter.process_spoilage(2) == {}
    assert renter.inventory.get(ResourceType.FOOD) == 32


def test_owned_and_rented_capacity_sum_without_double_counting():
    renter = _player(0, "Farmer")
    transporter = _player(1, "Transporter")
    manager = _manager([renter, transporter])
    renter.add_capital("common.food_store")
    _cold_contract(manager, renter, transporter, 20)

    assert renter.owned_storage_capacity(ResourceType.FOOD) == 92
    assert renter.rented_storage_capacity(ResourceType.FOOD) == 20
    assert renter.storage_capacity(ResourceType.FOOD) == 112


def test_oversubscribing_a_transporter_warehouse_is_refused():
    renter = _player(0, "Farmer")
    other_renter = _player(1, "Manufacturer")
    transporter = _player(2, "Transporter")
    manager = _manager([renter, other_renter, transporter])
    transporter.add_capital("transporter.bulk_warehouse")
    manager.create_storage_contract(
        renter, transporter, "transporter.bulk_warehouse", ResourceType.GRAIN,
        100, year=0, season=0,
    )

    with pytest.raises(ValueError, match="free capacity"):
        manager.create_storage_contract(
            other_renter, transporter, "transporter.bulk_warehouse", ResourceType.SPARES,
            21, year=0, season=0,
        )


def test_unpaid_contract_lapses_and_loses_next_seasons_protection():
    renter = _player(0, "Farmer", dollops=0.0)
    transporter = _player(1, "Transporter")
    manager = _manager([renter, transporter])
    contract = _cold_contract(manager, renter, transporter, 20)
    renter.receive_resources(ResourceType.FOOD, 32)

    manager._process_storage_contract_payments(year=0, season=0)

    assert contract.status == StorageContractStatus.LAPSED
    assert renter.storage_capacity(ResourceType.FOOD) == 12
    # At tick 1 the formerly protected stock only begins ageing; it is not
    # retroactively destroyed in the season where the fee missed.
    assert renter.process_spoilage(1) == {}


def test_storage_fees_move_cash_each_season():
    renter = _player(0, "Farmer", dollops=10.0)
    transporter = _player(1, "Transporter", dollops=5.0)
    manager = _manager([renter, transporter])
    contract = _cold_contract(manager, renter, transporter, 10)

    manager._process_storage_contract_payments(year=0, season=0)
    manager._process_storage_contract_payments(year=0, season=1)

    assert contract.fee_per_season == 1.5
    assert contract.payments_made == 2
    assert renter.dollops == 7.0
    assert transporter.dollops == 8.0


def test_contracts_survive_save_and_load(tmp_path):
    game = Game(GameConfig(
        player_specs=[
            PlayerSpec(name="Farm", role_names=["Farmer"], is_human=False),
            PlayerSpec(name="Ship", role_names=["Transporter"], is_human=False),
        ],
        num_years=1,
        starting_dollops=100.0,
    ), FakeIOAdapter())
    game.setup()
    renter, transporter = game.players
    transporter.add_capital("transporter.cold_warehouse")
    contract = game.turn_manager.create_storage_contract(
        renter, transporter, "transporter.cold_warehouse", ResourceType.FOOD,
        20, year=0, season=0,
    )
    path = tmp_path / "storage-contract.json"
    game.save(str(path))

    loaded = Game.load(str(path), FakeIOAdapter())
    loaded_renter = loaded.players[0]
    loaded_contract = loaded.storage_contract_ledger.get(contract.contract_id)

    assert loaded_contract.status == StorageContractStatus.ACTIVE
    assert loaded_renter.rented_storage_capacity(ResourceType.FOOD) == 20


def test_cancel_or_lapse_frees_capacity_for_reletting():
    renter = _player(0, "Farmer", dollops=0.0)
    next_renter = _player(1, "Manufacturer")
    transporter = _player(2, "Transporter")
    manager = _manager([renter, next_renter, transporter])
    transporter.add_capital("transporter.bulk_warehouse")
    contract = manager.create_storage_contract(
        renter, transporter, "transporter.bulk_warehouse", ResourceType.GRAIN,
        120, year=0, season=0,
    )
    manager._process_storage_contract_payments(year=0, season=0)

    assert contract.status == StorageContractStatus.LAPSED
    replacement = manager.create_storage_contract(
        next_renter, transporter, "transporter.bulk_warehouse", ResourceType.SPARES,
        120, year=0, season=1,
    )
    manager.cancel_storage_contract(replacement.contract_id, year=0, season=1)
    reopened = manager.create_storage_contract(
        renter, transporter, "transporter.bulk_warehouse", ResourceType.GRAIN,
        120, year=0, season=1,
    )

    assert reopened.status == StorageContractStatus.ACTIVE
