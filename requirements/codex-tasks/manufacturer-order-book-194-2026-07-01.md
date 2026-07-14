# Brief — #194 Manufacturer Order Book + Production Scheduling (2026-07-01)

**Suggested owner:** Codex (engine: production queue model, sequencing/
reprioritisation, capacity-aware scheduling).
**Base off:** `origin/pre-release` at `3399e9f` (APP_VERSION `0.1.5-dev.2026-06-22.16`
— confirm current tip with `git rev-parse --short origin/pre-release` before starting).
**Tracking issue:** [#194](https://github.com/ashersilver/island-traders/issues/194).
File as `Closes #194`. Related but out of scope: [#43](https://github.com/ashersilver/island-traders/issues/43)
(full Bill-of-Materials / Master Production Schedule modelling — phase 2, not
this brief) and [#184](https://github.com/ashersilver/island-traders/issues/184)
(general manufacturing modelling concerns — background only).
**Pairs with:** Claude wires the Manufacturer-facing Order Book UI (accept/
decline/counter list, drag-to-reorder production queue).

> **Process:** See `requirements/codex-tasks/_README.md` — that file is the
> standing working agreement and overrides anything here on process.

---

## Context — what already exists

Capital equipment purchases already go through a **buyer ↔ Manufacturer
negotiation**: `CapitalOrderNegotiation` in `island_traders/models/capital_negotiation.py`
(fields: `negotiation_id`, `buyer_id`, `manufacturer_id`, `item_id`,
`maintenance_term_years`, `spares_kits`, `financing`, `buyer_offer`,
`counter_total`, `status`, `awaiting_id`). The `"review_capital_order"` pending
action already exists (`app.py:2821`) and `_handle_capital_order` (`app.py:3498`)
drives accept/decline/counter for a *single* negotiation at a time.

**What's missing:** the Manufacturer has no way to see the *whole set* of
orders they're currently carrying, prioritise which gets produced first, or
understand how their current capacity/inputs constrain the queue. Issue #194
asks for:

1. A dialog listing all (ordered) items in the order they were placed,
   able to accept/decline/counter *individual* deals from one view (not one
   negotiation surfaced at a time via the sequential wizard).
2. A sortable production schedule — items produced first consume resources,
   not necessarily processed in placement order.
3. Support for negotiation, capacity planning, and production planning as
   three coupled concerns (in that dependency order — capacity affects what
   can be promised; the schedule affects when resources get consumed).

This brief scopes **phase 1**: the order-book view + manual resequencing +
capacity-aware promise dates. Full per-item Bill-of-Materials modelling (Oil/
Metal/Patents per catalogue item, multi-season builds, computer-lab
requirements for electronics — issue #43) is **out of scope** here; use the
existing flat `production_capacity` / `capital_owned` slot model as-is.

---

## What to build

### 1 — `ManufacturerOrderBook` — a queue on top of existing negotiations

Add a new lightweight model, `island_traders/models/order_book.py`:

```python
from dataclasses import dataclass, field


@dataclass
class ManufacturerOrderBookEntry:
    negotiation_id: int          # foreign key into CapitalNegotiationLedger
    manufacturer_id: int
    queue_position: int          # 0-based; lower = produced sooner
    promised_year: int | None = None
    promised_season: int | None = None
    locked: bool = False         # True once production has started on it


@dataclass
class ManufacturerOrderBook:
    entries: list[ManufacturerOrderBookEntry] = field(default_factory=list)

    def for_manufacturer(self, manufacturer_id: int) -> list[ManufacturerOrderBookEntry]:
        return sorted(
            (e for e in self.entries if e.manufacturer_id == manufacturer_id),
            key=lambda e: e.queue_position,
        )

    def add(self, negotiation_id: int, manufacturer_id: int) -> ManufacturerOrderBookEntry:
        existing = self.for_manufacturer(manufacturer_id)
        entry = ManufacturerOrderBookEntry(
            negotiation_id=negotiation_id,
            manufacturer_id=manufacturer_id,
            queue_position=len(existing),
        )
        self.entries.append(entry)
        return entry

    def remove(self, negotiation_id: int) -> None:
        self.entries = [e for e in self.entries if e.negotiation_id != negotiation_id]
        self._renumber_all()

    def reorder(self, manufacturer_id: int, ordered_negotiation_ids: list[int]) -> None:
        """Reorder a manufacturer's queue. Locked entries cannot move before
        an unlocked entry that currently precedes them — if the caller's
        ordering violates that, raise ValueError (Claude surfaces the error;
        don't silently reorder around it)."""
        current = self.for_manufacturer(manufacturer_id)
        current_ids = [e.negotiation_id for e in current]
        if set(ordered_negotiation_ids) != set(current_ids):
            raise ValueError("Reorder list must contain exactly this manufacturer's current queue")
        locked_ids = {e.negotiation_id for e in current if e.locked}
        # Validate: every locked entry keeps its relative position among locked entries.
        old_locked_order = [nid for nid in current_ids if nid in locked_ids]
        new_locked_order = [nid for nid in ordered_negotiation_ids if nid in locked_ids]
        if old_locked_order != new_locked_order:
            raise ValueError("Cannot reorder locked (in-production) entries")
        by_id = {e.negotiation_id: e for e in current}
        for pos, nid in enumerate(ordered_negotiation_ids):
            by_id[nid].queue_position = pos

    def _renumber_all(self) -> None:
        by_manufacturer: dict[int, list[ManufacturerOrderBookEntry]] = {}
        for e in sorted(self.entries, key=lambda e: e.queue_position):
            by_manufacturer.setdefault(e.manufacturer_id, []).append(e)
        for group in by_manufacturer.values():
            for pos, e in enumerate(group):
                e.queue_position = pos
```

Attach an instance to `Game`: `game.order_book: ManufacturerOrderBook`, created
in `Game.__init__` alongside the existing `game.capital_negotiations` (or
wherever `CapitalNegotiationLedger` currently lives — mirror that pattern).

### 2 — Enqueue on order acceptance

Find where a `CapitalOrderNegotiation` transitions to `ACCEPTED` (search
`_handle_capital_order` in `app.py` and the negotiation-acceptance path in the
engine — likely `turn.py` around the counter-offer / accept handlers). The
moment a negotiation is accepted (buyer and Manufacturer agree), call:

```python
game.order_book.add(negotiation.negotiation_id, negotiation.manufacturer_id)
```

When production for an item **starts** (the existing capital-order fulfilment
/ dispatch logic — find where `buyer.place_capital_order(...)` triggers
`arrives_at` scheduling in `app.py:3891`), mark the corresponding order-book
entry `locked = True` and compute `promised_year` / `promised_season` from the
manufacturer's current queue position and remaining capacity (see §3).

When an order is fully delivered/cancelled, call `game.order_book.remove(negotiation_id)`.

### 3 — Capacity-aware promise dates

For each Manufacturer, compute how many "production slots" they have per
season (use the existing `production_capacity` concept already computed for
Manufacturer role — check `ProductionEngine` in `production.py` for the
current per-season output cap). Walking the ordered queue from the front:

```python
def compute_promise_dates(order_book: ManufacturerOrderBook, manufacturer_id: int,
                           slots_per_season: int, current_year: int, current_season: int) -> None:
    entries = order_book.for_manufacturer(manufacturer_id)
    season_capacity_used = 0
    year, season = current_year, current_season
    for entry in entries:
        if season_capacity_used >= slots_per_season:
            season += 1
            if season >= 4:  # len(SEASONS)
                season = 0
                year += 1
            season_capacity_used = 0
        entry.promised_year = year
        entry.promised_season = season
        season_capacity_used += 1
```

Call this whenever the queue changes (add, remove, reorder) so promise dates
stay current. Round-robin re-run is O(n) and fine at this scale (a handful of
orders per Manufacturer).

### 4 — New WS messages

**`manufacturer_order_book`** (read) — no new message needed; expose via
`game_state` (see §5).

**`manufacturer_reorder_queue`** (write):
```json
{ "type": "manufacturer_reorder_queue", "negotiation_ids": [12, 7, 9] }
```
Handler in `app.py`:
```python
case "manufacturer_reorder_queue":
    try:
        game.order_book.reorder(player.player_id, msg["negotiation_ids"])
        compute_promise_dates(game.order_book, player.player_id, slots_per_season, year, season)
        await ws.send_json({"type": "manufacturer_reorder_ack", "ok": True})
        await _broadcast_game_state()
    except ValueError as exc:
        await ws.send_json({"type": "manufacturer_reorder_ack", "ok": False, "error": str(exc)})
```

The existing `_handle_capital_order` (accept/decline/counter) already covers
per-negotiation actions — no new message needed there; the order-book view
just needs to call the *same* existing handler for each row, plus the new
reorder message for sequencing.

### 5 — Expose in `game_state`

In `_build_player_state()` for Manufacturer players, add:

```python
"order_book": [
    {
        "negotiation_id": e.negotiation_id,
        "queue_position": e.queue_position,
        "locked": e.locked,
        "promised_year": e.promised_year,
        "promised_season": e.promised_season,
        # Merge in the negotiation's own fields the frontend already knows
        # how to render (item_id, buyer_id, status, buyer_offer, counter_total, etc.)
        **_negotiation_summary_dict(negotiation_for(e.negotiation_id)),
    }
    for e in game.order_book.for_manufacturer(player.player_id)
],
```

Reuse whatever dict-building helper already serialises a single
`CapitalOrderNegotiation` for the existing `review_capital_order` payload —
don't duplicate field lists; call that helper and merge the order-book-only
fields on top.

---

## Tests to write

Create `tests/test_engine/test_manufacturer_order_book.py`:

1. `order_book.add()` appends at the end of that manufacturer's queue;
   `queue_position` is 0-based and contiguous.
2. `order_book.reorder()` with a valid full permutation updates positions.
3. `reorder()` raises `ValueError` if the id set doesn't match the current queue.
4. `reorder()` raises `ValueError` if it tries to move an unlocked entry ahead
   of a locked one that currently precedes it in queue order.
5. `remove()` renumbers remaining entries contiguously (no gaps).
6. `compute_promise_dates()`: with `slots_per_season=2` and 5 orders, entries
   0-1 get season N, entries 2-3 get season N+1, entry 4 gets season N+2
   (wrapping year at season index 4).
7. Integration: accept a capital-order negotiation → order-book entry appears
   for that Manufacturer with correct starting `queue_position`.
8. Integration: `manufacturer_reorder_queue` WS message updates order and
   recomputes promise dates; a second Manufacturer's queue is unaffected.

Full suite must pass: `pytest`.

---

## What Claude does next (do not implement)

- **Order Book dialog** for the Manufacturer: a table of all queued orders in
  `queue_position` order — buyer, item, agreed/proposed price, promised
  delivery date, status (proposed / countered / accepted / in-production).
  Row-level Accept / Decline / Counter buttons reuse the existing capital-order
  negotiation flow.
- **Drag-to-reorder** (or up/down buttons) on unlocked rows; sends
  `manufacturer_reorder_queue` with the full new order. Locked (in-production)
  rows are visually pinned and not draggable.
- Capacity indicator: "N of M production slots free this season" using the
  same capacity figure the engine used for `compute_promise_dates`.
