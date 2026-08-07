"""QoL explanation guide (#227).

The guide is what the player reads to work out *why* their Quality of Life
index is where it is and what to do about it.  Its whole value is that it
matches the calculation, so these tests pin it against the constants
`seasonal_qol_breakdown` actually scores with — if someone retunes a weight
without updating the prose, this fails.
"""
from __future__ import annotations

from island_traders.constants import (
    MEDICAL_SUPPLIES_STOCKPILE_PEOPLE_PER_UNIT,
    NURSE_QOL_BONUS_CAP_POINTS,
    NURSE_QOL_WORKFORCE_COVERAGE,
    PEOPLE_PER_MEAL,
    QOL_PRODUCTIVITY_MAX,
    QOL_PRODUCTIVITY_MIN,
)
from island_traders.engine.qol import qol_guide, qol_productivity_multiplier


def test_guide_covers_every_scored_component():
    """Every component key must match what seasonal_qol_breakdown emits."""
    keys = [c["key"] for c in qol_guide()["components"]]
    assert keys == ["nutrition", "medical", "consumer_goods", "stability"]


def test_component_maxima_match_the_scoring_constants():
    comps = {c["key"]: c["max_points"] for c in qol_guide()["components"]}

    # Nutrition: 20 for meals satisfied + 10 for >=3 food varieties.
    assert comps["nutrition"] == 30.0
    # Medical: 10 insurance + nurse-ratio cap + 10 stockpile.
    assert comps["medical"] == 10.0 + NURSE_QOL_BONUS_CAP_POINTS + 10.0
    assert comps["consumer_goods"] == 20.0
    # Stability starts at 15 but is clamped to 20 after cycle adjustments.
    assert comps["stability"] == 20.0


def test_maxima_deliberately_over_sum_and_the_guide_says_so():
    guide = qol_guide()
    total = sum(c["max_points"] for c in guide["components"])

    assert total > 100, "components are meant to over-sum so one can cover another"
    assert guide["total_is_clamped_to"] == 100


def test_productivity_range_matches_the_multiplier_function():
    prod = qol_guide()["productivity"]

    assert prod["min_multiplier"] == QOL_PRODUCTIVITY_MIN
    assert prod["max_multiplier"] == QOL_PRODUCTIVITY_MAX
    assert qol_productivity_multiplier(0) == QOL_PRODUCTIVITY_MIN
    assert qol_productivity_multiplier(100) == QOL_PRODUCTIVITY_MAX


def test_improvement_advice_quotes_the_live_constants():
    """The advice must carry real numbers, not numbers frozen at writing time."""
    by_key = {c["key"]: c for c in qol_guide()["components"]}
    nutrition = " ".join(by_key["nutrition"]["improve"])
    medical = " ".join(by_key["medical"]["improve"])

    assert f"1 meal per {PEOPLE_PER_MEAL} residents" in nutrition
    assert f"{NURSE_QOL_WORKFORCE_COVERAGE} workers" in medical
    assert f"per {MEDICAL_SUPPLIES_STOCKPILE_PEOPLE_PER_UNIT} residents" in medical


def test_every_component_tells_the_player_what_to_do():
    for component in qol_guide()["components"]:
        assert component["label"]
        assert component["measures"], f"{component['key']} has no description"
        assert component["improve"], f"{component['key']} has no advice"
