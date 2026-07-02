# Brief — Manufacturer Spares Economy: produce spares, repairs consume them (2026-07-02)

**Suggested owner:** Codex (engine: new product line, repair-path rework).
**Base off:** current `origin/pre-release` (confirm tip with
`git rev-parse --short origin/pre-release`; APP_VERSION `0.1.5-dev.2026-06-22.17`+).
**Tracking issue:** none filed yet — file one titled "Manufacturer spares
economy (produce spares; repairs consume 1 set)" and close it in the PR.
Related: [#190](https://github.com/ashersilver/island-traders/issues/190)
(repair process), [#188](https://github.com/ashersilver/island-traders/issues/188)
(failure probability), [#185](https://github.com/ashersilver/island-traders/issues/185)
(capital ordering, where `spares_kits` originated).
**Pairs with:** Claude surfaces Spares in the market/inventory UI (it's a
normal resource, so most UI comes free) and adds a "no spares — repair
blocked" indicator to the capital panel.

> **Process:** See `requirements/codex-tasks/_README.md` — the standing
> working agreement; it overrides anything here on process.

---

## The playtest ask (2026-07-02)

1. Manufacturing should require **Metal** to produce equipment, to repair, and
   to produce spares. (Production already consumes Metal via
   `MANUFACTURER_PRODUCT_LINES` — that half is done. Repairs currently consume
   only dollops + Freight.)
2. Manufacturing should **produce spares**, and **any repair should consume
   1 set of spares**.

## Existing machinery (read first)

- `MANUFACTURER_PRODUCT_LINES` (`constants.py:256`) — recipe dict per line
  (inputs incl. Metal, output resource, qty, skilled/unskilled labour,
  freight_per_unit). Adding a line here gives production, capacity checks and
  the product-picker for free (see `ProductionEngine.produce_product`,
  `production.py`).
- Repair path today: `Game._attempt_pending_capital_repairs` /
  `_attempt_capital_repair` (`engine/game.py:~737-838`) — auto-runs each tick,
  charges `EQUIPMENT_FAILURE_REPAIR_FRACTION` (0.35) of unit value in dollops
  plus air/ship Freight; a `spares_attached` unit consumes one attached kit
  (`game.py:~1012, ~1111`) and `EQUIPMENT_SPARES_REPAIR_DISCOUNT` (0.5) halves
  the bill.
- `spares_kits` are bought at order time on a #185 capital order
  (`CapitalOrderNegotiation.spares_kits`) and attach to the delivered unit.
- `ResourceType` enum (`models/resource.py`) — Spares must become a real
  resource so it's tradeable on the market and in deals.

## What to build

### 1 — `Spares` as a resource + Manufacturer product line

- Add `SPARES = "Spares"` to `ResourceType`, with a base price in
  `BASE_PRICES` (suggest ~12 Dp: 2 Metal ≈ 8 Dp of input + margin).
- New entry in `MANUFACTURER_PRODUCT_LINES`:

```python
"Spares": {
    "inputs":           {"Metal": 2, "Oil": 1},
    "output":           "Spares",
    "qty":              4,
    "skilled":          1,   # Mechanic/AssemblyWorker
    "unskilled":        2,
    "freight_per_unit": 0,   # small parts; ship with the repair freight instead
    "desc":             "Equipment Spares Kits",
},
```

### 2 — Repairs consume 1 Spares

Rework `_attempt_capital_repair`:

- **Requires:** 1 `Spares` from the owner's inventory + the existing Freight
  (delivery) + a reduced dollop labour fee (suggest halve
  `EQUIPMENT_FAILURE_REPAIR_FRACTION` to ~0.175, since the parts cost now
  arrives via the Spares kit the player had to buy/make).
- **`spares_attached` units:** an attached kit IS the spare — consume it as
  today, skip the inventory draw, and drop the separate
  `EQUIPMENT_SPARES_REPAIR_DISCOUNT` concept (the discount was standing in
  for exactly this; keep the constant but mark deprecated if tests reference it).
- **No spares available:** repair stays queued (the unit stays failed) and the
  repair-preview (`capital_repair_preview`) reports
  `{"repairable": false, "reason": "No Spares in inventory — buy from the
  market or the Manufacturer"}`. Do NOT hard-deadlock the game: keep an
  emergency fallback — repair without a kit at the FULL old fraction (0.35)
  **plus** a premium multiplier (suggest 1.5×), representing one-off
  fabrication, so a Sparesless island can still limp. Emit a log line nudging
  them to stock Spares.
- The Manufacturer repairing their OWN equipment consumes their own Spares
  stock the same way (no special case).

### 3 — AI + seeding

- Seed the Manufacturer with a few Spares at start (e.g. 4) via
  `STARTING_INVENTORY`, replacing/alongside the "starting spares storage"
  note at `constants.py:~587`.
- `engine/ai.py`: the sim AI for Manufacturer should produce Spares when
  stocks are low and list them on the market; other roles should buy 1-2
  Spares when they own failure-eligible capital and hold none (mirror the
  vaccine-buying heuristic's shape).

### 4 — Balance check

Run `.venv/bin/python -m island_traders.simulation.runner --games 1000 --seed
42` before and after; report the win-rate table in the PR. The new Spares
revenue stream should help the Manufacturer (10-11% win rate lately, below
the 14.3% target) — if it overshoots, tune the line's qty/price, not the
repair requirement.

## Tests

`tests/test_engine/test_spares_economy.py`:
1. Manufacturer produces Spares from Metal+Oil via the product line.
2. Repair with Spares in inventory: consumes exactly 1, charges the reduced
   fee + freight, restores the unit.
3. Repair with an attached kit: consumes the attachment, not inventory.
4. Repair with no Spares: emergency path charges full fraction × premium, OR
   stays queued with `repairable: false` preview (per whichever variant you
   implement — assert the chosen behaviour).
5. Spares is tradeable: market sell/buy round-trip moves it between players.
Full suite green: `pytest`.

## What Claude does next (do not implement)

- Capital panel: show Spares stock next to repair buttons; "no spares" state
  on the repair-cost line (the `repair_cost.reason` plumbing already exists).
- Market UI: nothing — Spares rides the existing resource table.
