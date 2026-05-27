# Codex Task — Market bug cluster: bid mismatch, no-cross, stale hints (2026-05-27)

**Owner:** Codex
**Origin:** [Triage `0.1.0-dev.2026-05-26.5`](../playtest-feedback/triage-0.1.0-dev.2026-05-26.5.md) §3.5. Three independent market defects from two playtesters. Bundled because they're all in the `Market` model / matching logic / hint generator code paths.

- **Comet 1 #6** — "Bid price auto-filled with unexpected values. When entering quantities in the Market Buy 'Place Bid' column, the price fields sometimes auto-filled with values that didn't match the reference price shown (e.g., **Food showed 17.18 but the bid was calculated at 40.00/unit** in the market board). The bid price input and the resulting confirmed price were inconsistent."
- **Comet 1 #8** — "FarmMachinery listed at 9 Dp never sold despite Agriculture having capital. After listing 6x FarmMachinery at 9 Dp and Comet Educator (Agriculture) gaining ~49–172 Dp in capital, no automatic matching occurred. **The market board showed both an Ask (9 Dp) and a Bid (9 Dp) simultaneously but they never crossed.** Possible order-matching bug."
- **Codex Player** — "Market and hint behavior was uneven. **'Meals runway: 0' told me to buy food, but there was no ask, only bids.** The hint remained prominent even after I posted a food bid."

Each needs its own diagnosis but ships in one brief because the fixes likely touch overlapping code in `models/market.py` and the hint generator in `engine/turn.py` / `server/app.py`.

## Goal

Three independent fixes, each with a regression test:

1. **Bid price display vs commit consistency.** Whatever the player sees as the "price per unit" on the Place Bid form must be the price that lands in `MarketBid.price_per_unit` server-side. No silent multiplier, no quantity ↔ price field swap.
2. **Crossing same-price Bid + Ask.** A 9 Dp Bid and a 9 Dp Ask on the same resource from different players must cross immediately on the second order's arrival.
3. **Hint freshness.** The "Meals runway: 0 — buy food" hint must (a) disappear when the player posts a food bid that's reasonably-priced, AND (b) be suppressed entirely when no Asks exist in the market (suggest production / training / sustenance rebalance instead).

## Branching

- **Base:** `pre-release` at `8b6fd37` (current head) or later.
- **Branch name:** `codex/market-bug-cluster-2026-05-27`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec

### Fix 1: bid price consistency

Reproduction hypothesis: the Place Bid form on the dashboard prefills `price_per_unit` from `Market.current_price(resource)` (which is the supply/demand-adjusted mid), but the engine commits at `Market.current_ask(resource)` (an offer price). When supply is thin, the ask is materially higher than the mid — and the player sees the mid (17.18) but the bid posts at the ask (40.00).

Action items:

- Trace the price field flow from `_market_payload` (server) through the dashboard form fields to `Market.post_bid`. Identify the source of the displayed price and the source of the committed price; reconcile.
- Add an explicit `display_price_per_unit` field on the market payload so the client knows EXACTLY what number to render; the server then validates on commit that the submitted `price_per_unit` matches what it sent (within a small tolerance).
- Regression test: a market in a known state where mid != ask, the bid form's displayed price matches `Market.post_bid`'s accepted price.

### Fix 2: same-price Bid + Ask not crossing

Reproduction: `_auto_match_bid` (line 230 in `models/market.py`) uses `if offer.price_per_unit > bid.price_per_unit: break` — meaning a 9 Dp Bid against a 9 Dp Ask should match (the condition is `>`, not `>=`). So why didn't they cross?

Possible causes — investigate:

- The order in which orders are posted: if the Bid posted first, the Bid's `_auto_match_bid` saw no Asks at that moment. Then when the Ask posted, did `_auto_match_offer` re-check resting Bids? Confirm both sides have symmetric resting-order matching.
- `available_offers` filter — does it filter out the player's own offers correctly? If the buyer and seller are the same player, the offer is correctly skipped (line 245-246). But if they're different players and the offer is in some "expired" / "cancelled" / "not-yet-active" state, it might be silently filtered.
- `season_key` mismatch — if the Bid is from this season and the Ask is from last season (or vice versa), is one filtered out by season-based eligibility?

Action items:

- Confirm `_auto_match_offer` exists and mirrors `_auto_match_bid` semantically (a new resting Bid should be crossed by a new arriving Ask).
- Add a regression test mirroring the Comet 1 #8 scenario: player A posts 6x FarmMachinery Ask at 9, player B posts 6x FarmMachinery Bid at 9, then assert the trade completed.

### Fix 3: hint freshness

Reproduction: the "Meals runway: 0" hint generator probably emits whenever `meals_runway() == 0`, with no check on whether the player has *already* posted a bid OR whether the market has any matchable supply.

Action items:

- Identify the hint generator (likely in `server/app.py` or a sibling module that builds the per-player Decision Hints payload).
- For each food-resource hint, gate the emission on:
  - The player has NOT already posted a Bid for that resource at a reasonable price (>= `current_price * 0.8`).
  - The market has at least one resting Ask for that resource (otherwise the hint "buy food" is impossible advice; suggest "train Farmer / build Kitchen" instead).
- Add a regression test: a player with `meals_runway() == 0` and a resting reasonable Bid does NOT receive the "buy food" hint.

### Files to touch (suggested)

- `island_traders/models/market.py` — `post_bid`, `post_offer`, `_auto_match_bid`, `_auto_match_offer`.
- `island_traders/server/app.py` — market payload `display_price_per_unit`, hint-generator gates.
- Tests: new `tests/test_models/test_market_bug_cluster.py`.

### UI follow-up (Claude separate)

The three Claude-side market UX items already batched in the triage doc (real-time affordability counter, Place Bid vs Buy Now distinction, List-at-Best-Bid, listed-on-market badge in inventory) are NOT part of this brief — they're the UX side. This brief is engine + payload only.

## Tests

- `tests/test_models/test_market_bug_cluster.py` (new):
  - Bid price consistency: market with mid=17.18 and ask=40.00; posting a bid at price 17.18 commits at 17.18 (the displayed price, not the ask).
  - Same-price cross (Comet 1 #8): two players, FarmMachinery, both 9 Dp, opposite sides — trade completes regardless of post order.
  - Hint suppression with resting bid: player with runway=0 and resting reasonable Food Bid receives no "buy food" hint.
  - Hint suppression with no asks: player with runway=0 and no Food Asks in market receives an alternate suggestion (production / training), not "buy food".

## Acceptance criteria

- Three fixes land with three regression tests, each independently verifiable.
- Diagnostic note in the PR description identifying the root cause of each defect (especially Fix #2 — playtester explicitly flagged it as possibly an order-matching bug).
- Full test suite green (463 + new tests).
- No calibration drift (these are bug fixes, not balance changes).
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/market-bug-cluster-2026-05-27` block.

## Out of scope

- Market UX improvements (Place Bid vs Buy Now distinction, affordability indicator, etc.) — Claude UI follow-up.
- Adding new market order types (limit-with-expiry, all-or-none, etc.) — separate future scope.
- Rewriting `Market` storage from list-of-orders to a proper order-book — performance is fine at game scale.
- Game-log denoising — separate Claude UI item.
