# Codex Task — Banker wholesale funding: lower reserves + per-Banker loan cap (2026-05-26)

**Owner:** Codex
**Origin:** 2026-05-26 playtest (`0.1.0-dev.2026-05-26`). User report: *"Finance is never able to lend more than its own capital + 50%. Finance should be able to borrow from an imaginary lender at the current interest funding rates."*

The wholesale-funding architecture **already exists** — `engine/turn.py:_fund_bank_external_portion` borrows the non-own-capital portion of every loan from a synthetic `lender_id=-1` at the posted funding rate, and creates a real depositor obligation the Bank must repay at maturity. What's blocking the user is the **reserve ratio**: currently 50% (`MBA_RESERVE_RATIO_BASE`) below 3 MBA-qualified Banker Managers, 20% (`MBA_RESERVE_RATIO_QUALIFIED`) at/above. At 50%, max loan = own capital × 2, which matches the "own capital + 50%" feel the user described.

The user has decided we should keep the wholesale-funding mechanism intact but loosen it significantly, with a **per-Banker active-loan headcount cap** as the new soft ceiling so we don't drift into infinite-leverage degeneracy.

## Goal

Two related changes:

1. **Lower the reserve ratios.** Both the base and the MBA-qualified thresholds drop. Concretely:
   - `MBA_RESERVE_RATIO_BASE: float = 0.05`  (was `0.50`)
   - `MBA_RESERVE_RATIO_QUALIFIED: float = 0.02`  (was `0.20`) — optional, see calibration note below
   - The 3-MBA threshold (`MBA_QUALIFIED_THRESHOLD`) stays at 3 for now.

2. **Cap active loans per qualified Banker.** A Bank with N qualified Banker Managers (Manager-tier `Profession.BANKER` workers, MBA flag not required for this cap) can hold at most `2 × N` simultaneously **active** loans on its book (status `ACTIVE` in `LoanLedger`). Synthetic depositor loans (`lender_id=-1`) **do not count** against this cap — they're the funding side, not the lending side. Loans that have been repaid or defaulted free up a slot.
   - If `N = 0` (no Banker Managers on roster), the Bank can hold at most 1 active loan (one "starter" slot so a fresh game isn't completely locked out).
   - If `N = 2`, max 4 active loans; if `N = 3`, max 6; etc.

## Branching

- **Base:** `pre-release` at `ba74a59` (current head — Kitchen + training-diagnostic briefs merged) or later.
- **Branch name:** `codex/banker-wholesale-funding-2026-05-26`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec

### Reserve ratio

In `island_traders/constants.py`:

```python
MBA_RESERVE_RATIO_BASE: float = 0.05       # was 0.50  — wholesale funding fills the rest
MBA_RESERVE_RATIO_QUALIFIED: float = 0.02  # was 0.20  — qualified team gets a small further break
```

No code changes needed in `_banker_reserve_ratio` itself — it already reads these constants.

### Loan-count cap

Add a new helper in `engine/turn.py` (next to `_banker_reserve_ratio`):

```python
def _banker_active_loan_cap(self, banker: Player) -> int:
    """Max simultaneous active loans the Bank can hold on its book.

    Cap = max(1, 2 × number_of_Banker_Manager_workers).  Synthetic
    depositor loans (lender_id=-1) are funding obligations, not
    lending — they do not count toward the cap.
    """
    n_bankers = banker.workforce.count_profession(Profession.BANKER.value)
    return max(1, 2 * n_bankers)

def _banker_active_loan_count(self, banker: Player) -> int:
    """Active loans where this banker is the lender (excludes depositor obligations)."""
    return sum(
        1 for loan in self.loan_ledger.loans
        if loan.lender_id == banker.player_id
        and loan.status == LoanStatus.ACTIVE
    )
```

Then in `_action_offer_loan` (and the Banker-auto-quote path used by AI), before calling `_fund_bank_external_portion`, check:

```python
cap = self._banker_active_loan_cap(player)
active = self._banker_active_loan_count(player)
if active >= cap:
    self.io.print(
        f"  Cannot issue loan: Bank already at active-loan cap "
        f"({active}/{cap}). Wait for a loan to be repaid, or train another "
        f"Banker Manager to raise the cap."
    )
    return
```

Surface `active` and `cap` in the Banker player payload (game state) so the dashboard can show "Loans: 3 / 6 active" without an extra round-trip.

### AI Banker behaviour

`engine/ai.py` already uses `_banker_reserve_ratio`. After the cap is added, the AI Banker's loan-offer routine must also respect the cap — if it's at cap, AI should decline new loan opportunities for that season rather than crashing or silently failing.

## Tests

- `tests/test_engine/test_banker_loans.py` (or similar) — new tests:
  - Bank with 1 Banker Manager + 0 active loans can issue 2 loans, third is refused with the cap message.
  - Bank with 0 Banker Managers can issue exactly 1 active loan.
  - Repaid / defaulted loans free up a slot (issue, repay, issue another → succeeds).
  - Depositor loans (`lender_id=-1`) do not count toward the cap.
  - Reserve math: at 5% reserve, a 100 Dp loan locks 5 Dp of own capital and sources 95 Dp externally.
  - At 2% reserve (3+ MBA Bankers), a 100 Dp loan locks 2 Dp and sources 98 Dp.

## Acceptance criteria

- Reserve ratios lowered to 5% / 2% in `constants.py`.
- `_banker_active_loan_cap` and `_banker_active_loan_count` helpers exist and are checked in both human (`_action_offer_loan`) and AI loan-offer paths.
- Cap respects "depositor loans don't count" semantics.
- Calibration sweep (1000g seed 42 + 4-seed sweep) shows all 7 roles still in [12 – 18 %] win rate. Banker has more headroom now — if it goes hot, recalibrate by raising `BANKER_INTEREST_MARGIN` (or whatever the margin constant is) before raising the reserve ratios back.
- Full test suite green at the new baseline count (429 + new tests).
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/banker-wholesale-funding-2026-05-26` block.

## UI follow-up (Claude will handle separately)

- Surface "Active loans: X / Y" on the Banker's player card.
- Show the new reserve ratio in the loan-offer dialog (e.g. "Reserve 5%: bank locks 5 Dp own + 95 Dp wholesale at 4.2% posted").
- When the AI Banker declines a loan request due to the cap, show the requester a clear reason.

## Out of scope

- Variable wholesale funding rate based on Bank leverage (could come later if calibration shows runaway behaviour).
- Insurance-deposit pools (separate future feature).
- Per-loan collateral checks (the existing `banker_quote_rate` already prices in borrower risk).
