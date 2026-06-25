# Brief — "Student Loan": bank-finance a training request (2026-06-25)

**Owner:** Codex (training + bank finance engine + tests). **Process:** see `_README.md`.
**Base off:** `origin/pre-release` (fetch first; quote tip + APP_VERSION in handoff). Own
worktree; push your branch. **Frontend is Claude's** (checkbox + cash line on the form).

## Why

When making a training request, the requester should be able to tick **"Student Loan"** to
**borrow the educator fee from the Bank** instead of paying cash up front — mirroring the
existing capital-order financing (Capital Orders II).

## Reuse (don't reinvent)

The capital finance loan path already does exactly this shape for capital orders:
`TurnManager.issue_capital_finance_loan(...)`, `MANUFACTURER_FINANCE_REFERRAL_RATE`,
`CapitalFinanceError`, and the bank-reserve logic (`engine/turn.py` ~3726+, `models/loan.py`).
Generalise / parallel it for training rather than writing a new loan system.

## Spec

1. **Financed training request.** A training request flagged `financing: true` borrows the
   `dollops_to_educator` (the educator fee; decide with the user whether transport cost is
   included — default: **fee only**) from the Bank: requester treasury stays flat, the Educator
   is paid in full at approval/settlement, a loan is recorded against the requester.
2. **Cash fallback.** No Banker / bank at cap → fall back to paying cash if the requester can
   afford it, else reject with a clear message (same pattern as capital finance).
3. **Settle at the right moment.** The loan is drawn when the training is **approved/dispatched**
   (not at request time), so a rejected/withdrawn request creates no debt.
4. **Expose state.** Add the financing flag to the training request payload + `game_state` so the
   UI can show it; surface the loan in the requester's loan book.

## Frontend (Claude, after merge)
- A **"Student Loan (finance via Bank)"** checkbox on the training request form, plus a
  **"Cash available: N Dp"** line (the capital order form just got the same — mirror it).

## Tests
- Financed request: requester treasury flat after approval; Educator paid; loan outstanding.
- No Banker: falls back to cash; broke + no bank → rejected, no debt.
- Rejected/withdrawn financed request → no loan created.
- Full `pytest` green; quote the count. Open question for PR: include transport in the loan?
