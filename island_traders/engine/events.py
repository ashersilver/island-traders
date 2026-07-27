from __future__ import annotations
import random
from dataclasses import dataclass, field
from pathlib import Path
import yaml

from ..constants import PANDEMIC_DURATION_SEASONS, SEVERITY_PROFILES
from ..engine.cycle import BusinessCycleSnapshot, event_weight_multiplier
from ..models.resource import ResourceType


@dataclass
class EventResult:
    event_name: str
    yield_modifier: float = 1.0
    productivity_bonus: int = 0
    outage: bool = False
    damage_seasons: int = 0
    natural_disaster: bool = False
    price_shock_resource: ResourceType | None = None
    price_shock_multiplier: float = 1.0
    price_shock_duration_seasons: int = 0
    flu_strain_loss: float = 0.0
    flu_doses_needed: int = 0
    flu_doses_administered: int = 0
    flu_effective_loss: float = 0.0
    severity_enabled: bool = False
    severity: str = ""
    workforce_sidelined_fraction: float = 0.0
    capital_failure_multiplier: float = 1.0
    rebuild_levy_fraction: float = 0.0
    pandemic: bool = False
    baby_boom: bool = False
    population_growth_multiplier: float = 1.0
    qol_stability_delta: int = 0

    @property
    def is_normal(self) -> bool:
        return (
            self.yield_modifier == 1.0
            and not self.outage
            and self.damage_seasons == 0
            and not self.natural_disaster
            and self.flu_effective_loss == 0.0
            and self.workforce_sidelined_fraction == 0.0
            and self.rebuild_levy_fraction == 0.0
            and not self.baby_boom
        )

    @property
    def is_halt_event(self) -> bool:
        """A production-halting event for the per-year cap (2026-05-27
        event-frequency-cap brief).  Either a full outage or a yield so
        low (<= 10%) that the season is functionally a write-off.  Soft
        damage (yield ~0.5) is NOT a halt — it's annoying but playable."""
        return self.outage or self.yield_modifier <= 0.1

    def describe(self) -> str:
        if self.outage:
            return f"[OUTAGE] {self.event_name} — no production this season"
        if self.yield_modifier != 1.0:
            pct = int(self.yield_modifier * 100)
            return f"{self.event_name} — yield at {pct}%"
        return self.event_name

    def copy(self) -> "EventResult":
        return EventResult(
            event_name=self.event_name,
            yield_modifier=self.yield_modifier,
            productivity_bonus=self.productivity_bonus,
            outage=self.outage,
            damage_seasons=self.damage_seasons,
            natural_disaster=self.natural_disaster,
            price_shock_resource=self.price_shock_resource,
            price_shock_multiplier=self.price_shock_multiplier,
            price_shock_duration_seasons=self.price_shock_duration_seasons,
            flu_strain_loss=self.flu_strain_loss,
            flu_doses_needed=self.flu_doses_needed,
            flu_doses_administered=self.flu_doses_administered,
            flu_effective_loss=self.flu_effective_loss,
            severity_enabled=self.severity_enabled,
            severity=self.severity,
            workforce_sidelined_fraction=self.workforce_sidelined_fraction,
            capital_failure_multiplier=self.capital_failure_multiplier,
            rebuild_levy_fraction=self.rebuild_levy_fraction,
            pandemic=self.pandemic,
            baby_boom=self.baby_boom,
            population_growth_multiplier=self.population_growth_multiplier,
            qol_stability_delta=self.qol_stability_delta,
        )


@dataclass
class EventChart:
    role_name: str
    # (cumulative_weight, EventResult) — built once at load time for fast draw
    _buckets: list[tuple[float, EventResult]] = field(default_factory=list)
    _entries: list[tuple[float, EventResult]] = field(default_factory=list)

    def draw(
        self,
        rng: random.Random,
        cycle: BusinessCycleSnapshot | None = None,
    ) -> EventResult:
        if not self._entries and not self._buckets:
            return EventResult("Normal Operations")
        result = self._draw_template(rng, cycle).copy()
        if result.severity_enabled:
            result = apply_severity(result, rng)
        return result

    def _draw_template(
        self,
        rng: random.Random,
        cycle: BusinessCycleSnapshot | None,
    ) -> EventResult:
        entries = self._entries
        if cycle is not None and entries:
            weighted = [
                (weight * event_weight_multiplier(result.event_name, cycle.phase), result)
                for weight, result in entries
            ]
            total = sum(weight for weight, _ in weighted)
            roll = rng.random() * total
            acc = 0.0
            for weight, result in weighted:
                acc += weight
                if roll <= acc:
                    return result
            return weighted[-1][1]
        roll = rng.random()
        for threshold, result in self._buckets:
            if roll <= threshold:
                return result
        return self._buckets[-1][1]

    def draw_avoiding_halt(
        self,
        rng: random.Random,
        max_tries: int = 3,
        cycle: BusinessCycleSnapshot | None = None,
    ) -> EventResult:
        """Draw, re-rolling up to ``max_tries`` times to avoid a halt
        event.  Falls back to Normal Operations if every roll is a halt.
        Used by the per-year halt cap (2026-05-27 event-frequency-cap
        brief) when a player has already used their halt budget."""
        result = self.draw(rng, cycle=cycle)
        tries = 0
        while result.is_halt_event and tries < max_tries:
            result = self.draw(rng, cycle=cycle)
            tries += 1
        if result.is_halt_event:
            return EventResult("Normal Operations")
        return result

    def draw_avoiding_disaster(
        self,
        rng: random.Random,
        max_tries: int = 5,
        cycle: BusinessCycleSnapshot | None = None,
    ) -> EventResult:
        """Draw, re-rolling up to ``max_tries`` times to avoid a natural
        disaster.  Falls back to Normal Operations if every roll is a disaster.
        Used for the early-game grace period (first two seasons of Year 1)
        so every island can establish before the weather turns."""
        result = self.draw(rng, cycle=cycle)
        tries = 0
        while result.natural_disaster and tries < max_tries:
            result = self.draw(rng, cycle=cycle)
            tries += 1
        if result.natural_disaster:
            return EventResult("Normal Operations")
        return result

    @classmethod
    def from_entries(cls, role_name: str, entries: list[dict]) -> EventChart:
        chart = cls(role_name=role_name)
        cumulative = 0.0
        raw_weights = [float(entry["weight"]) for entry in entries]
        total_weight = sum(raw_weights) or 1.0
        for entry, raw_weight in zip(entries, raw_weights):
            weight = raw_weight / total_weight
            cumulative += weight
            shock_r = entry.get("price_shock_resource")
            result = EventResult(
                event_name=entry["name"],
                yield_modifier=float(entry.get("yield_modifier", 1.0)),
                productivity_bonus=int(entry.get("productivity_bonus", 0)),
                outage=bool(entry.get("outage", False)),
                damage_seasons=int(entry.get("damage_seasons", 0)),
                natural_disaster=bool(entry.get("natural_disaster", False)),
                price_shock_resource=ResourceType(shock_r) if shock_r else None,
                price_shock_multiplier=float(entry.get("price_shock_multiplier", 1.0)),
                price_shock_duration_seasons=int(entry.get("price_shock_duration_seasons", 0)),
                severity_enabled=bool(entry.get("severity", False)),
                pandemic=bool(entry.get("pandemic", False)),
                baby_boom=bool(entry.get("baby_boom", False)),
                population_growth_multiplier=float(entry.get("population_growth_multiplier", 1.0)),
                qol_stability_delta=int(entry.get("qol_stability_delta", 0)),
            )
            chart._buckets.append((round(cumulative, 6), result))
            chart._entries.append((weight, result))
        return chart


def roll_severity(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.50:
        return "Minor"
    if roll < 0.85:
        return "Major"
    return "Catastrophic"


def apply_severity(result: EventResult, rng: random.Random) -> EventResult:
    severity = roll_severity(rng)
    profile = SEVERITY_PROFILES[severity]
    result.severity = severity
    result.capital_failure_multiplier = profile["capital_failure_multiplier"]
    if result.pandemic:
        result.yield_modifier = profile["pandemic_yield_modifier"]
        result.workforce_sidelined_fraction = profile["pandemic_sidelined_fraction"]
        result.damage_seasons = max(0, PANDEMIC_DURATION_SEASONS - 1)
        result.outage = False
        return result

    if severity == "Major":
        result.yield_modifier = max(0.0, result.yield_modifier - profile["yield_penalty"])
        result.damage_seasons += int(profile["damage_bonus"])
    elif severity == "Catastrophic":
        result.yield_modifier = min(result.yield_modifier, 0.2)
        if result.yield_modifier <= 0.1:
            result.outage = True
        result.damage_seasons += int(profile["damage_bonus"])
    result.workforce_sidelined_fraction = profile["workforce_sidelined_fraction"]
    if result.natural_disaster or severity == "Catastrophic":
        result.rebuild_levy_fraction = profile["rebuild_levy_fraction"]
    return result


class EventChartLoader:
    @staticmethod
    def from_yaml(path: str | Path) -> dict[str, EventChart]:
        with open(path) as f:
            data = yaml.safe_load(f)
        charts: dict[str, EventChart] = {}
        for role_name, role_data in data.items():
            entries = role_data.get("events", [])
            charts[role_name] = EventChart.from_entries(role_name, entries)
        return charts

    @staticmethod
    def default_charts() -> dict[str, EventChart]:
        default_path = Path(__file__).parent.parent.parent / "config" / "event_charts.yaml"
        if default_path.exists():
            return EventChartLoader.from_yaml(default_path)
        # Fallback: every role gets "Normal Operations"
        from ..models.role import ROLES
        return {name: EventChart(role_name=name) for name in ROLES}


class SeasonEventResolver:
    def __init__(self, charts: dict[str, EventChart], rng: random.Random | None = None):
        self.charts = charts
        self.rng = rng or random.Random()
        # Per-year halt-event budget tracking (2026-05-27 brief).
        # Reset whenever resolve_all sees a new game year.
        self._halt_counts: dict[int, int] = {}
        self._halt_count_year: int | None = None
        # Human-readable suppression messages from the most recent
        # resolve_all call; the caller (Game.run) prints them via the
        # io adapter so the cap is visible during play.
        self.last_suppressions: list[str] = []

    def resolve_all(
        self,
        players: list,
        damage_counters: dict[int, int],
        year: int | None = None,
        season_index: int | None = None,
    ) -> dict[int, EventResult]:
        from ..constants import (
            HALT_EVENTS_PER_PLAYER_PER_YEAR,
            DISASTER_GRACE_SEASONS,
        )

        # Early-game grace: no natural disasters in the first
        # DISASTER_GRACE_SEASONS seasons of Year 1, so every island can
        # establish trade/production before the weather turns.  Year is
        # 0-indexed (year 0 == "Year 1"); season_index 0 == Spring.
        in_disaster_grace = (
            year == 0
            and season_index is not None
            and season_index < DISASTER_GRACE_SEASONS
        )

        # Reset the per-year halt budget when the year rolls over.  When
        # `year` is None (legacy callers / tests that don't pass it) the
        # cap is effectively disabled — every season is treated as its
        # own budget window, preserving prior behaviour.
        if year is not None and year != self._halt_count_year:
            self._halt_counts = {}
            self._halt_count_year = year

        self.last_suppressions = []
        results: dict[int, EventResult] = {}
        disaster_event: EventResult | None = None

        for player in players:
            pid = player.player_id
            # Players with active damage draw from a restricted "damaged"
            # result (0.5 yield — NOT a halt, so uncapped).
            if damage_counters.get(pid, 0) > 0:
                results[pid] = EventResult(
                    event_name="Infrastructure Damage",
                    yield_modifier=0.5,
                    damage_seasons=0,
                )
                damage_counters[pid] -= 1
                continue

            role_names = [r.name for r in player.roles]
            # Use first role's chart; multi-role players share the primary role's chart
            chart = self.charts.get(role_names[0]) if role_names else None
            if not chart:
                results[pid] = EventResult("Normal Operations")
                continue

            result = chart.draw(self.rng, cycle=getattr(self, "current_cycle", None))

            # Early-game grace: re-draw away from natural disasters in the
            # opening seasons so nobody is wiped out before establishing.
            if in_disaster_grace and result.natural_disaster:
                result = chart.draw_avoiding_disaster(
                    self.rng, cycle=getattr(self, "current_cycle", None),
                )

            # Per-year halt cap: if this draw is a halt and the player has
            # already used their yearly halt budget, re-draw avoiding
            # halts (2026-05-27 brief).  Only applies when `year` is
            # provided.
            if (
                year is not None
                and result.is_halt_event
                and self._halt_counts.get(pid, 0) >= HALT_EVENTS_PER_PLAYER_PER_YEAR
            ):
                suppressed_name = result.event_name
                result = chart.draw_avoiding_halt(
                    self.rng,
                    cycle=getattr(self, "current_cycle", None),
                )
                self.last_suppressions.append(
                    f"{player.name}: suppressed halt event "
                    f"'{suppressed_name}' "
                    f"({self._halt_counts.get(pid, 0)}/"
                    f"{HALT_EVENTS_PER_PLAYER_PER_YEAR} halts already used "
                    f"this year). Drew '{result.event_name}' instead."
                )
            elif year is not None and result.is_halt_event:
                # Within budget — count it.
                self._halt_counts[pid] = self._halt_counts.get(pid, 0) + 1

            results[pid] = result
            if result.natural_disaster and disaster_event is None:
                disaster_event = result

        # Apply disaster to all players not already outaged (0.5 cascade,
        # not a halt, so it doesn't consume the budget).
        if disaster_event:
            for player in players:
                existing = results.get(player.player_id)
                if existing and not existing.outage and not existing.natural_disaster:
                    results[player.player_id] = EventResult(
                        event_name=f"Disaster: {disaster_event.event_name}",
                        yield_modifier=min(existing.yield_modifier, 0.5),
                        natural_disaster=True,
                    )

        return results
