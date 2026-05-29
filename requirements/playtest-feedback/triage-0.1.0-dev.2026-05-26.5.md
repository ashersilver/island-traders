# Triage: playtest `0.1.0-dev.2026-05-26.5`

Source: [playtest-0.1.0-dev.2026-05-26.5.md](./playtest-0.1.0-dev.2026-05-26.5.md)
Reports: Comet Player 1 (Manufacturer), AyaySir (Mining), Codex Player (Banking), Real Human (general).
Triaged: 2026-05-27.

Server-takedown / reconnection items are excluded throughout (the operator confirmed the disconnects were from a deliberate server stop, not a defect).

## Summary

| Bucket | Count | Notes |
|---|---:|---|
| ✅ Already fixed | 0 | Nothing in this report has been merged after .26.5 *except* the named-options purchase picker, which addresses a different complaint than any here. |
| 🐛 New Codex briefs | **6** | See §3. |
| 🎨 Claude UI follow-ups | **9** | Most batch into one Action-Panel-and-Hints sweep. See §4. |
| ⚖️ Calibration / design | **5** | Discussion items including the workforce-cap question already open. See §5. |
| ⏭ Deferred / out of scope | **3** | Server takedown, plus 2 items duplicating existing GitHub issues. See §6. |

## 1. The big cross-cutting theme

**One root bug appears in seven of the items reported, across all three player reports:** *"End Turn"* (which the server treats as "mark player ready / done for the season") is being entered in ways the player did not intend, and once entered there is no way out until the next season. References:

| Report | Item | Symptom |
|---|---|---|
| Comet 1 | Bug #2 | "Action panel disappears after End Turn — no way back" |
| Comet 1 | Bug #3 | "Open Market Buy →" hint buttons disabled after End Turn |
| Comet 1 | Bug #4 | Produce buttons in hints visible but non-interactive |
| Comet 1 | Bug #10 | "Done Trading ✓" shown before player clicked End Turn |
| Comet 1 | IMP-1 | "End Turn should be reversible until timer hits zero" |
| AyaySir | BUG-01 | "Done Trading state auto-set at season start" (called Critical) |
| AyaySir | BUG-02 | Hint shortcut shows spinner forever in Done state |
| AyaySir | IMP-04 | Hint shortcuts should auto-undo Done Trading |
| AyaySir | IMP-05 | "Done Trading must never be auto-set by the server" |
| Codex Player | (defects) | "Done Trading carrying into the next season" |

The previous round shipped a 📋 Menu recovery button + server-side prompt replay, but those address the *retrieval* path, not the *entry* path. There are two distinct sub-issues:

- **Sub-issue A: Server is auto-setting Done Trading**, either on connect, on season-start, or on some other event. Should never happen without an explicit player click. This is a state-sync bug — `mark_player_ready` is being called when it shouldn't be.
- **Sub-issue B: Once Done is set, there is no Undo path** while time remains on the season clock. Conceptually fine to *have* a Done state, but it should be an *un-set-able* "I'm done early" flag, not a one-way terminator.

These belong in **one focused Codex brief** (§3, brief #1) because they share the same `submit_ready` / `mark_player_ready` code paths.

## 2. ✅ Already fixed

None of the items in this report were addressed by merges after `0.1.0-dev.2026-05-26.5`. The named-options purchase picker (merged at `a2c31cb`, version `.27`) is a different complaint than any reported here.

## 3. 🐛 New Codex briefs proposed

Six briefs, ordered by player impact. Suggested branch names included so the briefs slot cleanly into the existing `codex-tasks/` convention.

### Brief 3.1 — `done-trading-undo-and-auto-set-fix-2026-05-27` (Critical)

Addresses Comet 1 #2, #3, #4, #10, IMP-1; AyaySir BUG-01, BUG-02, IMP-04, IMP-05; Codex Player season-rollover defect. Seven references across three players, called Critical by AyaySir.

- **A) Stop auto-setting Done Trading.** Audit every call site of `mark_player_ready` and `submit_ready(ready=True)`. Identify what's flipping the flag on season-start / connect / state-pull and fix the offending path. The only legitimate setter is the player explicitly clicking "End Turn / Done Trading ✓".
- **B) Add an Undo Done Trading path.** New `UNREADY` action that calls `submit_ready(ready=False)` mid-season. Server-side already supports this (`unmark_player_ready`); just needs the action wiring + UI button + prompt-replay so the player gets their action menu back when they un-done.
- **C) Decision Hints when Done.** Hint shortcut buttons (`_actOnHint` → `_isActionPromptOpen`) should EITHER auto-undo when clicked (preferred per AyaySir IMP-04) OR be hidden entirely while Done. The current "visible but disabled forever" state is the worst of both.
- Tests: state-sync regression covering season transitions; undo path; AI behaviour unchanged.

### Brief 3.2 — `training-expertise-deadlock-2026-05-27` (Critical)

Addresses AyaySir BUG-04 (training requests stuck for 9 seasons because Education needed 1 Expertise), Codex Player "Training dependencies got stuck around Expertise". Two players observed the same total-system deadlock.

Root cause hypothesis: AI Educator can't produce Expertise without `LaboratoryEquipment` and Manufacturer wasn't shipping LabEquipment (which **PR #46 was supposed to fix**, but the playtest predates calibration of that fix in a real game). Either the human-demand scoping kicked AI Manufacturer off LabEquipment, or AI Educator's Expertise pipeline has its own input blocker.

- Trace the full Expertise production chain in an all-AI sim with one human Mining player who has filed training requests.
- Add explicit logging at every input shortage point in the Educator's production action.
- Decide whether **AyaySir IMP-03** (allow requester to supply Educator's missing resources) should ship as part of the fix or as a separate brief.
- Add a system-wide "training pipeline blocked because X" indicator on the requester's dashboard so the player knows whether to wait or take action.

### Brief 3.3 — `loan-and-insurance-consent-bugs-2026-05-27`

Addresses three related Banker-side defects:

- **AyaySir BUG-07** — Insurance policies auto-issued without player consent ("Policy issued" appeared in log, 110 Dp spent without click). Audit auto-confirm paths in the insurance issuance flow.
- **Codex Player** — "App let Banking accept a loan on behalf of the borrower" — same root cause pattern (a side actor auto-confirming for another player).
- **Codex Player** — "Loan rollover broken: 'matures in 1 season' but 'No active loans to roll over'; mature loan defaulted before I could intervene" — separate loan-state-machine bug, but ships in the same brief because all three are loan/insurance integrity issues.

### Brief 3.4 — `event-frequency-cap-2026-05-27`

Addresses Comet 1 #9, Comet 1 IMP-4, AyaySir BUG-08, AyaySir IMP-10.

- 5 consecutive production-halting events in 5 seasons (Comet 1).
- Pandemic + Factory Fire + Infrastructure Damage in consecutive seasons (AyaySir).
- Proposed: max 1 production-halt event per player per year, plus a per-role cooldown. AyaySir suggests "disaster insurance" as a mitigation; deferred unless the cap alone isn't enough.

### Brief 3.5 — `market-bug-cluster-2026-05-27`

Addresses three independent market bugs from Comet 1:

- **#6** — Bid price auto-filled with unexpected values (Food reference 17.18 but bid calculated at 40.00/unit).
- **#8** — FarmMachinery listed at 9 Dp never sold despite a 9 Dp Bid simultaneously present — possible order-matching bug.
- **Codex Player** — "Meals runway: 0" hint said to buy food but only Bids existed, no Asks. Hint stayed even after the requester posted a food Bid.

Each needs separate investigation; one brief because they're all `Market` model / matching logic.

### Brief 3.6 — `training-request-withdraw-by-requester-2026-05-27` (Small)

Addresses AyaySir BUG-05 / IMP-01. The `educator-approval-queue` brief added Reject/Counter from the Educator side; this is the symmetric requester-side action.

- New `WITHDRAW_TRAINING_REQUEST` action keyed by `batch_id`, callable only by the original requester.
- Refunds any seats/dollops that haven't been consumed yet (handled by the existing dispatch-readiness check from PR #37).
- One-page brief — could also be folded as an amendment into `educator-approval-queue-2026-05-26.md` if Codex would prefer.

## 4. 🎨 Claude UI follow-ups

These are all dashboard work. Batch them into one or two passes once the Codex briefs above start landing.

### Pass A — Action panel + Decision Hints (depends on Brief 3.1 to land first)

| Item | From |
|---|---|
| "Undo End Turn" button visible whenever player is in Done state with time remaining | Comet 1 IMP-1, AyaySir IMP-04 |
| Decision Hint buttons link directly to the relevant pre-filtered action (currently they open the bare action) | Comet 1 IMP-5 |
| Capital Catalogue z-index / click-target overlap with Market Buy | Comet 1 #5 |

### Pass B — Market UX

| Item | From |
|---|---|
| Real-time capital affordability indicator in Market Buy (running "Remaining after this order" counter) | Comet 1 #7, IMP-2 |
| Clearer Place Bid vs Buy Now distinction (colour coding, headers, tooltips) | Comet 1 IMP-3 |
| "List at Best Bid" one-click button in Market Sell | Comet 1 IMP-8 |
| Inventory panel shows items currently listed on market ("listed" badge) | Comet 1 IMP-9 |

### Pass C — Dashboard surfaces (small, can ship piecemeal)

| Item | From |
|---|---|
| "Meals runway: 0" prominent warning (flashing red banner / mandatory ack) | Comet 1 IMP-6 |
| Persistent compact leaderboard in sidebar (currently requires scroll) | Comet 1 IMP-10 |
| "Start Game" button + host indicator in waiting room | Comet 1 IMP-12 |
| Production Capacity panel inline blocking reason ("Blocked: no active Technicians" / "missing 0.05 Oil") | AyaySir IMP-06 |
| Public Education Island capacity visibility (slots available, blocking resources) | AyaySir IMP-07 |
| Show Educator resource requirements on the training-request form before submit | AyaySir IMP-02 |
| Banker "Active loans: X / Y" chip (payload already shipped in PR #40) | Carried over from previous cycle |
| Educator drag-reorder queue + inline Reject/Counter + requester decisions badge (payload shipped in PR #41) | Carried over from previous cycle |

### Standalone — Game log readability

Codex Player: "the game log became noisy and hard to scan, especially when old history dominated the page." Suggested: collapse-by-default for prior seasons, sticky "current season" header, search/filter. Small Claude UI follow-up; doesn't depend on engine.

### Standalone — Final game-over screen

AyaySir IMP-09 / Codex Player. Winner announcement + final leaderboard + per-player production/trade summary when the game ends. Currently the session ends abruptly. Probably wants engine support for a `GameOver` payload too — could be a small Codex brief instead.

## 5. ⚖️ Calibration / design conversations

Items that don't have a single right answer yet. Surfacing for your decision before they become briefs.

| # | Item | Source | Suggested resolution |
|---|---|---|---|
| 5.1 | **Workers run out (Manufacturer at zero workforce mid-game)** | Real Human #1 | Already in flight — you flagged this last turn and we discussed lifting `MAX_WORKFORCE_FRACTION_OF_POPULATION` or raising `STARTING_POPULATION`. Real Human's preferred fix is *neither* — instead, a new mechanic to **hire workers from other islands for a fee + PassengerSeats for a fixed duration**. Interesting because it creates a new inter-island contract market. Would be its own brief. |
| 5.2 | **Cash on deposit with the Bank** | Real Human #2 | New feature: deposit cash for 1–3 years at the cost-of-funds rate. Would model real deposit-taking, increases Bank balance-sheet authentically, and ties into the wholesale-funding architecture already in place. Pair with #5.3 below. |
| 5.3 | **Lease default 10 Dp penalty + auto-withdraw from deposits** | Real Human #3 | Depends on #5.2 landing. The penalty pattern is already partially modeled (LeaseStatus.BUYOUT_DEFAULTED). |
| 5.4 | **Reduce Food required per population by 50%** | Real Human #4 | All players ran out of Food late game. Could be a sustenance recalibration (`PEOPLE_PER_MEAL` 10 → 20) or improving Food supply via Kitchen / Fertiliser. Worth investigating whether the late-game crunch is caused by Farmer workforce attrition (linked to #5.1) before changing the basket. |
| 5.5 | **Unmatured loans at game end** | Codex Player balance notes | Scoring question: a 3-year loan written in Year 3 of a 3-year game won't mature. Should we (a) mark-to-market the principal + accrued interest as a Bank asset, (b) write down to NPV, or (c) only count loans that mature in-game? Affects Banker's score visibility. |

## 6. ⏭ Deferred / out of scope

- All "connection lost / reconnection loop" / "server disconnection at end of Year 3" items (Comet 1 #1, AyaySir BUG-06, Codex Player websocket loop, Comet 1 IMP-11). **Excluded per operator note** — server was deliberately stopped at end of session.
- Comet 1 #11 ("Production capacity dropped to max 0 after workers returned from training") — possibly addressed by PR #37 (training-flow-diagnostic) but reported against `.5` which has PR #37 merged. Needs reproduction before opening a brief; logged here so it's not lost. Possible duplicate of the Expertise deadlock (Brief 3.2) — investigate together.
- Comet 1 IMP-7 ("Training request flow too many steps") — UX consolidation but **not blocking**; revisit after Brief 3.6 (requester withdraw) ships and we know the natural shape of the request lifecycle.

## 7. Open questions for the playtester

Before some of the briefs above can be finalised, would help to clarify:

- **AyaySir BUG-07 (insurance auto-purchase):** were the policies issued by the Banker (an automated underwrite-on-eligibility path) or by AyaySir's own client (a UI default-click)? Either is fixable but the brief looks different.
- **Comet 1 #6 (bid price 17.18 vs 40.00):** was this a Place Bid (limit order) at 40.00 against a reference price of 17.18, or did the form actively change the number after submit? Want to know if it's a UI display bug or a real market-side mismatch.
- **Real Human #4 (food reduction):** is the late-game Food crunch felt before or after Brief 3.2 (Expertise deadlock) is fixed? If the deadlock blocks Education → which blocks Farmer training → which blocks Food supply, then 3.2 may resolve the symptom and a sustenance change becomes unnecessary.
