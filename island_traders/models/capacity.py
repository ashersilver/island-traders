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
    # Manufacturer capacity consumed to build this item. A light tool is 1;
    # large plant, aircraft, shipyards, labs, and theatres consume more.
    capacity_units: int = 1
    # Counts toward the seasonal grid-electricity Oil surcharge. Defaults to
    # False so mobile fuel-burners, storage, offices, and classrooms are not
    # double-charged beyond their existing production inputs.
    energy_intensive: bool = False
    # Optional lease terms; when set, this capital item can be financed
    # through the lease subsystem.
    lease_terms: dict | None = None


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
    items = list(catalogue)
    return [it for it in items if it.role == role] + [it for it in items if it.role == "Any"]


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


def technical_workshop_trainee_capacity(
    catalogue: Iterable[CapitalItem], owned: dict[str, int],
) -> int:
    """Sum the flat ``effects['technical_workshop_trainees']`` from every
    owned item — the maximum number of technician trainees that can be
    in training at the same time on this island.

    Technical Workshops are the physical-plant prerequisite for running
    Technician-tier training courses. The cap is per-trainee (the
    workshop floor space holds a fixed headcount), independent of how
    many distinct courses those trainees are spread across.
    """
    total = 0
    for it in catalogue:
        n = owned.get(it.item_id, 0)
        if n <= 0:
            continue
        total += int(it.effects.get("technical_workshop_trainees", 0)) * n
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
    # Wave 7.3 (CNC Workshop): stepped-staffing metadata. tier_capacity is the
    # portion of equipment/workforce cap contributed by tiered items;
    # tier_dedicated is how many workers were auto-dedicated to them; and
    # next_tier_gain is the extra output one more dedicated worker would add
    # (0 when every owned tiered unit is fully staffed) — surfaced to the
    # What-If panel so the UI can hint "add 1 tradesman → +4 Spares/season".
    tier_capacity: float = 0.0
    tier_dedicated: int = 0
    next_tier_gain: float = 0.0

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


# Wave 7.3 — stepped-staffing capacity primitive.  An equipment effect
#     tiered_capacity: {"output": "Spares", "base": 2,
#                       "per_worker": [6, 10], "band": "skilled"}
# replaces the linear workforce term for THAT ITEM'S units only: each owned
# unit contributes `base` output capacity unstaffed, or `per_worker[k-1]`
# with k dedicated workers (k capped at len(per_worker)).  Other equipment
# keeps the flat-capacity + linear-workforce model.
#
# Draw order (contract): dedicated workers are drawn from the named band
# BEFORE general allocation, walking the catalogue in declaration order and
# filling each owned unit to its worker cap before moving to the next unit.
# The remaining pool is what every recipe's linear workforce term then sees,
# so dedicating tradesmen to a CNC Workshop deliberately thins the labour
# available to the island's other lines.
_TIER_BAND_ALIASES: dict[str, WorkerBand] = {
    "skilled": WorkerBand.TECHNICIAN,
    "technician": WorkerBand.TECHNICIAN,
    "manager": WorkerBand.MANAGER,
    "worker": WorkerBand.WORKER,
}


def tiered_dedication(
    catalogue: Iterable[CapitalItem],
    owned: dict[str, int],
    workforce: dict[WorkerBand, int],
) -> tuple[dict[str, float], dict[WorkerBand, int], dict[str, dict]]:
    """Auto-assign dedicated workers to tiered-capacity equipment.

    Returns ``(tier_capacity_by_output, remaining_workforce, meta_by_output)``
    where meta carries ``{"dedicated": n, "next_tier_gain": g}`` per output.
    The input ``workforce`` dict is not mutated.
    """
    remaining: dict[WorkerBand, int] = dict(workforce)
    tier_caps: dict[str, float] = {}
    meta: dict[str, dict] = {}
    for it in catalogue:
        n = owned.get(it.item_id, 0)
        if n <= 0:
            continue
        spec = it.effects.get("tiered_capacity")
        if not spec:
            continue
        output = str(spec.get("output", ""))
        base = float(spec.get("base", 0))
        steps = [float(x) for x in spec.get("per_worker", [])]
        band = _TIER_BAND_ALIASES.get(
            str(spec.get("band", "skilled")).lower(), WorkerBand.TECHNICIAN
        )
        out_meta = meta.setdefault(output, {"dedicated": 0, "next_tier_gain": 0.0})
        for _unit in range(int(n)):
            k = min(len(steps), max(0, remaining.get(band, 0)))
            remaining[band] = remaining.get(band, 0) - k
            contribution = steps[k - 1] if k > 0 else base
            tier_caps[output] = tier_caps.get(output, 0.0) + contribution
            out_meta["dedicated"] += k
            if k < len(steps) and out_meta["next_tier_gain"] == 0.0:
                next_step = steps[k]
                prev_step = steps[k - 1] if k > 0 else base
                out_meta["next_tier_gain"] = max(0.0, next_step - prev_step)
    return tier_caps, remaining, meta


def compute_capacity(
    recipe: ProductionRecipe,
    catalogue: Iterable[CapitalItem],
    owned: dict[str, int],
    workforce: dict[WorkerBand, int],
    on_hand: dict[str, float],
) -> CapacityResult:
    catalogue = list(catalogue)
    tier_caps, remaining_wf, tier_meta = tiered_dedication(catalogue, owned, workforce)
    tier_total = tier_caps.get(recipe.output, 0.0)
    # The linear workforce term always sees the post-dedication pool; the
    # tiered units' output rides on their dedicated staff, so it is added on
    # top of whatever the remaining pool supports linearly.
    workforce_cap = workforce_capacity(recipe, remaining_wf)
    if tier_total > 0 and workforce_cap != float("inf"):
        workforce_cap += tier_total
    meta = tier_meta.get(recipe.output, {})
    return CapacityResult(
        output=recipe.output,
        equipment_cap=equipment_capacity(catalogue, owned, recipe.output) + tier_total,
        workforce_cap=workforce_cap,
        input_cap=input_capacity(recipe, on_hand),
        tier_capacity=tier_total,
        tier_dedicated=int(meta.get("dedicated", 0)),
        next_tier_gain=float(meta.get("next_tier_gain", 0.0)),
    )
