from __future__ import annotations

from ..constants import (
    OIL_POLLUTION_SCALE,
    POLLUTION_HEALTH_MITIGATION,
    QOL_WEIGHT_FOOD,
    QOL_WEIGHT_FOREST,
    QOL_WEIGHT_HEALTH,
    QOL_WEIGHT_POLLUTION,
)


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def food_coverage(demanded: int, bought: int) -> float:
    """Fraction of annual food demand met by households."""
    if demanded <= 0:
        return 1.0
    return _clamp_unit(bought / demanded)


def health_coverage(demanded: int, bought: int) -> float:
    """Fraction of annual health-services demand met by households."""
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
