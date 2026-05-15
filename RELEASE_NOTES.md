# Island Traders Release Notes

Release notes are required before merging a feature/fix branch into
`pre-release`.

## Unreleased

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
