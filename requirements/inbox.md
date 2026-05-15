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

- [2026-05-15] Education Island self-training bug: Educator should be able to train its own workforce. Self-training Professors should take one season but require no educator fee and no transport fee/tickets.
- [2026-05-15] Rename player-facing `Purchase Capital` wording to `Purchase Equipment`.
- [2026-05-15] Investigate AI live-play economy behavior: required outputs may exist but AI behavior is too passive / narrow after production. Current workaround is to propose a trade that forces the AI to accept a deal instead of relying on it to list useful offers. Add automated trading logic so AI islands can place bids, list offers, and evaluate profitable cross-island deals / inventory arbitrage (example: Mining can trade Ore plus cash to Education; Education may resell Ore for profit or hold it until worthwhile bids appear). Verify Transportation produces and makes PassengerSeats / air tickets available so training is not blocked.
- [2026-05-15] Personnel shortages should be described using missing specialties/professions, not generic `Managers` / `Technicians`.
- [2026-05-15] Food model adjustment: base island population is assumed self-fed; additional population from added workers creates incremental food demand.
- [2026-05-15] Players need to be able to cancel open bids and open offers. Existing partially filled offers should keep reduced remaining quantity after sales.
- [2026-05-15] Education model refinement: rename the tradable Education output `Knowledge` to `Expertise`. Education also produces `Courses`, starting with a baseline of about 5 Courses, and producing Courses consumes Expertise as an input. Education starts with about 6 Expertise so first-season training is not blocked. Training requests consume Courses; course capacity should eventually be tied to Professors for managerial training and Instructors for technician / apprenticeship programs. Education Island should start with 4 Professors and 4 Instructors.
- [2026-05-15] Early automated-market heuristic: allow near-match clearing instead of requiring exact prices. A bid and offer should match when they are within either 1 Dollop or 3% of each other; examples that should clear include 97/100 and 9/10. If a new bid makes an existing offer viable, execute at the offer price. If a new offer makes an existing bid viable, also execute at the offer price. Fill the lesser of the bid quantity and offer quantity, reducing the remaining quantity on any partially filled standing order.
- [2026-05-15] Item valuation rule: estimated market value for deal evaluation should be the last deal price, or the current offer price if no deals have taken place yet. Existing inventory should be valued at the lower of cost or market value for wealth calculations. This affects AI trade valuation and player / island wealth reporting.


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
