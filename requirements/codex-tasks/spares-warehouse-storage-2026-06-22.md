# Brief — Manufacturer spares production + warehouse storage cap (2026-06-22)

**Suggested owner:** Codex (engine model + capital catalogue + tests).
**Relates to:** #185/#188 (capital orders, spares kits), Capital Orders III.
**Base off:** `origin/pre-release` at **`9e07b41`** (the commit that added these briefs) or
later. This is the exact, canonical version — `git fetch origin` and confirm
`git rev-parse origin/pre-release` resolves to `9e07b41` (or a newer pre-release tip).

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees — do NOT use the primary checkout.** The primary checkout
  (`/Users/ashleysilver/Documents/projects/island-traders`) currently holds **unrelated
  uncommitted Claude work** (in-progress room-rejoin edits to `server/app.py` +
  `tests/test_server/test_join_rejoin.py` on branch `claude/integrate-qol-pollution-48-45`).
  Ignore it and leave it untouched. Create your **own dedicated worktree** off the base and
  work there — this is exactly how PR #192 was done:
  `git fetch origin && git worktree add -b codex/spares-warehouse-storage-2026-06-22 ../it-codex-spares origin/pre-release`
- **Branch.** Cut a fresh branch off the base above; never commit onto
  `pre-release`/`master`.
- **PRs only.** Reach `pre-release` through a PR that Claude (integrator) merges. Link
  `Refs #185`. Update `RELEASE_NOTES.md` and bump `APP_VERSION` `.N` in `constants.py`.
- **Git discipline.** No `--no-verify`/`--amend`/force-push. Run the **full** `pytest`
  suite before handoff.
- **Handoff.** "branch X at commit Y — ready to integrate."

## Why

Playtest 2026-06-22: the Manufacturer (Forge) can already manufacture generic spares
(`Player.manufacture_spares`, `island_traders/models/player.py:544`, which adds
`ResourceType.SPARES` to inventory), and capital orders carry `spares_kits` that ride onto
the delivered unit as `spares_attached`. But spares production is **unbounded** — there is
no physical storage limit. The user wants spares to require **warehouse capacity**: a
Manufacturer must own **one warehouse per 12 spares** it wishes to hold. Without enough
warehouse capacity, spares production is capped at what fits.

## What exists today (read before starting)

- `ResourceType.SPARES` (`island_traders/models/resource.py`).
- `Player.manufacture_spares(count)` — `player.py:544`. Adds SPARES to inventory, returns
  count produced. **No cap.**
- Capital order form / settlement: `spares_kits` → `spares_attached` on the delivered unit
  (`player.py:49,109`; settlement in `server/app.py` `_settle_capital_negotiation`).
- Capital catalogue: `island_traders/constants_capacity.py`. Manufacturer items today are
  `manufacturer.foundry / assembly_line / precision_workshop / shipyard`. **No warehouse.**
- `CapitalItem` schema + `effects` dict pattern (e.g. `farmer.storage_building` already
  models commodity storage — use it as the template for the new warehouse).

## Spec

### 1. Two warehouse sizes (capital items)

Each warehouse declares a `spares_storage` effect; total capacity is the **sum** across
owned, maintained warehouse units. Add to `CAPITAL_CATALOGUE` (`constants_capacity.py`)
under `role="Manufacturer"`:

- `manufacturer.small_warehouse` — **"Small Spares Warehouse"**, `effects={"spares_storage": 10}`.
  This is the **starting warehouse** every Manufacturer island begins with (see §1a). Cheap;
  cost/`delivery_seasons` in line with light infra.
- `manufacturer.warehouse` — **"Spares Warehouse"**, `effects={"spares_storage": 12}`. The
  standard orderable upgrade; cost in line with other Manufacturer infra (suggest ~50 Dp —
  Codex tune against balance tests), `delivery_seasons` consistent with siblings.
- Neither is `cash_only` (both are manufactured like other Manufacturer equipment) unless
  that conflicts with self-build settlement — confirm against the current
  `_handle_capital_order` self-build path (a Manufacturer building its own warehouse must
  settle cleanly; self-build now settles immediately, see commit `94bf44c`).

`spares_storage` is a **new effect key**; match existing `effects` conventions (`capacity`,
`labour_relief`, …).

### 1a. Starting warehouse

Every Manufacturer island **starts with one `manufacturer.small_warehouse`** already built
(10-spares capacity) so it can hold spares from turn one. Seed it where starting capital
units are configured (game setup / starting-capital seeding — find how other starting
capital is placed; if the Manufacturer has no starting capital today, add this unit).

### 2. Storage cap derivation

Add a helper on `Player` (or alongside `effective_capital_inventory`) returning the total
spares capacity as the **sum of `spares_storage` effects across owned, maintained warehouse
units**:

```
spares_capacity = Σ spares_storage(item) for each owned+maintained warehouse unit
                = 10 (starting small warehouse) + 12 * (standard warehouses) + 10 * (extra small)
```

Use `effective_capital_inventory()` so an unmaintained warehouse does not count that season
(mirrors `_has_enhanced_metal_equipment`). A new Manufacturer therefore starts at **10**
capacity (one small warehouse); ordering one standard warehouse takes it to 22.

### 3. Enforce the cap in production

`manufacture_spares(count)` must clamp to remaining capacity:

```
room_left = max(0, spares_capacity - current SPARES in inventory)
produced  = min(count, room_left)
```

Return the actual number produced (callers already use the return value). When clamped,
the production/turn log should say why ("Spares warehouse full — built N of M; add a
warehouse for +12 capacity."). Find every caller of `manufacture_spares` (the Manufacturer
production path in `engine/production.py` / `engine/turn.py`) and surface the message.

### 4. Spares attached to delivered equipment

Spares **moved onto a delivered capital unit** (`spares_attached`) are consumed from the
held pool at settlement and no longer occupy warehouse capacity — confirm the settlement
path debits inventory SPARES when kits are attached, so attaching frees warehouse room.
(If attachment currently does not debit held SPARES, that is a separate bug — note it in
the handoff, don't silently change scope.)

### 5. UI / state (minimal)

- Expose spares capacity + current spares in `game_state` for the Manufacturer
  (`server/app.py` get_game_state) so the frontend can show "spares: 7 / 12". Claude wires
  the frontend display separately — you provide the payload fields
  (`spares_held`, `spares_capacity`).

## Tests

- Both warehouse items are in the catalogue and orderable; a Manufacturer self-build of a
  warehouse settles immediately (no negotiation deadlock).
- A new Manufacturer **starts with one small warehouse ⇒ capacity 10**.
- `manufacture_spares` clamps to total warehouse capacity and returns the clamped count
  (e.g. starting island can hold 10; the 11th spare is refused with a clear message).
- Ordering one standard warehouse raises the cap to **22** (10 + 12).
- An unmaintained warehouse does not count toward capacity.
- Full `pytest` suite green (baseline: **799 passing** on `9e07b41`).

## Resolved (user, 2026-06-22)

- **Starting storage:** the island starts with **one small warehouse holding 10 spares**
  (not 0). Additional standard warehouses add +12 each.
