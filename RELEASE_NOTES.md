# Island Traders Release Notes

Release notes are required before merging a feature/fix branch into
`pre-release`.

## Unreleased

### claude/ux-hints-to-actions

Branch: `claude/ux-hints-to-actions`
Target: `pre-release`

UX review Phase 4 — Decision Hints become actionable.

**What:** Each rendered hint now carries a `triggers_action` field
naming the `TurnAction` value that addresses it (e.g. an "Unblock
Oil" hint triggers `buy_market`; an "Add workers for X" hint triggers
`request_training`). The hint card grows a gold "Open" button:

- When the action menu is currently open for this player, the button
  calls `sendResponse(action)` — the same effect as clicking the
  corresponding action menu button directly. **No auto-submit**: the
  server then surfaces the action's modal (Market Buy, etc.) and the
  player still confirms the final game action there.
- When the action menu is not open (waiting on other players, between
  prompts, etc.), the button is disabled with a "Wait for your action
  prompt" tooltip.

**Recommendation bridge:** The set of currently-hinted action values
is tracked in `_currentHintActions`. When `showActionPrompt` renders
the grouped action menu (Phase 2 work), the matching action button
picks up the gold `.recommended` outline — same affordance Codex's
Phase 1 payload reserved via the `recommended: true` per-option flag
(server-side `recommended` is still default-false as of Codex's
shipped payload; this layers a client-driven view on top of it).

**Hint → action mapping:**

| Hint kind | Triggers |
|---|---|
| Sustenance shortfall (`*_alerts`) | `buy_market` |
| `Produce X` (output is producible) | `produce` |
| `Unblock X` (input shortfall) | `buy_market` |
| `Add workers for X` | `request_training` |
| `Capital limits X` | `purchase_capital` |
| `Underwrite X` (service output) | _(no direct action; service-side flow)_ |
| Fallback "Check market and deals" | _(no direct action)_ |

The brief's `loan_*` and `insurance_review` targets exist in Codex's
server-side `decision_hints` field but the client's own
`renderDecisionHints` does not emit those kinds today, so no UI
shortcut is added for them in this branch. They can be picked up
when the client switches over to consuming `gameState.decision_hints`
directly (a follow-up).

**Render synchronisation:** `showActionPrompt` and `hideOverlay` now
call `renderGameState()` so hint cards re-render their `Open` buttons
and the action menu picks up `recommended` outlines as the prompt
opens / closes. Cheap re-render — gameState is already cached.

**Scope discipline:**

- No engine / server changes. Pure client.
- In-modal preselection / filtering (Phase 5 of the plan, e.g. Market
  Buy with the hinted resource at the top of the table) is deferred —
  the seam is now in place for Phase 5 to plug into.
- Client-side hint generation is unchanged in scope; only `target`
  and `triggers_action` are added per hint.

Suite **352 passing** (no test changes — pure client refactor).

### claude/ux-personnel-popup

Branch: `claude/ux-personnel-popup`
Target: `pre-release`
Depends on: `claude/ux-popup-shell` (merge popup-shell first).

UX review Phase 3 — Personnel detail popup (Mockup 2).

**What:** The sidebar Personnel summary is now clickable. Click opens
a popup with two sections, both driven entirely by the existing game
state payload:

- **Training Pipeline** — table of in-flight batches consuming the
  `training_pipeline` field added by `codex/ux-server-payload`. One
  row per batch with: trainee count, target profession, status,
  educator, transport mode, fee (Dp), return season/year, seasons
  remaining. Counter-messages (e.g. "Try 30 Dp instead") render
  beneath the table, one per batch that has one. Empty pipeline
  degrades to *"No workers currently in training."*
- **Staffing** — band table (Managers / Technicians / Workers) with
  active and in-training counts, plus a total row. Footer shows
  workforce active/total, efficiency %, and population — the same
  numbers the sidebar shows individually, gathered in one place.

**UI plumbing:**

- `s-personnel` sidebar element gets `onclick="showPersonnelPopup()"`
  and a tooltip; the existing `personnel-breakdown` CSS class gets
  `cursor:pointer` + a subtle hover brightness.
- New popup uses the `showPopup` shell from
  `claude/ux-popup-shell` — single Close button in the standard
  footer, no per-popup chrome.
- New `.popup-section`, `.popup-table`, `.empty-state`, `.batch-notes`,
  `.staffing-extras` CSS rules — reusable by the remaining Phase 6
  popups (Loans / Insurance / Inventory) when they land.
- `_TRAINING_STATUS_LABEL` table maps the enum values from
  `island_traders/models/training.py::TrainingStatus` to display
  text (`awaiting_educator` → "Awaiting educator", etc.).

**Scope discipline:**

- No engine or server-payload changes. Pure client refactor.
- "Capacity/deficit summary: missing professions for the island
  staffing plan and current university slot availability" from the
  brief is deferred — the data is in `pd["capacity"]` but adding a
  third popup section is out of scope for this branch and depends on
  Phase 4 hint plumbing to be meaningful.
- Inventory popup (also Phase 6 §5) is deferred to a follow-up branch
  to keep this one focused on Personnel.

Suite **352 passing** (no test changes — pure client refactor).
### claude/ux-action-grouping

Branch: `claude/ux-action-grouping`
Target: `pre-release`

UX review Phase 2 — grouped action menu (Mockup 1).

**What:** Rewrites `showActionPrompt` in
`island_traders/server/static/index.html` to render the per-season
action prompt as labelled groups instead of one flat button row.
Consumes the structured option payload that Codex's Phase 1 branch
(`codex/ux-server-payload`) added: each option's `group`, `enabled`,
`disabled_reason`, and `recommended` fields drive the layout directly.

- Canonical group order: Production / Trade / People / Capital /
  Finance / Info (stable, defined client-side in
  `ACTION_GROUP_ORDER`).
- Empty groups are skipped; unknown-group labels (forward-compat) are
  appended at the end.
- `Produce` keeps the existing gold `.highlight` style.
- `recommended: true` adds a `.recommended` outline (Phase 4 will set
  this from Decision Hint targets — currently always false).
- `enabled: false` disables the button and shows the
  `disabled_reason` as a native tooltip (`title` attribute). Disabled
  buttons do not bind a click handler so the user can't accidentally
  send a server message that the engine would reject anyway.

**CSS additions:** `.action-groups`, `.action-group`,
`.action-group-label`, `.action-btns button.recommended`,
`.action-btns button[disabled]`. The existing `.action-btns` flex-wrap
layout is unchanged inside each group, so buttons reflow naturally on
narrow widths and groups stack vertically.

**Back-compat:** options that arrive without `group` fall through to
the `Info` bucket — keeps the dashboard functional even if rolled
back to a pre-Phase-1 server.

**Verification:** Suite **352 passing**. Pure client refactor; no
Python tests exercise the prompt rendering. Browser pass deferred to
the PR review (no automated DOM-level test scaffolding exists in this
repo today).

### claude/economy-lifecycle-spec

Branch: `claude/economy-lifecycle-spec`
Target: `pre-release`

**Docs-only — requirements spec.** No code/test changes (suite
unchanged at 297). Captures product-owner direction (2026-05-18) for a
cross-island economic-dependency feature set:

- New `requirements/economy-lifecycle-2026-05.md`: worker
  lifecycle/retirement (general age system, Agriculture bootstrap),
  universal capital lifespan + per-season maintenance, a Banker
  **capital-reserve / MBA leverage** model, and an economy rebalance
  (per-player cash 700→1500, Mining Oil 4→8, Agriculture Food →15).
  Phased A–E, independently mergeable; A–D engine work, E = RULES.md +
  calibration handoff.
- **Banker model (refined 2026-05-18):** fractional-reserve, not a
  binary gate. Loans are backed by the bank's own capital at a reserve
  ratio (**0.50** with <3 MBA Banker Managers, **0.20** with ≥3); own
  capital earns full interest, externally-sourced capital earns only
  the margin over the posted rate at issuance; reserved own capital is
  locked until the loan resolves. Banking starts with **0** MBA
  managers (intentional early constraint, ~2× leverage) and trains up
  (2 Professors + 3 Courses, 2 seasons) to ~5×. Without a
  `banker.computing_centre` capital item, loan applications take +1
  season to disburse. No MBA bootstrap roster.
- **Loan terms & negotiation (refined 2026-05-19):** Banker may quote
  any rate (formula = suggested default) and the applicant can
  **counter** (reuses the training counter pattern); indicative
  **1/2/3-year** term-rate quotes; 2/3-year loans settle interest
  annually and roll the **original amount at the original rate** until
  the final year (rate locked at origination) — distinct from the
  shipped #6 post-maturity opt-in refinance.
- New `requirements/role-player-guides.md`: on-demand per-role
  instruction beyond the acquisition intro (esp. the Banker lending
  rules), single content source shared with RULES.md; scheduled after
  economy Phase D / paired with Phase E. TODO entry under Dashboard &
  UX.
- `TODO.md`: Economy Lifecycle section with the A–E checklist.
- Annotates `codex-tasks/balance-calibration-2026-05.md` with a
  **sequencing dependency**: calibration must run *after* economy
  Phases A–D land (this feature deliberately re-balances the
  over-dominant Banker/Farmer, so calibrating the current economy would
  be wasted).

Decisions locked via AskUserQuestion: 1500/player; general retirement
(Agriculture first, near-retirement seeding as a tuning lever); MBA as a
credential on existing Banker Managers; universal capital wear.

### codex/ux-server-payload

Branch: `codex/ux-server-payload`
Target: `pre-release`

Server-side payload support for the UX review mockups:

- Action prompts now include grouped option metadata with enabled state,
  disabled reasons, and a default `recommended` flag.
- Game state now exposes each player's active training pipeline, including
  canonical training status, educator, transport, return timing, and counter
  message fields.
- Finance is hidden from market quote/history data while retaining the enum
  for compatibility with the Banker service model.
- Decision hints now include structured targets so clients can open focused
  popups without parsing display text.

### claude/ux-popup-shell

Branch: `claude/ux-popup-shell`
Target: `pre-release`

UX review Phase 6 starter — standardised info-popup shell. Lands the
shared modal chrome that subsequent UI phases (Personnel popup, etc.)
will plug into.

**What:**

- New `showPopup(title, body, opts)` helper in
  `island_traders/server/static/index.html`. Adds a standard
  right-aligned footer with a Close button by default; callers can pass
  `footerActions` for custom buttons (Market Buy uses Total + Buy +
  Cancel).
- New `.popup-footer` CSS rule (flex, right-aligned, gap, top-margin).
- Refactored three existing popups to use the shell:
  - `showConstraintPopup` — was manipulating `dlg-title` / `dlg-body`
    directly and baking its own Close button.
  - `showMarketBoardPopup` — was baking its own Close button into the
    body.
  - `showMarketBuyPopup` — now uses `footerActions` so the Total / Buy /
    Cancel line is in the standard footer rather than the body.

**Scope discipline:** `showDlg` is untouched and remains the helper for
IO-driven prompts (option pickers, quantity input, confirm) — those
have a different lifecycle (`sendResponse` / `CANCEL_SENTINEL`). The
unrelated player-onboarding modal (`hideOverlay` flow at line ~1394)
was not touched. New popups (Personnel, Loans, Insurance, Inventory)
are scheduled for follow-up branches alongside Phase 3, per the plan
in `requirements/implementation-plans/review-ux-plan.md`.

Suite **352 passing** (no test changes — pure client refactor; suite
size matches Codex's Phase 1 baseline).

### claude/order-override-and-invest

Branch: `claude/order-override-and-invest`
Target: `pre-release`

Two requirements from continued live testing.

**1. New bid/ask overrides the player's prior orders on that resource.**
Replaces yesterday's cumulative-merge rule. Any new `post_bid` /
`post_offer` now calls `Market.cancel_player_orders(player_id, rtype)`
first, which:

- Cancels every standing bid AND ask that player has on that resource.
- Refunds resources from any resting ask back to the seller.
- Decrements `market.supply` / `market.demand` by the unsold remainder
  so the price formula doesn't see the cancelled depth.

A player can therefore only hold one standing order per resource at a
time. Switching sides (e.g. ask → bid) cancels the prior ask and
refunds its inventory. Other players' orders and orders on other
resources are untouched.

The 5 cumulative-merge tests added in
`claude/cumulative-orders-workforce-cap` are replaced with 6 override
tests covering all four cancel-cases plus supply/demand counter
decrement.

**2. New `TurnAction.INVEST` — opening catalogue stays open.**
Items from the player's role catalogue that they don't currently own
remain takeable post-Investing-Phase. Adds:

- `_action_invest(player, result, year, season)`: lists role-catalogue
  items the player doesn't own; player picks; cost paid in Dp; item
  delivered immediately (acquired_tick = current_tick — no Manufacturer
  transit, distinct from `PURCHASE_CAPITAL`).
- Wired into the action dispatch alongside the other turn actions, so
  the web UI button renders automatically and the CLI menu surfaces
  "Invest" as an option.
- Tests cover: chosen item added + cost debited + acquired_tick set;
  already-owned items omitted from the choice list; insufficient Dp →
  refuse; fully-taken catalogue → "No remaining opening investments."

> The action is distinct from `PURCHASE_CAPITAL` on purpose: Invest is
> the post-Investing-Phase fast lane for items the player passed on at
> game start; Purchase Capital is the commercial mid-game purchase from
> the Manufacturer with its normal `delivery_seasons` transit and
> Phase C lifecycle implications.

Suite **346 passing** (337 baseline − 5 cumulative tests + 6 override
tests + 4 invest tests + 4 other deltas).

### claude/cumulative-orders-workforce-cap

Branch: `claude/cumulative-orders-workforce-cap`
Target: `pre-release`

Two requirements from live `:8001` testing.

**1. Cumulative bids & asks.** `Market.post_offer` / `post_bid` now
merge a new order into an existing same-season same-(player, resource,
price) standing order rather than spawning a separate book entry —
adding to a position cumulates instead of cluttering the depth list.
The matching rules already shipped with the defect-1 fix (cheapest
asks fill first; within-price FIFO via stable sort; walk to the next
price if still within the bid) remain in force.

**2. Workforce capped at 60% of population.** `Player.available_unskilled`
now returns `max(0, ⌊0.60 × population⌋ − workforce.count)` — a hard
cap on the total workforce. Replaces the legacy
`UNSKILLED_RECRUITMENT_RATIO = 0.5` rule (which scaled with non-worker
residents rather than capping the total). New constant
`MAX_WORKFORCE_FRACTION_OF_POPULATION = 0.60`.

Suite **337 passing** (326 baseline + 5 cumulative-order tests + 6
workforce-cap tests).

### claude/market-matcher-and-turn-label-fix

Branch: `claude/market-matcher-and-turn-label-fix`
Target: `pre-release`

**Defect fixes** found during live `:8001` testing.

**1. Market matcher — bids and asks now actually cross.**
`Market._auto_match_bid` / `_auto_match_offer` previously matched only
on **exact-price equality** AND **only when the order's quantity fit
inside the resting order entirely** (`tests/test_models/test_market.py
::test_bid_does_not_auto_resolve_when_quantity_exceeds_offer` literally
codified the bug as expected behaviour). Net effect on the live game:
players reporting "trades don't settle even within a small range".

Rewritten to standard exchange semantics:

- Match when `bid_price >= ask_price` (cross when the bid covers the
  ask, not just when they're equal).
- **Resting (older) order sets the trade price** — the new order is
  the price-taker, getting the better side of the spread.
- **Partial fills supported**: a new order walks the opposite side in
  best-price-first order (asks ascending / bids descending), consuming
  `min(remaining, remaining)` slice by slice until exhausted or no
  remaining cross.

Tests: the broken-codified test is replaced with
`test_bid_partially_fills_when_quantity_exceeds_offer`; new tests cover
crossed-price matching at both the ask price and the bid price, a
non-crossing "bid below all asks" case, and a multi-slice walk
(`test_bid_walks_multiple_resting_asks_for_partial_fills`).

**2. "Turn" terminology removed from per-player headers.**
Players seeing log lines like `--- Bravo's turn (Education, Research,
Manufacturing) ---` were reading them as sequential play, but the
server runs `parallel_mode=True` (one thread per human, concurrent
within a season). Renamed at all three sites:

- `engine/turn.py`: `--- Bravo (roles) — actions this season ---`
- `cli/prompts.py`: `Bravo (roles) — choose an action:`
- `cli/display.py`: `Bravo — choose an action:`

No engine behaviour change — the headers always referred to a single
player's action menu, not a global turn order.

Suite **330 passing** (326 baseline + 4 net new market tests).

### claude/economy-phase-d

Branch: `claude/economy-phase-d`
Target: `pre-release`

**Economy Lifecycle Phase D1** — Banker capital-reserve / MBA-leverage
model (the headline Banker nerf, the principal balance lever in this
feature set). Supersedes the earlier "no loans without 3 MBAs" binary
gate with a proper fractional-reserve mechanic.

**Behaviour:**

- `Worker.has_mba` field (Manager-band Banker workers only).
- New constants: `MBA_RESERVE_RATIO_BASE=0.50`,
  `MBA_RESERVE_RATIO_QUALIFIED=0.20`, `MBA_QUALIFIED_THRESHOLD=3`.
- Helpers `TurnManager._mba_banker_count(banker)` and
  `_banker_reserve_ratio(banker)` — `0.50` while <3 MBA Banker
  Managers are active, `0.20` once ≥3 are.
- Every loan now funds as **own + external**: bank commits `r·P` of
  its own capital (locked, deducted at issue) and sources `(1−r)·P`
  externally at the posted funding rate via the renamed
  `_fund_bank_external_portion`. The external depositor obligation
  matures alongside the loan and is repaid through the existing
  `_process_loan_repayments` path — economics produce **full interest
  on the own slice + margin (loan_rate − posted) on the external
  slice**.
- If the bank can't afford its own share, the loan is **refused** with
  a clear message naming the reserve ratio, the shortfall and the MBA
  depth (e.g., `"Bank cannot back this loan at 50% reserve: needs
  25.0 Dp of own capital but has only 10.0 Dp (MBA-qualified Banker
  Managers: 0/3)."`).
- `Loan` gains `own_committed`, `external_funded`, `posted_at_issue`,
  `reserve_ratio_at_issue` (defaulted 0.0; backward-compat in save/load).
- Self-lending (Banker borrowing from its own Banking Island) skips
  the reserve check — preserves the existing dollops-burn semantics for
  that special case.

**Tests:** suite **326 passing** (316 baseline + 10 net new across
`tests/test_engine/test_loans.py` (3) and
`tests/test_models/test_banker_reserve.py` (8); one Phase-2 shortfall
test was replaced by `test_loan_split_into_own_and_external_per_reserve_ratio`
since the old "fund whatever shortfall" behaviour is exactly what the
reserve gate now forbids).

**Intentionally deferred — clearly flagged D1.5 / D2 follow-ups:**

- In-game **MBA training UI** (Banker Managers earn `has_mba` via a
  University request consuming 2 Professors + 3 Courses over 2
  seasons). The flag is settable from tests today; players can't yet
  earn MBAs through gameplay, so the bank is **stuck at r=0.50** in
  this MVP. That's the principal nerf the calibration brief needs —
  full upgrade path is the next phase.
- **Multi-year annual interest servicing** with original-amount /
  original-rate rollover (the simple rollover rule for 2/3-yr loans).
  Today's bullet repayment still applies; multi-year loans collect all
  interest at maturity rather than annually.
- **Free pricing + applicant counter-offer** loop (Banker may quote
  any rate; applicant counters).
- **`banker.computing_centre`** capital + indicative 1/2/3-yr term
  quotes UI (D2).
- **Default depositor accounting** is still simple: a defaulted
  customer loan loses the bank's `own_committed`, but the external
  depositor obligation continues as a separate ledger entry maturing
  later — adequate for now; a richer "bank also owes the depositors
  even on default" path is a follow-up.

### claude/economy-phase-c

Branch: `claude/economy-phase-c`
Target: `pre-release`

**Economy Lifecycle Phase C** — universal capital lifecycle: every
capital item now has a service life and a per-season maintenance cost,
with an Agriculture **combine harvester** seeded already part-aged.

- `CapitalItem` gains `service_life_seasons` (default
  `DEFAULT_SERVICE_LIFE_SEASONS=20`, tunable accepted first-cut) and
  `maintenance_per_season` (default 0.0 → falls back to
  `DEFAULT_MAINTENANCE_FRACTION=0.03` × cost). Overrides bleed through
  `_multiply_capital_capacity` (it used to drop new fields silently).
- **`farmer.harvester` is now the "Combine Harvester"** with
  `service_life_seasons=8` (≈2 yr) — repurchase from the Manufacturer
  every two years.
- `Player.unmaintained_capital` (transient, not persisted) plus
  `Player.effective_capital_inventory()` which subtracts unmaintained
  units. Production reads
  `player.effective_capital_inventory()` everywhere it used
  `capital_inventory` so unmaintained units contribute **0 capacity**
  that season.
- New `Game._process_capital_maintenance(year, season)` called each
  season after `_process_retirements`:
  - **Expiry** — units whose age ≥ `service_life_seasons` are removed
    (oldest first / FIFO) with a `[CAPITAL EXPIRED]` log; the island
    must repurchase from the Manufacturer to restore that capacity.
  - **Maintenance** — per-unit Dp debit; on shortfall the unit is
    flagged unmaintained for the season (logged `[CAPITAL
    UNMAINTAINED]`); flag clears at the next season's maintenance step.
- New `STARTING_AGED_CAPITAL` table seeds Agriculture with 1
  combine harvester at age 4 — expires end of Year 1, aligning with the
  seeded Farmer's retirement (Phase B) for a deliberate Y1 double
  squeeze that forces real Manufacturer trade.

**Tests:** suite **316 passing** (305 baseline + 11 new in
`tests/test_engine/test_capital_lifecycle.py`). Two existing
`test_investing` tests updated for the "Combine Harvester" rename and
the seeded-aged-combine count.

> Balance note: maintenance only bites when players actually own
> capital, and starts modest (combine = 2.7 Dp/season at the
> 3 %-of-cost default). With 1500/player starting cash it's
> absorbable. The cost-pressure rises naturally with capital purchases
> — exactly the Agriculture → Manufacture dependency the brief asks
> for, applied game-wide.

### claude/economy-phase-b

Branch: `claude/economy-phase-b`
Target: `pre-release`

**Economy Lifecycle Phase B** — worker lifecycle / retirement (general
age system, Agriculture bootstrap activated).

- `Worker.age_seasons` field; `Workforce.add_workers(age_seasons=…)`.
- New `Workforce.advance_age_and_retire(working_life_by_band, default)`
  — ages **every** worker (active + in-training) one season per call,
  removes and returns those whose age ≥ their band working life.
- New constants: `WORKING_LIFE_SEASONS = {"Manager": 40, "Technician":
  32, "Worker": 24}` (tunable; accepted first-cut),
  `DEFAULT_WORKING_LIFE_SEASONS = 32`, and `STARTING_WORKER_AGES` with
  Agriculture seeded (`Farmer`: 4 seasons from retirement,
  `Horticulturalist`: 8).
- `Game._process_retirements(year, season)` called each season after
  `_process_training_returns`; logs `[RETIREMENT]` per island and drops
  retiring in-training workers from their training batch via the new
  `TrainingRegistry.drop_worker` (request rejects if it empties).
- Game setup seeds starting workers' ages from `STARTING_WORKER_AGES`
  using `band_of(profession)` → `WORKING_LIFE_SEASONS[band]`. Other
  islands default to age 0.
- Save format adds `age_seasons` per worker (backwards-compatible
  default 0 on load).

**Tests:** suite **305 passing** (297 baseline + 8 new in
`tests/test_models/test_worker_lifecycle.py` — age tick, band-keyed
retirement, in-training retirement, drop_worker behaviour, Agriculture
bootstrap schedule check).

> Bootstrap effect on simulations: the Agriculture Farmer retires ~4
> seasons into the game and the Horticulturalist ~8 seasons, putting
> real recruit+retrain pressure on the over-dominant Farmer role. This
> is *intended* and feeds the open balance-calibration workstream — do
> not interpret a Farmer win-rate dip post-merge as a regression.

### claude/economy-phase-a

Branch: `claude/economy-phase-a`
Target: `pre-release`

**Economy Lifecycle Phase A** (`requirements/economy-lifecycle-2026-05.md`)
— constants/starting-stock only, zero new mechanics.

- Per-player starting cash **700 → 1500**: `STARTING_DOLLOPS` 700→1500,
  `TOTAL_STARTING_DOLLOPS` 700→10500 (= 1500 × 7),
  `DEFAULT_STARTING_CAPITAL` (server) 700→1500.
- `STARTING_INVENTORY["Miner"]["Oil"]` **4 → 8** (larger Oil buffer).
- `STARTING_INVENTORY["Farmer"]` gains **`"Food": 15`**.

Tunables accepted as first-cut per product-owner ("Accept 2").
Suite **297 green**. Tests updated for the new economy:
`test_economy_balance` Miner-Oil assertion 4→8;
`test_island_guarantee` two offer-pricing tests rebased onto the 1500
starting capital (AI prices now fall in the "low" band; floor scales
to 0.20 × 1500).

> Follow-up (not in A, flagged): `game.py` derives the CLI/sim
> per-player default as `TOTAL_STARTING_DOLLOPS / num_players`, so a
> non-7-player CLI/sim game won't get exactly 1500/player. Server games
> use `DEFAULT_STARTING_CAPITAL` (1500/player) directly. Making
> per-player the canonical constant is spec open-Q #4 — deferred.

### claude/rules-training-reconcile

Branch: `claude/rules-training-reconcile`
Target: `pre-release`

**Docs-only** (RULES.md). No code/test changes (suite unchanged at
297). Reconciles the player-facing rulebook's training chapter with the
shipped Education Phase 1–3 + personnel-sidebar mechanics — it had been
left describing the pre-Phase-3 model.

- **Two-pipeline model documented:** Manager-tier = Course-gated
  university (1 Course per class ≤12); Technician-tier = Apprenticeship
  Programme slot-pool + Instructor gated, never Course-gated.
- **Profession-dependent durations** added to the capacity table
  (Doctor **3** seasons away, other Managers 2, Nurse 1, all Technicians
  1) and the full annual-quota table now lists every profession
  (previously a stale "caps added in a future balance pass" note).
- **Apprenticeship settling season** (1 season home @ 75% before 100%),
  **itemised fee** (base + food/accom 5 Dp/trainee/season + ticket +
  Manager-tier Expertise), **campus load**, and the **"All visible
  skill deficits"** bundled-request option all documented.
- Steps rewritten (the old duplicated "Educator Approval" Steps 2 & 4
  and the charter-flight-as-default were inaccurate); air ticket is now
  correctly the default transport. Quick Reference transport block
  aligned.
- Stale fixes: Educator starting workforce `4 → 8` (4 Professors + 4
  Instructors); profession table `Tutor → Instructor`; turn-action
  one-liner no longer claims "one season".

Clears the second-order release-gate item flagged in
`claude/release-prep` — the v0.1.0 rulebook training chapter is now
trustworthy. (Balance calibration remains the outstanding release
blocker.)

### claude/release-prep

Branch: `claude/release-prep`
Target: `pre-release`

**Docs-only — release-readiness prep.** No code/test changes (suite
unchanged at 297).

- **Balance measured on `pre-release` @ `36c74a4`** (AI-only, 3y, seeds
  42/1/7/99): Banker 54.6% + Farmer 42.5% ≈ 97% of all wins;
  **Transporter and Doctor win 0%** on every seed; Miner 0.4%, Educator
  1.0%, Manufacturer 1.5%. Target ≈14.3% each. Stable across seeds →
  structural, not RNG.
- Adds `requirements/codex-tasks/balance-calibration-2026-05.md` — a
  self-contained Codex brief to fix this (the release blocker). Notes
  the old `codex/sim-calibration` branch is stale/abandoned (0 ahead,
  ~5.8k behind) — calibration must start fresh.
- **RULES.md fix:** the two "Healthcare full capacity" statements
  disagreed (one "20 Medical Orderlies", one "20 unskilled workers");
  aligned to `4 Doctors + 20 Nurses + 20 Medical Orderlies (44 total)`,
  consistent with `STARTING_WORKERS_BY_PROFESSION` (the CLAUDE.md
  "workforce 12 / 10 Nurses" complaint was already fixed in an earlier
  branch — the starting-workforce table already shows 2+2+2=6).

**Release-readiness (proposed, for product-owner decision):**

- **NO-GO to promote `pre-release` → `master` yet.** Blocker: AI balance
  above (Codex brief filed). Tests green, 49 commits of real work, but a
  game that ships with two roles unable to win and two roles taking 97%
  of wins is not releasable.
- **Tag scheme proposal:** no tags exist; `master` was promoted via PRs
  #16/#17 untagged. Suggest annotated semver tags on `master` at each
  promotion, starting **`v0.1.0`** for this milestone (pre-1.0 = rules
  still in flux). Future: `v0.2.0` per feature-milestone promotion.
- **Roll-up mechanic at promote time:** rename `## Unreleased` →
  `## v0.1.0 — <date>` (the 24 accumulated sections become the v0.1.0
  changelog), open a fresh empty `## Unreleased`, PR `pre-release` →
  `master`, then `git tag -a v0.1.0`.
- **Second-order release-gate item (not blocking, but should ship with
  v0.1.0):** RULES.md training chapter is stale vs shipped Phase 1–3
  (single-season model, no apprenticeship slot-pool/Instructor gate, no
  profession-dependent duration, no 75% settling, "Tutor" vs
  "Instructor"). Needs a doc-reconciliation pass before the rulebook is
  a trustworthy v0.1.0 deliverable.

### claude/education-phase3

Branch: `claude/education-phase3`
Target: `pre-release`

Education Model **Phase 3** — training cost components + the
apprenticeship pipeline (Issue #18). Implements the 2026-05-17 rulings
now canonical in `requirements/education-model.md`.

**Behaviour changes:**

- **Two distinct training pipelines (decision (a)).** Phase 2 shipped a
  Course debit for *all* tiers; Phase 3 scopes Courses to **Manager-tier
  only**. Technician-tier training is now gated by the Educator's
  **apprenticeship slot pool** (`educator.apprenticeship_programme`
  capital, +3 slots each) **and** at least one **Instructor** on the
  Education Island workforce — never by Courses. A slot is held while a
  Technician batch is in flight and frees automatically on return.
- **Profession-dependent course duration is now wired into dispatch.**
  Previously every batch returned the next season regardless of
  profession. Now: Doctor **3** seasons away, other Managers **2**,
  Nurse **1**, all Technicians **1** (`EDUCATION_SEASONS[DOCTOR]` 2→3;
  `APPRENTICESHIP_SEASONS` flat 2→1).
- **Apprenticeship settling ramp.** A returning Technician works exactly
  **one season at 75% productivity** on the home island before reaching
  100% (`Worker.settling_seasons`; new constants
  `APPRENTICESHIP_SETTLING_SEASONS=1`,
  `APPRENTICESHIP_SETTLING_EFFICIENCY=0.75`). University (Manager)
  graduates do **not** settle. Persisted in save games.
- **Fee suggestion now itemised.** The training-fee prompt suggests
  `base + food/accom + tickets + expertise` where food/accom is
  `TRAINEE_FOOD_ACCOM_PER_SEASON` (5 Dp) × trainees × course duration,
  and the Expertise term is 1 Expertise per Course per season
  (Manager-tier only — apprenticeships are not Course/Expertise gated).
  Expertise is **not** debited from inventory on training approval (it
  is burned at Course *production* time, per Phase 2) — verified by
  `test_training_approval_does_not_consume_expertise_per_attendee`.
- **Campus load.** The Educator review screen surfaces visiting trainees
  on campus (`TrainingRegistry.visiting_trainees`) as a forward-looking
  "+N Food demand" note. Phase 3 merged **after** Codex's
  `codex/sustenance-model`, so this branch also wires the seam: the
  server now calls `population_food_fish_needs(extra_residents=…)` with
  the Education Island's visiting-trainee count, so campus load actually
  raises the island's marginal Food demand and runway warnings (the §21
  balance-aware model, not the legacy Food/Fish path).

**No-ops:** `provides_apprenticeship_facility` / cross-island
sellable-apprenticeship-token never existed in code (only in the
now-reconciled requirements docs), so nothing to remove.

**Tests:** suite **293 passing** (283 baseline → 10 net new). New
`tests/test_engine/test_education_phase3.py` covers the apprenticeship
gate, slot-pool overbooking, duration-into-dispatch, and the settling
ramp. Six Phase-2 Course tests were repointed to a Manager profession
(Nurse) since Technicians are no longer Course-gated; the duration test
and the self-training return test were updated to the new durations.

**Calibration follow-up:** AI/sim Educators must now hold an
Apprenticeship Programme + an Instructor to admit Technician trainees.
This is a deliberate gate per spec; flag for the Codex sim-calibration
pass if Technician supply tightens.

### codex/sustenance-model

Branch: `codex/sustenance-model`
Target: `pre-release`

- Replaces the legacy population Food-demand path with the §21
  balance-aware model: the first 100 permanent residents are self-fed,
  while residents above that baseline create 1 unit of marginal Food
  demand each season.
- Adds the `extra_residents` seam to
  `Player.population_food_fish_needs()` so Education Phase 3 can charge
  visiting trainees against campus sustenance without mutating resident
  population.
- Adds focused model coverage for baseline demand, population growth, and
  transient residents.
- Leaves the Healthcare workforce wording unchanged because current
  merged code and rules already agree on the newer 2 Doctors + 2 Nurses +
  2 Medical Orderlies composition; the older handoff's “2 Doctors + 4
  Nurses” note is stale against present `pre-release`.

### codex/personnel-sidebar-breakdown

Branch: `codex/personnel-sidebar-breakdown`
Target: `pre-release`

- Makes the left-side Personnel summary readable as an indented multiline
  breakdown and shows per-band workers currently in training.
- Adds a Request Training deficit report so players can see which formal
  professions their island staffing plan is missing.
- Adds an “All visible skill deficits” training option that submits the
  currently requestable missing professions together while preserving
  per-profession University-capacity batches internally.

### claude/codex-brief-sustenance

Branch: `claude/codex-brief-sustenance`
Target: `pre-release`

**Docs-only.** Adds `requirements/codex-tasks/sustenance-model.md` — a
self-contained Codex hand-off to implement the §21 balance-aware
sustenance model (and the standing RULES.md Doctor-workforce fix) in
parallel with Education Phase 3. Defines the campus-load interface seam
and an explicit file-ownership split so the two tracks merge cleanly.
No code or test changes (suite unchanged at 283).

### claude/docs-phase3-reconcile

Branch: `claude/docs-phase3-reconcile`
Target: `pre-release`

**Docs-only.** No code or test changes (suite unchanged at 283).
Reconciles the requirements so Education Phase 3 is unambiguous, after
Codex's role-structuring merge changed the surrounding model.

Decisions ruled by the product owner 2026-05-17, now canonical:

- **Doctor training = 3 seasons** (was ambiguous 2-vs-4). Fixed in
  `education-model.md` duration table + `production-capacity-model.md §5`
  (and flagged for `EDUCATION_SEASONS[DOCTOR] 2→3` in Phase 3 code).
- **Courses vs apprenticeship are distinct, non-overlapping pipelines
  (decision (a))**: Manager-tier = Course-gated; Technician-tier =
  Educator apprenticeship-slot-pool + Instructor gated, **not**
  Course-gated. Phase 2 (shipped) Course-gates all tiers — Phase 3
  scopes that to Manager-tier.
- **Apprenticeship model**: 1 season away at Education, then **75%
  productivity for exactly one season** on the home island, then 100%.
  Supersedes both the old "home-island Apprenticeship Facility" idea
  and `production-capacity-model.md §8`'s "stays home / no loss" model.
- **Dropped**: `provides_apprenticeship_facility` capital flag; the
  in-house cross-island apprenticeship sellable-token mechanic.
- **1 Expertise per Course per season** (per Course, not per trainee).
- **Campus load** must use the new balance-aware sustenance model
  (`production-capacity-model.md §21`), not the legacy Food/Fish path.

Files touched: `requirements/education-model.md` (Phase 1/2 marked done,
Phase 3 promoted + spec'd, training-pipelines split, duration table,
open-questions closed), `requirements/production-capacity-model.md`
(§5 Doctor=3, §8 now points to education-model.md as canonical),
`requirements/medical-laboratory.md` (Ecologist/Actuary durations align
to the apprenticeship model), `TODO.md` (Phase 2 ✅, Phase 3 rewritten).

### claude/education-phase2

Branch: `claude/education-phase2`
Target: `pre-release`
Implements: `requirements/education-model.md` Phase 2 + GitHub #22 (market UX)

Rebased onto `pre-release` after Codex's `codex/role-structuring` split
landed (`f0c0960`). Both bodies of work came from the same combined
safety snapshot `fd519e0`; this branch is exactly the Claude-owned delta
(`git diff f0c0960 fd519e0`), re-applied cleanly in the separate
`island-traders-claude` worktree.

#### Education Model — Phase 2 (Courses + Instructor)

- **New resource `Courses`** (`ResourceType.COURSES`, base price 25 Dp) —
  classroom slots produced by the Education Island.
- **New Educator recipe**: Courses production consumes `Expertise` as an
  input; Patents production now also consumes a small Expertise input.
- **`Tutor` → `Instructor` consolidation**: `Profession.TUTOR` renamed to
  `Profession.INSTRUCTOR` (canonical Technician on the Education Island);
  "Tutor" kept as a display-title alias in `BAND_TITLES`.
- **Course-gated training**: `_action_request_training` /
  `_approve_training_request` / AI educator / self-training now debit
  `ceil(trainees / MAX_CLASS_SIZE_PER_COURSE)` Courses on approval
  (`MAX_CLASS_SIZE_PER_COURSE = 12`). No Courses → request stays pending.
  Course availability is peeked *before* air tickets are consumed so a
  shortfall can't burn the Educator's PassengerSeats.
- **Starting state**: Educator workforce 4 → 8 (4 Professors + 4
  Instructors); starting inventory gains 6 Expertise + 5 Courses.

#### GitHub #22 — Market UX

- New generic `choose_option(prompt, options)` IO prompt (named choice
  buttons) used for product selection — replaces the numeric-index
  picker.
- `ask_dollop_amount` gained a `prefill` argument; market **sell** prompt
  pre-fills the best bid, market **buy** modal pre-fills the ask, with
  bid-vs-buy made visually explicit.
- Market board popup rendered as a clean grid.
- Immediate-fill on a bid that crosses an existing ask now logs the fill.

#### Tests

- New `tests/test_engine/test_education_courses.py`.
- Updated `test_educator_self_training.py`, `test_training_review.py`,
  `test_training_menu.py`, `test_profession_bands.py`,
  `test_market_prefill.py` for Courses + Instructor + prefill.
- **Full suite: 283 passed** in the Claude worktree on top of
  `pre-release` @ `f0c0960` (Codex's 271 + this delta = 283 — reconciles
  exactly with the original combined `fd519e0`).

---

### codex/ai-trading

Branch: `codex/ai-trading`
Target: `pre-release`
Implements: `requirements/codex-tasks/ai-trading.md`

#### Player-Facing Changes

- AI islands now place standing bids when they are short of required production inputs instead of waiting for humans to rescue the supply chain.
- AI islands review pending peer deals with market-aware valuation and accept profitable deals while rejecting value-destroying ones.
- AI islands can capture visible bid/ask arbitrage when the market already exposes a profitable spread.
- Transporter AI now lists produced `PassengerSeats` for sale; previously those seats were produced but omitted from AI selling because the stale role metadata only advertised `Freight`.

#### Before / After Market Activity

- Before: an input-starved Farmer with 0 `FarmMachinery` placed no standing bid; after: it posts a market bid for the missing machinery on its turn.
- Before: Transporter AI produced `PassengerSeats` but did not list them; after: a post-production regression test confirms a standing `PassengerSeats` offer exists.
- Before: AI deal acceptance used only formula prices in the human-turn path; after: AI-targeted deals use latest accepted cash/unit deal price, then current best offer, then formula price as fallback.

#### Known Follow-Ups

- The task brief asks for trade-row verification in the simulation price-history CSV, but the current simulation exporter records seasonal price snapshots only, not executed-trade rows. I left that exporter untouched to stay inside the agreed file scope.
- `Transporter` role metadata still lists only `Freight` in `models/role.py` even though production constants also emit `PassengerSeats`; this branch works around that by selling actual produced resources, but the metadata should be reconciled separately.
- The 1000-game AI-only run still shows structural balance drift once active trading is enabled (Banker 68.0% wins, Educator and Doctor 0.0%); balancing is intentionally left for the separate calibration workstream.

#### Verification

- Test suite: `265 passed` (baseline 262, +3 AI-trading regressions).
- Simulation: `.venv/bin/python -m island_traders.simulation.runner --games 1000 --seed 42 --output simulation_results/ai_trading`.

---

### claude/education-phase1-rename

Branch: `claude/education-phase1-rename`
Target: `pre-release`
Implements: `requirements/education-model.md` — Phase 1 (mechanical rename)

**Pure rename — zero behavioural change.** Test suite unchanged at
**262 passed** (same count and same tests as before).

`ResourceType.KNOWLEDGE` (`"Knowledge"`) → `ResourceType.EXPERTISE`
(`"Expertise"`) everywhere:

- `models/resource.py` — enum member + value
- `models/role.py` — Educator produces / Banker & Doctor need Expertise
- `constants.py` — `BASE_PRICES`, `BASE_PRODUCTION`, `PRODUCTION_INPUTS`,
  `STARTING_INVENTORY`, comments; dead `TRAINING_KNOWLEDGE_COST` →
  `TRAINING_EXPERTISE_COST`
- `constants_capacity.py` — Educator recipe `output="Expertise"`, capacity
  effects, input-relief, descriptions
- `server/app.py` — `ROLE_INFO` produce/needs display strings
- `config/event_charts.yaml` — price-shock resource keys
- `RULES.md`, `README.md` — all player-facing references
- `board/game_board.html` — visible label text (internal DOM id
  `res-knowledge` and JS `gameState.knowledge` left as-is; that file is a
  standalone demo, not the live dashboard)
- `tests/test_engine/test_production.py` — assertions

Phase 2 (add `Courses` resource, Educator produces Courses by consuming
Expertise, Course-gated training, `Profession.INSTRUCTOR`, rebalanced
Education starting workforce) remains a separate future branch per the
spec.

#### Verification

- Test suite: 262 passed (unchanged — confirms pure rename).
- Smoke-tested: enum has `EXPERTISE` and no `KNOWLEDGE`; server imports;
  `island-traders-export` printables contain no "Knowledge".

---

### claude/issue-22-market-ux

Branch: `claude/issue-22-market-ux`
Target: `pre-release`
Closes: GitHub #22

Four market UI/UX fixes from the 2026-05-15 playtest:

1. **Market Prices popup as a grid** — `renderMarketTable` now uses a new
   `.market-grid` style (gridlined, tabular-numeric, right-aligned,
   zebra-striped, colour-coded bid/ask) in the board popup.  The compact
   side-panel mini-table is unchanged.
2. **Bid vs Buy clarity** — the Market Buy popup now has a legend
   ("⬤ Buy Now" = immediate at the ask; "⬤ Place Bid" = limit order at
   your price), grouped headers, gridline separators, tinted columns
   (gold for buy-now, green for place-bid), and tooltips on each input.
3. **Buying prefill** — the new-bid price field is pre-filled with the
   current ask (when one exists) instead of the formula price, so a
   buyer placing a bid starts from the price that would clear.
4. **Selling prefill** — the asking-price prompt is pre-filled with the
   best bid (when one exists).  New optional `prefill` parameter on
   `ask_dollop_amount` across all three IO adapters; the WS message
   carries `prefill` and the dashboard input uses it as its initial
   value with a hint line.

#### Tests

- 7 new tests in `tests/test_engine/test_market_prefill.py`: base
  adapter honours/overrides prefill, FakeIOAdapter accepts the new
  kwarg, WS message carries `prefill`, and `_action_market_sell`
  prefills the asking price with the best bid.

#### Verification

- Test suite: 262 passed (was 255, +7).  Existing test IO adapters that
  override `ask_dollop_amount` with the old 2-arg signature are
  unaffected (they aren't on the market-sell path).

---

### claude/ux-quickwins-20-21

Branch: `claude/ux-quickwins-20-21`
Target: `pre-release`
Closes: GitHub #20, #21

#### #21 — Product selection by name, not index

Producing used to print a numbered list then ask via `choose_quantity`
(a numeric input box on the dashboard).  Players had to read the list and
type a number.

New generic **`choose_option(prompt, options)`** prompt added to all three
IO adapters (base terminal `IOAdapter`, `FakeIOAdapter`, and
`WebSocketIOAdapter`).  `options` is `[{"value", "label"}, …]`; it returns
the chosen `value`.  The dashboard renders it as labelled buttons (reuses
the existing option picker — new `choose_option` WS message case).

`_action_produce` and `_choose_product_line_human` now use it, so the
player picks **"Farmer: Food — up to N now"** or
**"Heavy Machinery — Inputs: … → …"** as a button, never an index.

#### #20 — Personnel counts on the left panel

New **"Personnel"** stat row in the left info panel showing the
trained/untrained breakdown:
`N trained (X Mgr · Y Tech) · Z untrained`.  The "Workers" row label
clarified to "Workers (active/total)".  Server payload already exposed
`workforce_bands`; this is UI-only.

#### Tests

- 9 new tests in `tests/test_engine/test_choose_option.py`:
  base terminal picker (selection + reprompt), FakeIOAdapter default,
  WS round-trip / timeout-first / cancel-sentinel-raises / unknown-value
  fallback, and an integration test asserting `_action_produce` calls
  `choose_option` with human labels.

#### Verification

- Test suite: 255 passed (was 246, +9 new).  No regressions — existing
  production tests still pass (FakeIOAdapter.choose_option returns the
  first option, same effective behaviour as the old choose_quantity=min).

---

### claude/issues-2026-05-15-synthesis

Branch: `claude/issues-2026-05-15-synthesis`
Target: `pre-release`

Docs-only branch.  Synthesises **9 new GitHub Issues** (#18–#26) posted
during the 2026-05-15 playtest into specs and TODO entries.  No code or
test changes.

#### New spec: `requirements/medical-laboratory.md`

Roots three interconnected issues (#19, #25, #26) under a single coherent
spec:

1. **#26 — Medical & Laboratory Island** — Doctor role keeps its
   internal identifier but display label becomes "Medical & Laboratory";
   adds a new tradeable output `LaboratoryTests` (base price ≈ 35 Dp).
2. **#25 — Ecologist profession** — new Technician profession required
   to certify capital-equipment installations.  Each install needs an
   Ecologist on staff + 1 Environmental Assessment Lab Test.
3. **#19 — Doctor-certified insurance** — Doctors issue Lab Tests
   ("Health Certificates") that halve insurance premiums; insured
   workers don't lose productivity from injury; death benefits pay
   replacement training cost.

Lab Tests are the glue — same enum value, four different narrative
"types":

| Consumer | Test type | Why |
|---|---|---|
| Mining | Metal Assay | Required to smelt Ore + Oil → Metal |
| Farmer | Soil Analysis | Seasonal production gate |
| Any island installing capital | Environmental Assessment | Required for activation |
| Banking | Health Certificate | Halves insurance premium |

Five-phase implementation plan (A through E) keeps each piece
independently mergeable.

#### `requirements/education-model.md` extended with Issue #18

New "Training cost components" section formalises the cost breakdown:

* Profession-dependent **course duration** (Doctor=4, most Managers=2,
  Nurse=1, Technicians=1 with apprenticeship facility or 2 without)
* **Expertise consumption = 1 unit per trainee per season** (so a
  Doctor batch of 2 trainees consumes 4×2 = 8 Expertise)
* **Food & accommodation** cost layered into the suggested fee
* **Apprenticeship Facility** — a new capital item flag
  (`provides_apprenticeship_facility: bool`) reduces Technician training
  to 1 season

Duration table covering all professions including the new Ecologist and
Actuary entries from `medical-laboratory.md`.

#### TODO.md sections added / updated

* **New section:** `Medical & Laboratory Island` with phases A–E
  spanning #19, #25, #26
* **Education Model Refinement** got a new Phase 3 covering #18
* **Dashboard & UX** got 4 new entries: #20 (personnel counts), #21
  (product names not indexes), #22 (market UX polish), #23 (bolder
  logo + island popup)
* Two ticked off as already done in earlier merges:
  - `Purchase Capital` → `Purchase Equipment` (✓)
  - Personnel shortages named by profession (✓)

#### Issue #24 (Actuary)

Captured in `medical-laboratory.md §4` (Banking gets a new Actuary
Technician profession required to underwrite insurance policies).
Cross-references this work to the Banker institutional pool in
`island-ledger.md`.

#### Verification

- No code changes.  Test suite unchanged at 246 passed.

---

### claude/ux-polish-2026-05-15

Branch: `claude/ux-polish-2026-05-15`
Target: `pre-release`

Two small UX wins from the 2026-05-15 playtest inbox.

#### "Purchase Capital" → "Purchase Equipment" label

Pure display-label change.  Internal identifier
(`TurnAction.PURCHASE_CAPITAL`, value `"purchase_capital"`) is unchanged
— saved games, server JSON, and existing tests all keep working.

Implementation: new `action_label()` helper + `ACTION_LABEL_OVERRIDES`
dict in `cli/prompts.py`, used by both the CLI `IOAdapter` and the
WebSocket `WebSocketIOAdapter` so both menus render the same label.

#### Workforce shortage messages use profession titles, not band names

Constraint popup used to say *"+2 Technicians"* — not actionable.  Now
it says *"+2 Flight Crew"* (for the Transporter), *"+2 Farming
Technician"* (for the Farmer), *"+2 Banking Analyst"* (for the Banker),
etc.

Implementation: server-side `_player_capacity` now uses
`primary_title(recipe.role, band)` from `models/profession.py` when
building the `workforce_short` dict, so the dashboard receives
profession names ready to render.  Dashboard rendering didn't need to
change — it just prints the keys it gets.

#### Tests

- 4 new tests in `tests/test_engine/test_action_labels.py`:
  * `Purchase Capital` displays as `Purchase Equipment`
  * Unmapped actions still use default title-casing
  * Internal enum name + value are unchanged
  * Every override key points at a real `TurnAction` value
- 2 new tests in `tests/test_server/test_workforce_shortage_messages.py`:
  * Transporter shortages name Logistics Manager / Flight Crew /
    Seaman / Warehouse Manager / Stevedore — never generic bands
  * Banker shortages name Banker / Banking Analyst / Banking Clerk /
    Receptionist — never generic bands
- Updated `tests/test_server/test_investing.py` (1 assertion) to expect
  the new profession-titled keys instead of `"Technician"` / `"Worker"`.

#### Verification

- Test suite: 246 passed (was 240, +6 new).

---

### claude/educator-self-training

Branch: `claude/educator-self-training`
Target: `pre-release`

Bug fix from the 2026-05-15 playtest: the Education Island couldn't train
its own workforce because `_action_request_training` excluded the player
from the educator picker list, then bailed with "No Educator player in
this game."

#### Fix

In `_action_request_training`, detect when the requester is the Educator
(`is_self_training = any(r.name == "Educator" for r in player.roles)`)
and route through a short-circuit branch that:

* Sets `educator = player` (skips the educator-choice prompt)
* Sets `dollops_educator = 0.0` (no fee — skips the prompt entirely)
* Sets `transport_mode = "self_training"` (new mode; bypasses the
  PassengerSeats / air-ticket consumption)
* After submitting the request, **auto-approves and dispatches**
  immediately — the workers go into the on-island programme this
  season and return next season.

University capacity is still consumed for the chosen profession, so
self-training cannot bypass the annual / seasonal caps.

#### Files touched

- `island_traders/engine/turn.py` — self-training branch in
  `_action_request_training`
- `island_traders/models/training.py` — `describe()` now handles the
  new `"self_training"` transport mode

#### Tests

- 5 new tests in `tests/test_engine/test_educator_self_training.py`:
  * Skips the educator picker and fee prompt
  * Consumes zero PassengerSeats; dispatches immediately
  * Returns after exactly one season
  * Still counts against University capacity (no cap bypass)
  * Works in a solo / single-Educator scenario

#### Verification

- Test suite: 240 passed (was 235, +5 new).

---

### claude/edu-spec-and-codex-brief

Branch: `claude/edu-spec-and-codex-brief`
Target: `pre-release`

Docs-only branch.  Two updates following the 2026-05-15 inbox-processing
session and the product decisions that came out of it.

#### `requirements/education-model.md` updates

* **Patents now consume Expertise as an input** (~0.25 Expertise per
  Patent) on top of Laboratory Equipment + Manager capacity.
* **Class-size rule:** 1 Course covers a class of up to **12 students**.
  When a training batch exceeds 12 trainees the system auto-splits across
  multiple Courses (debiting `ceil(trainees/12)`).
* **Self-training Course consumption** clarified: yes, self-training
  still debits a Course even though it skips fees + transport.  The
  12-student class size applies, so multiple workers on the Education
  Island can be trained on a single Course.
* **Tutor → Instructor consolidation:** Profession.TUTOR is renamed to
  Profession.INSTRUCTOR.  The clean Manager/Technician pairing is
  Professor / Instructor.  "Tutor" can stay as a display title alias.
* New constant flagged: `MAX_CLASS_SIZE_PER_COURSE = 12`.
* Open-questions section updated to mark items 1, 3, and 4 as decided.

#### `requirements/codex-tasks/ai-trading.md` (new)

Self-contained Codex task brief for the next parallel work item: making
heuristic AI islands proactively participate in the market (place bids,
list offers, evaluate cross-island arbitrage).  Mirrors the existing
`codex-tasks/sim-calibration.md` format — goal, scope, in/out-of-scope
files, acceptance criteria, hand-off mechanics.

Specific scoped behaviours:

1. List most fresh output for sale each season
2. Bid on missing inputs
3. **Transporter AI must list Passenger Seats** (currently silently
   blocking training)
4. Cross-island arbitrage / opportunistic deals
5. Switch deal valuation to last-deal / best-offer (TODO item)

#### Verification

- No code changes.  Test suite unchanged.

---

### claude/inbox-2026-05-15

Branch: `claude/inbox-2026-05-15`
Target: `pre-release`

Docs-only branch.  Processed the 8 playtest items captured in
`requirements/inbox.md` on 2026-05-15.  No code or test changes.

#### What landed where

| Item | Destination |
|---|---|
| Educator self-training (no fee / no transport / 1 season) | `TODO.md` Bugs section |
| Rename `Purchase Capital` → `Purchase Equipment` | `TODO.md` Dashboard & UX |
| AI live-play economy / automated trading | `TODO.md` new "AI Trading Behaviour" section (proposed next Codex task) |
| Personnel shortages by specialty | `TODO.md` Dashboard & UX |
| Food: base population self-fed | `requirements/production-capacity-model.md §21` (new) + `TODO.md` |
| Cancel open bids / offers + partial fills | `TODO.md` new "Market & Trading" section |
| Education refinement: Knowledge → Expertise, +Courses, +Instructors | **New spec** `requirements/education-model.md` + `TODO.md` new "Education Model Refinement" section |
| Near-match auto-clearing (±1 Dp / ±3%) | `TODO.md` "Market & Trading" |
| Item valuation: last-deal / lower-of-cost-or-market | `TODO.md` Financial Model |

#### Highlight: Education model refinement is the largest piece

`requirements/education-model.md` (new) lays out a two-phase migration:

* **Phase 1 (mechanical):** rename `ResourceType.KNOWLEDGE` →
  `ResourceType.EXPERTISE` and display label "Expertise" everywhere.  Pure
  cascade — zero behavioural change.  ~40-file touch surface.
* **Phase 2 (gameplay):** add `ResourceType.COURSES` (new tradable);
  Education produces Courses by consuming Expertise; training requests
  debit Courses on approval; add `Profession.INSTRUCTOR` (consolidating
  with Tutor is the recommended open question); rebalance Education
  starting workforce to 4 Professors + 4 Instructors.

The spec flags open questions (Tutor vs Instructor consolidation, Course
trade-ability, self-training Course consumption) for product-side
decisions before implementation starts.

#### Highlight: AI Trading Behaviour is the next Codex candidate

The playtest reported that AI islands behave too passively after
production — humans have to push trades on them.  The new "AI Trading
Behaviour" TODO section enumerates the concrete missing behaviours
(placing bids, listing offers, cross-island arbitrage, deal valuation
based on last-deal price).  This is well-scoped, lives mostly in
`engine/ai.py`, and doesn't overlap with Claude's current workstreams —
exactly the kind of task Codex can pick up on a `codex/ai-trading`
branch.

#### Verification

- No code changes.  Test suite unchanged.

---

### claude/banker-rebalance

Branch: `claude/banker-rebalance`
Target: `pre-release`

Banker is a **service business**, not a commodity producer.  Income comes
from loan interest spread + insurance premiums (and, future, deal
guarantees, brokerage, and project finance).  This branch removes the
`Finance` commodity from the production loop — the root cause Codex
identified for the 75.6% Banker win rate.

#### What changed

- **Banker BASE_PRODUCTION is now empty** (was: 30 Finance/season).  The
  Banker no longer "produces" anything on the market.  Banker income comes
  exclusively from the existing loan ledger (interest at the quoted rate)
  and from insurance premiums sold via the existing `SELL_INSURANCE`
  action.
- **Banker PRODUCTION_INPUTS is now empty** (was: 1 Knowledge).  Banking
  doesn't gate on per-season inputs.  Knowledge still useful for training
  workers, but isn't consumed by an idle Produce action.
- **Educator PRODUCTION_INPUTS dropped Finance** (was: Lab Equipment +
  Finance, now: Lab Equipment).  No more "operating budget paid in a
  tradeable commodity".
- **STARTING_INVENTORY:** Banker no longer starts with 2 Finance to sell;
  Educator no longer starts with 2 Finance to spend.
- **`models/role.py`:** Banker `produces=()`, no longer `(FINANCE,)`.
  Educator `needs=(LABORATORY_EQUIPMENT,)`.  Banker short_name renamed
  from "Finance" to "Banking" to reflect the service-focus.
- **`constants_capacity.py`:**
  * Removed the `Banker → Finance` production recipe.
  * Updated Banker capital items (Vault, Trading Floor) to express
    capacity in `Loans` / `InsurancePolicies` instead of `Finance`.
  * Removed `Finance` from Educator recipe inputs.
- **`server/app.py` ROLE_INFO** updated: Banker produces "Loans,
  Insurance" not "Finance"; Educator needs "Laboratory Equipment" only.
- **`RULES.md`** updated: Seven Islands table, Production Inputs table,
  Base Prices table, physical contents list, and Quick Reference now
  reflect Banker as a service business with no Finance commodity.

#### What didn't change

- The `ResourceType.FINANCE` enum still exists — back-compat for any
  saved games or external references.  No code now produces or consumes
  it during normal play.
- The existing loan engine (`models/loan.py`, banker_quote_rate, etc.)
  is unchanged — that was already the right shape.
- The Insurance products (Life + Medical, with manage/cancel/refund
  flows) are unchanged.

#### Simulation impact (500 games × 4 seeds {42, 1, 7, 99})

| Role         | Before       | After (mean) |
|--------------|-------------:|-------------:|
| Banker       | **75.0%**    | **1.1%**     |
| Transporter  | 23.6%        | 95.2%        |
| Farmer       | 1.4%         | 3.8%         |
| Miner        | 0.0%         | 0.0%         |
| Educator     | 0.0%         | 0.0%         |
| Manufacturer | 0.0%         | 0.0%         |
| Doctor       | 0.0%         | 0.0%         |

Banker dominance is **eliminated** — exactly the goal of this fix.

#### Honest caveats

This is a *targeted* fix for the Banker exploit.  It does **not** balance
the overall game.  The post-fix distribution surfaces a separate
structural problem: **Transporter now dominates at ~95%** (already over-
monetized; with Banker out, Transporter sweeps).  Roles at 0% wins still
need their own structural look.

Two known follow-ups, both out of scope for this branch:

1. **Banker AI strategy** — the heuristic AI doesn't yet proactively
   offer/seek loans, so the Banker has almost no income in AI-only
   simulations.  Real multiplayer should be different (humans will seek
   loans).  Once the Island Ledger refactor lands and the institutional
   cash pool + deposit accounts exist, the Banker's economics will be
   meaningfully different — re-baseline at that point.
2. **Transporter economy** — `damage_seasons` semantics and AI market
   behaviour need separate work (Codex's diagnostics noted this).

#### Future Banker revenue streams (TBD, on the roadmap)

- **Deal guarantees** — Banker charges a fee to guarantee a P2P deal so
  the counterparty is paid even if the proposer defaults
- **Brokerage** — Banker negotiates deals between two other islands for
  a commission
- **Project finance** — when project-based capital expenditures are
  introduced, Banker provides structured loans for specific projects
- **Deal insurance** — premium-priced cover for a single transaction
  (vs. the seasonal Life / Medical policies that exist today)

#### Verification

- Test suite: 235 passed (unchanged count; 3 Banker-production tests
  rewritten to assert no production rather than asserting on Finance flow).
- Baseline simulation (`--games 500 --seed 42`) vs post-fix simulation
  recorded in the table above.

---

### codex/sim-calibration

Branch: `codex/sim-calibration`
Target: `pre-release`

Simulation calibration iteration for the current `pre-release` economy.
This is not a final balance certification; further calibration iterations are
expected before the next major release is promoted from `pre-release` to
`main`.

#### Baseline

Ran:

```bash
.venv/bin/python -m island_traders.simulation.runner --games 1000 --seed 42 --output /tmp/island-traders-baseline
```

Current win rates:

| Role | Wins | Win rate | Avg wealth |
|---|---:|---:|---:|
| Farmer | 12 | 1.2% | 112.1 Dp |
| Miner | 0 | 0.0% | 49.9 Dp |
| Transporter | 232 | 23.2% | 993.3 Dp |
| Educator | 0 | 0.0% | 87.2 Dp |
| Banker | 756 | 75.6% | 3770.6 Dp |
| Manufacturer | 0 | 0.0% | 131.1 Dp |
| Doctor | 0 | 0.0% | 89.1 Dp |

#### Diagnosis

Event-chart tuning alone is not enough to satisfy the calibration target
(roughly 14% wins per role, with no role below 8% or above 22%).
Sensitivity runs with extreme Banker / Transporter outage charts and boosted
underdog yield modifiers still left Banker and Transporter structurally
dominant, while Miner, Educator, and Doctor remained near 0%.

The biggest blockers appear structural rather than event-probability driven:

- Banker and Transporter generate high-value inventory from the current
  AI-only economy loop and can remain competitive even under very harsh event
  charts.
- Several low-win roles are wealth-capped by input availability, turn-order
  market flow, and resource valuation; multiplying their event yields did not
  reliably turn into final wealth.
- `damage_seasons` on outage events converts future turns into
  `Infrastructure Damage` at 50% yield rather than extending the outage, so
  "harsher" disaster tuning can accidentally preserve meaningful production.

#### Runner tooling

Added `--seeds` to the simulation runner so calibration can run comparable
multi-seed batches without shell loops:

```bash
.venv/bin/python -m island_traders.simulation.runner --games 1000 --seeds 42,1,7,99
```

Each seed writes its own CSV pair using the configured output prefix plus
`_seed_<seed>`, and stdout includes a compact cross-seed win-rate summary.

#### Known follow-ups

Coordinate before changing out-of-scope balance surfaces. Likely follow-up
work needs to address the AI-only economy and/or production constants before
event chart weights can be meaningfully calibrated:

- Review Banker personal wealth from Finance production versus the planned
  institutional cash-pool model.
- Review Transporter output valuation and AI market behavior.
- Add richer simulation diagnostics for per-role production, input shortages,
  sales, retained inventory value, and insurance / loan income.

---

### claude/fix-playtest-bugs

Branch: `claude/fix-playtest-bugs`
Target: `pre-release`

Three bugs surfaced during live playtesting on `pre-release`.

#### Bug 1 — Post-auction guarantee UI hung after purchase

After the islandless buyer clicked Buy on an AI extra, the guarantee panel
hid but the user stayed on the auction screen.  The investing screen never
opened automatically.  Eventually the game proceeded (the server had moved
on) but the player was left staring at a blank screen until they refreshed.

**Fix:** `onIslandGuaranteeComplete` now proactively switches the user to
the investing screen.  If `investData` has already arrived it renders
immediately; otherwise the existing `investing_start` handler renders when
the data lands.

#### Bug 2 — Training menu lost Banker (and other) options too eagerly

Two issues:
1. The new technician professions added with the workforce baseline rule
   (Logistics Manager, Flight Crew, Seaman, Warehouse Manager, Lecturer,
   Tutor, Banking Analyst, Banking Clerk, Medical Orderly) had no entries
   in `UNIVERSITY_CAPACITY`, so they didn't appear in the Request Training
   menu at all.
2. When a profession exhausted its annual cap the menu silently dropped it,
   so the user couldn't see WHY their option had disappeared (felt buggy).

**Fix:**
- Extended `UNIVERSITY_CAPACITY` with caps for all 9 new professions
  (reasonable defaults: Manager-tier 2/yr, Technician-tier 4-8/yr).
- `_action_request_training` now prints exhausted professions with a `FULL
  — X/Y already requested this year` line so the user understands the
  capacity state.

#### Bug 3 — Cancel button still executed a partial action

Pressing Cancel on a prompt chain (e.g. Request Training) caused the engine
to fall back to default values (`min_qty`, `available[0]`, etc.).  Result:
"I pressed Cancel and it still trained 1 doctor."

**Fix:** Plumbed an explicit cancel signal end-to-end:
- New `cli/signals.py` with `CANCEL_SENTINEL` constant and
  `ActionCancelled` exception (lives in its own module to avoid the
  circular import between `cli/prompts` and `engine/turn`).
- Client `cancelDlg()` now sends `CANCEL_SENTINEL` instead of `null`.  Two
  other "treat as cancel" spots in the dashboard (market-buy modal cancel,
  empty market-buy submit) updated to match.
- `WebSocketIOAdapter` checks the sentinel at the top of every prompt
  method (`_check_cancel`) and raises `ActionCancelled`.  A plain `None`
  response (timeout / interrupt) still falls back to the default — only an
  explicit Cancel raises.
- `engine/turn.py` main action loop catches `ActionCancelled` and prints
  "Action cancelled" — no partial execution.

#### Tests

- 9 new tests in `tests/test_engine/test_action_cancellation.py`:
  * Each of the 7 WS-adapter prompt methods raises `ActionCancelled` on the
    sentinel.
  * `choose_quantity` returns the min on plain `None` (timeout fallback
    preserved, NOT cancelled).
  * End-to-end-ish: a cancelling IO in the training action handler results
    in no training request being created.
- 5 new tests in `tests/test_engine/test_training_menu.py`:
  * All 9 new professions have `UNIVERSITY_CAPACITY` entries.
  * Every Profession (other than Unskilled) is trainable.
  * `capacity_summary` includes all professions.
  * Banker cap is ≥ 2.
  * Request Training menu shows exhausted professions as `FULL`.

#### Verification

- Test suite: `233 passed` (up from 219).

---

### claude/rules-md-refresh

Branch: `claude/rules-md-refresh`
Target: `pre-release`

Documentation-only refresh of `RULES.md` to match the current online rules
(no code changes; tests unchanged at 219 passing).

#### What was updated

- **Seven Islands table** — produces/needs columns refreshed for Metal,
  Farm Machinery, Mining Equipment, Lab Equipment, Patents, Passenger Seats,
  and Insurance/Loans as Banker outputs.
- **Starting Conditions table** — Dollops corrected to 700 (auction budget);
  starting workforce updated to match `STARTING_WORKERS_BY_PROFESSION`,
  including the new transport professions (Logistics Manager / Flight Crew /
  Seaman / Warehouse Manager) and Educator / Banker / Doctor technician
  backfills (Tutors, Banking Analyst & Clerk, Medical Orderlies).
- **Your Turn actions table** — added Purchase Capital, Apply Patent, Sell /
  Buy / Manage Insurance, Offer / Take / Roll Over Loan, View Loans.  Added
  a callout box on simultaneous play, pre-season window, and host Pause.
- **Production inputs table** — updated to current values (Farm Machinery,
  Mining Equipment, Lab Equipment, Metal flow into Manufacturer, etc.).
- **Base Prices table** — added Metal, Farm Machinery, Mining Equipment,
  Medical Devices, Transport Equipment, Lab Equipment, Passenger Seats,
  Patents.
- **Worker Professions table** — full refresh listing every profession with
  its band (Manager / Technician / Worker), with new entries in bold.
- **Training Capacity table** — bands added.  *(The "future balance pass"
  gap this section originally noted was subsequently closed by
  `claude/fix-playtest-bugs`, which added `UNIVERSITY_CAPACITY` entries
  for all 9 new professions.)*

#### New sections added

- **Setting Up: Auction, Island Guarantee, and Investing** (between
  Starting Conditions and Structure of Play) — covers the sealed-bid role
  auction, the §19.1 post-auction human island guarantee (with pricing
  formula explainer), and the Investing Phase.
- **Loans** (between Vaccines and Event Charts) — bullet-bond mechanics,
  borrowing flow with banker quote rate, repayment / default, and Roll Over.
- **Insurance** — Life and Medical products, Buy/Sell/Manage flows,
  pro-rata cancellation refund formula, high-hazard role flag.
- **Capital Equipment** subsection (under Production) — outright purchase,
  mid-game Purchase Capital action, 2-season delivery delay for complex
  items, 5-year straight-line depreciation, future lease pointer.
- **Patents** subsection — Apply Patent action, –20% input cost per Patent,
  cap 3 per output.

#### Misc

- Physical Contents list updated with the current resource and equipment
  token set, band-aware worker tokens, and loan/insurance contract cards.
- Export command updated to the installed `island-traders-export` entry
  point.
- Quick Reference fully refreshed (turn actions, setup phases, formulae,
  resources, capital-equipment lines, workforce baseline, loan-rate
  formula, insurance refund formula).

---

### claude/post-auction-human-guarantee

Branch: `claude/post-auction-human-guarantee`
Target: `pre-release`
Implements: `requirements/production-capacity-model.md §19.1`

#### Player-Facing Changes

- **Post-auction human island guarantee.** If a human player ends the auction
  with no island AND at least one AI player won two or more roles, a new
  guarantee phase opens before Investing.  Islandless humans are walked
  through sequentially (in join order) and offered every AI-extra island to
  take, at a price set by the §19.1 formula.  Each buyer may accept one or
  decline all.
- The islandless buyer sees a panel listing every eligible AI-extra island
  with its seller, the price they'd pay, and a tooltip explaining how the
  price was calculated.  Spectators see "X is choosing whether to take an
  AI island…" while the buyer decides.
- After the human takes control of an AI island, the island state (inventory,
  workforce, etc.) is preserved; the human can review and override the AI's
  default Investing-Phase orders in the next phase.

#### Pricing (§19.1)

Final price = `max(formula, floor)` where:
  * `floor` = 20% of buyer's current cash
  * `formula` depends on `ratio = ai_paid / starting_budget`:
    - `ratio in [11%, 15%]` (inclusive) → `2 × ai_paid`
    - `ratio > 15%`                     → `1.05 × ai_paid`
    - `ratio < 11%`                     → `ai_paid`

#### Server-Side

- New `IslandGuaranteeState` dataclass + `GameRoom.guarantee` field.
- New `room.status = "guarantee"` between `auction` and `investing`.
- New `room.ai_role_prices` captures per-role winning bid amounts so the
  guarantee phase can quote prices.
- New `compute_guarantee_price()` pure helper (testable in isolation).
- New GameManager methods: `_should_run_island_guarantee`, `_build_offers_for`,
  `_start_island_guarantee`, `_advance_island_guarantee`, `_finalize_island_guarantee`,
  `submit_guarantee_choice`, plus `_guarantee_timer` (90s per buyer, default).
- `_resolve_auction` now routes to the guarantee phase when conditions are met,
  otherwise straight to investing as before.
- WS protocol: `island_guarantee_state` (broadcast on entry / on each buyer's
  turn), `guarantee_choice` (client → server `{accept, role}`),
  `guarantee_ack`, `island_guarantee_resolved` (per buyer outcome),
  `island_guarantee_complete` (phase finished).
- Reconnect catch-up: clients connecting mid-guarantee receive the current
  guarantee state immediately.

#### UI

- New "🏝 Island Guarantee" panel on the auction screen (appears after
  auction-result-overlay is hidden).  Per-offer row with role, seller name,
  price, breakdown line ("seller paid X / floor / band"), and Buy / Decline
  buttons.  Unaffordable offers are dimmed.
- "How is the price calculated?" inline explainer.

#### Tests

- 20 new tests in `tests/test_server/test_island_guarantee.py` covering:
  * All three price bands + boundary inclusivity at 11% and 15%
  * Floor-dominates-formula case
  * Degenerate zero-starting-wealth input
  * Trigger condition true/false
  * Offer list building (all AI extras shown, affordability flags)
  * Phase entry sets state correctly
  * Accept path: role transfer, deductions updated
  * Decline path: queue advances
  * Not-your-turn rejection
  * Unknown-role rejection
  * Sequential buyers with two-AI scenarios
  * Sole-AI-loses-extras-after-one-sale skip path

#### Verification

- Test suite: `219 passed` (up from 199 baseline).

---

### claude/workforce-min-manager-tech

Branch: `claude/workforce-min-manager-tech`
Target: `pre-release`

#### Rules / Balance Changes

- **Workforce baseline rule:** every island now starts with at least 1 Manager
  and 2 Technicians.  Workforce totals adjusted where needed:
  * Transporter: 4 (was 4) — composition replaced
  * Educator: 4 (was 3) — bumped to fit the new technicians
  * Banker: 4 (was 3) — bumped to fit the new technicians
  * Doctor: 6 (unchanged) — mix changed (2 Doctors + 2 Nurses + 2 Medical Orderlies)

#### New Professions

- **Transporter:**
  * `LogisticsManager` (Manager) — strategic transport leadership
  * `FlightCrew` (Technician) — air freight ops
  * `Seaman` (Technician) — sea freight ops
  * `WarehouseManager` (Technician — ground-ops supervisor; named "Manager"
    by industry convention but classified as Technician per the operational
    tier)
- **Educator:**
  * `Lecturer` (Manager) — secondary faculty tier
  * `Tutor` (Technician) — apprenticeship-trained teaching staff
- **Banker:**
  * `BankingAnalyst` (Technician)
  * `BankingClerk` (Technician)
- **Doctor:**
  * `MedicalOrderly` (Technician) — backfills the missing technician tier
    on the Healthcare island

All new professions wired into:
  * `PROFESSION_BAND`
  * `BAND_TITLES` (Transporter / Educator / Banker titles refreshed)
  * `EDUCATION_SEASONS` (Logistics Manager, Lecturer = 2)
  * `APPRENTICESHIP_SEASONS` (all new technicians = 2)
  * `ROLE_PROFESSIONS`
  * `PROFESSION_LABEL`
  * `SKILLED_PROFESSIONS`
  * `STARTING_WORKERS_BY_PROFESSION`

#### Tests

- 5 new tests in `tests/test_models/test_profession_bands.py`:
  * `test_new_transporter_professions_have_correct_bands`
  * `test_new_technician_professions_for_educator_banker_doctor`
  * `test_transporter_band_titles_use_new_profession_names`
  * `test_every_island_starts_with_at_least_one_manager_and_two_technicians`
    — the invariant test
  * `test_every_profession_has_a_label`

#### Verification

- Test suite: `199 passed` (up from 194 baseline).

---

### claude/loans-and-insurance

Branch: `claude/loans-and-insurance`
Target: `pre-release`
Closes: GitHub #5, #6

#### Player-Facing Changes

- **Loan roll-over (Issue #6).** New `Roll Over Loan` action in the player
  action menu. The borrower picks an active loan, chooses a new term (1-3
  years), and the Banker quotes a new rate. The old loan's repayment becomes
  the new loan's principal — no cash moves at rollover, the new advance
  exactly covers the old repayment. Useful at or before maturity to extend
  obligations or to lock in a fresh rate quote.
- **Insurance review & cancellation (Issue #5).** New `Manage Insurance`
  action lists the player's active policies with seasons remaining and the
  pro-rata refund amount. Cancellation deactivates the policy and the Banker
  pays out a pro-rata refund (`premium × seasons_remaining / total_seasons`).
- Loans and Insurance side panels in the dashboard now show structured
  per-loan / per-policy detail: principal, rate, term, repayment amount,
  maturity date, seasons remaining, and cancel refund.
- Loans nearing maturity (≤1 season) and policies nearing expiry (≤1 season)
  are highlighted in gold to flag the renewal decision.

#### Engine

- New `LoanStatus.ROLLED_OVER`.
- New `Loan.rolled_over_from_loan_id` traceability field.
- New `LoanLedger.rollover_loan(loan_id, new_rate, new_term_years, year,
  season) -> Loan`. Refuses non-active loans or out-of-range terms.
- New `InsurancePolicy.seasons_remaining()` and `cancel_refund()` methods.
- New `Player.cancel_insurance_policy(policy_id, year, season) -> float` —
  returns the refund amount; caller is responsible for the cash transfer.
- New `TurnAction.ROLLOVER_LOAN` and `TurnAction.MANAGE_INSURANCE` with
  full prompt-chain implementations in `engine/turn.py`. Funding-side loans
  (lender_id == -1) are filtered out of rollover candidates.

#### Server

- `get_game_state` payload now includes `loans_detail` (structured per-loan
  info: role, principal, rate, term, maturity, seasons-to-maturity) and
  `policies_detail` (structured per-policy info: type, premium, expiry,
  seasons-remaining, cancel-refund). The plain `policies` string list is
  retained for back-compat.

#### Tests

- 15 new engine tests in `tests/test_engine/test_loan_rollover_and_insurance.py`:
  ledger primitives, action-level end-to-end (rollover, cancel, confirm-no
  cancellation), external bank funding-loan filtering, pro-rata math edge
  cases, double-cancel guard.
- 3 new server tests in `tests/test_server/test_game_state_loans_policies.py`
  covering the structured payload shape.

#### Verification

- Test suite: `194 passed` (up from 176 baseline).

---

### claude/pause-game

Branch: `claude/pause-game`
Target: `pre-release`
Closes: GitHub #1

#### Player-Facing Changes

- **Pause / Resume game (host only).** The room creator can pause the game at
  any point during auction, investing, or running phases. While paused:
  * All timers freeze (auction, investing, season-action, pre-season).
  * A full-screen "Game Paused" overlay covers the screen for every client.
  * Only the host sees the Resume button.
  * Players can still click Ready while paused, but the game does not advance
    until the host resumes.
- On resume, every timer end-epoch is bumped forward by the pause duration so
  no one loses time. If everyone clicked Ready while paused, the phase closes
  immediately on resume.

#### Server-Side

- New `paused: bool` and `paused_at: float` fields on `GameRoom`.
- New `request_pause(room_id, lobby_player_id, paused)` GameManager method,
  host-only.
- `_do_pause` cancels asyncio timer tasks (auction / investing / season);
  `_do_resume` reschedules them with the remaining seconds and bumps
  `*_timer_end` epochs forward.
- Pre-season game-thread wait loop now polls in 0.5s slices and respects
  `room.paused` — `pre_season_end` is bumped forward on resume so the wait
  naturally extends.
- `submit_ready` collects Ready presses during pause but does NOT fire
  `interrupt_all` or `_pre_season_done.set` until resume.
- WS protocol: client → `{type: "pause_request", paused: bool}`; server →
  `game_paused` / `game_resumed` broadcasts; `pause_ack` reply.
- Reconnecting clients receive `game_paused` if the game is currently paused.
- `room.to_dict()` now includes `creator_id` (so clients know who's host) and
  `paused`.

#### Tests

- New `tests/test_server/test_pause_game.py` — 12 tests covering host gating,
  pause/resume round-trip, timer-end bumping for auction/investing/season/
  pre-season, ready-during-pause queueing, quorum-on-resume short-circuit,
  and asyncio timer-task cancellation.
- Fixed `test_concurrent_ensure_player_does_not_create_duplicate_events`
  isinstance check (`threading.Lock` is a factory function on Python 3.9, not
  a class).

#### Verification

- Test suite: `176 passed`.

---

### claude/fix-action-menu-bug2

Branch: `claude/fix-action-menu-bug2`
Target: `pre-release`

#### Fixes

- **Fixed Bug #2: action menu stops displaying for some players.** Root cause
  was three race conditions in `WebSocketIOAdapter`:
  1. `_ensure_player` was not thread-safe — concurrent calls for the same
     player could create duplicate `Event`/`Lock` objects, leaving threads
     waiting on different Events.
  2. `_send_and_wait` had a split-lock gap between `event.clear()` and storing
     the pending message, allowing `interrupt_all()` or `receive_response()` to
     fire in the gap and be lost.
  3. No logging on timeouts or `None` responses made the issue hard to diagnose.
- Added structured logging in `ws_adapter.py` (choose_action, _send_and_wait)
  and `app.py` (unmapped lobby player IDs).
- Fixed `test_loans.py` Python 3.9 compatibility (missing `from __future__
  import annotations`).

#### Tests

- Added `test_concurrent_ensure_player_does_not_create_duplicate_events` —
  verifies thread-safe lazy initialisation with a 4-thread barrier.
- Added `test_response_during_send_and_wait_is_not_swallowed` — verifies
  near-instantaneous responses are not lost.

#### Verification

- Test suite: `135 passed, 2 skipped`.

---

### claude/test-fixes-and-spec-cleanup

Branch: `claude/test-fixes-and-spec-cleanup`
Target: `pre-release`

#### Balance Changes

- Every island now starts with sufficient resources for at least 2 seasons of
  production inputs (previously 1 season). Gives players breathing room to
  establish trade relationships before running out of critical inputs.

#### Fixes

- Fixed `test_loans.py` Python 3.9 compatibility (missing `from __future__
  import annotations`).
- Cleaned up spec cross-references between `production-capacity-model.md` and
  `island-ledger.md` to eliminate duplication.

#### Tests

- Added `test_every_island_starts_with_at_least_two_seasons_of_inputs`
  invariant test covering all 7 roles.
- Updated `test_economy_balance.py` assertions to match new starting inventory.

#### Verification

- Test suite: `135 passed, 2 skipped`.

---

## 0.1 (codex/future-fixes)

Branch: `codex/future-fixes`
Merged to: `pre-release`

### Player-Facing Changes

- Expanded browser dashboard with richer production capacity, funding-rate,
  market, training, loan, and deal-response flows.
- Added island artwork backgrounds and a wider right-hand market/info panel.
- Renamed player-facing role labels to island specialties, while preserving
  existing internal role identifiers.
- Added Release Notes and release-process documentation before the
  `pre-release` merge gate.

### Rules / Balance Changes

- Added Metal as an intermediate resource; Manufacturing product lines now use
  Metal instead of raw Ore.
- Reduced Mining Oil production and added Metal smelting with enhanced crusher
  and smelter support.
- Added mid-game capital equipment purchases from Manufacturing output.
- Added population-based Food/Fish demand signals, with educated workforces
  increasing Fish demand.
- Added richer loan terms, posted funding rates, banker quote logic, and
  net-wealth treatment including loans and depreciated equipment.
- Documented future requirements for cross-island machinery, product/equipment
  Help text, post-auction human island guarantees, and Claude worktree usage.

### Fixes

- Fixed deal response flow so counterparties can review pending deals on their
  turn.
- Fixed selected-product production so players choose what and how many to
  produce.
- Fixed training review/counteroffer flows and air-ticket requirements.
- Fixed multi-role Banker loan access.
- Fixed market board modal dismissal verification tracking.
- Fixed production capacity and constraint reporting around ordered/owned
  capital equipment.

### Known Issues / Follow-Up

- ~~Issue #2 remains open~~ — fixed in `claude/fix-action-menu-bug2`.
- Cross-island machinery, leases, release-ready Help catalogue, island-ledger
  ownership model, and post-auction AI island purchase are documented future
  requirements, not complete implementations.

### Verification

- Test suite status: `161 passed`.
- Manual browser testing: server restarted on `127.0.0.1:8001`; live gameplay
  testing still recommended before final merge.
