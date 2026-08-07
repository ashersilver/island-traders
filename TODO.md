# Island Traders — Enhancement Tracker

<!-- Sync policy:
     GitHub issues are the canonical record for bugs and feature requests.
     This file tracks development priority, grouping, and implementation state.
     Completed items move to the Completed section below. -->

---

## Bugs (fix before new features)

- [x] **#2 — Action menu stops displaying for some players** *(multiplayer
      blocker, fixed claude/bug-action-menu-race)* — root cause was a
      reconnect race in `server/app.py`, not the TLS / `_send_and_wait`
      surface the prior TODO suspected (those were already hardened).
      When a player's browser reconnected quickly (refresh, brief network
      blip, second tab), the new socket's `register_ws` ran on the
      asyncio loop thread BEFORE the old socket's `finally`-block
      `unregister_ws`. The old socket's late unregister then evicted the
      newly-registered socket from `_ws_connections`. Subsequent
      `_thread_safe_send` calls found no entry and silently dropped every
      message — most visibly the `choose_action` payload. Fix:
      identity-aware `unregister_ws(room_id, player_id, ws)` that only
      removes the entry if it's still the same socket, plus a
      `GameManager._ws_lock` protecting every read / write of the
      connection table. 5 regression tests in
      `tests/test_server/test_ws_reconnect_race.py`.
- [x] **Trainees never return from training** *(playtest 2026-05-24, fixed
      claude/training-return-bug)* — the **self-training** shortcut in
      `engine/turn.py::_action_request_training` was calling
      `training.dispatch` (registry side) without the matching
      `player.workforce.dispatch_for_training(req.worker_ids)`
      (workforce side). At the return tick the registry correctly flipped
      `DISPATCHED → COMPLETED`, but `workforce.return_from_training` is a
      no-op for workers whose `in_training` flag is still False — so the
      self-trained worker's `training_level` never advanced and they never
      "graduated." Cross-island training was always wired correctly. Fix:
      one-line addition mirroring the cross-island `_dispatch_training`
      helper. Three new regression tests in
      `tests/test_engine/test_training_returns.py` cover both the
      cross-island and self-training round trips so this can't silently
      regress again.
- [x] **Educator self-training** *(playtest 2026-05-15, fixed)* —
      `_action_request_training` short-circuits when requester is the
      Educator: no fee, no air ticket, auto-approve + auto-dispatch.

## In Progress

### Release Process

- [ ] Before merging this branch into `pre-release`, update `RELEASE_NOTES.md`
      with tested changes, known issues, and verification notes.
- [x] Document separate Claude Code worktree convention.

### Production Capacity Model
See [`requirements/production-capacity-model.md`](requirements/production-capacity-model.md) for full spec.

- [ ] Worker bands (Manager / Technician / Worker) with per-island titles
- [ ] Per-output capital catalogue + per-unit input requirements
- [ ] Production Capacity sidebar panel
- [ ] Production Constraint Popup — which cap (equipment / workforce / inputs) is binding and by how much
- [ ] Product/equipment Help catalogue — every product and capital item has a shared Help paragraph covering purpose, pros/outputs, cons/inputs, logistics, and risks
- [ ] **#4 — What-If production table** — interactive spreadsheet-like calculator; if viable, "Enact" button triggers required purchases
- [ ] Patents (Educator output; permanent +% boost; max 3 active per output)
- [ ] Apprenticeship pipeline (separate slot pool from university education)
- [ ] Education pipeline (Doctor 2 seasons, Nurse 1 season, other Managers 2)
- [ ] Mechanic profession (–20% downtime per Mechanic, capped at –60%)
- [ ] Equipment Insurance (Banker product; market-rate replacement payout on destruction event)
- [ ] AI auction bidding (per-role heuristic + 2nd-round top-up)
- [x] Mid-game capital equipment purchases from Manufacturing output (2-season delivery for complex items)
- [x] Metal intermediate: Mining smelts Ore + Oil into Metal; enhanced crusher/smelter boosts Metal productivity and reduces Oil use
- [ ] Capital equipment leases (3-year lease, return or buy out at 5-year straight-line book value)
- [ ] Cross-island machinery licences — any island can buy non-native machinery from Manufacturing, operate the matching recipe if it supplies inputs/workforce, absorb standard-of-living/salary/perk impacts, and respect commodity/equipment shipping delays
- [ ] **Food demand: base population is self-fed** *(playtest 2026-05-15)* —
      starting ~100 residents generate **no** market Food/Fish demand
      (self-sufficient subsistence).  Only **added** residents beyond the
      baseline generate +1 Food demand/season.  Add
      `BASE_POPULATION_SELF_FED = 100` constant; refactor
      `population_food_demand` to subtract it before scaling.  See
      `production-capacity-model.md §21`.

### AI Players
See [`requirements/llm-player-adapter.md`](requirements/llm-player-adapter.md) for the LLM adapter design.
Draft PR #12 documents the spec; implementation is the next step.

- [ ] `PlayerStrategy` protocol / base class (`take_turn(...)`) shared by heuristic and LLM players
- [ ] `GameStateSnapshot` serializer (public + player-private context only)
- [ ] `ActionProposal` schema covering all legal action types
- [ ] Validation layer — rejects or repairs illegal proposals before engine sees them
- [ ] `LLMPlayerStrategy` implementation behind optional configuration
- [ ] Tests proving invalid LLM proposals cannot mutate game state
- [ ] Keep `AIStrategy` as default heuristic for simulations and tests

### AI Trading Behaviour
*(From the 2026-05-15 playtest inbox.)* Heuristic AI is too passive after
production today.  Humans currently have to *propose* trades to AIs to get
anything moving.  Suggested candidate for the next Codex task.

- [ ] AI islands should **place bids** on inputs they're short on
- [ ] AI islands should **list offers** for outputs they have surplus of
- [ ] AI islands should **evaluate profitable cross-island deals / inventory
      arbitrage** (e.g. Mining trades Ore + cash to Education; Education may
      resell Ore for profit or hold it until worthwhile bids appear)
- [ ] Verify Transportation actually produces & lists Passenger Seats / air
      tickets so training isn't silently blocked when no human Transporter is
      online.  Likely just a check; add a test asserting Transporter AI lists
      Passenger Seats by season 2.
- [ ] AI deal-valuation logic should use the **last-deal price or current
      offer price** (see Item Valuation below), not formula price

### Education Model Refinement
See [`requirements/education-model.md`](requirements/education-model.md) for full spec.
*(From the 2026-05-15 playtest inbox.)*  Two-phase migration recommended;
don't combine the phases.

#### Phase 1 — Rename ✅ (done — claude/education-phase1-rename)
- [x] `ResourceType.KNOWLEDGE` → `ResourceType.EXPERTISE` (mechanical
      rename, zero behavioural change — 262 tests still green)
- [x] Update RULES.md / README.md / constants / event charts / board
      labels.  Banker input + Educator output are now "Expertise".

#### Phase 2 — Courses + new training flow ✅ (done — claude/education-phase2)
- [x] Add `ResourceType.COURSES` (new tradable resource, base price 25 Dp)
- [x] New Education recipe: Courses production consumes Expertise as an input
- [x] `Profession.TUTOR` → `Profession.INSTRUCTOR` consolidation
- [x] Training requests debit `ceil(trainees/12)` Courses on approval;
      no Courses → request stays pending
- [x] `STARTING_WORKFORCE[Educator] = 8`: 4 Professors + 4 Instructors
- [x] `STARTING_INVENTORY[Educator]` += Expertise + 5 Courses
- [x] Self-training consumes a Course but skips fees and transport
- [x] *(Phase 3 correction)* Phase 2 Course-debit scoped to Manager-tier
      only (Technicians now apprenticeship-gated)

#### Phase 3 — Training cost components + apprenticeship pipeline (#18) ✅ (done — claude/education-phase3)
*(All decisions ruled 2026-05-17 — see `requirements/education-model.md`.
Suite 293 green.)*
- [x] Scope Phase-2 Course-debit to **Manager-tier only** (decision (a):
      Courses ≠ apprenticeship; non-overlapping pipelines)
- [x] Technician training → **apprenticeship slot pool**
      (`educator.apprenticeship_programme`) + Instructor (trainer) gate,
      **not** Course-gated
- [x] Apprentice: **1 season away** at Education, then **75% productivity
      for exactly one season** on the home island, then 100%
      (`APPRENTICESHIP_SEASONS` away-duration → 1; settling ramp on Worker)
- [x] Course duration by profession: **Doctor = 3**, other Managers = 2,
      Nurse = 1  →  `EDUCATION_SEASONS[DOCTOR]` 2 → 3, wired into dispatch
- [x] **Expertise consumption: 1 Expertise per Course per season**
      (per Course, *not* per trainee) — in the fee suggestion; not a
      second inventory debit (Courses already burn Expertise at
      production time, Phase 2)
- [x] Food & accommodation cost: 5 Dp per trainee per season at college
      (`TRAINEE_FOOD_ACCOM_PER_SEASON`)
- [x] **Campus load**: visiting-trainee count surfaced
      (`TrainingRegistry.visiting_trainees`) on the Educator review
      screen.  Demand-model integration via the §21 `extra_residents`
      seam is owned by `requirements/codex-tasks/sustenance-model.md`
      (Codex) — Phase 3 does NOT touch the legacy Food/Fish path
- [x] `_action_request_training` fee suggestion includes all cost
      components (base fee + food/accom + tickets + expertise/Course)
- [x] Drop the `provides_apprenticeship_facility` flag / sellable-token
      — no-op: never existed in code (only in reconciled requirements)

### Medical & Laboratory Island
See [`requirements/medical-laboratory.md`](requirements/medical-laboratory.md)
for full spec.  Covers GitHub issues **#19, #25, #26**.  Five-phase
implementation; recommend not combining phases.

#### Phase A — Role rename + Lab Tests resource (#26 root)
- [x] Display rename: "Healthcare" → "Medical & Laboratory" (internal
      `ROLES["Doctor"]` key unchanged)
- [ ] New `ResourceType.LABORATORY_TESTS` (base price ≈ 35 Dp)
- [ ] Add Doctor production recipe for Lab Tests
- [ ] Starting inventory: small Lab Test stockpile

#### Phase B — Cross-island Lab Test consumers (#26)
- [ ] Mining Ore → Metal smelting requires 1 Lab Test ("Metal Assay")
      per batch
- [ ] Farmer seasonal production requires 1 Lab Test ("Soil Analysis")
- [ ] RULES.md updated with Lab Test consumers

#### Phase C — Ecologist + Environmental Assessment gate (#25)
- [ ] Add `Profession.ECOLOGIST` (Technician, 2-season apprenticeship)
- [ ] Add `installation_review_required: bool` field on CapitalItem;
      default true for high-cost items
- [ ] Hook into capital activation: held until Ecologist + Environmental
      Assessment Lab Test present
- [ ] `UNIVERSITY_CAPACITY[Ecologist] = 6` (or similar)

#### Phase D — Actuary + insurance underwriting gate (#24)
- [ ] Add `Profession.ACTUARY` (Technician, 2-season)
- [ ] `SELL_INSURANCE` requires ≥1 Actuary on Banker's workforce
- [ ] Banker pays actuarial evaluation cost (5 Dp) from institutional pool

#### Phase E — Doctor-certification insurance economics (#19)
- [ ] Annual physical (1 Lab Test "Health Certificate") halves premium
- [ ] Anniversary physical maintains the half-rate at renewal
- [ ] Insured workers don't lose productivity from injury events
      (medical insurance injury reduction → 1.0 when policy active)
- [ ] Death benefit becomes profession-based replacement training cost
      (paid from Bank pool to island working capital)

### Economy Lifecycle & Cross-Island Dependency
See [`requirements/economy-lifecycle-2026-05.md`](requirements/economy-lifecycle-2026-05.md)
for full spec.  Product-owner direction 2026-05-18.  Five mechanics,
phased A–E (independently mergeable).  **Re-balances the open
Banker/Farmer over-dominance — calibrate AFTER A–D land.**

#### Phase A — Economy constants + starting stocks (smallest, do first)
- [ ] Per-player starting cash 700 → **1500** (`STARTING_DOLLOPS`,
      `TOTAL_STARTING_DOLLOPS` 10500, `DEFAULT_STARTING_CAPITAL`)
- [ ] `STARTING_INVENTORY["Miner"]["Oil"]` 4 → **8**
- [ ] `STARTING_INVENTORY["Farmer"]["Food"]` → **15** (new key)

#### Phase B — Worker lifecycle + Agriculture bootstrap
- [ ] `Worker.age_seasons`; `WORKING_LIFE_SEASONS` per band (M40/T32/W24,
      tunable); retire→remove at season roll-over (reuse remove_workers)
- [ ] `STARTING_WORKER_AGES` seeding; Agriculture: Farmer −4,
      Horticulturalist −8 (retire end Y1 / Y2)
- [ ] Mid-training retiree → drop from batch + log

#### Phase C — Capital lifecycle
- [ ] `CapitalItem.service_life_seasons` (def 20) +
      `maintenance_per_season` (≈3 % cost); per-unit age from
      `capital_acquired_ticks`
- [ ] Maintenance debit each season; unmaintained → 0 capacity + warn;
      expiry removes unit (repurchase from Manufacturer)
- [ ] `farmer.harvester` service life = 8 (combine, ~2 yr) + start aged

#### Phase D — Banker capital-reserve & MBA model
*(Fractional-reserve model, supersedes the binary "no loans w/o MBA"
gate.)*  May split D1 (reserve model — balance-critical) / D2
(computing-centre latency).
- [ ] `Worker.has_mba`; MBA training branch (2 Professors + 3 Courses,
      2 seasons, Course-gated Manager pipeline)
- [ ] Reserve model: own capital backs loans at `r` = **0.50** (<3 MBA
      managers) / **0.20** (≥3); reserved own-capital locked until loan
      resolves; external funds the rest
- [ ] Returns: full interest on own capital + margin `(loan−posted)`
      on external; default loses committed own capital
- [ ] **No** Banking MBA bootstrap — starts with 0 MBA managers,
      `r=0.50` (intentional early constraint), trains up to scale
- [ ] Loan negotiation: Banker may quote ANY rate (formula = suggested
      default); applicant **counter-offer** loop (reuse training
      counter pattern); AI uses fair-rate thresholds
- [ ] Loan **terms** 1/2/3 yr; 2/3-yr = interest settled annually,
      principal rolled at **original amount + original rate** until
      final year (rate locked at origination). Distinct from shipped
      #6 `ROLLOVER_LOAN` (post-maturity opt-in fresh-rate refinance)
- [ ] D2: `banker.computing_centre` capital — without it, loan
      application takes +1 season to disburse (Phase C lifecycle applies)
- [ ] D2: indicative 1/2/3-yr term-rate quotes surfaced in loan UI

#### Phase E — RULES.md + calibration handoff
- [ ] Document all four mechanics in RULES.md
- [ ] Re-baseline / hand `codex-tasks/balance-calibration-2026-05.md`
      to Codex **against Phases A–D**

### Island Ledger & Ownership Model
See [`requirements/island-ledger.md`](requirements/island-ledger.md) for the full spec.
*Prerequisite for financial model improvements, role resale, and Banker institutional pool.*

- [ ] Island/role entity with its own inventory, working capital, and obligations
- [ ] Separate player ownership cash from island working capital
- [ ] Banker institutional cash pool (separate from player-owner personal cash)
- [ ] Owner deposit accounts (auction surplus deposited with Bank at 5% p.a.)
- [ ] Capital injection / withdrawal flow between player and island ledger
- [ ] Ownership transfer (role resale) preserving island state

### Financial Model

- [x] **#6 — Loan roll-over** — `ROLLOVER_LOAN` action; old loan ROLLED_OVER, new loan inherits repayment as principal at fresh banker_quote_rate
- [x] **#5 — Insurance review** — `MANAGE_INSURANCE` action; pro-rata cancel refund (premium × seasons_remaining / total). Renewal via existing BUY_INSURANCE action.
- [ ] Rename "Dollops" heading → "Working Capital" (suffix `Dp` stays)
- [x] Wealth = total assets at market value + depreciated capital equipment book value + loans receivable − loans outstanding (balance sheet view)
- [ ] All monetary values show `Dp` suffix consistently in UI
- [ ] **Item valuation rule** *(playtest 2026-05-15)* — for deal evaluation and
      wealth reporting, an item's estimated market value should be the **last
      deal price**, falling back to the **current best offer price** when no
      deals have happened yet (instead of the formula price).  Existing
      inventory should be valued at **lower of cost or market** for wealth
      calculations.  Affects AI valuation heuristics and player / island
      wealth reporting.

### Market & Trading
*(Playtest 2026-05-15 additions.)*

- [ ] **Cancel open bids and offers** — players need a UI action to withdraw
      their own standing bid/offer.  Existing partially filled offers should
      retain the **reduced remaining quantity** after sales.
- [ ] **Near-match auto-clearing heuristic** — a bid and offer should
      cross-match when within either **1 Dollop** OR **3%** of each other
      (e.g. 97/100 and 9/10 should clear).  Match price = the offer price.
      Fill the lesser of the two quantities; partially filled standing orders
      keep the residual.

### Dashboard & UX

- [ ] **Role-player guides** — on-demand per-role instruction beyond
      the acquisition intro (esp. Banker lending/reserve/MBA rules).
      See [`requirements/role-player-guides.md`](requirements/role-player-guides.md).
      Single content source (intro + guide + RULES.md); schedule after
      economy-lifecycle Phase D, pair with Phase E RULES.md pass;
      candidate Codex docs/UX task.
- [x] **#1 — Pause game** — host-only pause/resume; freezes all timers (auction/investing/season-action/pre-season); full-screen overlay; ready submissions queued during pause and processed on resume
- [ ] **#3 — Action alerts / event subscriptions** — chips on the log panel to filter by event type; popup notification when a subscribed event fires. *(See also `inbox.md` event-filtering requirement.)*
- [ ] **#7 — All-player summary on island layout** — overlay player values (wealth, output, workforce) on the island map SVG
- [ ] **#8 — Intro screen** — animated board with hotspot tooltips explaining each island; requires island graphics assets
- [ ] Event log: player-relevant lines are highlighted (done ✓ — verify in play)
- [ ] Consolidated view when controlling multiple islands (tab + "Consolidated" already exists; verify multi-role aggregation is correct)
- [x] **Rename action wording: `Purchase Capital` → `Purchase Equipment`** *(playtest 2026-05-15, done)* — display-layer rename via `ACTION_LABEL_OVERRIDES` in `cli/prompts.py`; internal `TurnAction.PURCHASE_CAPITAL` unchanged.
- [x] **Personnel shortages named by specialty/profession** *(playtest 2026-05-15, done)* — `workforce_short` payload now uses `primary_title(role, band)` so the dashboard shows "+2 Flight Crew" / "+1 Banking Analyst" etc.
- [x] **#20 — Personnel counts on left panel** *(playtest 2026-05-15)* —
      add trained / untrained personnel counts (including general
      workers) to the left-hand info panel.  Server payload already
      exposes `workforce_bands` + `workforce_count`; just needs UI
      rendering.
- [x] **#21 — Product selection by name, not index** *(playtest 2026-05-15)* —
      when producing, the choice list must show the product name (e.g.
      "Farm Machinery", "Lab Equipment") not numeric index.  Touches the
      production prompt chain when Manufacturer picks a product line.
- [x] **#22 — Market UI/UX polish** *(playtest 2026-05-15, done)*
  - [x] Market Prices popup rendered as a grid (.market-grid style)
  - [x] Buy popup: legend + grouped/tinted columns distinguishing
        "Buy Now @ ask" from "Place Bid @ your price"
  - [x] Buying: new-bid price prefilled with the current ask
  - [x] Selling: asking-price prompt prefilled with the best bid
        (new `prefill` param on ask_dollop_amount)
- [ ] **#23 — Logo + island detail popup** *(playtest 2026-05-15)*
  - [ ] Top-left game logo: bolder + more readable
  - [ ] Clicking on any island brings up a well-formatted popup with
        description, role info, and the island's graphic.  Aligns with
        GitHub #8 (Intro screen).

---

## Backlog

### From CLAUDE.md
- [x] README.md (proper GitHub project readme) — exists and up to date
- [x] RULES.md — Doctor workforce numbers fixed (6 total: 2 Doctors + 4 Nurses)
- [ ] Simulation recalibration after ForgeHaven + insurance + capacity-model changes
- [ ] PDF export via reportlab (stretch goal)

### Feature Roadmap
- [ ] Auction margin lending: borrow up to 50% of starting capital at 10% (Banker, back-to-back 5% IMF loan). See `requirements/production-capacity-model.md §18`.
- [ ] Roleless players — role aftermarket (secondary sales) + on-call bank deposits expanding Banker lending capacity. See `requirements/production-capacity-model.md §19` and `requirements/island-ledger.md`.
- [x] Post-auction human island guarantee — sequential per-buyer phase between auction and investing; AI must sell, price = max(20% floor, banded formula); see `requirements/production-capacity-model.md §19.1`.
- [ ] Brokerage services: Banker negotiates deals between islands for a commission
- [ ] Contracts & Futures (forward agreements between players)
- [ ] Infrastructure Investment (upgrade production capacity mid-game)
- [ ] In-game chat (WebSocket-backed messaging between players)
- [ ] Market orders (limit orders, standing offers)
- [ ] Tournament mode (bracket play across multiple games)
- [ ] Population migration: islands lose population to others with higher standard of living (Food per capita, insurance coverage, health services index)

---

## Completed

- [x] Simultaneous-play architecture — per-player threading, season timer, Ready button
- [x] Pre-season review window (timer + Ready-to-start short-circuit)
- [x] Per-role island tabs in game dashboard
- [x] Starting capital as a configurable game parameter (default 700 Dp)
- [x] Pre-season / action-phase UI (banner overlay, phase-aware Ready button, player dots)
- [x] Event log player-relevant line highlighting
- [x] Role auction phase (AuctionState, timer, AI participation)
- [x] Investing Phase between auction and Year 1 (InvestingState, capital catalogue)
- [x] Public/private rooms + join code
- [x] Proportional starting wealth based on player count
- [x] Reconnect: replay pending prompts after client disconnect
- [x] LLM player adapter spec documented (PR #12 — draft; implementation pending)
- [x] ForgeHaven product line differentiation (4 specialised product lines)
- [x] Banker insurance products (life + medical)
- [x] Workplace risk system (injuries, fatalities, experience scaling)
- [x] WebSocket game server + responsive dashboard
- [x] Fix WebSocket 403 (future annotations + local imports)
- [x] Loans system (Banker bullet bonds — 1-year term, repaid at maturity with interest)
- [x] **#10 — Market Board modal can be dismissed** *(verified live)*
- [x] Food/Fish demand signals scale with island population and educated workforce mix
