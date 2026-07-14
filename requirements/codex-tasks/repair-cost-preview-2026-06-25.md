# Brief — Expose capital-repair cost/freight preview (for a confirm dialog) (2026-06-25)

**Owner:** Codex (engine + game_state + tests). **Process:** see `_README.md`.
**Base off:** `origin/pre-release` (fetch first; quote tip + APP_VERSION). Own worktree; push.
**Frontend is Claude's** (the confirm dialog).

## Why

The Repair button (just shipped) fires `capital_repair` **immediately**. The user wants a
confirmation box first, showing the **Dp cost and Freight** the repair will consume, with
Confirm / Cancel. The cost is currently only computed *inside* `Game._attempt_capital_repair`
(`engine/game.py` ~782–847, see the `repair_fee` + `freight_qty` it logs) at repair time, so
the UI has nothing to show beforehand.

## Spec

1. **Pure cost preview.** Extract a side-effect-free helper, e.g.
   `Game.capital_repair_preview(player, item_id) -> {"dp": float, "freight": int, "repairable": bool, "reason": str}`,
   that computes the same fee + freight as `_attempt_capital_repair` **without applying** it
   (refactor the fee/freight calc out of `_attempt_capital_repair` and call it from both, so
   they can't drift).
2. **Expose per repairable item in `game_state`.** On each `capital_owned` entry that has
   `repairable_failed > 0`, add `repair_cost: {dp, freight}` (and an affordability/`reason`
   hint if it can't be afforded). Use the existing capital_owned payload block in
   `server/app.py` (~2150–2280).
3. **No behaviour change to actual repair** — `_attempt_capital_repair` keeps working; it just
   now shares the cost calc with the preview.

## Frontend (Claude, after merge)
- Replace the immediate `repairCapitalItem()` send with a **confirm dialog** showing
  "Repair {item}: {dp} Dp + {freight} Freight" and Confirm/Cancel; only send `capital_repair`
  on Confirm. Disable/explain when unaffordable.

## Tests
- `capital_repair_preview` returns the same dp/freight that `_attempt_capital_repair` charges.
- `game_state` capital_owned entries with failed units carry `repair_cost`.
- Preview is side-effect-free (no inventory/treasury change). Full `pytest` green; quote count.
