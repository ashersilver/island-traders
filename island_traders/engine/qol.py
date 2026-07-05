from __future__ import annotations

from ..constants import (
    MEDICAL_SUPPLIES_STOCKPILE_PEOPLE_PER_UNIT,
    NURSE_PRODUCTIVITY_BONUS_CAP,
    NURSE_QOL_BONUS_CAP_POINTS,
    NURSE_QOL_WORKFORCE_COVERAGE,
    OIL_POLLUTION_SCALE,
    POLLUTION_HEALTH_MITIGATION,
    QOL_PRODUCTIVITY_MAX,
    QOL_PRODUCTIVITY_MIN,
    QOL_WEIGHT_FOOD,
    QOL_WEIGHT_FOREST,
    QOL_WEIGHT_HEALTH,
    QOL_WEIGHT_POLLUTION,
)
from ..models.player import Player
from ..models.resource import ResourceType


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def food_coverage(demanded: int, bought: int) -> float:
    """Fraction of annual food demand met by households."""
    if demanded <= 0:
        return 1.0
    return _clamp_unit(bought / demanded)


def health_coverage(demanded: int, bought: int) -> float:
    """Fraction of annual medical-supplies demand met by households."""
    if demanded <= 0:
        return 1.0
    return _clamp_unit(bought / demanded)


def raw_pollution_index(oil_consumed: int, population: int) -> float:
    """Unmitigated pollution index in [0, 1]."""
    if population <= 0:
        return 0.0
    scale = OIL_POLLUTION_SCALE * max(1, population)
    return _clamp_unit(oil_consumed / scale)


def mitigated_pollution_index(
    oil_consumed: int,
    population: int,
    health_cov: float,
) -> float:
    """Pollution impact after health-coverage mitigation."""
    raw = raw_pollution_index(oil_consumed, population)
    mitigation = _clamp_unit(health_cov) * POLLUTION_HEALTH_MITIGATION
    return max(0.0, raw * (1.0 - mitigation))


def compute_qol(
    food_cov: float,
    health_cov: float,
    pollution_idx: float,
    forest_coverage: float = 0.0,
) -> float:
    """Composite QoL score in [0, 1]."""
    score = (
        _clamp_unit(food_cov) * QOL_WEIGHT_FOOD
        + _clamp_unit(health_cov) * QOL_WEIGHT_HEALTH
        + (1.0 - _clamp_unit(pollution_idx)) * QOL_WEIGHT_POLLUTION
        + _clamp_unit(forest_coverage) * QOL_WEIGHT_FOREST
    )
    return _clamp_unit(score)


def qol_productivity_multiplier(qol_index: float) -> float:
    """Map a 0-100 QoL index to the brief's 0.85-1.15 production range."""
    score = max(0.0, min(100.0, qol_index))
    return round(QOL_PRODUCTIVITY_MIN + (score / 100.0) * (
        QOL_PRODUCTIVITY_MAX - QOL_PRODUCTIVITY_MIN
    ), 4)


def seasonal_qol_breakdown(
    player: Player,
    *,
    pandemic_or_disaster_active: bool = False,
    business_cycle_stability_delta: float = 0.0,
) -> dict:
    """Compute the medical-brief seasonal QoL index and component scores."""
    meals_needed = max(0, getattr(player, "_qol_meals_needed_this_season", 0))
    meals_satisfied = max(0, getattr(player, "_qol_meals_satisfied_this_season", 0))
    nutrition = 20.0 if meals_needed <= 0 or meals_satisfied >= meals_needed else (
        20.0 * meals_satisfied / meals_needed
    )
    if len(getattr(player, "_qol_food_variety_this_season", set())) >= 3:
        nutrition += 10.0

    medical = 10.0 if getattr(player, "_qol_medical_insurance_active", False) else 0.0
    workforce_count = max(1, player.workforce.count)
    active_nurses = max(0, getattr(player, "_qol_active_nurses_this_season", 0))
    nurse_ratio = min(1.0, active_nurses * NURSE_QOL_WORKFORCE_COVERAGE / workforce_count)
    medical += nurse_ratio * NURSE_QOL_BONUS_CAP_POINTS
    stockpile_needed = max(
        1,
        (max(0, player.population) + MEDICAL_SUPPLIES_STOCKPILE_PEOPLE_PER_UNIT - 1)
        // MEDICAL_SUPPLIES_STOCKPILE_PEOPLE_PER_UNIT,
    )
    if player.inventory.get(ResourceType.MEDICAL_SUPPLIES) >= stockpile_needed:
        medical += 10.0

    goods_plan = max(0, getattr(player, "_qol_goods_demanded_this_season", 0))
    goods_bought = max(0, getattr(player, "_qol_goods_bought_this_season", 0))
    consumer_goods = 20.0 if goods_plan <= 0 else min(20.0, 20.0 * goods_bought / goods_plan)

    stability = 15.0
    if pandemic_or_disaster_active:
        stability -= 10.0
    untreated = getattr(player, "_qol_untreated_sidelined_this_season", 0)
    if untreated > 0:
        stability -= 5.0
    stability += business_cycle_stability_delta
    stability = max(0.0, min(20.0, stability))

    score = max(0.0, min(100.0, nutrition + medical + consumer_goods + stability))
    nurse_productivity_bonus = min(NURSE_PRODUCTIVITY_BONUS_CAP, active_nurses * 0.10)
    return {
        "score": round(score, 2),
        "nutrition": round(nutrition, 2),
        "medical": round(medical, 2),
        "consumer_goods": round(consumer_goods, 2),
        "stability": round(stability, 2),
        "nurse_productivity_bonus": round(nurse_productivity_bonus, 3),
        "productivity_multiplier": qol_productivity_multiplier(score),
    }
