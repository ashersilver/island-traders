# Island Traders — Enhancement Tracker

<!-- Sync policy:
     GitHub issues are the canonical record for bugs and feature requests.
     This file tracks development priority, grouping, and implementation state.
     Completed items move to the Completed section below. -->

---

## Bugs (fix before new features)

- [ ] **#2 — Action menu stops displaying for some players** *(multiplayer blocker)*
      During concurrent play some players' action menus disappear. Likely a
      TLS/thread race in ws_adapter — `set_active_player` called on wrong thread
      or `_ensure_player` races, causing `_send_and_wait` to silently return None.
      Reconnect/replay work may help but needs a dedicated investigation.
- [ ] **Educator self-training** *(playtest 2026-05-15)* — the Education
      Island can't currently send its own workers to college.  Self-training
      should take 1 season, require **no educator fee** and **no transport
      ticket**.  Touches `_action_request_training` + `_action_review_training`
      in `engine/turn.py` (skip the educator-choice prompt + transport
      requirement when requester == educator).

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

#### Phase 1 — Rename
- [ ] `ResourceType.KNOWLEDGE` → `ResourceType.EXPERTISE` (mechanical
      rename, ~40-file cascade, zero behavioural change)
- [ ] Update RULES.md / README.md / dashboard labels

#### Phase 2 — Courses + new training flow
- [ ] Add `ResourceType.COURSES` (new tradable resource, base price ≈ 25 Dp)
- [ ] New Education recipe: Courses production consumes Expertise as an input
- [ ] Add `Profession.INSTRUCTOR` (Technician); consider consolidating
      Tutor → Instructor (open question in the spec)
- [ ] Training requests debit 1 Course from Educator inventory on approval;
      no Courses → request stays pending
- [ ] `UNIVERSITY_CAPACITY` re-segments: Manager-tier training gated by
      Professors; Technician-tier training gated by Instructors
- [ ] `STARTING_WORKFORCE[Educator] = 8`: 4 Professors + 4 Instructors
- [ ] `STARTING_INVENTORY[Educator]` += 6 Expertise + 5 Courses
- [ ] Self-training (Educator training its own workforce) still consumes a
      Course but skips fees and transport — coordinate with the related Bug
      entry above

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

- [x] **#1 — Pause game** — host-only pause/resume; freezes all timers (auction/investing/season-action/pre-season); full-screen overlay; ready submissions queued during pause and processed on resume
- [ ] **#3 — Action alerts / event subscriptions** — chips on the log panel to filter by event type; popup notification when a subscribed event fires. *(See also `inbox.md` event-filtering requirement.)*
- [ ] **#7 — All-player summary on island layout** — overlay player values (wealth, output, workforce) on the island map SVG
- [ ] **#8 — Intro screen** — animated board with hotspot tooltips explaining each island; requires island graphics assets
- [ ] Event log: player-relevant lines are highlighted (done ✓ — verify in play)
- [ ] Consolidated view when controlling multiple islands (tab + "Consolidated" already exists; verify multi-role aggregation is correct)
- [ ] **Rename action wording: `Purchase Capital` → `Purchase Equipment`** *(playtest 2026-05-15)* — pure label change; touches `engine/turn.py` enum value (TurnAction.PURCHASE_CAPITAL stays as the internal identifier, just changes the player-facing label), the action dispatch in the dashboard, and the action button labels.  Update `Apply Patent` similarly if needed.
- [ ] **Personnel shortages named by specialty/profession** *(playtest 2026-05-15)* — when production capacity is constrained by missing workers, the UI/log should say *"need 2 more Flight Crew"* or *"need 1 more Banker"*, not the generic *"need 2 more Technicians"*.  Touches the constraint-popup text + workforce-shortage log lines.

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
