# Brief — #193 Pre-season Island Status Report (2026-06-28)

**Suggested owner:** Codex (engine: P&L tracking, balance sheet, manpower
forecast serialisation).
**Base off:** `origin/pre-release` at `1e75609` (APP_VERSION `0.1.5-dev.2026-06-22.16`).
**Tracking issue:** [#193](https://github.com/ashersilver/island-traders/issues/193).
File as `Closes #193`.
**Pairs with:** Claude wires the report UI into the pre-season banner (reads
the new `season_report` block from the `pre_season_start` WS message).

> **Process:** See `requirements/codex-tasks/_README.md` — that file is the
> standing working agreement and overrides anything here on process.

---

## Goal

During the pre-season review players currently see nothing about what happened
last season. Add a concise **Island Status Report** — four panels: P&L,
Balance Sheet, Production Deficiencies, Manpower Forecast — delivered in the
`pre_season_start` WS message so Claude can display them in the banner.

---

## What to build

### 1 — Seasonal P&L accumulator on `Player`

Track revenue and costs during each season so we can report them at year-end /
season-start.  Add these to `Player.__init__` with defaults:

```python
# Reset at season-start; accumulated during that season.
player._season_revenue: float = 0.0
player._season_costs:   float = 0.0
```

**Accumulate revenue** wherever a player receives Dp from a sale:
- `player.receive_payment(amount, ...)` — increment `_season_revenue += amount`

**Accumulate costs** wherever a player spends Dp:
- `player.spend(amount, ...)` — increment `_season_costs += amount`

If `receive_payment` / `spend` don't exist as single entry-points, instrument
the market-fill paths in `turn.py` that call `player.treasury +=` or `-=`
directly; look for the pattern and add the tracking there.

**Reset at season-start:** in `TurnManager._start_season()` (or wherever season
setup runs), add:

```python
player._season_revenue = 0.0
player._season_costs   = 0.0
```

Also maintain a **rolling four-season history** on Player so the report can
show last-season and last-year figures:

```python
# Append at season-end; cap at 4 entries.
player._pl_history: list[dict] = []  # [{season, revenue, costs, profit}, ...]
```

At season-end (before reset):

```python
player._pl_history.append({
    "season": current_season_name,   # e.g. "Spring"
    "revenue": round(player._season_revenue, 2),
    "costs":   round(player._season_costs,   2),
    "profit":  round(player._season_revenue - player._season_costs, 2),
})
if len(player._pl_history) > 4:
    player._pl_history.pop(0)
```

### 2 — Balance sheet snapshot

A balance sheet is a point-in-time read of existing data. No new engine
machinery required — just serialise at pre-season time:

```python
# Assets
treasury:         player.treasury            # cash on hand
inventory_value:  sum(
    qty * market_price(res, prices)
    for res, qty in player.inventory.items()
)
capital_value:    sum(
    item.value * (item.units - item.failed_units)
    for item in player.capital_owned
)                                            # depreciated value of working capital

# Liabilities
loans_outstanding: sum(loan.balance for loan in player.loans)
```

Where `market_price(res, prices)` looks up the current buy/sell mid from the
`prices` dict (pass in the last-computed prices). If a resource has no active
market, use its base price from `constants.py`.

Compute net worth: `treasury + inventory_value + capital_value - loans_outstanding`.

### 3 — Production deficiencies

Walk `player.capital_owned` and flag any item where `failed_units > 0` or where
production last season was below capacity due to labour shortage (if that's
tracked). Return a list of dicts:

```python
[{
    "item_id":   item.item_id,
    "name":      item.name,
    "failed":    item.failed_units,
    "repairable": item.repairable,   # bool
}, ...]
```

If labour-shortfall data isn't readily available, omit it for now — the failed
equipment list is sufficient for v1.

### 4 — Manpower forecast

Compute for the coming season:

```python
{
    "population":       player.population,
    "employed":         sum(slot.count for slot in player.staffing if slot.filled),
    "capacity":         sum(slot.count for slot in player.staffing),
    "vacancies":        capacity - employed,
    "training_queue":   len([t for t in player.training_queue if not t.complete]),
    "graduating_next":  count of trainees completing in next 1 season,
}
```

(Adjust field names to match the actual `Player` attributes — check
`player.py` for the real attribute names.)

### 5 — Deliver via `pre_season_start` WS message

In `app.py`, find where `pre_season_start` is sent to the WebSocket (search
for `"pre_season_start"` in the WS broadcast / per-player send). Add a
`season_report` key **only for the receiving player** (it contains that
player's private P&L, balance sheet, etc. — don't broadcast to all):

```python
season_report = {
    "pl_history": player._pl_history,          # list of last ≤4 seasons
    "balance_sheet": {
        "treasury":         round(player.treasury, 2),
        "inventory_value":  round(inventory_value, 2),
        "capital_value":    round(capital_value, 2),
        "loans":            round(loans_outstanding, 2),
        "net_worth":        round(net_worth, 2),
    },
    "deficiencies": deficiencies_list,          # list of dicts from §3
    "manpower": manpower_dict,                  # dict from §4
}
```

The `pre_season_start` message is already sent per-player (or is it broadcast?
If broadcast, add `season_report` only to the per-player send path, not the
global one. If there's no per-player path yet, add one for this field: broadcast
everything else, then send a player-specific supplement message typed
`season_report_private`.)

**Preferred approach:** a separate WS message `season_report` sent only to the
player, immediately after `pre_season_start`, to avoid restructuring the broadcast:

```python
await ws.send_json({
    "type": "season_report",
    "season_report": season_report,
})
```

Claude will handle this in the frontend as a new WS message type.

### 6 — Serialisation

`_season_revenue`, `_season_costs`, `_pl_history` must survive save/load. Add
them to the `Player` serialise/deserialise methods (or the `__getstate__` /
`__setstate__` pattern used elsewhere). The balance sheet and deficiency data
are derived at message-send time and do NOT need to be serialised.

---

## Tests to write

Create `tests/test_engine/test_island_report.py`:

1. After a season where the player sells goods, `_season_revenue > 0`.
2. After a season where the player buys inputs, `_season_costs > 0`.
3. `_pl_history` accumulates across seasons, caps at 4, resets each season.
4. Balance sheet: `net_worth = treasury + inventory_value + capital_value - loans`.
5. Deficiencies list includes capital items with `failed_units > 0` and excludes
   fully-working items.
6. Manpower forecast: `vacancies = capacity - employed`.
7. Integration: run two seasons of a mini-game; confirm `season_report` WS
   message arrives and contains non-empty `pl_history` after season 2.

---

## What Claude does next (do not implement)

- Parse the `season_report` WS message on the frontend.
- Render four collapsible panels in the pre-season banner:
  - **P&L** — table of last ≤4 seasons with revenue / costs / profit.
  - **Balance Sheet** — treasury, inventory, capital, loans, net worth.
  - **Production Issues** — list of failed capital items with repair flags.
  - **Manpower** — population / employed / vacancies / graduating.
- Highlight deficiencies in red; profitable seasons in green.
