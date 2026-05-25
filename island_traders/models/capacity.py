"""
Production capacity model.

A first-class, additive description of *what each island can produce* given
the capital equipment it owns, the workforce it employs, and the operating
inputs it has on hand.  See `requirements/production-capacity-model.md`.

This module is **purely declarative** at first — the engine consults the
recipes and catalogue to compute capacity caps, but does not yet *enforce*
this model in production.  The existing engine (BASE_PRODUCTION, FARMER_SEASONAL_CONVERSION,
PRODUCTION_INPUTS, MANUFACTURER_PRODUCT_LINES, etc.) continues to work
unchanged; the capacity model layers on top.

Subsequent steps in the rollout (Investing Phase, Constraint Popup,
sidebar capacity panel) will plug into this data.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable

from .profession import WorkerBand


@dataclass(frozen=True)
class CapitalItem:
    """One buyable piece of capital equipment.

    Stable identifier `item_id` lets us serialise player-owned counts without
    coupling to display names.  `effects` is a free-form dict the engine can
    interpret — typical shape: {"capacity": {"Food": 5}}, or
    {"unlocks_line": "MedicalDevices"}, etc.  Specific keys will harden as
    the engine integrates the model.
    """
    item_id: str
    name: str
    role: str
    cost: float
    delivery_seasons: int          # 0 = arrives immediately, 2 = complex item
    effects: dict = field(default_factory=dict)
    description: str = ""
    # Phase C — capital lifecycle.
    # Useful life in seasons; once a unit's age reaches this it is removed
    # from the owner's capital_inventory and must be repurchased from the
    # Manufacturer. <= 0 means "never expires".
    service_life_seasons: int = 20
    # Dp charged each season per owned unit while in service.  0.0 = fall
    # back to DEFAULT_MAINTENANCE_FRACTION × cost (the engine's rule of
    # thumb).  Set explicitly to override or to zero out (use a negative
    # sentinel like -1.0 to mean "actually nothing" if needed — for now
    # 0.0 triggers the default).
    maintenance_per_season: float = 0.0


@dataclass(frozen=True)
class ProductionRecipe:
    """Per-unit input/labour recipe for one (role, output) pair.

    All quantities are **per unit of output produced**.  Workforce values are
    fractional (e.g. 0.25 means 1 Technician can support 4 units of output
    per season).  Resource costs are in raw units of each input resource.
    """
    role: str
    output: str                                 # ResourceType value
    inputs: dict[str, float] = field(default_factory=dict)
    manager_per_unit: float = 0.0
    technician_per_unit: float = 0.0
    worker_per_unit: float = 0.0
    money_per_unit: float = 0.0                 # Dp consumed per unit (Banker model)
    description: str = ""

    def labour_per_unit(self, band: WorkerBand) -> float:
        return {
            WorkerBand.MANAGER:    self.manager_per_unit,
            WorkerBand.TECHNICIAN: self.technician_per_unit,
            WorkerBand.WORKER:     self.worker_per_unit,
        }[band]


# ---------------------------------------------------------------------------
# Helper queries — operate on iterables of CapitalItem / ProductionRecipe
# ---------------------------------------------------------------------------

def items_for_role(catalogue: Iterable[CapitalItem], role: str) -> list[CapitalItem]:
    return [it for it in catalogue if it.role == role]


def find_item(catalogue: Iterable[CapitalItem], item_id: str) -> CapitalItem | None:
    for it in catalogue:
        if it.item_id == item_id:
            return it
    return None


def recipes_for_role(recipes: Iterable[ProductionRecipe], role: str) -> list[ProductionRecipe]:
    return [r for r in recipes if r.role == role]


def recipe_for(
    recipes: Iterable[ProductionRecipe], role: str, output: str,
) -> ProductionRecipe | None:
    for r in recipes:
        if r.role == role and r.output == output:
            return r
    return None


# ---------------------------------------------------------------------------
# Capacity computation
# ---------------------------------------------------------------------------

def equipment_capacity(
    catalogue: Iterable[CapitalItem], owned: dict[str, int], output: str,
) -> float:
    """Sum the `effects['capacity'][output]` contribution from every owned item.

    `owned` maps item_id -> count.  An item with `effects = {"capacity": {"Food": 5}}`
    owned 2× contributes 10 Food capacity.
    """
    total = 0.0
    for it in catalogue:
        n = owned.get(it.item_id, 0)
        if n <= 0:
            continue
        cap = it.effects.get("capacity", {}).get(output, 0)
        total += cap * n
    return total


def technical_workshop_slot_capacity(
    catalogue: Iterable[CapitalItem], owned: dict[str, int],
) -> int:
    """Sum the flat `effects['technical_workshop_slots']` from every owned item.

    Technical Workshops are the physical-plant prerequisite for running
    Technician-tier training courses.
    """
    total = 0
    for it in catalogue:
        n = owned.get(it.item_id, 0)
        if n <= 0:
            continue
        total += int(it.effects.get("technical_workshop_slots", 0)) * n
    return total


def workforce_capacity(
    recipe: ProductionRecipe, available: dict[WorkerBand, int],
) -> float:
    """Maximum units producible given current workforce counts and the recipe's
    per-unit labour requirements.  A band requirement of 0 imposes no cap."""
    caps = []
    for band in WorkerBand:
        per_unit = recipe.labour_per_unit(band)
        if per_unit <= 0:
            continue
        caps.append(available.get(band, 0) / per_unit)
    return min(caps) if caps else float("inf")


def input_capacity(
    recipe: ProductionRecipe, on_hand: dict[str, float],
) -> float:
    """Maximum units producible given the inputs on hand."""
    caps = []
    for resource, per_unit in recipe.inputs.items():
        if per_unit <= 0:
            continue
        caps.append(on_hand.get(resource, 0) / per_unit)
    return min(caps) if caps else float("inf")


@dataclass
class CapacityResult:
    output: str
    equipment_cap: float
    workforce_cap: float
    input_cap: float

    @property
    def max_producible(self) -> float:
        return min(self.equipment_cap, self.workforce_cap, self.input_cap)

    @property
    def binding_constraint(self) -> str:
        caps = {
            "equipment": self.equipment_cap,
            "workforce": self.workforce_cap,
            "inputs":    self.input_cap,
        }
        return min(caps, key=caps.get)


def compute_capacity(
    recipe: ProductionRecipe,
    catalogue: Iterable[CapitalItem],
    owned: dict[str, int],
    workforce: dict[WorkerBand, int],
    on_hand: dict[str, float],
) -> CapacityResult:
    return CapacityResult(
        output=recipe.output,
        equipment_cap=equipment_capacity(catalogue, owned, recipe.output),
        workforce_cap=workforce_capacity(recipe, workforce),
        input_cap=input_capacity(recipe, on_hand),
    )
