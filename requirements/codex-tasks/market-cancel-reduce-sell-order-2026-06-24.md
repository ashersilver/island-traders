# Brief — Cancel / reduce a resting sell order (return escrowed units, no buy-back) (2026-06-24)

**Suggested owner:** Codex (market model + server WS handler + tests). Frontend cancel UI is Claude's.
**Relates to:** market order book; playtest 2026-06-24.
**Base off:** `origin/pre-release` at the current tip (was `5928276`+; `git fetch origin` and confirm).

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees — do NOT use the primary checkout.** It holds unrelated Claude
  work. Create your own worktree:
  `git fetch origin && git worktree add -b codex/market-cancel-reduce-2026-06-24 ../it-codex-cancel origin/pre-release`
- **PRs only.** Reach `pre-release` via a PR Claude merges. Update `RELEASE_NOTES.md` and bump
  `APP_VERSION` `.N`.
- **Git discipline.** No `--no-verify`/`--amend`/force-push. Run the **full** `pytest` suite.
- **Handoff.** "branch X at commit Y — ready to integrate", noting the **frontend** cancel/reduce
  UI is Claude's (you provide the WS contract).

## Why (observed)

Playtest 2026-06-24: "once you put up a quantity to sell, and want to reduce it, you have to buy
it back — although technically no money changes hands the game prevents you if you can't cover
the order in cash."

Root cause: `Market.post_offer` (`island_traders/models/market.py:250`) **escrows** the listed
units out of the seller's inventory (`seller.give_resources(rtype, qty)` removes them) into the
order book. The engine already has `Market.cancel_player_orders(player_id, rtype)`
(`market.py:221`), **but no server WebSocket handler and no UI expose it** — only auction bids
have a withdraw path (`withdraw_bid`). So a seller wanting to reduce/cancel a resting ask has no
recourse except to `market_buy` their own units back, which requires cash they shouldn't need.

## Spec — server (this repo)

1. **Add a WS action to cancel or reduce a resting sell order**, e.g. `cancel_order` /
   `reduce_order` (`type`, `resource`, optional `quantity` to reduce by; omit ⇒ cancel all of
   that resource's resting asks for the player). Returns the escrowed units to the seller's
   inventory and updates `supply` / the order book. Reuse / extend `cancel_player_orders`; add a
   **partial-reduce** variant if only `quantity` is given (cancel that many units, keep the rest
   resting).
2. **No cash required, no buy-back.** Cancelling/reducing must move units from the resting offer
   straight back to the seller's inventory — never route through a buy. Confirm `supply` and any
   market-maker depth bookkeeping stay consistent.
3. **Only the order's owner** can cancel/reduce it; validate ownership and that the resting qty
   covers the requested reduction.
4. **Expose resting orders in `game_state`** (per player: their resting asks with resource +
   remaining qty + price + an id) so the frontend can render a "your listings" list with a
   cancel/reduce control. (Claude wires that UI — you provide the fields + the WS contract.)

## Tests

- Listing N to sell escrows N out of inventory; cancelling returns exactly N with **no Dp
  change**.
- Reducing by k returns k units, leaves N−k resting, no Dp change.
- A non-owner cannot cancel someone else's order; reducing by more than rests is rejected.
- `supply` and best-ask reflect the change.
- Full `pytest` suite green (baseline: **811 passing**).

## Frontend follow-up (Claude, after the contract lands)

- Render the player's resting sell orders with a **Cancel / Reduce** control that calls the new
  WS action — so reducing a listing no longer needs a cash-backed buy-back.
