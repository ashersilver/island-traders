from __future__ import annotations

from dataclasses import replace
from math import floor

from ..models.capacity import CapacityResult, ProductionRecipe
from ..models.player import Player
from ..models.profession import ENGINEER_SPECIALTY_STACK_CAP, EngineerSpecialty, WorkerBand
from ..models.resource import ResourceType


INDUSTRIAL_CAPACITY_PER_ENGINEER = 2
CHEMICAL_OIL_RELIEF_PER_ENGINEER = 0.20
CHEMICAL_REAGENTS_CAPACITY_PER_ENGINEER = 2
ELECTRICAL_EFFICIENCY_PER_ENGINEER = 0.05


def active_engineer_specialty_counts(player: Player) -> dict[str, int]:
    """Active Engineer specialties, capped by the island stacking rule."""
    raw = player.workforce.engineer_specialty_counts()
    return {
        specialty.value: min(raw.get(specialty.value, 0), ENGINEER_SPECIALTY_STACK_CAP)
        for specialty in EngineerSpecialty
    }


def adjusted_recipe_for_engineers(
    recipe: ProductionRecipe,
    counts: dict[str, int],
) -> ProductionRecipe:
    """Apply recipe-level Engineer specialty effects."""
    chemical = counts.get(EngineerSpecialty.CHEMICAL.value, 0)
    inputs = dict(recipe.inputs)
    if chemical > 0 and ResourceType.OIL.value in inputs:
        oil_mult = max(0.0, 1.0 - CHEMICAL_OIL_RELIEF_PER_ENGINEER * chemical)
        inputs[ResourceType.OIL.value] *= oil_mult
    if inputs != recipe.inputs:
        return replace(recipe, inputs=inputs)
    return recipe


def adjusted_workforce_for_engineers(
    workforce: dict[WorkerBand, int],
    counts: dict[str, int],
) -> dict[WorkerBand, int]:
    mechanical = counts.get(EngineerSpecialty.MECHANICAL.value, 0)
    if mechanical <= 0:
        return workforce
    adjusted = dict(workforce)
    adjusted[WorkerBand.TECHNICIAN] = adjusted.get(WorkerBand.TECHNICIAN, 0) + mechanical
    return adjusted


def adjusted_capacity_for_engineers(
    cap: CapacityResult,
    counts: dict[str, int],
    output: str,
) -> CapacityResult:
    """Apply direct capacity Engineer specialty effects after base capacity."""
    bonus = INDUSTRIAL_CAPACITY_PER_ENGINEER * counts.get(
        EngineerSpecialty.INDUSTRIAL.value, 0
    )
    if output == ResourceType.REAGENTS.value:
        bonus += CHEMICAL_REAGENTS_CAPACITY_PER_ENGINEER * counts.get(
            EngineerSpecialty.CHEMICAL.value, 0
        )
    if bonus <= 0:
        return cap
    return CapacityResult(
        output=cap.output,
        equipment_cap=cap.equipment_cap + bonus,
        workforce_cap=cap.workforce_cap,
        input_cap=cap.input_cap,
    )


def electrical_efficiency_bonus(player: Player) -> float:
    counts = active_engineer_specialty_counts(player)
    return ELECTRICAL_EFFICIENCY_PER_ENGINEER * counts.get(
        EngineerSpecialty.ELECTRICAL.value, 0
    )


def effective_capital_service_life(player: Player, base_life: int) -> int:
    if base_life <= 0:
        return base_life
    counts = active_engineer_specialty_counts(player)
    if counts.get(EngineerSpecialty.MECHANICAL.value, 0) <= 0:
        return base_life
    return max(1, floor(base_life * 1.25))


def specialty_payload(player: Player) -> dict[str, object]:
    counts = active_engineer_specialty_counts(player)
    return {
        "counts": counts,
        "stack_cap": ENGINEER_SPECIALTY_STACK_CAP,
        "industrial_capacity_bonus": INDUSTRIAL_CAPACITY_PER_ENGINEER
        * counts.get(EngineerSpecialty.INDUSTRIAL.value, 0),
        "mechanical_service_life_multiplier": (
            1.25 if counts.get(EngineerSpecialty.MECHANICAL.value, 0) > 0 else 1.0
        ),
        "electrical_efficiency_bonus_pct": round(electrical_efficiency_bonus(player) * 100),
        "chemical_oil_input_multiplier": max(
            0.0,
            1.0
            - CHEMICAL_OIL_RELIEF_PER_ENGINEER
            * counts.get(EngineerSpecialty.CHEMICAL.value, 0),
        ),
    }
