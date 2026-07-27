# Brief set: Wave 4 decision-support UI (#4, #3)

**Date:** 2026-07-12 · **Repo:** island-traders (`pre-release`) · **Owner:** Claude (frontend)
These are player-facing tools with no Codex/economy dependency. Both benefit from live
verification against a running game (launch, refresh a human tab, exercise the panel).

---

## #4 — What-If production tables
**Ask:** an interactive panel where the player picks an output and a target quantity and sees
what inputs/workforce/equipment it needs vs. what they hold, and whether it's feasible.

**Server change (required first — verified 2026-07-12):** `app.py` already computes per-unit
recipe data server-side (`boosted.inputs[res] = per_unit`, `recipe.labour_per_unit(band)`,
capital `capacity_each`) but does NOT send it to the client — only the derived shortfalls at
max. Add to each `capacity.outputs[]` entry a `per_unit` block:
```
"per_unit": {
  "inputs":   {resource: qty_per_output_unit, ...},
  "labour":   {band_or_profession: workers_per_unit, ...},
  "equipment_capacity_per_unit": <float>   # how much equipment_cap one unit consumes
}
```
Pull straight from the recipe already in scope at app.py:1959-1984; no new engine logic.

**Client (index.html):** a "What-If" control in the existing Production/Capacity panel
(near `s-capacity-outputs`, renderCapacityPanel at :3410):
- output `<select>` (the player's producible lines) + quantity input (prefill = current
  max_producible).
- table: per input → need (per_unit × qty) vs on-hand (from `me.inventory`) → shortfall;
  per workforce band → need (ceil) vs active; equipment capacity need vs `equipment_cap`.
- feasibility line: green "can produce N now" / amber "short: buy X, train Y, +Z capacity"
  reusing the existing shortfall colour scheme and the `equipment_short.options` catalogue
  hint. Pure display — do NOT auto-submit a produce action (mirror the hint-card rule).
- recompute on select/quantity change, client-side from the payload (no round-trip).

Effort: medium. Server add is small; the panel is the bulk.

---

## #3 — User-defined action alerts
**Ask:** let a player subscribe to a condition and be notified when it fires, instead of only
the system-generated alerts (sustenance/training/capital) that exist today.

**Design (keep client-side; no engine change needed):**
- A small "Alerts" panel: add-alert form (condition type + resource + threshold) and a list of
  active alerts with remove buttons. Persist in `localStorage` keyed by room+player so they
  survive refresh.
- Condition types, all evaluable from the `game_state` the client already receives each tick:
  - price above/below X for resource R (from `market[R].formula_price` / bid / ask)
  - own stock of R below X (from `me.inventory`)
  - a bid/ask appeared for R (market change vs last snapshot)
  - treasury below X
- On each `game_state`, evaluate active alerts; when one fires, surface it as a decision-hint-
  style card (reuse the `renderDecisionHints` card styling) and optionally a toast. Debounce so
  a persistently-true condition fires once per edge, not every tick.
- No server involvement → no balance/sim impact; ship behind the existing UI, verify live.

Effort: small–medium, fully client-side.

---

**Verification (both):** launch a game (launcher in island-traders-testing, poo-3 Digger), open
a human tab, refresh (static files serve from disk), exercise each panel. No pytest needed for
#3 (client-only); #4's server payload add gets a unit test asserting `per_unit` is present and
correct for a known recipe.
