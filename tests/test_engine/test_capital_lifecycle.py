"""Economy Lifecycle Phase C — universal capital lifespan + maintenance."""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import (
    DEFAULT_SERVICE_LIFE_SEASONS, DEFAULT_MAINTENANCE_FRACTION,
    EQUIPMENT_FAILURE_REPAIR_FRACTION,
    EQUIPMENT_REPAIR_AIR_FREIGHT,
    EQUIPMENT_REPAIR_SHIP_FREIGHT,
    EQUIPMENT_WARRANTY_ANNUAL_RATE,
    STARTING_AGED_CAPITAL,
)
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.capacity import CapitalItem, find_item
from island_traders.models.resource import ResourceType


# ---------------------------------------------------------------------------
# Constants & catalogue
# ---------------------------------------------------------------------------

def test_capitalitem_lifecycle_field_defaults():
    item = CapitalItem(
        item_id="x.test", name="X", role="Farmer", cost=100.0,
        delivery_seasons=0,
    )
    assert item.service_life_seasons == DEFAULT_SERVICE_LIFE_SEASONS == 20
    assert item.maintenance_per_season == 0.0


def test_combine_harvester_has_8_season_life():
    combine = find_item(CAPITAL_CATALOGUE, "farmer.harvester")
    assert combine is not None
    assert combine.service_life_seasons == 8       # ~2 years
    assert combine.name == "Combine Harvester"


def test_default_maintenance_fraction_is_three_percent():
    assert DEFAULT_MAINTENANCE_FRACTION == 0.03


def test_starting_aged_capital_seeds_farmer_combine_age_4():
    assert STARTING_AGED_CAPITAL["Farmer"] == [("farmer.harvester", 1, 4)]


# ---------------------------------------------------------------------------
# Player.effective_capital_inventory
# ---------------------------------------------------------------------------

def test_effective_inventory_subtracts_unmaintained():
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES
    p = Player(0, "P", [ROLES["Farmer"]], 100.0, is_human=True)
    p.capital_inventory = {"farmer.harvester": 2, "farmer.tractor": 1}
    p.unmaintained_capital = {"farmer.harvester": 1}
    eff = p.effective_capital_inventory()
    assert eff == {"farmer.harvester": 1, "farmer.tractor": 1}


def test_effective_inventory_no_unmaintained_returns_same_dict():
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES
    p = Player(0, "P", [ROLES["Farmer"]], 100.0, is_human=True)
    p.capital_inventory = {"farmer.tractor": 1}
    assert p.effective_capital_inventory() is p.capital_inventory


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------

def _farmer_game(starting_dollops: float = 1500.0) -> Game:
    config = GameConfig(
        num_years=1,
        player_specs=[PlayerSpec(
            name="P", role_names=["Farmer"], is_human=False,
            starting_dollops=starting_dollops,
        )],
    )
    game = Game(config, FakeIOAdapter())
    game.setup()
    return game


class _FixedRng:
    def __init__(self, values: list[float]):
        self.values = list(values)

    def random(self) -> float:
        if self.values:
            return self.values.pop(0)
        return 1.0


def _service_game() -> Game:
    config = GameConfig(
        num_years=2,
        player_specs=[
            PlayerSpec(name="Owner", role_names=["Educator"], is_human=False),
            PlayerSpec(name="Forge", role_names=["Manufacturer"], is_human=False),
            PlayerSpec(name="Hauler", role_names=["Transporter"], is_human=False),
        ],
    )
    game = Game(config, FakeIOAdapter())
    game.setup()
    return game


def test_setup_seeds_farmer_with_aged_combine_harvester():
    game = _farmer_game()
    p = game.players[0]
    assert p.capital_inventory.get("farmer.harvester", 0) == 1
    # Seeded acquired_tick = -age = -4 so age at start (tick 0) = 4.
    assert p.capital_acquired_ticks["farmer.harvester"] == [-4]


def test_maintenance_charges_three_percent_of_cost_per_season():
    game = _farmer_game(starting_dollops=1500.0)
    p = game.players[0]
    start = p.dollops
    # Combine cost 90 → default maintenance 0.03 × 90 = 2.7 Dp/unit.
    game._process_capital_maintenance(year=0, season=0)
    assert abs((start - p.dollops) - 2.7) < 1e-9
    assert p.unmaintained_capital == {}


def test_unmaintained_when_dollops_insufficient():
    game = _farmer_game(starting_dollops=1.0)   # < combine maintenance 2.7
    p = game.players[0]
    game._process_capital_maintenance(year=0, season=0)
    assert p.unmaintained_capital == {"farmer.harvester": 1}
    # Dollops untouched on the unmaintained unit.
    assert p.dollops == 1.0
    # Effective inventory hides it for production.
    assert p.effective_capital_inventory().get("farmer.harvester", 0) == 0


def test_combine_expires_after_8_seasons_and_is_removed():
    game = _farmer_game()
    p = game.players[0]
    # Seeded age = 4. After 4 more seasons (tick 4) age = 8 >= 8 → expire.
    # Run the season-by-season tick.
    for tick in range(0, 5):
        year, season = divmod(tick, 4)
        game._process_capital_maintenance(year, season)
    assert p.capital_inventory.get("farmer.harvester", 0) == 0
    assert p.capital_acquired_ticks.get("farmer.harvester", []) == []


def test_unmaintained_resets_each_season():
    game = _farmer_game(starting_dollops=1.0)
    p = game.players[0]
    game._process_capital_maintenance(year=0, season=0)
    assert p.unmaintained_capital == {"farmer.harvester": 1}
    # Top the player up and run the next season — flag should clear.
    p.dollops = 1500.0
    game._process_capital_maintenance(year=0, season=1)
    assert p.unmaintained_capital == {}


def test_warranty_premium_debits_owner_and_credits_manufacturer_annually():
    game = _service_game()
    owner, manufacturer, _ = game.players
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    assert item is not None
    owner.add_capital(item.item_id, 1, acquired_tick=0)
    owner.add_capital_warranty(item.item_id, 1)

    owner_start = owner.dollops
    manufacturer_start = manufacturer.dollops
    game._process_capital_maintenance(year=0, season=0)

    premium = item.cost * EQUIPMENT_WARRANTY_ANNUAL_RATE
    maintenance = item.cost * DEFAULT_MAINTENANCE_FRACTION
    assert manufacturer.dollops == manufacturer_start + premium
    assert abs(owner.dollops - (owner_start - premium - maintenance)) < 1e-9
    assert owner.capital_warranties[item.item_id] == 1


def test_uninsured_failure_pays_manufacturer_and_ship_freight_with_downtime():
    game = _service_game()
    owner, manufacturer, transporter = game.players
    game.turn_manager._rng = _FixedRng([0.0])
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    assert item is not None
    owner.add_capital(item.item_id, 1, acquired_tick=-8)
    owner.receive_resources(ResourceType.FREIGHT, EQUIPMENT_REPAIR_SHIP_FREIGHT)
    manufacturer_start = manufacturer.dollops
    transporter_start = transporter.dollops
    freight_credit = game.market.current_price(ResourceType.FREIGHT)

    game._process_capital_maintenance(year=0, season=3)

    repair_fee = item.cost * EQUIPMENT_FAILURE_REPAIR_FRACTION
    assert manufacturer.dollops == manufacturer_start + repair_fee
    assert transporter.dollops == transporter_start + freight_credit
    assert owner.inventory.get(ResourceType.FREIGHT) == 0
    assert owner.failed_capital[item.item_id] == 1
    assert owner.effective_capital_inventory().get(item.item_id, 0) == 0
    assert owner.capital_repair_in_progress == [{
        "item_id": item.item_id,
        "count": 1,
        "completes_at_tick": 4,
    }]

    game._process_capital_maintenance(year=1, season=0)
    assert owner.failed_capital.get(item.item_id, 0) == 0
    assert owner.capital_repair_in_progress == []
    assert owner.effective_capital_inventory().get(item.item_id, 0) == 1


def test_uninsured_failure_stays_down_when_owner_cannot_pay_repair():
    game = _service_game()
    owner, manufacturer, _ = game.players
    game.turn_manager._rng = _FixedRng([0.0])
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    assert item is not None
    owner.add_capital(item.item_id, 1, acquired_tick=-8)
    owner.dollops = 1.0
    manufacturer_start = manufacturer.dollops

    game._process_capital_maintenance(year=0, season=3)

    assert manufacturer.dollops == manufacturer_start
    assert owner.failed_capital[item.item_id] == 1
    assert owner.capital_repair_in_progress == []
    assert owner.effective_capital_inventory().get(item.item_id, 0) == 0


def test_cargo_plane_allows_same_season_air_repair():
    game = _service_game()
    owner, manufacturer, transporter = game.players
    game.turn_manager._rng = _FixedRng([0.0])
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    assert item is not None
    owner.add_capital(item.item_id, 1, acquired_tick=-8)
    owner.receive_resources(ResourceType.FREIGHT, EQUIPMENT_REPAIR_AIR_FREIGHT)
    transporter.add_capital("transporter.cargo_plane", 1, acquired_tick=0)
    transporter.add_capital_warranty("transporter.cargo_plane", 1)
    manufacturer_start = manufacturer.dollops
    transporter_start = transporter.dollops
    freight_credit = (
        game.market.current_price(ResourceType.FREIGHT)
        * EQUIPMENT_REPAIR_AIR_FREIGHT
    )
    cargo_plane = find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane")
    assert cargo_plane is not None
    cargo_plane_maintenance = cargo_plane.cost * DEFAULT_MAINTENANCE_FRACTION

    game._process_capital_maintenance(year=0, season=3)

    repair_fee = item.cost * EQUIPMENT_FAILURE_REPAIR_FRACTION
    assert manufacturer.dollops == manufacturer_start + repair_fee
    assert (
        transporter.dollops
        == transporter_start + freight_credit - cargo_plane_maintenance
    )
    assert owner.inventory.get(ResourceType.FREIGHT) == 0
    assert owner.failed_capital.get(item.item_id, 0) == 0
    assert owner.capital_repair_in_progress == []
    assert owner.effective_capital_inventory().get(item.item_id, 0) == 1
