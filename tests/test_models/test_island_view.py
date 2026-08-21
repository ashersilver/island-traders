"""Per-island attribution for a multi-role player (#252).

The dashboard's island tabs render one island "as if it were the only island
the player owned".  The engine pools cash, stock and workers across the roles a
player holds, so `island_view` attributes those pooled figures per island.  The
invariants that matter: every unit is allocated exactly once (the tabs sum back
to Consolidated), and a single-role player is untouched.
"""
from __future__ import annotations

import pytest

from island_traders.models.island_view import (
    equipment_value_by_island,
    island_breakdown,
    island_weights,
    personnel_by_island,
    role_professions,
    role_resources,
    split_int,
)
from island_traders.models.player import Player
from island_traders.models.resource import ResourceBundle, ResourceType
from island_traders.models.role import ROLES
from island_traders.models.workforce import Worker, Workforce
from island_traders.constants_capacity import CAPITAL_CATALOGUE


def _player(role_names, workers, dollops=300.0, inventory=None):
    p = Player(
        player_id=1,
        name="Ash",
        roles=[ROLES[name] for name in role_names],
        dollops=dollops,
    )
    p.workforce = Workforce(workers=[
        Worker(worker_id=idx + 1, profession=prof, **kwargs)
        for idx, (prof, kwargs) in enumerate(workers)
    ])
    if inventory:
        p.inventory = ResourceBundle(dict(inventory))
    return p


def _miner_banker(**kwargs):
    return _player(
        ["Miner", "Banker"],
        [
            ("Miner", {}),
            ("MiningTechnician", {}),
            ("OilExtractionWorker", {}),
            ("Banker", {}),
            ("Actuary", {}),
            ("Unskilled", {}),
        ],
        **kwargs,
    )


# --- static maps -----------------------------------------------------------

def test_role_professions_covers_the_island_specialists():
    assert "Miner" in role_professions("Miner")
    assert "Actuary" in role_professions("Banker")
    assert "Actuary" not in role_professions("Miner")


def test_role_resources_covers_outputs_inputs_and_product_lines():
    miner = role_resources("Miner")
    assert {"Ore", "Metal", "Oil", "Freight"} <= miner
    # Farmer's seasonal conversion table, not BASE_PRODUCTION.
    assert {"Grain", "Produce", "Fish"} <= role_resources("Farmer")
    # Manufacturer's outputs come from the product lines.
    assert {"Goods", "FarmMachinery"} <= role_resources("Manufacturer")


# --- allocation primitives -------------------------------------------------

@pytest.mark.parametrize("total", [0, 1, 2, 3, 7, 10, 101])
def test_split_int_allocates_every_unit_exactly_once(total):
    parts = split_int(total, {"Miner": 0.7, "Banker": 0.3})
    assert sum(parts.values()) == total
    assert all(v >= 0 for v in parts.values())


def test_split_int_is_stable_and_favours_the_larger_weight():
    parts = split_int(10, {"Miner": 0.7, "Banker": 0.3})
    assert parts == {"Miner": 7, "Banker": 3}
    assert split_int(10, {"Miner": 0.7, "Banker": 0.3}) == parts


# --- island weights --------------------------------------------------------

def test_weights_come_from_unambiguously_held_workers():
    # 3 mining specialists vs 2 banking specialists; Unskilled is claimed by
    # neither island and so does not move the weights.
    weights = island_weights(_miner_banker())
    assert weights["Miner"] == pytest.approx(0.6)
    assert weights["Banker"] == pytest.approx(0.4)


def test_weights_fall_back_to_labour_requirements_without_specialists():
    p = _player(["Miner", "Banker"], [("Unskilled", {}), ("Unskilled", {})])
    weights = island_weights(p)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert set(weights) == {"Miner", "Banker"}


# --- personnel -------------------------------------------------------------

def test_personnel_puts_each_specialist_on_their_own_island():
    per_island = personnel_by_island(_miner_banker())
    assert set(per_island["Miner"]) == {"Miner", "MiningTechnician",
                                        "OilExtractionWorker", "Unskilled"}
    assert set(per_island["Banker"]) == {"Banker", "Actuary"}


def test_personnel_totals_match_the_consolidated_roster():
    p = _miner_banker()
    per_island = personnel_by_island(p)
    consolidated = p.workforce.profession_summary()
    for key, counts in consolidated.items():
        allocated = sum(
            per_island[role].get(key, {}).get("active", 0)
            for role in per_island
        )
        assert allocated == counts["active"], key


def test_shared_professions_are_split_not_duplicated():
    # Chef and Mechanic belong to several islands; each worker still lands on
    # exactly one tab so the tabs do not double-count them.
    p = _player(
        ["Miner", "Manufacturer"],
        [("Miner", {}), ("AssemblyWorker", {}), ("Chef", {}), ("Mechanic", {})],
    )
    per_island = personnel_by_island(p)
    for profession in ("Chef", "Mechanic"):
        placed = sum(
            per_island[role].get(profession, {}).get("active", 0)
            for role in per_island
        )
        assert placed == 1, profession


# --- equipment -------------------------------------------------------------

def test_equipment_lands_on_the_island_that_owns_it():
    p = _miner_banker()
    p.capital_inventory = {"miner.excavator": 1}
    values = equipment_value_by_island(p, CAPITAL_CATALOGUE, current_tick=0)
    assert values["Miner"] > 0
    assert values["Banker"] == 0
    assert values["Miner"] == pytest.approx(
        p.capital_book_value(CAPITAL_CATALOGUE, 0), abs=0.1
    )


# --- full breakdown --------------------------------------------------------

def test_single_role_player_has_no_breakdown():
    p = _player(["Farmer"], [("Farmer", {})])
    assert island_breakdown(p, CAPITAL_CATALOGUE) == []


def test_breakdown_isolates_cash_stock_and_people():
    p = _miner_banker(inventory={
        ResourceType.ORE: 10,
        ResourceType.FINANCE: 6,
    })
    miner, banker = island_breakdown(p, CAPITAL_CATALOGUE)

    assert miner["role"] == "Miner"
    assert banker["role"] == "Banker"
    # Ore is a Mining resource; Finance is a Banking one.
    assert miner["inventory"] == {"Ore": 10}
    assert banker["inventory"] == {"Finance": 6}
    # Cash is pooled in the engine, so it splits by island weight.
    assert miner["treasury"] == pytest.approx(180.0)
    assert banker["treasury"] == pytest.approx(120.0)
    assert "Banker" not in miner["workforce_professions"]
    assert "Miner" not in banker["workforce_professions"]


def test_breakdown_sums_back_to_the_consolidated_figures():
    p = _miner_banker(inventory={
        ResourceType.ORE: 7,
        ResourceType.OIL: 5,
        ResourceType.FINANCE: 3,
        ResourceType.MEAT: 4,          # claimed by neither island
    })
    islands = island_breakdown(p, CAPITAL_CATALOGUE)

    assert sum(i["treasury"] for i in islands) == pytest.approx(p.dollops)
    assert sum(i["workforce_count"] for i in islands) == p.workforce.count
    assert sum(i["workforce_active"] for i in islands) == len(
        p.workforce.active_workers
    )
    for resource, qty in p.inventory.amounts.items():
        allocated = sum(i["inventory"].get(resource.value, 0) for i in islands)
        assert allocated == qty, resource


def test_unclaimed_stock_is_shared_out_rather_than_dropped():
    p = _miner_banker(inventory={ResourceType.MEAT: 5})
    islands = island_breakdown(p, CAPITAL_CATALOGUE)
    assert sum(i["inventory"].get("Meat", 0) for i in islands) == 5
    assert all(i["inventory"].get("Meat", 0) > 0 for i in islands)
