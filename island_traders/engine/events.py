from __future__ import annotations
import random
from dataclasses import dataclass, field
from pathlib import Path
import yaml

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

    @property
    def is_normal(self) -> bool:
        return (
            self.yield_modifier == 1.0
            and not self.outage
            and self.damage_seasons == 0
            and not self.natural_disaster
        )

    def describe(self) -> str:
        if self.outage:
            return f"[OUTAGE] {self.event_name} — no production this season"
        if self.yield_modifier != 1.0:
            pct = int(self.yield_modifier * 100)
            return f"{self.event_name} — yield at {pct}%"
        return self.event_name


@dataclass
class EventChart:
    role_name: str
    # (cumulative_weight, EventResult) — built once at load time for fast draw
    _buckets: list[tuple[float, EventResult]] = field(default_factory=list)

    def draw(self, rng: random.Random) -> EventResult:
        if not self._buckets:
            return EventResult("Normal Operations")
        roll = rng.random()
        for threshold, result in self._buckets:
            if roll <= threshold:
                return result
        return self._buckets[-1][1]

    @classmethod
    def from_entries(cls, role_name: str, entries: list[dict]) -> EventChart:
        chart = cls(role_name=role_name)
        cumulative = 0.0
        for entry in entries:
            cumulative += entry["weight"]
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
            )
            chart._buckets.append((round(cumulative, 6), result))
        return chart


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

    def resolve_all(
        self, players: list, damage_counters: dict[int, int]
    ) -> dict[int, EventResult]:
        results: dict[int, EventResult] = {}
        disaster_event: EventResult | None = None

        for player in players:
            # Players with active damage draw from a restricted "damaged" result
            if damage_counters.get(player.player_id, 0) > 0:
                results[player.player_id] = EventResult(
                    event_name="Infrastructure Damage",
                    yield_modifier=0.5,
                    damage_seasons=0,
                )
                damage_counters[player.player_id] -= 1
                continue

            role_names = [r.name for r in player.roles]
            # Use first role's chart; multi-role players share the primary role's chart
            chart = self.charts.get(role_names[0]) if role_names else None
            if chart:
                result = chart.draw(self.rng)
                results[player.player_id] = result
                if result.natural_disaster and disaster_event is None:
                    disaster_event = result
            else:
                results[player.player_id] = EventResult("Normal Operations")

        # Apply disaster to all players not already outaged
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
