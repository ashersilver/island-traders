# Brief — Deal response: notify the proposer + accept / return / reject (2026-06-16)

**Suggested owner:** Codex (engine model + server WS handlers + state payload).
**Base off:** current `origin/pre-release`.
**Tracking issue:** [#167](https://github.com/ashersilver/island-traders/issues/167).
File the engine+server work as `Refs #167` (this brief is the whole backend; the
UI follow-on also references #167, which closes when the UI ships).
**Pairs with:** Claude builds the **frontend** — toast/notification + the
accept / return / reject controls and a "your proposals & their responses"
section — against the message contracts below. Per the standing rule, the
**second of {backend PR, UI PR} to merge wires the integration call**; the
first leaves a stub.

---

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees.** You work in the **primary checkout**
  (`/Users/ashleysilver/Documents/projects/island-traders`). Claude works in a
  **separate worktree** on a `claude/*` branch. Do not edit Claude's worktree
  and do not run `git reset/checkout/stash` against it. Coordinate only through
  pushed branches + PRs.
- **Branch creation.** `git fetch` first, confirm you are current
  (`git merge-base --is-ancestor origin/pre-release HEAD`), then cut a fresh
  branch off `origin/pre-release` named for the task, e.g.
  `codex/deal-response-2026-06-16`. Never commit straight onto `pre-release` or
  `master`.
- **PRs only — no fast-forwards.** Every change reaches `pre-release` through a
  PR that Claude (integrator) merges. Do **not** push/fast-forward to
  `pre-release`. Link the issue (`Closes #N` / `Refs #N`). Update
  `RELEASE_NOTES.md` and bump `APP_VERSION` `.N` in `constants.py` (today's date
  resets `.N` to 1).
- **Git discipline.** No `--no-verify`, no `--amend`, no force-push; always new
  commits. Run the **full** `pytest` suite before handoff.
- **Handoff.** When ready: "branch X at commit Y — ready to integrate", with a
  note on whether you wired the UI call or left a stub.

---

## The problem (player-facing)

In the web UI, structured barter deals are **read-only**. The frontend renders
a "Proposed Deals" table (`renderBarterMarket`,
`island_traders/server/static/index.html:4550`) showing From / Offers / Wants /
To, and the comment at `index.html:4031` admits *"Negotiation actions
(structured deals) arrive with phase 3."* There is **no way for the target to
respond** and **no notification to the proposer** when a deal is acted on. So a
player can propose a deal and nothing ever happens in the UI.

The CLI already has the full interactive flow (`_review_pending_deals` and
`_action_propose_deal` in `island_traders/engine/turn.py`), and the engine
primitives exist (`TradingEngine.propose_deal` / `accept_deal`,
`island_traders/engine/trading.py:175` / `:213`; `DealLedger`,
`island_traders/models/deal.py:46`). The gap is **web wiring + a "return /
counter" path + proposer notification**.

The user's words: *"nowhere in the UI does a player get notified that someone
has responded to a proposed deal and either accept or return the proposal."*
"Return" = bounce the proposal back to the proposer with modified terms
(a counter-offer), not just accept/reject.

---

## Use the training counter-offer flow as your template

There is already a complete, working accept / counter / reject + notification
loop for **training** in `island_traders/server/app.py`:

- `_handle_training_counter_response` (`app.py:2447`) — dispatches
  `action ∈ {accept, counter, reject, ack}`, mutates the registry, and sends an
  ack message + notifies the counterparty (`app.py:2523`).
- Status vocabulary includes `"countered"` (`app.py:2398`,
  `training.py` request statuses), with `counter_message` / `counter_fee`
  carried in the payload (`app.py:2263`, `:2331`).
- The requester side mirrors it in the CLI
  (`_review_training_counteroffers`, `turn.py:2093`+) with
  `requester_accept_counter` / `requester_counter` / `requester_reject_counter`.

**Build the deal-response flow to match this shape** so the UI, the
notification mechanism, and the tests all reuse familiar patterns.

---

## Engine / model changes (`models/deal.py`, `engine/trading.py`)

1. **Add a `RETURNED` (countered) status** to `DealStatus`
   (`deal.py:7`). Current set is `PENDING / ACCEPTED / REJECTED / EXPIRED`.
2. **Track counter terms + provenance on `DealProposal`** (`deal.py:14`):
   - who the ball is with (a `awaiting_id` or a derived `responder_turn`
     boolean — proposer vs target), and
   - an optional free-text `message` per round, and
   - a small history is nice-to-have but not required; a single current set of
     terms that gets overwritten on each return is acceptable for v1.
3. **`DealLedger` methods** (`deal.py:46`): add `reject(deal_id)` (sets
   `REJECTED`) and `return_to_proposer(deal_id, new_offer/new_request/
   new_sweetener, message)` (sets `RETURNED`, swaps which party must respond,
   updates terms). `accept` already exists (`deal.py:74`).
4. **`TradingEngine`** (`trading.py:213`): keep `accept_deal`'s revalidation of
   both sides' inventory/dollops (`trading.py:222`–`:254`) — a returned deal
   that is later accepted must re-check stock at acceptance time
   (`StaleResourceError`). Add a `reject_deal` and (optional) a thin
   `return_deal` that just calls the ledger; the actual resource movement only
   happens on accept.
5. **Expiry:** decide and document when a `PENDING`/`RETURNED` deal expires.
   Simplest: expire at end of the proposer's next turn if untouched, mirroring
   how stale deals are swept. Wire it where pending deals are reviewed
   (`_review_pending_deals`, `turn.py`).

Keep the **pure engine / CLI path working** — do not break
`_review_pending_deals` or `_action_propose_deal`; the web path is additive.

## Server changes (`server/app.py`)

1. **WS action: propose a deal.** Add a structured `propose_deal` (or
   `deal_propose`) client action that calls `TradingEngine.propose_deal`. (The
   barter board read model already exists at `app.py:3165`–`:3332`,
   `game_state.barter_market.deals`.)
2. **WS action: respond to a deal.** `deal_respond` with
   `{deal_id, action: "accept"|"return"|"reject", new_offer?, new_request?,
   new_sweetener?, message?}`, dispatched like
   `_handle_training_counter_response` (`app.py:2447`).
3. **Notify the proposer.** When the target responds, push a message to the
   proposer (and vice-versa when the proposer accepts/returns a counter) — model
   it on the training counterparty notify at `app.py:2523`. Type e.g.
   `{"type": "deal_response", "deal_id", "result": "accepted"|"returned"|
   "rejected", "from": <name>, ...}`.
4. **State payload.** Extend `game_state` so each player can see, for the
   *current viewer*: (a) **deals awaiting my response** (I am the party the ball
   is with), and (b) **my proposals + their latest status/terms**. Add these
   alongside `barter_market` (`app.py:3332`) — e.g.
   `deals_awaiting_me: [...]`, `my_deals: [...]` with deal_id, counterparty,
   offer/want terms, status, last message, and who must act next. The frontend
   binds to these.

**Contract to hand Claude (write this verbatim in the PR):** the exact JSON
shapes for `deal_respond` (request) and `deal_response` (push), plus the new
`deals_awaiting_me` / `my_deals` payload fields with field names and types.

---

## Constraints & gotchas

- **Revalidate on accept.** A deal accepted several turns after proposal must
  re-check both parties still hold the goods/dollops (`accept_deal` already does
  this — keep it). A returned-then-accepted deal is the risky path.
- **AI players** drive the same turn loop. The rule AI proposes/accepts via the
  engine primitives (`engine/ai.py` references deals). Keep the non-web path
  intact and gate web-only behaviour behind the IO seam like the existing
  training handlers.
- **`barter_market.needs[*].roles` is a string**, not a list, in the payload
  (consistency note — the deal payload should be explicit about its types).
- **`ResourceBundle` is immutable** (`models/resource.py:42`) — `add/subtract`
  return new bundles; the trading primitives already handle this.
- **Don't double-spend on return.** Returning a deal must not move resources;
  only `accept` transfers. Verify a propose → return → return → accept chain
  moves goods exactly once.

## Tests to add (`tests/test_models`, `tests/test_engine`, `tests/test_server`)

1. `DealLedger.return_to_proposer` flips the responding party and updates terms;
   status becomes `RETURNED`.
2. Engine: propose → target returns (new terms) → proposer accepts → resources
   move exactly once; both ledgers/inventories correct.
3. Engine: accept of a stale returned deal raises `StaleResourceError` and
   moves nothing.
4. Engine: reject sets `REJECTED` and is terminal; expiry sweeps an untouched
   pending/returned deal.
5. Server: `deal_respond` round-trips through the WS handler for
   accept/return/reject and emits a well-formed `deal_response` to the
   proposer; `game_state` exposes `deals_awaiting_me` / `my_deals` correctly for
   each viewer (follow `tests/test_server` patterns + `_bootstrap_game`).

## Definition of done

- `DealStatus.RETURNED` + ledger/engine return/reject/expiry methods, additive
  and leaving the CLI/AI paths intact.
- `propose_deal` + `deal_respond` WS handlers, proposer notification, and the
  `deals_awaiting_me` / `my_deals` state payload fields.
- New tests green; **full suite green**.
- `APP_VERSION` bump + `RELEASE_NOTES.md` entry.
- PR into `pre-release` with `Closes #N` (engine+server) / leave the UI as
  `Refs #N`, plus a one-line note on whether you wired the UI call or stubbed.
- Hand back to Claude: "branch X at commit Y — `deal_respond` /
  `deal_response` / `deals_awaiting_me` / `my_deals` contracts live" with the
  exact JSON shapes, so the notification + accept/return UI can bind to them.
