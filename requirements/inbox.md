# Requirements Inbox

Quick-capture file for requirements you think of between Claude sessions.
**Append freely** — don't worry about format, structure, or duplicates.

At the start of each session, Claude will:
1. Read this file
2. Synthesise items into the right place (existing spec, new spec file, TODO.md, or a GitHub issue)
3. Clear the captured items below

## Pending

<!-- Add new requirements below this line.  One bullet per idea is fine.
     Date-stamp optional but helpful: -->


<!--
- [2026-05-05] Players should be able to ___
- Apprenticeship slot capacity needs to scale with the ___
-->



## Captured (Claude — keep this section as a running log)

<!-- Claude moves processed items here with a short note on where they landed. -->

- **[2026-05-07] Separate island operating accounts from player ownership** →
  Full spec written in `requirements/island-ledger.md`. TODO.md updated with
  "Island Ledger & Ownership Model" section. Proposed: 300 Dp island working
  capital (separate from 700 Dp personal auction budget); `IslandLedger` entity
  holds inventory, equipment, workforce, loans; two-phase migration plan.

- **[2026-05-07] Banker institutional cash pool** →
  Covered in `requirements/island-ledger.md §3`. Bank starts with 2,000 Dp
  institutional pool; loans draw from that pool, not the player-owner's cash;
  dividends are the mechanism to move retained earnings to personal cash.

- **[2026-05-08] Role resale / late entry market** →
  Covered in `requirements/island-ledger.md §4` and TODO.md backlog. Marked as
  depending on the island-ledger model (ownership transfer must carry island state).
  Out of scope for v1 fractional ownership.

- **[2026-05-11] Event log filtering / subscriptions** →
  Merged with GitHub Issue #3 (Action alerts). Basic client-side highlighting
  implemented this session (player-relevant lines get `.log-mine` highlight).
  Filter chips and popup alerts are the next step; tracked in TODO.md under
  Dashboard & UX → #3.

- **[2026-05-15] Education self-training (no fee / no transport / 1 season)** →
  `TODO.md` Bugs section.  Engine fix in `_action_request_training` +
  `_action_review_training` to skip the educator-choice prompt and transport
  requirement when requester == educator.

- **[2026-05-15] Rename `Purchase Capital` → `Purchase Equipment`** →
  `TODO.md` Dashboard & UX section.  Pure label change (internal enum name
  `TurnAction.PURCHASE_CAPITAL` stays).

- **[2026-05-15] AI live-play economy / automated trading** →
  `TODO.md` new "AI Trading Behaviour" section.  Proposed as next Codex
  task: AI islands placing bids, listing offers, evaluating cross-island
  arbitrage.  Includes the "verify Transporter actually produces &
  lists Passenger Seats / air tickets" sub-bullet so training isn't
  silently blocked.

- **[2026-05-15] Personnel shortages by specialty** →
  `TODO.md` Dashboard & UX section.  Constraint popup + workforce-shortage
  log lines should name the missing profession (e.g. "need 2 Flight Crew")
  rather than the generic band.

- **[2026-05-15] Food: base population self-fed; only added pop creates demand** →
  Added as `requirements/production-capacity-model.md §21` (Food demand
  model refinement) + cross-referenced in `TODO.md` Production Capacity
  section.  Proposed `BASE_POPULATION_SELF_FED = 100` constant.

- **[2026-05-15] Cancel open bids / offers + partial-fill state** →
  `TODO.md` new "Market & Trading" section.  Players need a UI action to
  withdraw their own standing bids/offers; partial fills keep the residual
  quantity.

- **[2026-05-15] Education model refinement (Knowledge → Expertise, +Courses, +Instructors)** →
  Full spec written at `requirements/education-model.md`.  `TODO.md` has a
  new "Education Model Refinement" section laying out the two-phase
  migration (mechanical rename first, then Courses + new training flow).

- **[2026-05-15] Near-match auto-clearing (±1 Dp or ±3%)** →
  `TODO.md` Market & Trading section.  Match price = the offer price; fill
  the lesser of the two quantities; partial fills keep the residual.

- **[2026-05-15] Item valuation: last-deal / lower-of-cost-or-market** →
  `TODO.md` Financial Model section.  Affects deal-evaluation heuristics in
  the AI and player/island wealth reporting.
