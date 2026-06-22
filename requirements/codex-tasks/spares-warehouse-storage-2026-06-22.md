# Brief — Manufacturer spares production + warehouse storage cap (2026-06-22)

**Suggested owner:** Codex (engine model + capital catalogue + tests).
**Relates to:** #185/#188 (capital orders, spares kits), Capital Orders III.
**Base off:** `origin/pre-release` (currently `94bf44c`). `git fetch` first; cut
`codex/spares-warehouse-storage-2026-06-22` off it.

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees.** Work in the **primary checkout**
  (`/Users/ashleysilver/Documents/projects/island-traders`). Claude works in a separate
  `claude/*` worktree — do not edit it or run `git reset/checkout/stash` against it.
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

### 1. New capital item — `manufacturer.warehouse`

Add to `CAPITAL_CATALOGUE` (`constants_capacity.py`) under `role="Manufacturer"`:

- `item_id="manufacturer.warehouse"`, sensible name ("Spares Warehouse"), cost in line with
  other Manufacturer infra (suggest ~50 Dp — Codex tune against balance tests),
  `delivery_seasons` consistent with siblings.
- `effects={"spares_storage": 12}` — a **new effect key** meaning "+12 spares storage
  capacity". Choose the key name to match existing `effects` conventions (`capacity`,
  `labour_relief`, …); `spares_storage` is suggested.
- Not `cash_only` (it is manufactured like other Manufacturer equipment), unless that
  conflicts with the self-build settlement — confirm against the current
  `_handle_capital_order` self-build path (a Manufacturer building its own warehouse must
  settle cleanly; self-build now settles immediately, see commit `94bf44c`).

### 2. Storage cap derivation

Add a helper on `Player` (or alongside `effective_capital_inventory`) that returns the
spares storage cap:

```
spares_capacity = 12 * (count of owned, maintained manufacturer.warehouse units)
```

Use `effective_capital_inventory()` so an unmaintained warehouse does not count that season
(mirrors `_has_enhanced_metal_equipment`). A Manufacturer with **0 warehouses has 0 spares
capacity** — decide with the user whether a small free baseline (e.g. 0 or a token) is
desired; default to **0** (warehouse strictly required to hold spares).

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

- New warehouse item is in the catalogue and orderable; a Manufacturer self-build of a
  warehouse settles immediately (no negotiation deadlock).
- `manufacture_spares` clamps to `12 * warehouses` and returns the clamped count.
- 0 warehouses ⇒ 0 spares can be produced/held.
- Adding a 2nd warehouse raises the cap to 24.
- An unmaintained warehouse does not count toward capacity.
- Full `pytest` suite green (baseline: **799 passing** on `94bf44c`).

## Open question for the user (note in PR if unresolved)

- Free baseline spares storage with 0 warehouses: **0** (assumed) vs a small token.
