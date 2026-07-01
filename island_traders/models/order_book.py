from __future__ import annotations

from dataclasses import dataclass, field

from ..constants import SEASONS


@dataclass
class ManufacturerOrderBookEntry:
    negotiation_id: int
    manufacturer_id: int
    queue_position: int
    promised_year: int | None = None
    promised_season: int | None = None
    locked: bool = False

    def to_dict(self) -> dict:
        return {
            "negotiation_id": self.negotiation_id,
            "manufacturer_id": self.manufacturer_id,
            "queue_position": self.queue_position,
            "promised_year": self.promised_year,
            "promised_season": self.promised_season,
            "locked": self.locked,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "ManufacturerOrderBookEntry":
        return cls(
            negotiation_id=int(raw["negotiation_id"]),
            manufacturer_id=int(raw["manufacturer_id"]),
            queue_position=int(raw.get("queue_position", 0)),
            promised_year=raw.get("promised_year"),
            promised_season=raw.get("promised_season"),
            locked=bool(raw.get("locked", False)),
        )


@dataclass
class ManufacturerOrderBook:
    entries: list[ManufacturerOrderBookEntry] = field(default_factory=list)

    def for_manufacturer(self, manufacturer_id: int) -> list[ManufacturerOrderBookEntry]:
        return sorted(
            (e for e in self.entries if e.manufacturer_id == manufacturer_id),
            key=lambda e: e.queue_position,
        )

    def get(self, negotiation_id: int) -> ManufacturerOrderBookEntry | None:
        return next((e for e in self.entries if e.negotiation_id == negotiation_id), None)

    def add(self, negotiation_id: int, manufacturer_id: int) -> ManufacturerOrderBookEntry:
        existing = self.get(negotiation_id)
        if existing is not None:
            return existing
        entry = ManufacturerOrderBookEntry(
            negotiation_id=negotiation_id,
            manufacturer_id=manufacturer_id,
            queue_position=len(self.for_manufacturer(manufacturer_id)),
        )
        self.entries.append(entry)
        return entry

    def remove(self, negotiation_id: int) -> None:
        self.entries = [e for e in self.entries if e.negotiation_id != negotiation_id]
        self._renumber_all()

    def reorder(self, manufacturer_id: int, ordered_negotiation_ids: list[int]) -> None:
        current = self.for_manufacturer(manufacturer_id)
        current_ids = [e.negotiation_id for e in current]
        if set(ordered_negotiation_ids) != set(current_ids):
            raise ValueError(
                "Reorder list must contain exactly this manufacturer's current queue"
            )
        locked_ids = {e.negotiation_id for e in current if e.locked}
        old_locked_order = [nid for nid in current_ids if nid in locked_ids]
        new_locked_order = [nid for nid in ordered_negotiation_ids if nid in locked_ids]
        if old_locked_order != new_locked_order:
            raise ValueError("Cannot reorder locked (in-production) entries")
        first_locked_pos = next(
            (idx for idx, entry in enumerate(current) if entry.locked),
            None,
        )
        if first_locked_pos is not None:
            locked_prefix = set(current_ids[: first_locked_pos + 1])
            if set(ordered_negotiation_ids[: first_locked_pos + 1]) != locked_prefix:
                raise ValueError("Cannot move unlocked entries ahead of locked queue entries")
        by_id = {e.negotiation_id: e for e in current}
        for pos, negotiation_id in enumerate(ordered_negotiation_ids):
            by_id[negotiation_id].queue_position = pos

    def _renumber_all(self) -> None:
        by_manufacturer: dict[int, list[ManufacturerOrderBookEntry]] = {}
        for entry in sorted(self.entries, key=lambda e: (e.manufacturer_id, e.queue_position)):
            by_manufacturer.setdefault(entry.manufacturer_id, []).append(entry)
        for group in by_manufacturer.values():
            for pos, entry in enumerate(group):
                entry.queue_position = pos

    def to_dict(self) -> dict:
        return {"entries": [entry.to_dict() for entry in self.entries]}

    @classmethod
    def from_dict(cls, raw: dict | None) -> "ManufacturerOrderBook":
        if not raw:
            return cls()
        return cls([
            ManufacturerOrderBookEntry.from_dict(entry)
            for entry in raw.get("entries", [])
        ])


def compute_promise_dates(
    order_book: ManufacturerOrderBook,
    manufacturer_id: int,
    slots_per_season: int,
    current_year: int,
    current_season: int,
) -> None:
    entries = order_book.for_manufacturer(manufacturer_id)
    slots = max(1, int(slots_per_season))
    season_capacity_used = 0
    year = int(current_year)
    season = int(current_season)
    for entry in entries:
        if season_capacity_used >= slots:
            season += 1
            if season >= len(SEASONS):
                season = 0
                year += 1
            season_capacity_used = 0
        entry.promised_year = year
        entry.promised_season = season
        season_capacity_used += 1
