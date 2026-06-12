# Brief — Order Desk & Training Desk batch engine seams (2026-06-12)

**Suggested owner:** Codex (engine + server message handlers).
**Base off:** current `origin/pre-release`.
**Tracking issue:** #114 (UI v2), **phase 2**. File the engine work as
`Refs #114` (the tracking issue stays open until phase 4).
**Pairs with:** Claude builds the Order Desk + Training Desk **tiles**
(frontend) against the message contracts below. Per the standing rule, the
**second of {engine PR, UI PR} to merge wires the integration call**; the
first leaves a stub.

Full design context: `requirements/ui-v2-modular-design-2026-06-12.md` §4–§5.
Phase 1 (tiles, Trade Finder, input conventions, log windowing) shipped in
PR #117.

---

## The goal (player-facing)

Today every market trade and every training request walks the player through
the sequential prompt wizard (`choose_action → choose_resource →
choose_quantity → confirm/ask_dollop_amount`), one WebSocket round-trip per
step. Inside a timed season window, placing five orders means five full wizard
passes. The user wants to **stage multiple orders / multiple training
requests in a basket and submit them as one batch**, with per-row results.

This is an **engine/protocol seam**, not a rules change: a batch must be
*semantically identical* to the same orders entered one-by-one through the
existing wizard — same price movement per fill, same validation, same ledger
effects. No new market mechanics.

---

## Good news — most of the machinery already exists

Read these before writing anything; you are mostly **generalizing**, not
building from scratch.

### Buy side is already batched
`TurnManager._action_market_buy` (`island_traders/engine/turn.py:2802`) already
accepts a **multi-resource** payload from `io.market_buy_bulk` and, in one
action, iterates buys (`market.buy_from_offers`, `turn.py:2824`) **and** posts
multiple limit bids (`market.post_bid`, `turn.py:2838`). The IO seam
`WsTurnAdapter.market_buy_bulk` (`island_traders/server/ws_adapter.py:562`)
already parses a `{"buy": {res: qty}, "bids": {res: {quantity, price}}}` JSON
payload and normalises it. So a buy-only Order Desk could *almost* ride the
existing `market_buy_bulk` message — what's missing is the **sell side** and a
**structured per-row result** back to the client.

### Sell side is still one-at-a-time
`_action_market_sell` (`turn.py:2907`) prompts for a single resource/qty, then
either `market.sell_to_bids` (`market.py:493`) or `market.post_offer`
(`market.py:238`). This is the half that needs a bulk path.

### Training already models a batch
`TrainingRequest` is keyed by `batch_id` (`island_traders/models/training.py:74`)
and `TrainingRegistry.propose` (`training.py:247`) already creates one request
covering a **bundle** of trainees for a target profession. The full
counter-offer negotiation (`educator_approve/reject/counter`,
`requester_accept_counter/...`) is keyed by `batch_id` and already round-trips
over the `training_counter_*` WS messages. So a Training Desk that submits
several cohorts is **N calls to the existing `propose`**, each returning its own
`batch_id` — the negotiation flow then works unchanged per request.

---

## What to build

### A. Engine: a unified order-list executor

Add to `TradingEngine` (`island_traders/engine/trading.py`):

```python
def execute_order_list(self, player, orders, players=None) -> list[dict]:
    """Execute a basket of buy/sell orders in submission order.

    Each order: {"side": "buy"|"sell", "resource": <enum value str>,
                 "quantity": int, "limit_price": float | None}

    Returns one result dict per input order, in the same order:
      {"index": i, "side", "resource", "status": "filled"|"partial"|
       "rejected", "quantity": <filled>, "unit_price": <avg>,
       "total": <signed Dp>, "reason": <str if not fully filled>}
    """
```

Semantics — reuse the existing primitives, do **not** reimplement pricing:

- **buy, no limit** → `market.buy_from_offers(player, rtype, qty)` (lifts the
  ask, same as the current bulk buy).
- **buy, with limit** → `market.post_bid(player, rtype, limit, qty)`; report the
  immediately-filled portion (`bid.quantity - bid.remaining`) as filled and the
  rest as a resting bid (status `partial`, reason "resting bid for N").
- **sell, no limit** → `market.sell_to_bids(player, rtype, qty, players)` (hits
  the bid).
- **sell, with limit** → `market.post_offer(player, rtype, limit, qty)`; same
  partial-fill reporting against matching asks.
- Each row **validates independently and never aborts the rest**: insufficient
  stock / cash / no counter-side depth → that row is `rejected` with a reason,
  the loop continues. (The existing bulk-buy loop already swallows per-row
  exceptions at `turn.py:2829` / `:2853` — formalise that into the result dict
  instead of just printing.)
- Orders execute **strictly in submission order** so price movement per fill
  matches sequential entry. This is the contract the UI's client-side estimate
  is reconciled against — the result message is authoritative.

Then route it from the turn loop. Cleanest: a new `TurnAction.ORDER_BATCH`
(or fold into the existing MARKET_BUY/MARKET_SELL handlers) whose IO call is a
new adapter method `order_batch(player, market_summary) -> list[order] | None`,
mirroring `market_buy_bulk`. The handler calls
`self.trading.execute_order_list(...)` and feeds the per-row results back so the
adapter can return them to the client.

### B. Server: `order_batch` WS message

In `island_traders/server/app.py` (the WS message dispatch where `chat`,
`training_counter_response`, `buy_out_float` etc. are handled, ~`app.py:4005`):

```jsonc
// client → server (only valid during this player's action window)
{"type": "order_batch", "batch_ref": "ob-17",
 "orders": [
   {"side": "buy",  "resource": "Oil",  "quantity": 12, "limit_price": 9.5},
   {"side": "sell", "resource": "Food", "quantity": 30}
 ]}
// server → client (echo batch_ref so the UI can match its basket)
{"type": "order_batch_result", "batch_ref": "ob-17",
 "results": [ ...execute_order_list output... ]}
```

The Order Desk "Open" action **parks the wizard** exactly like the existing
done-trading/training picker (`WsTurnAdapter.park_player` /
`choose_action`'s park loop, `ws_adapter.py:195`, `:341`): the parked turn
thread stays alive, accepts one or more `order_batch` messages, and resumes on
the player's Done/End-turn. Reuse that machinery — don't invent a new
lifecycle.

### C. Engine + server: `training_batch` WS message

Generalize the request submission to accept several cohorts at once:

```jsonc
{"type": "training_batch", "batch_ref": "tb-4",
 "requests": [
   {"profession": "Nurse",   "count": 2, "campus_player_id": 3,
    "transport_mode": "air_ticket"},
   {"profession": "Engineer", "count": 1, "specialty": "..."}
 ]}
{"type": "training_batch_result", "batch_ref": "tb-4",
 "results": [
   {"index": 0, "status": "submitted", "batch_id": 41},
   {"index": 1, "status": "rejected", "reason": "University fully booked: Engineer"}
 ]}
```

Each request row → one `TrainingRegistry.propose(...)` call (`training.py:247`),
returning its `batch_id`. Validate capacity per row via the existing
`capacity_remaining` (`training.py:217`) and surface a reason on rejection
rather than aborting the batch. **Do not touch the counter-offer flow** — once
each request has a `batch_id`, `educator_approve` / `requester_counter` / the
`training_counter_*` messages keep working unchanged. The returned `batch_id`s
let the UI track each cohort through that existing negotiation.

---

## Constraints & gotchas

- **Identical semantics.** A batch must equal N sequential wizard entries.
  Diff a batch run against sequential entry in a test (same orders, same seed)
  — net cash, inventory, and order-book state must match.
- **Timer.** The season timeout still applies while a basket is open; an
  unsubmitted basket is lost on timeout. The UI shows the timer inside the
  desk; the engine doesn't need to change, just don't hold locks across the
  park wait.
- **AI players.** The rule AI and LLM agents drive the same turn loop. Keep the
  single-order wizard path working (don't delete `_action_market_sell`'s
  interactive branch) so non-batch callers and the `FakeIOAdapter` tests still
  pass. The batch path should be additive, gated on
  `hasattr(self.io, 'order_batch')` like the existing `market_buy_bulk` guard
  (`turn.py:2809`).
- **`ResourceBundle` is immutable** — `add()`/`subtract()` return new bundles
  (`island_traders/models/resource.py:42`). The market primitives already
  handle this; just don't assume in-place mutation if you touch inventory.
- **`barter_market.needs[*].roles` is a string**, not a list, in the
  `game_state` payload (noted because the Order Desk UI reads the same payload).

## Tests to add (`tests/test_engine`, `tests/test_server`)

1. `execute_order_list`: mixed buy/sell basket — all filled; one row rejected
   for insufficient stock leaves the others intact; limit buy partially fills
   and rests; result dicts carry correct signed totals.
2. Equivalence: a 4-order basket vs. the same 4 orders entered sequentially
   (via `FakeIOAdapter`) produce identical final state.
3. `training_batch`: two cohorts submitted, each gets a `batch_id`; an
   over-capacity row is rejected with a reason while the other submits; a
   subsequent `educator_approve(batch_id)` still works on a submitted row.
4. Server: `order_batch` / `training_batch` round-trip through the WS handler
   returning a well-formed `*_result` (follow the existing
   `tests/test_server` patterns and `_bootstrap_game` helper).

## Definition of done

- `execute_order_list` + `order_batch`/`training_batch` handlers, additive and
  guarded so existing wizard/AI/test paths are untouched.
- New tests green; full suite green.
- `APP_VERSION` bump + `RELEASE_NOTES.md` entry.
- PR into `pre-release` with `Refs #114`, plus a one-line note in the PR on
  whether you wired the UI integration call or left a stub for Claude's tile PR.
- Hand back to Claude: "branch X at commit Y — order_batch/training_batch
  contracts live" so the Order Desk / Training Desk tiles can bind to them.
