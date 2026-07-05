from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BusinessCyclePhase:
    name: str
    rate_modifier: float
    consumer_demand_multiplier: float
    stability_delta: int
    note: str


PHASES: dict[str, BusinessCyclePhase] = {
    "Expansion": BusinessCyclePhase(
        "Expansion", -0.0075, 1.10, 2, "credit easy, demand rising",
    ),
    "Boom": BusinessCyclePhase(
        "Boom", 0.0150, 1.25, 5, "credit tight, demand high",
    ),
    "Contraction": BusinessCyclePhase(
        "Contraction", 0.0075, 0.85, -3, "credit tight, demand softening",
    ),
    "Trough": BusinessCyclePhase(
        "Trough", -0.0050, 0.75, -5, "credit easing, demand weak",
    ),
}

PHASE_ORDER: tuple[str, ...] = ("Expansion", "Boom", "Contraction", "Trough")
POSITIVE_EVENT_NAMES: frozenset[str] = frozenset({
    "Bumper Harvest",
    "Rich Vein",
    "High Demand Season",
    "High Demand",
    "Bull Market",
    "Production Surge",
    "Academic Excellence",
    "Medical Breakthrough",
    "Baby Boom",
})
NEGATIVE_FINANCIAL_EVENT_NAMES: frozenset[str] = frozenset({
    "Credit Crunch",
    "Bank Crisis",
})


@dataclass(frozen=True)
class BusinessCycleSnapshot:
    phase: str
    seasons_remaining: int
    rate_modifier: float
    consumer_demand_multiplier: float
    stability_delta: int
    note: str

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "seasons_remaining": self.seasons_remaining,
            "rate_modifier": self.rate_modifier,
            "consumer_demand_multiplier": self.consumer_demand_multiplier,
            "stability_delta": self.stability_delta,
            "note": self.note,
        }


class BusinessCycle:
    """Game-level business cycle using the approved phase duration table."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.phase = "Expansion"
        self.seasons_remaining = 2
        self.last_phase_change: tuple[str, str] | None = None

    def snapshot(self) -> BusinessCycleSnapshot:
        phase = PHASES[self.phase]
        return BusinessCycleSnapshot(
            phase=phase.name,
            seasons_remaining=self.seasons_remaining,
            rate_modifier=phase.rate_modifier,
            consumer_demand_multiplier=phase.consumer_demand_multiplier,
            stability_delta=phase.stability_delta,
            note=phase.note,
        )

    def advance_season(self) -> BusinessCycleSnapshot:
        """Return this season's phase, then advance the internal clock."""
        current = self.snapshot()
        self.last_phase_change = None
        self.seasons_remaining -= 1
        if self.seasons_remaining <= 0:
            old = self.phase
            self.phase = self._next_phase(old)
            self.seasons_remaining = self._duration_for(self.phase)
            self.last_phase_change = (old, self.phase)
        return current

    @staticmethod
    def _next_phase(phase: str) -> str:
        idx = PHASE_ORDER.index(phase)
        return PHASE_ORDER[(idx + 1) % len(PHASE_ORDER)]

    def _duration_for(self, phase: str) -> int:
        if phase == "Expansion":
            return 2
        if phase == "Boom":
            return self.rng.choice((1, 2))
        if phase == "Contraction":
            return 2
        return 1


def fallback_phase_for_date(year: int, season: int) -> BusinessCycleSnapshot:
    """Deterministic fallback for callers without a Game-owned cycle.

    Start at Trough to preserve the legacy Y1/Spring posted-rate curve for
    standalone helpers and unit tests that are not attached to a Game.
    Game-owned callers pass a real snapshot and start in Expansion.
    """
    tick = max(0, year * 4 + season)
    pattern = (
        ("Trough", 1),
        ("Expansion", 2),
        ("Boom", 1),
        ("Contraction", 2),
    )
    position = tick % sum(duration for _, duration in pattern)
    for phase, duration in pattern:
        if position < duration:
            info = PHASES[phase]
            return BusinessCycleSnapshot(
                phase=info.name,
                seasons_remaining=duration - position,
                rate_modifier=info.rate_modifier,
                consumer_demand_multiplier=info.consumer_demand_multiplier,
                stability_delta=info.stability_delta,
                note=info.note,
            )
        position -= duration
    return BusinessCycle().snapshot()


def event_weight_multiplier(event_name: str, phase: str) -> float:
    if phase == "Boom" and event_name in POSITIVE_EVENT_NAMES:
        return 1.5
    if phase in {"Contraction", "Trough"} and event_name in NEGATIVE_FINANCIAL_EVENT_NAMES:
        return 1.5
    return 1.0
