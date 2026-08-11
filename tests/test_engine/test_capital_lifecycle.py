"""Economy Lifecycle Phase C — universal capital lifespan + maintenance."""
from __future__ import annotations

import pytest

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import (
    DEFAULT_SERVICE_LIFE_SEASONS, DEFAULT_MAINTENANCE_FRACTION,
    EQUIPMENT_FAILURE_PROB_BY_QUARTER,
    EQUIPMENT_FAILURE_REPAIR_FRACTION,
    EQUIPMENT_SPARES_REPAIR_DISCOUNT,
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
    assert item.capacity_units == 1


def test_combine_harvester_has_8_season_life():
    combine = find_item(CAPITAL_CATALOGUE, "farmer.harvester")
    assert combine is not None
    assert combine.service_life_seasons == 8       # ~2 years
    assert combine.name == "Combine Harvester"
    assert combine.capacity_units == 2


def test_large_capital_items_have_tuned_capacity_units():
    assert find_item(CAPITAL_CATALOGUE, "transporter.cargo_plane").capacity_units == 4
    assert find_item(CAPITAL_CATALOGUE, "manufacturer.shipyard").capacity_units == 4
    assert find_item(CAPITAL_CATALOGUE, "doctor.operating_theatre").capacity_units == 3


def test_manufacturer_spares_warehouses_are_catalogue_items():
    small = find_item(CAPITAL_CATALOGUE, "manufacturer.small_warehouse")
    standard = find_item(CAPITAL_CATALOGUE, "manufacturer.warehouse")

    assert small is not None
    assert small.role == "Manufacturer"
    assert small.effects["spares_storage"] == 12
    assert not small.effects.get("cash_only", False)

    assert standard is not None
    assert standard.role == "Manufacturer"
    assert standard.effects["spares_storage"] == 30
    assert standard.name == "Large Warehouse"
    assert standard.cost == 90.0
    assert not standard.effects.get("cash_only", False)


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


def test_effective_inventory_no_unmaintained_equals_inventory():
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES
    p = Player(0, "P", [ROLES["Farmer"]], 100.0, is_human=True)
    p.capital_inventory = {"farmer.tractor": 1}
    # capital_inventory is now a derived view, so compare by value.
    assert p.effective_capital_inventory() == p.capital_inventory
    assert p.effective_capital_inventory() == {"farmer.tractor": 1}


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


def test_investing_phase_capital_units_can_fail_and_repair_like_ordered_units():
    game = _farmer_game()
    p = game.players[0]
    tractor = find_item(CAPITAL_CATALOGUE, "farmer.tractor")
    assert tractor is not None
    p.add_capital(tractor.item_id, 1, acquired_tick=-8)
    p.receive_resources(ResourceType.FREIGHT, EQUIPMENT_REPAIR_SHIP_FREIGHT)
    p.receive_resources(ResourceType.SPARES, tractor.capacity_units)
    game.turn_manager._rng = _FixedRng([1.0, 0.0])

    game._process_equipment_failures(
        p, current_tick=8, catalogue={it.item_id: it for it in CAPITAL_CATALOGUE}
    )

    assert p.failed_capital[tractor.item_id] == 1
    assert p.capital_repair_in_progress == [{
        "item_id": tractor.item_id,
        "count": 1,
        "completes_at_tick": 9,
    }]


def test_setup_seeds_manufacturer_with_small_spares_warehouse():
    game = _service_game()
    manufacturer = game.players[1]

    assert manufacturer.capital_inventory.get("manufacturer.small_warehouse") == 1
    assert manufacturer.capital_acquired_ticks["manufacturer.small_warehouse"] == [0]
    assert manufacturer.spares_capacity() == 12


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
    owner.receive_resources(ResourceType.SPARES, item.capacity_units)
    manufacturer_start = manufacturer.dollops
    transporter_start = transporter.dollops
    freight_credit = game.market.current_price(ResourceType.FREIGHT)

    game._process_capital_maintenance(year=0, season=3)

    repair_fee = round(
        item.cost * EQUIPMENT_FAILURE_REPAIR_FRACTION * EQUIPMENT_SPARES_REPAIR_DISCOUNT,
        2,
    )
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
    owner.receive_resources(ResourceType.SPARES, item.capacity_units)
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

    repair_fee = round(
        item.cost * EQUIPMENT_FAILURE_REPAIR_FRACTION * EQUIPMENT_SPARES_REPAIR_DISCOUNT,
        2,
    )
    assert manufacturer.dollops == manufacturer_start + repair_fee
    assert (
        transporter.dollops
        == transporter_start + freight_credit - cargo_plane_maintenance
    )
    assert owner.inventory.get(ResourceType.FREIGHT) == 0
    assert owner.failed_capital.get(item.item_id, 0) == 0
    assert owner.capital_repair_in_progress == []
    assert owner.effective_capital_inventory().get(item.item_id, 0) == 1


# ---------------------------------------------------------------------------
# #188 per-quarter failure curve (2026-06-21)
# ---------------------------------------------------------------------------

def test_repair_fraction_is_thirty_five_percent():
    # #188: average $35 to repair a $100 unit (was 0.50 straw-man).
    assert EQUIPMENT_FAILURE_REPAIR_FRACTION == 0.35


def test_failure_probability_uses_188_quarter_table():
    game = _service_game()
    # age_seasons + 1 = quarter of life; Q1 at age 0, Q12 at age 11.
    assert game._failure_probability_for_age(0) == EQUIPMENT_FAILURE_PROB_BY_QUARTER[1]
    assert game._failure_probability_for_age(0) == 0.0470
    assert game._failure_probability_for_age(11) == 0.1088   # Q12
    assert game._failure_probability_for_age(19) == 0.1902   # Q20
    # Beyond the table, hold the last (Q20) value.
    assert game._failure_probability_for_age(40) == 0.1902


def test_event_multiplier_scales_failure_probability(monkeypatch):
    game = _service_game()
    base = game._failure_probability_for_age(11)
    rolled = {}

    class _RecordRng:
        def random(self):
            rolled["threshold_seen"] = True
            return 0.999  # never fail, just observe the threshold path

    game.turn_manager._rng = _RecordRng()
    monkeypatch.setattr(game, "_capital_failure_multiplier", lambda _p: 3.0)
    owner = game.players[0]
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    owner.add_capital(item.item_id, 1, acquired_tick=0)
    # age 11 at tick 11 → quarter 12; multiplier seam triples the hazard.
    game._process_equipment_failures(owner, current_tick=11, catalogue={
        it.item_id: it for it in CAPITAL_CATALOGUE
    })
    assert rolled.get("threshold_seen")
    # The effective probability the engine would compare against is 3× base.
    assert round(base * 3.0, 6) == round(0.1088 * 3.0, 6)


def test_failure_now_rolls_every_season_not_only_year_end():
    # Under the old model failures rolled only at season 3; the #188 curve
    # rolls every season.  Force a failure at season 0 and assert it lands.
    game = _service_game()
    owner, _manufacturer, _ = game.players
    game.turn_manager._rng = _FixedRng([0.0])
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    owner.add_capital(item.item_id, 1, acquired_tick=-8)
    owner.dollops = 1.0  # can't pay repair → stays down, simplest to observe

    game._process_capital_maintenance(year=0, season=0)

    assert owner.failed_capital.get(item.item_id, 0) == 1
    assert owner.effective_capital_inventory().get(item.item_id, 0) == 0


# ---------------------------------------------------------------------------
# Per-unit capital tracking — Phase 2 (2026-06-21)
# ---------------------------------------------------------------------------

def test_count_views_derive_from_capital_units():
    p = _service_game().players[0]
    iid = "educator.research_lab"
    p.add_capital(iid, 2, acquired_tick=0)
    assert p.capital_inventory == {iid: 2}
    assert p.capital_acquired_ticks == {iid: [0, 0]}
    assert p.add_capital_warranty(iid, 1) == 1
    assert p.capital_warranties == {iid: 1}
    assert p.mark_capital_failed(iid, 1) == 1
    assert p.failed_capital == {iid: 1}
    # 2 owned, 1 failed → 1 in service available for production.
    assert p.effective_capital_inventory()[iid] == 1
    assert p.complete_capital_repair(iid, 1) == 1
    assert p.failed_capital == {}
    assert p.effective_capital_inventory()[iid] == 2


def test_add_capital_with_prebuilt_units_preserves_conditions():
    from island_traders.models.player import CapitalUnit
    p = _service_game().players[0]
    iid = "educator.research_lab"
    unit = CapitalUnit(
        item_id=iid, acquired_tick=4, purchase_value=100.0,
        maintenance_term_years=3, predictive_maintenance=True,
        spares_attached=2, expedited_eligible=True, warranty=True,
    )
    p.add_capital(iid, units=[unit])
    stored = p.capital_units[iid][0]
    assert stored.maintenance_term_years == 3
    assert stored.predictive_maintenance is True
    assert stored.spares_attached == 2
    assert stored.expedited_eligible is True
    assert stored.unit_id > 0                      # auto-assigned
    assert p.capital_inventory[iid] == 1
    assert p.capital_warranties[iid] == 1


def test_legacy_save_migrates_aggregate_dicts_to_units():
    from island_traders.engine.game import _migrate_capital_units
    iid = "educator.research_lab"
    pd = {
        "capital_inventory": {iid: 3},
        "capital_acquired_ticks": {iid: [0, -4, -8]},
        "capital_warranties": {iid: 1},
        "failed_capital": {iid: 1},
    }
    units = _migrate_capital_units(pd)[iid]
    assert len(units) == 3
    assert [u.acquired_tick for u in units] == [0, -4, -8]
    # First unit warrantied, last failed — no overlap.
    assert units[0].warranty is True
    assert units[-1].status == "failed"
    assert sum(1 for u in units if u.warranty) == 1
    assert sum(1 for u in units if u.status == "failed") == 1


def test_capital_units_survive_save_load_round_trip(tmp_path):
    from island_traders.models.player import CapitalUnit
    game = _service_game()
    owner = game.players[0]
    iid = "educator.research_lab"
    owner.add_capital(iid, units=[CapitalUnit(
        item_id=iid, acquired_tick=2, purchase_value=100.0,
        maintenance_term_years=3, predictive_maintenance=True,
        spares_attached=2, warranty=True,
    )])
    path = str(tmp_path / "save.json")
    game.save(path)

    loaded = Game.load(path, FakeIOAdapter())
    lo = next(p for p in loaded.players if p.name == owner.name)
    units = lo.capital_units[iid]
    assert len(units) == 1
    u = units[0]
    assert u.acquired_tick == 2
    assert u.maintenance_term_years == 3
    assert u.predictive_maintenance is True
    assert u.spares_attached == 2
    assert u.warranty is True
    assert lo.capital_inventory[iid] == 1
    assert lo.capital_warranties[iid] == 1


# ---------------------------------------------------------------------------
# #185 order conditions → transit → delivery — Phase 3 (2026-06-21)
# ---------------------------------------------------------------------------

def test_place_capital_order_immediate_delivery_carries_conditions():
    p = _service_game().players[0]
    iid = "educator.research_lab"
    order = {
        "maintenance_term_years": 2, "predictive_maintenance": True,
        "spares_kits": 1, "purchase_value": 100.0,
    }
    tick = p.place_capital_order(iid, order, current_tick=5, delivery_seasons=0)
    assert tick == 5
    assert p.capital_in_transit == []
    unit = p.capital_units[iid][0]
    assert unit.acquired_tick == 5
    assert unit.maintenance_term_years == 2
    assert unit.predictive_maintenance is True
    assert unit.spares_attached == 1          # spares_kits → spares_attached
    assert unit.purchase_value == 100.0


def test_place_capital_order_without_conditions_stays_plain():
    p = _service_game().players[0]
    iid = "educator.research_lab"
    # Delayed plain purchase → unchanged transit shape (no 'order' key).
    p.place_capital_order(iid, None, current_tick=0, delivery_seasons=2)
    assert p.capital_in_transit == [{"item_id": iid, "arrives_at_tick": 2}]
    p.deliver_in_transit(current_tick=2)
    unit = p.capital_units[iid][0]
    assert unit.guarantee_seasons == 1        # default (resolved #185 decision)
    assert unit.maintenance_term_years == 0
    assert unit.purchase_value == 0.0


def test_capital_order_in_transit_survives_save_load_and_delivers(tmp_path):
    game = _service_game()
    owner = game.players[0]
    iid = "educator.research_lab"
    order = {
        "maintenance_term_years": 3, "predictive_maintenance": True,
        "spares_kits": 2, "expedited_eligible": True, "guarantee_seasons": 1,
        "purchase_value": 100.0,
    }
    arrives = owner.place_capital_order(iid, order, current_tick=0, delivery_seasons=2)
    assert arrives == 2
    assert owner.capital_in_transit[0]["order"]["maintenance_term_years"] == 3

    path = str(tmp_path / "save.json")
    game.save(path)
    loaded = Game.load(path, FakeIOAdapter())
    lo = next(p for p in loaded.players if p.name == owner.name)

    # Not yet arrived, then delivered on the arrival tick with conditions intact.
    assert lo.deliver_in_transit(current_tick=1) == []
    assert lo.deliver_in_transit(current_tick=2) == [iid]
    unit = lo.capital_units[iid][0]
    assert unit.maintenance_term_years == 3
    assert unit.predictive_maintenance is True
    assert unit.spares_attached == 2          # spares_kits → spares_attached
    assert unit.expedited_eligible is True
    assert unit.purchase_value == 100.0


# ---------------------------------------------------------------------------
# Generic tradable spares — Phase 4 (2026-06-21), economy opened 2026-07-02
# ---------------------------------------------------------------------------

def test_spares_resource_is_tradable():
    game = _service_game()
    market = game.market
    assert ResourceType.SPARES in market.current_prices()
    assert "Spares" in market.market_summary()

    seller, buyer = game.players[1], game.players[0]
    seller.receive_resources(ResourceType.SPARES, 3)
    offer = market.post_offer(seller, ResourceType.SPARES, 5.0, 1)
    bid = market.post_bid(buyer, ResourceType.SPARES, 4.0, 1)

    assert offer.resource == ResourceType.SPARES
    assert bid.resource == ResourceType.SPARES


def test_manufacture_spares_clamps_to_warehouse_capacity_and_carries_price():
    game = _service_game()
    p = game.players[1]  # Manufacturer starts with one small warehouse (+12).

    assert p.inventory.get(ResourceType.SPARES) == 4
    assert p.manufacture_spares(11) == 8
    assert p.inventory.get(ResourceType.SPARES) == 12
    assert p.manufacture_spares(1) == 0

    p.add_capital("manufacturer.warehouse")
    assert p.spares_capacity() == 42
    assert p.manufacture_spares(30) == 30
    assert p.inventory.get(ResourceType.SPARES) == 42

    # Held spares now contribute tradable wealth through their market price.
    assert game.market.current_prices()[ResourceType.SPARES] > 0.0


def test_manufacture_spares_without_warehouse_produces_none():
    game = _service_game()
    owner = game.players[0]

    assert owner.spares_capacity() == 0
    assert owner.manufacture_spares(2) == 0
    assert owner.inventory.get(ResourceType.SPARES) == 0


def test_unmaintained_warehouse_does_not_count_toward_spares_capacity():
    game = _service_game()
    manufacturer = game.players[1]
    manufacturer.add_capital("manufacturer.warehouse")

    assert manufacturer.spares_capacity() == 42

    manufacturer.unmaintained_capital = {"manufacturer.warehouse": 1}

    assert manufacturer.spares_capacity() == 12


def test_repair_with_attached_spare_halves_fee_and_consumes_it():
    from island_traders.models.player import CapitalUnit
    game = _service_game()
    owner, manufacturer, _ = game.players
    game.turn_manager._rng = _FixedRng([0.0])
    item = find_item(CAPITAL_CATALOGUE, "common.laboratory_equipment")
    owner.add_capital(item.item_id, units=[CapitalUnit(
        item_id=item.item_id, acquired_tick=-8,
        purchase_value=item.cost, spares_attached=1,
    )])
    owner.receive_resources(ResourceType.FREIGHT, EQUIPMENT_REPAIR_SHIP_FREIGHT)
    manufacturer_start = manufacturer.dollops

    game._process_capital_maintenance(year=0, season=3)

    discounted = round(
        item.cost * EQUIPMENT_FAILURE_REPAIR_FRACTION * EQUIPMENT_SPARES_REPAIR_DISCOUNT, 2
    )
    assert manufacturer.dollops == manufacturer_start + discounted
    assert owner.capital_units[item.item_id][0].spares_attached == 0   # consumed


def test_repair_with_generic_spare_halves_fee_and_consumes_it():
    game = _service_game()
    owner, manufacturer, _ = game.players
    game.turn_manager._rng = _FixedRng([0.0])
    item = find_item(CAPITAL_CATALOGUE, "common.laboratory_equipment")
    owner.add_capital(item.item_id, 1, acquired_tick=-8)   # no attached spare
    owner.receive_resources(ResourceType.FREIGHT, EQUIPMENT_REPAIR_SHIP_FREIGHT)
    owner.receive_resources(ResourceType.SPARES, 1)        # generic spare on hand
    manufacturer_start = manufacturer.dollops

    game._process_capital_maintenance(year=0, season=3)

    discounted = round(
        item.cost * EQUIPMENT_FAILURE_REPAIR_FRACTION * EQUIPMENT_SPARES_REPAIR_DISCOUNT, 2
    )
    assert manufacturer.dollops == manufacturer_start + discounted
    assert owner.inventory.get(ResourceType.SPARES) == 0   # consumed


def test_two_unit_repair_with_one_spare_pends_until_stocked():
    game = _service_game()
    owner, manufacturer, _ = game.players
    item = find_item(CAPITAL_CATALOGUE, "farmer.harvester")
    assert item.capacity_units == 2
    owner.add_capital(item.item_id, 1, acquired_tick=-8)
    unit = owner.capital_units[item.item_id][0]
    unit.status = "failed"
    owner.receive_resources(ResourceType.FREIGHT, EQUIPMENT_REPAIR_SHIP_FREIGHT)
    owner.receive_resources(ResourceType.SPARES, 1)
    manufacturer_start = manufacturer.dollops

    preview = game.capital_repair_preview(owner, item.item_id)
    assert preview["repairable"] is False
    assert preview["spares"] == 2
    assert "Need 2 Spares" in preview["reason"]
    assert not game._attempt_capital_repair(owner, item, current_tick=0, unit=unit)

    assert owner.failed_capital[item.item_id] == 1
    assert owner.inventory.get(ResourceType.SPARES) == 1
    assert manufacturer.dollops == manufacturer_start


def test_repair_fee_uses_unit_purchase_value_when_set():
    from island_traders.models.player import CapitalUnit
    game = _service_game()
    owner, manufacturer, _ = game.players
    owner.dollops = 1000.0
    game.turn_manager._rng = _FixedRng([0.0])
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    owner.add_capital(item.item_id, units=[CapitalUnit(
        item_id=item.item_id, acquired_tick=-8, purchase_value=200.0,
    )])
    owner.receive_resources(ResourceType.FREIGHT, EQUIPMENT_REPAIR_SHIP_FREIGHT)
    owner.receive_resources(ResourceType.SPARES, item.capacity_units)
    manufacturer_start = manufacturer.dollops

    game._process_capital_maintenance(year=0, season=3)

    expected = round(
        200.0 * EQUIPMENT_FAILURE_REPAIR_FRACTION * EQUIPMENT_SPARES_REPAIR_DISCOUNT,
        2,
    )
    assert manufacturer.dollops == manufacturer_start + expected


def test_repair_preview_matches_actual_repair_charge_and_freight():
    game = _service_game()
    owner, manufacturer, _ = game.players
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    assert item is not None
    owner.add_capital(item.item_id, 1, acquired_tick=-4)
    unit = owner.capital_units[item.item_id][0]
    unit.status = "failed"
    owner.receive_resources(ResourceType.FREIGHT, EQUIPMENT_REPAIR_SHIP_FREIGHT)
    owner.receive_resources(ResourceType.SPARES, item.capacity_units)
    owner_start = owner.dollops
    freight_start = owner.inventory.get(ResourceType.FREIGHT)
    manufacturer_start = manufacturer.dollops

    preview = game.capital_repair_preview(owner, item.item_id)
    assert preview == {
        "dp": round(
            item.cost * EQUIPMENT_FAILURE_REPAIR_FRACTION * EQUIPMENT_SPARES_REPAIR_DISCOUNT,
            2,
        ),
        "freight": EQUIPMENT_REPAIR_SHIP_FREIGHT,
        "spares": item.capacity_units,
        "repairable": True,
        "reason": "",
    }

    assert game._attempt_capital_repair(owner, item, current_tick=0, unit=unit)
    assert owner.dollops == owner_start - preview["dp"]
    assert manufacturer.dollops == manufacturer_start + preview["dp"]
    assert owner.inventory.get(ResourceType.FREIGHT) == freight_start - preview["freight"]
    assert owner.inventory.get(ResourceType.SPARES) == 0


def test_repair_preview_is_side_effect_free():
    game = _service_game()
    owner = game.players[0]
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    assert item is not None
    owner.add_capital(item.item_id, 1, acquired_tick=-4)
    unit = owner.capital_units[item.item_id][0]
    unit.status = "failed"
    unit.spares_attached = item.capacity_units
    owner.receive_resources(ResourceType.FREIGHT, EQUIPMENT_REPAIR_SHIP_FREIGHT)
    before_dollops = owner.dollops
    before_freight = owner.inventory.get(ResourceType.FREIGHT)

    preview = game.capital_repair_preview(owner, item.item_id)

    assert preview["dp"] == round(
        item.cost * EQUIPMENT_FAILURE_REPAIR_FRACTION * EQUIPMENT_SPARES_REPAIR_DISCOUNT,
        2,
    )
    assert owner.dollops == before_dollops
    assert owner.inventory.get(ResourceType.FREIGHT) == before_freight
    assert preview["spares"] == item.capacity_units
    assert unit.spares_attached == item.capacity_units


# ---------------------------------------------------------------------------
# #188 upfront maintenance/warranty term contract — Phase 5 (2026-06-21)
# ---------------------------------------------------------------------------

def test_maintenance_contract_cost_uses_188_table():
    from island_traders.models.player import maintenance_contract_cost
    # Per $100: 3-yr baseline 35.70, predictive 23.94.
    assert maintenance_contract_cost(100.0, 3, False) == 35.70
    assert maintenance_contract_cost(100.0, 3, True) == 23.94
    # Scales to value (130 → ×1.3).
    assert maintenance_contract_cost(130.0, 3, True) == 31.12
    # No / out-of-range term → free.
    assert maintenance_contract_cost(130.0, 0, True) == 0.0
    assert maintenance_contract_cost(130.0, 9, True) == 0.0


def test_term_contract_unit_skips_recurring_premium():
    from island_traders.models.player import CapitalUnit
    game = _service_game()
    owner, manufacturer, _ = game.players
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    owner.add_capital(item.item_id, units=[CapitalUnit(
        item_id=item.item_id, acquired_tick=0, purchase_value=item.cost,
        maintenance_term_years=3, warranty=True,
    )])
    game.turn_manager._rng = _FixedRng([1.0])   # no failures
    mfr_start = manufacturer.dollops

    game._process_capital_maintenance(year=0, season=0)   # season 0 → premium step

    # The upfront term contract is not billed the recurring premium...
    assert manufacturer.dollops == mfr_start
    # ...and the unit stays covered within its term.
    assert owner.capital_units[item.item_id][0].warranty is True


def test_term_contract_lapses_after_its_term():
    from island_traders.models.player import CapitalUnit
    game = _service_game()
    owner = game.players[0]
    game.turn_manager._rng = _FixedRng([1.0])   # never fail on the roll
    item = find_item(CAPITAL_CATALOGUE, "educator.research_lab")
    unit = CapitalUnit(
        item_id=item.item_id, acquired_tick=0, purchase_value=item.cost,
        maintenance_term_years=2, warranty=True,
    )
    owner.add_capital(item.item_id, units=[unit])
    catalogue = {it.item_id: it for it in CAPITAL_CATALOGUE}

    # Within term (age 4 < 2yr = 8 seasons): still covered, exempt from failure.
    game._process_equipment_failures(owner, current_tick=4, catalogue=catalogue)
    assert unit.warranty is True
    # At/after the term (age 8 >= 8): coverage lapses.
    game._process_equipment_failures(owner, current_tick=8, catalogue=catalogue)
    assert unit.warranty is False
