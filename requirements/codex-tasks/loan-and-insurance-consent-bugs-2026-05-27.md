# Codex Task — Loan + insurance consent bugs (2026-05-27)

**Owner:** Codex
**Origin:** [Triage `0.1.0-dev.2026-05-26.5`](../playtest-feedback/triage-0.1.0-dev.2026-05-26.5.md) §3.3. Three independent Banker-side defects that share a common pattern: a side actor (the Banker, or an auto-confirm path) takes an action on another player's behalf without explicit consent, OR the loan state machine fires the wrong transition.

- **AyaySir BUG-07** *(Medium)* — Insurance policies auto-issued without player confirmation. "Life Insurance (50 Dp) and Medical Insurance (60 Dp) were issued automatically mid-session ('Policy issued' appeared in the log without a player-initiated action), spending 110 Dp without explicit consent."
- **Codex Player defect** — "The app let Banking accept a loan on behalf of the borrower. Useful for testing, but in multiplayer that is a consent/authority bug."
- **Codex Player defect** — "Loan rollover was confusing or broken. A loan showing 'matures in 1 season' still produced 'No active loans to roll over,' and an earlier mature loan defaulted before I could intervene."

The first two are consent / authority bugs. The third is a loan-state-machine bug but ships in this brief because all three are loan/insurance integrity issues with overlapping code paths in `engine/turn.py`.

## Goal

Three fixes:

1. **Insurance auto-issue audit.** Find what path issued the policies for AyaySir without a click. Likely candidates: an "auto-buy basic insurance" default in the Banker AI's sell-insurance loop, or a stale prompt that resolved to YES on a state-replay. Remove the offending path; require explicit per-policy player confirmation.

2. **Loan-acceptance authority check.** The Banker writes the offer but the *borrower* must accept. Audit `_action_offer_loan` and any AI-acceptance path to ensure a human borrower's acceptance only comes from a confirmation the borrower's client actually sent, never from a Banker-side default or AI substitution when a real human player is the borrower.

3. **Loan rollover + early-default state-machine fix.** Two sub-issues from Codex Player:
   - A loan that shows "matures in 1 season" in the UI is not findable by `_action_rollover_loan` ("No active loans to roll over"). State mismatch: UI display vs `loan_ledger.eligible_for_rollover` (or whatever the rollover candidate query is).
   - "An earlier mature loan defaulted before I could intervene" — a loan marked DEFAULTED before the borrower's turn started, with no opportunity to repay/rollover. The default check (`_process_loan_repayments`) probably fires too early in the season cycle, before the borrower has had a chance to act.

## Branching

- **Base:** `pre-release` at `8b6fd37` (current head) or later.
- **Branch name:** `codex/loan-and-insurance-consent-bugs-2026-05-27`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec

### Fix 1: insurance auto-issue

- Trace every call to `InsurancePolicy(...)` constructor and to `Player.insurance_policies.append(...)`. Identify any path that doesn't gate on an explicit `io.confirm(...)` from the **buyer** (not the seller).
- In `_action_sell_insurance` confirm the buyer's confirmation is being awaited via the buyer's IO channel, not via the seller's. Real bug suspect: when buyer is human and seller is also human, the prompt may be routing to the seller's adapter.
- Add a regression test: AI Banker attempting to sell insurance to a human buyer must produce a prompt on the buyer's IO channel; if the buyer's confirm returns False, no policy is created and no Dp moves.

### Fix 2: loan-acceptance authority

- Same audit pattern: every call to `LoanLedger.create_loan(...)` from an offer-loan path must be gated on an explicit confirm from the **borrower**, with the prompt routed to the borrower's IO channel.
- AI borrower acceptance is fine (`rate <= 0.15` heuristic at `turn.py:2382` and similar) — the bug is when the borrower is a *human* and somehow the engine fills in a confirmation for them.
- Regression test: human borrower, AI Banker offers a loan. If the human's IO confirm returns False, no loan is created.

### Fix 3a: rollover candidate query

- `_action_rollover_loan` at `turn.py:2772` filters active loans for the player. Walk through that filter against a loan with `seasons_to_maturity == 1` and identify why it's being excluded from the candidate list.
- Likely bug: rollover requires `seasons_to_maturity > 0` strictly, but the UI display "matures in 1 season" rounds *down* from a more granular tick count that's already at 0. Or the filter requires "must mature in current year" semantics that exclude same-season-maturity loans.
- Fix the filter or the UI display so they agree. Add a regression test: a loan with the UI label "matures in 1 season" must appear in the rollover candidate list.

### Fix 3b: early default

- `_process_loan_repayments` is called at line 138 in the season main loop. Check the call order: is it firing BEFORE the borrower's action turn opens for the season?
- Expected order: borrower's action turn → opportunity to repay or rollover → THEN end-of-season repayment processing → default fires only if repayment never happened.
- If the order is wrong, swap it or split repayment processing into two phases: a "due notice" early-season pass that surfaces a "Loan #N matures this season; repay or rollover" prompt to the borrower, then a "final settlement" late-season pass that defaults only if the borrower didn't act.

### Files to touch (suggested)

- `island_traders/engine/turn.py` — `_action_sell_insurance`, `_action_offer_loan`, `_action_rollover_loan`, `_process_loan_repayments`.
- `island_traders/models/loan.py` — rollover candidate query (whatever method `_action_rollover_loan` calls).
- Tests: new `tests/test_engine/test_loan_insurance_consent.py` covering all three fixes.

### UI follow-up (Claude separate)

- Mid-season "Loan #N matures this season — repay or rollover" prompt visible on the borrower's dashboard the moment Fix 3b's due-notice phase fires.
- Insurance Manage panel showing currently active policies (also resolves Codex Player's "Insurance UI showed 'None' even after policies sold" defect — same data, just needs surfacing).

## Tests

- `tests/test_engine/test_loan_insurance_consent.py` (new):
  - Insurance auto-issue: AI Banker → human buyer with `confirm = False` returns no policy, no Dp movement.
  - Insurance auto-issue: state-replay (e.g. WS reconnect mid-prompt) doesn't resolve to YES.
  - Loan acceptance authority: AI Banker → human borrower with `confirm = False` creates no loan.
  - Loan acceptance authority: AI Banker → AI borrower respects existing AI heuristic (regression check on the legitimate path).
  - Rollover candidate: a loan with "matures in 1 season" UI label appears in `_action_rollover_loan` candidates.
  - Early default: a borrower with sufficient cash who plans to repay during their action turn must be given the chance — `_process_loan_repayments` must not default them before their turn.

## Acceptance criteria

- All three fixes land independently and demonstrably (each has a dedicated regression test).
- Diagnostic note in the PR description: which exact call path was issuing the auto-policies and the auto-acceptances? (Useful for the next playtest cycle's debrief.)
- No silent state changes — every Dp movement and every state transition logs the actor and the reason.
- Full test suite green (463 + new tests).
- Calibration sweep (1000g seed 42 + 4-seed sweep): all roles still in [12 – 18%] band.
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/loan-and-insurance-consent-bugs-2026-05-27` block.

## Out of scope

- Cash-on-deposit feature (Real Human #2 — separate brief).
- Lease-default penalty mechanics (Real Human #3 — depends on cash-on-deposit; separate brief).
- Unmatured loans at game-end scoring question (Codex Player balance notes — design conversation, not a defect).
- Insurance UI surfacing (Codex Player "Insurance UI showed 'None'") — that's the Claude UI follow-up above, not engine work.
