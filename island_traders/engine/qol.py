from __future__ import annotations

from ..constants import (
    MEDICAL_SUPPLIES_STOCKPILE_PEOPLE_PER_UNIT,
    PEOPLE_PER_MEAL,
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


def qol_guide() -> dict:
    """Player-facing explanation of the seasonal QoL index (#227).

    Derived from the constants that `seasonal_qol_breakdown` actually reads, so
    the explanation cannot drift from the calculation.  Static for a given
    build — the client fetches it once and caches it.

    Note the component maxima sum to more than 100 (30 + 35 + 20 + 20 = 105).
    That is deliberate: `seasonal_qol_breakdown` clamps the total to 100, so a
    strong showing on one component can cover a shortfall on another rather
    than every single line having to be perfect.
    """
    return {
        "index_range": [0, 100],
        "total_is_clamped_to": 100,
        "productivity": {
            "min_multiplier": QOL_PRODUCTIVITY_MIN,
            "max_multiplier": QOL_PRODUCTIVITY_MAX,
            "summary": (
                f"Production is scaled by {QOL_PRODUCTIVITY_MIN}x at QoL 0 rising "
                f"linearly to {QOL_PRODUCTIVITY_MAX}x at QoL 100 — a "
                f"{round((QOL_PRODUCTIVITY_MAX - QOL_PRODUCTIVITY_MIN) * 100)} "
                "percentage-point swing between a miserable island and a thriving one."
            ),
        },
        "components": [
            {
                "key": "nutrition",
                "label": "Nutrition",
                "max_points": 30.0,
                "measures": "Whether your residents are fed, and whether they eat a varied diet.",
                "improve": [
                    f"Up to 20 pts: satisfy every meal your population needs this season "
                    f"(1 meal per {PEOPLE_PER_MEAL} residents). Partial feeding scores pro-rata.",
                    "+10 pts: serve at least 3 distinct food types this season "
                    "(Food, Grain, Produce, Fish, Meat) — buy variety, don't just stockpile one.",
                ],
            },
            {
                "key": "medical",
                "label": "Medical",
                "max_points": 35.0,
                "measures": "Insurance cover, nursing capacity and medical stock on hand.",
                "improve": [
                    "+10 pts: hold an active medical insurance policy from the Banking island.",
                    f"Up to {NURSE_QOL_BONUS_CAP_POINTS} pts: employ Nurses — each covers "
                    f"{NURSE_QOL_WORKFORCE_COVERAGE} workers, and the bonus scales with the "
                    "fraction of your workforce covered.",
                    f"+10 pts: keep a MedicalSupplies stockpile of at least 1 unit per "
                    f"{MEDICAL_SUPPLIES_STOCKPILE_PEOPLE_PER_UNIT} residents.",
                ],
            },
            {
                "key": "consumer_goods",
                "label": "Consumer goods",
                "max_points": 20.0,
                "measures": "Whether households could buy the Goods they wanted this season.",
                "improve": [
                    "Buy Goods to meet your households' seasonal demand. Scores pro-rata, "
                    "so partial supply still earns partial credit.",
                ],
            },
            {
                "key": "stability",
                "label": "Stability",
                "max_points": 20.0,
                "measures": "Shocks and untreated illness — largely outside your direct control.",
                "improve": [
                    "Starts at 15 pts and is nudged by the business cycle (a boom adds, a bust subtracts).",
                    "-10 pts while a pandemic or disaster is active.",
                    "-5 pts if any worker is sidelined untreated — vaccinate and keep "
                    "MedicalSupplies on hand to avoid this.",
                ],
            },
        ],
    }


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
