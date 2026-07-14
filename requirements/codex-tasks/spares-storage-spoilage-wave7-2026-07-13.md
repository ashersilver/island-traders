# Wave 7 — Spares bundling, storage & spoilage, CNC Workshop (2026-07-13)

Source: Ash's defect list of 2026-07-13, items 4, 5, 10 (item 9, self-order
pricing, is in the Wave 5 quick-fix doc). Grounded against master
(post-#212). NOTE: this wave overlaps ROADMAP #64 (Warehousing) and
supersedes parts of `spares-warehouse-storage-2026-06-22.md` — see the
tier-renumbering decision in Task 7.2.

## Context: what exists today

- Spares is an ordinary tradable resource (`models/resource.py:32,44`), base
  price 12 Dp (`constants.py:135`), producible line `{Metal:2, Oil:1} → 4`
  (`constants.py:348-357`) enabled by the **Assembly Line only**
  (`constants_capacity.py:362`; the Foundry does NOT enable Spares).
- Manufacturer already starts with `Spares: 4` (`constants.py:110`) and one
  small warehouse (`constants.py:698`), `spares_storage: 10`
  (`constants_capacity.py:369-378`); orderable standard warehouse adds 12
  (`:379-388`). `manufacture_spares` clamps to warehouse room
  (`models/player.py:614-631`); capacity helper `player.py:473-484`.
- Repair consumes `unit.spares_attached` first, then held Spares
  (`engine/game.py:1125-1192`).
- **Latent bug (flagged in spares-warehouse brief §4, still unfixed):**
  capital-order `spares_kits` are priced at 15% of list (`app.py:3616-3619`)
  and attached to the delivered unit (`player.py:110`), but are **never
  manufactured and never debited from the Manufacturer's held Spares**
  (`player.py:563-612` has no `manufacture_spares`/inventory debit). Kits are
  conjured from nothing.
- No spoilage/perish/decay mechanic exists anywhere; `farmer.storage_building`
  has a dead, unenforced `inventory_cap` effect (`constants_capacity.py:117-122`).
- Workforce→capacity is linear per band (`models/capacity.py:161-220`); there
  is no stepped "base + per-dedicated-worker tier" primitive.

---

## Task 7.1 — Physical spares bundling on capital orders (item 4) — MEDIUM

Make spares kits real goods, closing the latent bug:

- At order **settlement**, debit the Manufacturer's held Spares by
  `spares_kits`; if short, auto-run `manufacture_spares` for the shortfall
  (consuming Metal/Oil + labour availability check). If the shortfall cannot
  be built, the order settles **without** the missing kits and the price
  drops accordingly (notify both parties) — never conjure.
- Debited/attached kits free warehouse room (they leave storage with the
  delivered unit).
- Enable Spares on the **Foundry** as well (add `"Spares": 2` to
  `constants_capacity.py:334-347` effects) so the "working Foundry + Assembly
  Line + spares warehouse" trio all contribute, making Spares one of the
  first viable lines. Keep starting inventory `Spares: 4` (it fits the
  starting 10/12-cap warehouse; bump to 6 only if sim shows early repair
  droughts).

## Task 7.2 — Storage limits & spoilage (item 5) — LARGE

**Tier renumbering decision (supersedes spares-warehouse-storage-2026-06-22):**
requested numbers are small = 12, large = 30. Map: `small_warehouse`
`spares_storage` 10 → **12**; rename `manufacturer.warehouse` ("Warehouse") →
**Large Warehouse** with `spares_storage` 12 → **30**, cost re-tuned (suggest
50 → 90 given 2.5× capacity). Update the old brief's §capacity notes.

**Spoilage engine (net-new, season-start pass alongside capital maintenance):**
- Each perishable has a shelf-life when stored OVER capacity (or with no
  storage building at all):
  - **Spares**: 4 seasons unprotected, then irretrievably lost.
  - **Food**: 2 seasons unprotected; a Food storage building protects 80
    units each (new capital item, any role can order; suggest cost 40).
  - **Grain**: 1 season unprotected; a **Grain Silo** protects 100 units
    (new capital item, Farmer-role; suggest cost 35, and make it enforce —
    replacing or retiring the dead `farmer.storage_building` effect).
- Implementation: age inventory in FIFO buckets per resource
  (`{acquired_tick, qty}` list on the player, serialised); at season start,
  protected quantity = Σ storage capacity across maintained units (reuse the
  `spares_capacity()` pattern generalised to `storage_capacity(rtype)`);
  overflow beyond protection ages, and buckets past shelf-life are destroyed
  with a per-player notice ("N Grain perished — no silo capacity").
- Surface in game_state: per-resource `protected`, `at_risk`,
  `perishes_in_seasons` (min bucket age remaining); UI shows an amber pill on
  the inventory rows at risk.
- **Failed/unmaintained storage does not protect** (consistent with
  `effective_capital_inventory`).

## Task 7.3 — CNC Workshop (item 10) — MEDIUM

New Manufacturer capital item + a new stepped-staffing capacity primitive:

- Catalogue entry `manufacturer.cnc_workshop` (`constants_capacity.py`
  Manufacturer block): cost **150**, delivery 1 season, effects contribute to
  the **Spares** line with a **tiered curve keyed to dedicated tradesmen**:
  0 staff → 2/season, 1 tradesman → 6, 2 tradesmen → 10 (cap).
- New primitive: allow an equipment effect
  `tiered_capacity: {output: Spares, base: 2, per_worker: [6, 10], band: skilled}`
  evaluated in `compute_capacity` (`models/capacity.py:187-220`) — the tier
  replaces the linear workforce term FOR THE UNITS OF THIS ITEM ONLY; other
  equipment keeps the linear model. Dedicated workers are drawn from the
  skilled band before general allocation (document the draw order).
- What-If panel and `capacity.outputs[].per_unit` must reflect the tier
  (workforce_cap becomes a step function — expose `next_tier_at` so the UI
  can hint "add 1 tradesman → +4 spares/season").

---

Sequencing: 7.1 → 7.3 → 7.2 (7.2 is the big one and benefits from 7.1's
warehouse-room accounting being settled). Sim gate: 3 same-seed sims;
assert no season-end crash, Manufacturer mean net worth within ±10% of
post-#212 baseline, and zero conjured spares (order settlements reconcile
against production + inventory). Expect Farmer net worth to dip when grain
spoilage lands — log the delta for calibration (#213 follow-up).
