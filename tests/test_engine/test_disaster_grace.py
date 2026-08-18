"""Tests for the early-game natural-disaster grace period.

Natural disasters are suppressed (re-rolled to a non-disaster, falling back
to Normal Operations) for the first DISASTER_GRACE_SEASONS seasons of Year 1,
so every island can establish before the weather can wipe it out.
"""
from __future__ import annotations

import random

from island_traders.constants import DISASTER_GRACE_SEASONS
from island_traders.engine.events import (
    EventChart, EventResult, SeasonEventResolver,
)
from island_traders.models.player import Player
from island_traders.models.role import ROLES


def _player(pid: int = 1, role: str = "Farmer") -> Player:
    return Player(pid, role, [ROLES[role]], 100.0, is_human=False)


def _disaster_only_chart(role: str = "Farmer") -> EventChart:
    """A chart that ALWAYS draws a natural disaster."""
    return EventChart.from_entries(role, [
        {"name": "Flood", "weight": 1.0, "yield_modifier": 0.0,
         "natural_disaster": True},
    ])


def _disaster_or_normal_chart(role: str = "Farmer") -> EventChart:
    """A chart with a disaster and a normal event so re-rolls can escape."""
    return EventChart.from_entries(role, [
        {"name": "Flood", "weight": 0.5, "yield_modifier": 0.0,
         "natural_disaster": True},
        {"name": "Fair Weather", "weight": 0.5, "yield_modifier": 1.0},
    ])


def test_disaster_suppressed_in_opening_seasons():
    """Seasons 0..GRACE-1 of Year 1 never surface a natural disaster."""
    for season in range(DISASTER_GRACE_SEASONS):
        farmer = _player()
        resolver = SeasonEventResolver(
            charts={"Farmer": _disaster_or_normal_chart()}, rng=random.Random(season)
        )
        results = resolver.resolve_all([farmer], {}, year=0, season_index=season)
        assert results[farmer.player_id].natural_disaster is False


def test_all_disaster_chart_falls_back_to_normal_in_grace():
    """If every re-roll is a disaster, grace falls back to Normal Operations."""
    farmer = _player()
    resolver = SeasonEventResolver(
        charts={"Farmer": _disaster_only_chart()}, rng=random.Random(1)
    )
    results = resolver.resolve_all([farmer], {}, year=0, season_index=0)
    res = results[farmer.player_id]
    assert res.natural_disaster is False
    assert res.event_name == "Normal Operations"


def test_disaster_allowed_after_grace_window():
    """Season index >= GRACE in Year 1 allows disasters again."""
    farmer = _player()
    resolver = SeasonEventResolver(
        charts={"Farmer": _disaster_only_chart()}, rng=random.Random(2)
    )
    results = resolver.resolve_all(
        [farmer], {}, year=0, season_index=DISASTER_GRACE_SEASONS
    )
    assert results[farmer.player_id].natural_disaster is True


def test_disaster_allowed_in_later_years():
    """The grace only applies to Year 1 (year==0); later years are exposed."""
    farmer = _player()
    resolver = SeasonEventResolver(
        charts={"Farmer": _disaster_only_chart()}, rng=random.Random(3)
    )
    results = resolver.resolve_all([farmer], {}, year=1, season_index=0)
    assert results[farmer.player_id].natural_disaster is True


def test_no_season_index_disables_grace_legacy():
    """Legacy callers that don't pass season_index get no grace."""
    farmer = _player()
    resolver = SeasonEventResolver(
        charts={"Farmer": _disaster_only_chart()}, rng=random.Random(4)
    )
    results = resolver.resolve_all([farmer], {}, year=0)
    assert results[farmer.player_id].natural_disaster is True
