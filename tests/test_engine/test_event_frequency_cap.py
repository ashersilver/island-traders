"""Tests for the 2026-05-27 event-frequency-cap brief.

A player can suffer at most HALT_EVENTS_PER_PLAYER_PER_YEAR
production-halting events per game year.  A halt event is one with
outage=True OR yield_modifier <= 0.1.  Soft damage (yield ~0.5) is
uncapped.  Addresses the "5 halt events in 5 consecutive seasons"
playtest reports.
"""
from __future__ import annotations

import random

from island_traders.constants import HALT_EVENTS_PER_PLAYER_PER_YEAR
from island_traders.engine.events import (
    EventChart, EventResult, SeasonEventResolver,
)
from island_traders.models.player import Player
from island_traders.models.role import ROLES


def _player(pid: int = 1, role: str = "Miner") -> Player:
    return Player(pid, role, [ROLES[role]], 100.0, is_human=False)


def _halt_only_chart(role: str = "Miner") -> EventChart:
    """A chart that ALWAYS draws a full-outage halt event."""
    return EventChart.from_entries(role, [
        {
            "name": "Mine Collapse",
            "weight": 1.0,
            "yield_modifier": 0.0,
            "outage": True,
            "damage_seasons": 0,
            "natural_disaster": False,
        },
    ])


def _halt_or_normal_chart(role: str = "Miner") -> EventChart:
    """A chart with a halt and a normal event so re-rolls can escape."""
    return EventChart.from_entries(role, [
        {
            "name": "Mine Collapse",
            "weight": 0.5,
            "yield_modifier": 0.0,
            "outage": True,
        },
        {
            "name": "Normal Output",
            "weight": 0.5,
            "yield_modifier": 1.0,
            "outage": False,
        },
    ])


# ─────────────────────────────────────────────────────────────────────────
# EventResult.is_halt_event
# ─────────────────────────────────────────────────────────────────────────


def test_is_halt_event_classification():
    assert EventResult("Outage", outage=True).is_halt_event is True
    assert EventResult("Zero yield", yield_modifier=0.0).is_halt_event is True
    assert EventResult("Tiny yield", yield_modifier=0.1).is_halt_event is True
    # Soft damage is NOT a halt.
    assert EventResult("Damage", yield_modifier=0.5).is_halt_event is False
    assert EventResult("Normal", yield_modifier=1.0).is_halt_event is False


# ─────────────────────────────────────────────────────────────────────────
# Cap behaviour
# ─────────────────────────────────────────────────────────────────────────


def test_first_halt_in_year_is_allowed():
    """The budgeted halt event fires normally."""
    miner = _player()
    resolver = SeasonEventResolver(
        charts={"Miner": _halt_only_chart()}, rng=random.Random(0)
    )
    results = resolver.resolve_all([miner], {}, year=0)
    assert results[miner.player_id].is_halt_event is True
    assert resolver.last_suppressions == []


def test_second_halt_in_same_year_is_suppressed():
    """Once the budget (1/year) is used, a second halt in the same year
    re-rolls.  With a halt-or-normal chart the re-roll can land on
    Normal Operations."""
    miner = _player()
    resolver = SeasonEventResolver(
        charts={"Miner": _halt_or_normal_chart()}, rng=random.Random(1)
    )
    # Force the budget to be already used this year.
    resolver._halt_count_year = 0
    resolver._halt_counts = {miner.player_id: HALT_EVENTS_PER_PLAYER_PER_YEAR}

    results = resolver.resolve_all([miner], {}, year=0)
    # The result must NOT be a halt (re-roll avoided it, or fell back to
    # Normal Operations).
    assert results[miner.player_id].is_halt_event is False


def test_suppressed_halt_falls_back_to_normal_when_chart_is_all_halt():
    """If every re-roll is a halt (all-halt chart), the suppression
    falls back to Normal Operations."""
    miner = _player()
    resolver = SeasonEventResolver(
        charts={"Miner": _halt_only_chart()}, rng=random.Random(2)
    )
    resolver._halt_count_year = 0
    resolver._halt_counts = {miner.player_id: HALT_EVENTS_PER_PLAYER_PER_YEAR}

    results = resolver.resolve_all([miner], {}, year=0)
    res = results[miner.player_id]
    assert res.is_halt_event is False
    assert res.event_name == "Normal Operations"
    # A suppression message was recorded.
    assert resolver.last_suppressions
    assert "suppressed halt" in resolver.last_suppressions[0].lower()


def test_budget_resets_each_year():
    """The halt budget resets when the year changes — a player can
    suffer one halt per year, not one per game."""
    miner = _player()
    resolver = SeasonEventResolver(
        charts={"Miner": _halt_only_chart()}, rng=random.Random(3)
    )
    # Year 0: first halt allowed.
    r0 = resolver.resolve_all([miner], {}, year=0)
    assert r0[miner.player_id].is_halt_event is True
    # Year 0 again (next season): second halt suppressed.
    r0b = resolver.resolve_all([miner], {}, year=0)
    assert r0b[miner.player_id].is_halt_event is False
    # Year 1: budget reset, halt allowed again.
    r1 = resolver.resolve_all([miner], {}, year=1)
    assert r1[miner.player_id].is_halt_event is True


def test_soft_damage_does_not_consume_budget():
    """A 0.5-yield damage event is not a halt, so it neither consumes
    the budget nor gets suppressed."""
    miner = _player()
    damage_chart = EventChart.from_entries("Miner", [
        {"name": "Minor Setback", "weight": 1.0, "yield_modifier": 0.5},
    ])
    resolver = SeasonEventResolver(
        charts={"Miner": damage_chart}, rng=random.Random(4)
    )
    # Many seasons of soft damage — none consume the halt budget.
    for _ in range(5):
        results = resolver.resolve_all([miner], {}, year=0)
        assert results[miner.player_id].is_halt_event is False
    assert resolver._halt_counts.get(miner.player_id, 0) == 0


def test_each_player_has_independent_budget():
    """Player A's halt doesn't consume player B's budget."""
    a = _player(pid=1)
    b = _player(pid=2)
    resolver = SeasonEventResolver(
        charts={"Miner": _halt_only_chart()}, rng=random.Random(5)
    )
    results = resolver.resolve_all([a, b], {}, year=0)
    # Both get their first-of-year halt.
    assert results[1].is_halt_event is True
    assert results[2].is_halt_event is True


def test_no_year_arg_disables_cap_legacy_behaviour():
    """When `year` is not passed (legacy callers / tests), the cap is
    disabled — every halt fires, preserving prior behaviour."""
    miner = _player()
    resolver = SeasonEventResolver(
        charts={"Miner": _halt_only_chart()}, rng=random.Random(6)
    )
    # Multiple resolve_all calls with no year — all halts fire.
    for _ in range(5):
        results = resolver.resolve_all([miner], {})
        assert results[miner.player_id].is_halt_event is True
    assert resolver.last_suppressions == []
