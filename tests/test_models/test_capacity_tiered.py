"""Wave 7.3 — CNC Workshop stepped-staffing capacity primitive.

A `tiered_capacity` equipment effect replaces the linear workforce term for
that item's units only: 0 dedicated staff → base, k staff → per_worker[k-1]
(capped).  Dedicated workers are drawn from the named band BEFORE general
allocation (catalogue order, each unit filled to its cap first), so the
remaining pool is what every other line's linear term sees.
"""
from __future__ import annotations

from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.engineering import adjusted_capacity_for_engineers
from island_traders.models.capacity import (
    CapitalItem,
    ProductionRecipe,
    compute_capacity,
    find_item,
    tiered_dedication,
)
from island_traders.models.profession import WorkerBand


def _cnc(item_id: str = "m.cnc") -> CapitalItem:
    return CapitalItem(
        item_id=item_id,
        name="CNC Workshop",
        role="Manufacturer",
        cost=150.0,
        delivery_seasons=1,
        effects={"tiered_capacity": {
            "output": "Spares", "base": 2, "per_worker": [6, 10],
            "band": "skilled",
        }},
    )


def _spares_recipe() -> ProductionRecipe:
    return ProductionRecipe(
        role="Manufacturer", output="Spares",
        inputs={"Metal": 2.0, "Oil": 1.0},
        technician_per_unit=1.0,
    )


_PLENTY = {"Metal": 1000.0, "Oil": 1000.0}


def test_tier_steps_2_6_10_by_dedicated_tradesmen():
    recipe = _spares_recipe()
    for technicians, expected in [(0, 2), (1, 6), (2, 10)]:
        cap = compute_capacity(
            recipe=recipe,
            catalogue=[_cnc()],
            owned={"m.cnc": 1},
            workforce={WorkerBand.TECHNICIAN: technicians},
            on_hand=_PLENTY,
        )
        assert cap.tier_capacity == expected
        # All technicians are dedicated (drawn before general allocation), so
        # the linear term contributes nothing and the tier IS the cap.
        assert cap.max_producible == expected
        assert cap.tier_dedicated == technicians


def test_extra_tradesmen_beyond_the_cap_feed_the_linear_term():
    # 3 technicians, 1 workshop: 2 dedicated (cap), the 3rd stays in the
    # general pool and supports 1 more unit linearly (1 tech per unit).
    cap = compute_capacity(
        recipe=_spares_recipe(),
        catalogue=[_cnc()],
        owned={"m.cnc": 1},
        workforce={WorkerBand.TECHNICIAN: 3},
        on_hand=_PLENTY,
    )
    assert cap.tier_capacity == 10
    assert cap.tier_dedicated == 2
    assert cap.workforce_cap == 11          # 1 linear + 10 tier
    assert cap.equipment_cap == 10          # tier only (no flat Spares plant)


def test_two_workshops_fill_in_order():
    # 3 technicians, 2 workshops: unit one fills to 2 (→10), unit two gets
    # the remaining 1 (→6).  Total tier 16, all three dedicated.
    cap = compute_capacity(
        recipe=_spares_recipe(),
        catalogue=[_cnc()],
        owned={"m.cnc": 2},
        workforce={WorkerBand.TECHNICIAN: 3},
        on_hand=_PLENTY,
    )
    assert cap.tier_capacity == 16
    assert cap.tier_dedicated == 3


def test_dedication_thins_the_pool_for_other_lines():
    goods = ProductionRecipe(
        role="Manufacturer", output="Goods",
        inputs={"Metal": 1.0}, technician_per_unit=1.0,
    )
    # Without a CNC: 2 technicians → 2 Goods linearly.
    base = compute_capacity(
        recipe=goods, catalogue=[_cnc()], owned={},
        workforce={WorkerBand.TECHNICIAN: 2}, on_hand=_PLENTY,
    )
    assert base.workforce_cap == 2
    # With a CNC owned, both technicians are dedicated to Spares first —
    # the Goods line sees an empty pool.
    thinned = compute_capacity(
        recipe=goods, catalogue=[_cnc()], owned={"m.cnc": 1},
        workforce={WorkerBand.TECHNICIAN: 2}, on_hand=_PLENTY,
    )
    assert thinned.workforce_cap == 0
    assert thinned.tier_capacity == 0       # Goods itself is not tiered


def test_next_tier_gain_powers_the_whatif_hint():
    # 0 staffed: next tradesman is worth 6-2 = +4.
    tier_caps, _remaining, meta = tiered_dedication(
        [_cnc()], {"m.cnc": 1}, {WorkerBand.TECHNICIAN: 0},
    )
    assert tier_caps == {"Spares": 2.0}
    assert meta["Spares"]["next_tier_gain"] == 4.0
    # 1 staffed: next is 10-6 = +4.  2 staffed (cap): no further gain.
    _t, _r, meta1 = tiered_dedication([_cnc()], {"m.cnc": 1}, {WorkerBand.TECHNICIAN: 1})
    assert meta1["Spares"]["next_tier_gain"] == 4.0
    _t, _r, meta2 = tiered_dedication([_cnc()], {"m.cnc": 1}, {WorkerBand.TECHNICIAN: 2})
    assert meta2["Spares"]["next_tier_gain"] == 0.0


def test_workforce_dict_is_not_mutated():
    workforce = {WorkerBand.TECHNICIAN: 2}
    tiered_dedication([_cnc()], {"m.cnc": 1}, workforce)
    assert workforce == {WorkerBand.TECHNICIAN: 2}


def test_catalogue_entry_exists_and_is_not_board_scaled():
    item = find_item(CAPITAL_CATALOGUE, "manufacturer.cnc_workshop")
    assert item is not None
    assert item.cost == 150.0
    assert item.delivery_seasons == 1
    assert item.energy_intensive is True
    spec = item.effects["tiered_capacity"]
    # _multiply_capital_capacity board-scales effects["capacity"] but must
    # leave the tier curve at player-facing per-season numbers.
    assert spec["base"] == 2
    assert spec["per_worker"] == [6, 10]
    assert spec["output"] == "Spares"


def test_no_tiered_items_means_identical_linear_behaviour():
    recipe = _spares_recipe()
    cap = compute_capacity(
        recipe=recipe, catalogue=[_cnc()], owned={},
        workforce={WorkerBand.TECHNICIAN: 4}, on_hand=_PLENTY,
    )
    assert cap.tier_capacity == 0.0
    assert cap.workforce_cap == 4
    assert cap.next_tier_gain == 0.0


def test_engineer_bonus_preserves_tier_metadata():
    cap = compute_capacity(
        recipe=_spares_recipe(), catalogue=[_cnc()], owned={"m.cnc": 1},
        workforce={WorkerBand.TECHNICIAN: 1}, on_hand=_PLENTY,
    )
    boosted = adjusted_capacity_for_engineers(cap, {"Industrial": 1}, "Spares")
    assert boosted.equipment_cap > cap.equipment_cap
    assert boosted.tier_capacity == cap.tier_capacity
    assert boosted.tier_dedicated == cap.tier_dedicated
    assert boosted.next_tier_gain == cap.next_tier_gain
