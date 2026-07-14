# Brief — Manufacturer Spares Economy: make Spares tradable + producible (2026-07-02, rev 2)

**Suggested owner:** Codex (engine: new product line, resource tradability,
AI heuristics).
**Base off:** current `origin/pre-release` (confirm tip with
`git rev-parse --short origin/pre-release`).
**Tracking issue:** filed by Ash — link it here once known; close it in the PR.
Related: [#190](https://github.com/ashersilver/island-traders/issues/190)
(repair process), [#188](https://github.com/ashersilver/island-traders/issues/188)
(failure probability), [#185](https://github.com/ashersilver/island-traders/issues/185)
(capital ordering, where `spares_kits` originated).
**Pairs with:** Claude surfaces Spares in the market/inventory UI once it's a
normal tradable resource (should come mostly free from existing market UI).

> **Process:** See `requirements/codex-tasks/_README.md` — the standing
> working agreement; it overrides anything here on process. **Worktree
> note:** if your assigned worktree path doesn't exist, do not attempt
> remote-only edits through a keyhole API — stop and report the exact path
> that failed so it can be provisioned, per the standing agreement's
> worktree-per-task convention (`git worktree add -b codex/<task-name>
> ../it-codex-<short> origin/pre-release`).

---

## Revision note (why this brief changed)

The original 2026-07-02 version of this brief assumed repairs didn't yet
consume Spares. **That's wrong** — a prior merged commit ("Add manufacturer
spares warehouse capacity") already built:

- `ResourceType.SPARES` exists (`models/resource.py:29`).
- Repairs already consume 1 Spares (attached kit first, else generic
  inventory) and halve the fee via `EQUIPMENT_SPARES_REPAIR_DISCOUNT`
  (`engine/game.py:_capital_repair_quote` / `_attempt_capital_repair`,
  ~lines 1007-1119). Read this code before touching anything here — it's
  already correct and should not be reworked.

**What's genuinely still missing** (confirmed by reading the current
codebase, not assumed):

1. `ResourceType.SPARES` is in `NON_TRADABLE_RESOURCES`
   (`models/resource.py:36`) — it cannot be bought, sold, or traded in a
   deal. Every market/AI/deal code path already special-cases
   `NON_TRADABLE_RESOURCES` generically, so removing Spares from that set
   should make it flow through the market, deals, and AI trading logic for
   free — verify this rather than hand-rolling new plumbing.
2. `Spares` has no entry in `BASE_PRICES` (`constants.py:109`) — needed once
   it's tradable so the market has a formula price to seed from.
3. `MANUFACTURER_PRODUCT_LINES` (`constants.py:256`) has no `"Spares"`
   recipe — the Manufacturer cannot currently *produce* Spares; it can only
   acquire them via `spares_kits` on a #185 capital order or (presumably)
   however the "spares warehouse capacity" commit seeded starting stock.
4. No AI heuristic for buying/producing Spares (`engine/ai.py`).

---

## What to build

### 1 — Make Spares tradable

- Remove `ResourceType.SPARES` from `NON_TRADABLE_RESOURCES`
  (`models/resource.py:36`).
- Add a `BASE_PRICES["Spares"]` entry (`constants.py:109`) — suggest ~12 Dp
  (2 Metal ≈ 8 Dp of input cost + margin, once the product line below exists).
- Confirm (via the existing tests, or new ones) that market bid/ask,
  `propose_deal`, and the AI's generic sell/buy scans (`turn.py:3383/3451/3460`,
  `ai.py:1070/1289/1399`) now include Spares without any further code
  changes — those all gate on `NON_TRADABLE_RESOURCES` generically. If any
  of them needs a Spares-specific change, that's a sign something else is
  hardcoded and worth flagging in the handoff, not silently working around.

### 2 — Manufacturer Spares product line

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

This gives production, capacity checks, and the product-picker for free via
`ProductionEngine.produce_product` (`production.py`) — same pattern as the
other `MANUFACTURER_PRODUCT_LINES` entries.

### 3 — Starting stock + no-spares behaviour

- Check what the merged "spares warehouse capacity" commit already seeded
  for Manufacturer starting Spares (`STARTING_INVENTORY` /
  `constants.py:~587` "starting spares storage" note) — top it up only if
  it's zero or clearly too thin to matter.
- Confirm the existing no-spares repair path (`_capital_repair_quote`
  returning `repairable: false` when there's no attached/generic spare, or
  whatever the actual current fallback is — read the function, don't
  assume) is acceptable, or add a modest emergency premium (e.g. repair
  without a spare at 1.5× the no-discount fraction) if the current
  behaviour can hard-deadlock a Sparesless island. State in the handoff
  which case applies today.

### 4 — AI heuristics (`engine/ai.py`)

- Manufacturer AI: produce Spares when stock is low (mirror whatever
  threshold pattern nearby product-line heuristics use) and list surplus on
  the market.
- Other roles' AI: buy 1-2 Spares when they own failure-eligible capital and
  currently hold none (mirror the vaccine-buying heuristic's shape/threshold).

### 5 — Balance check

Run `.venv/bin/python -m island_traders.simulation.runner --games 1000 --seed
42` before and after; report the win-rate table in the PR. Manufacturer has
been running 10-11% (target ~14.3% ± 6pp) — a new sellable line should help,
but don't force it if it overshoots; tune qty/price, not the repair mechanics.

---

## Tests

`tests/test_engine/test_spares_economy.py` (new):
1. Spares is no longer in `NON_TRADABLE_RESOURCES`.
2. Manufacturer produces Spares from Metal+Oil via the new product line.
3. Market sell/buy round-trip moves Spares between two players.
4. A deal offering/requesting Spares is accepted normally (not rejected as
   non-tradable).
5. (Only if you change the no-spares fallback) repair-without-spares uses
   the new emergency path.

Do **not** duplicate tests for the repair-consumes-a-spare behaviour — that's
already covered by existing tests; just confirm they still pass unmodified.

Full suite green: `pytest`.

---

## What Claude does next (do not implement)

- Confirm Spares appears in the market/inventory UI once tradable (likely
  needs zero changes — it's a normal `ResourceType` at that point).
- Nothing else; this is a small, additive brief.
