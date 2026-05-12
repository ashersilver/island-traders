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
