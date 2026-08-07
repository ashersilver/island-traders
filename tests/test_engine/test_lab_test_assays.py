"""Laboratory Tests and the soft assay gate (#26, Phase B).

Lab Tests are the Medical & Laboratory Island's third line. The Miner buys a
metal assay; without one, smelting still runs but at a reduced yield.

Deliberately a SOFT gate. `OUTPUT_PRODUCTION_INPUT_STEPS` skips an output
entirely when short, which for Metal would mean no Pathology Lab anywhere ->
no Metal -> the Manufacturer starves: exactly the cascade #47 / PR #212
removed.
"""
from __future__ import annotations

import pytest

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import ASSAY_REQUIREMENTS, BASE_PRODUCTION, BASE_PRICES
from island_traders.engine.events import EventResult
from island_traders.engine.production import ProductionEngine
from island_traders.models.resource import ResourceType
from island_traders.models.player import Player
from island_traders.models.role import ROLES


def _miner(lab_tests: int = 0) -> Player:
    miner = Player(1, "Mine", [ROLES["Miner"]], 500.0, is_human=False)
    miner.receive_resources(ResourceType.ORE, 20)
    miner.receive_resources(ResourceType.OIL, 20)
    miner.receive_resources(ResourceType.FREIGHT, 5)
    miner.receive_resources(ResourceType.MINING_EQUIPMENT, 2)
    # produce_product() is capacity-gated on plant AND workforce.
    miner.add_capital("miner.crusher", 1)
    miner.workforce.add_workers(4, training_level=2, profession="Miner")
    miner.workforce.add_workers(6, training_level=0)
    if lab_tests:
        miner.receive_resources(ResourceType.LABORATORY_TESTS, lab_tests)
    return miner


# ---------------------------------------------------------------------------
# The resource exists and is produced
# ---------------------------------------------------------------------------

def test_lab_tests_are_a_priced_medical_output():
    assert BASE_PRICES["LaboratoryTests"] > 0
    assert BASE_PRODUCTION["Doctor"]["LaboratoryTests"] > 0
    assert ResourceType.LABORATORY_TESTS in ROLES["Doctor"].produces


# ---------------------------------------------------------------------------
# assay_plan
# ---------------------------------------------------------------------------

def test_full_cover_produces_at_full_yield():
    plan = ProductionEngine().assay_plan("Miner", ResourceType.METAL, 60, on_hand=99)

    assert plan["coverage"] == 1.0
    assert plan["yield_multiplier"] == 1.0


def test_no_cover_falls_to_the_floor_but_never_to_zero():
    plan = ProductionEngine().assay_plan("Miner", ResourceType.METAL, 60, on_hand=0)
    floor = ASSAY_REQUIREMENTS["Miner"]["Metal"]["floor"]

    assert plan["used"] == 0
    assert plan["yield_multiplier"] == pytest.approx(floor)
    assert plan["yield_multiplier"] > 0, "a soft gate must never zero an output"


def test_partial_cover_scales_between_floor_and_full():
    engine = ProductionEngine()
    none = engine.assay_plan("Miner", ResourceType.METAL, 120, on_hand=0)
    half = engine.assay_plan("Miner", ResourceType.METAL, 120, on_hand=1)
    full = engine.assay_plan("Miner", ResourceType.METAL, 120, on_hand=2)

    assert none["yield_multiplier"] < half["yield_multiplier"] < full["yield_multiplier"]
    assert full["yield_multiplier"] == 1.0


def test_an_unassayed_output_is_untouched():
    plan = ProductionEngine().assay_plan("Miner", ResourceType.ORE, 60, on_hand=0)

    assert plan["needed"] == 0
    assert plan["yield_multiplier"] == 1.0


def test_assays_are_scaled_to_production_runs_not_single_units():
    """per_units is board-scale. Too fine a granularity demands more assays
    than the archipelago can make, pinning every consumer at the floor."""
    per_units = ASSAY_REQUIREMENTS["Miner"]["Metal"]["per_units"]
    season_metal = BASE_PRODUCTION["Miner"]["Metal"]

    needed = ProductionEngine().assay_plan(
        "Miner", ResourceType.METAL, int(season_metal), on_hand=0
    )["needed"]
    assert needed <= 2, f"{needed} assays for one season's Metal is too many"
    assert per_units >= season_metal / 2


# ---------------------------------------------------------------------------
# Both production paths consume assays
# ---------------------------------------------------------------------------

def test_the_bulk_path_consumes_assays():
    """The AI produces through `produce()`. The first cut only hooked
    `produce_product`, so assays were never consumed in simulation at all."""
    miner = _miner(lab_tests=4)
    before = miner.inventory.get(ResourceType.LABORATORY_TESTS)

    ProductionEngine().produce(miner, EventResult("Normal"), season_name="Spring")

    assert miner.inventory.get(ResourceType.LABORATORY_TESTS) < before


def test_both_paths_route_through_one_applier():
    """`produce()` and `produce_product()` both call `apply_assay`.

    Keeping a single applier is what stops the two paths drifting again — the
    original bug was assay logic living in `produce_product` only.
    """
    import inspect

    engine = ProductionEngine()
    for path in (engine.produce, engine.produce_product):
        assert "apply_assay" in inspect.getsource(path), (
            f"{path.__name__} must consume assays"
        )


def test_apply_assay_consumes_and_thins():
    engine = ProductionEngine()
    miner = _miner(lab_tests=1)

    thinned = engine.apply_assay(miner, "Miner", ResourceType.METAL, 120)

    assert miner.inventory.get(ResourceType.LABORATORY_TESTS) == 0   # spent what it had
    assert 0 < thinned < 120                                          # partial cover


def test_an_unassayed_miner_still_smelts():
    """The whole point of the soft gate — no Lab Tests must not stop Metal."""
    produced = ProductionEngine().produce(
        _miner(lab_tests=0), EventResult("Normal"), season_name="Spring"
    )

    assert produced.get(ResourceType.METAL, 0) > 0


def test_cover_beats_no_cover():
    engine = ProductionEngine()
    without = engine.produce(_miner(0), EventResult("Normal"), season_name="Spring")
    with_cover = engine.produce(_miner(4), EventResult("Normal"), season_name="Spring")

    assert with_cover[ResourceType.METAL] > without[ResourceType.METAL]
