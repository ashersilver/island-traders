# Wave 6 — Banking: early repayment, consolidation, fixed deposits (2026-07-13)

Source: Ash's defect list of 2026-07-13, items 1, 2, 8. Grounded against the
loan subsystem on master (post-#212). Sequenced smallest-first. Each task
must pass the standard same-seed sim gate before merge (re-baseline vs the
post-#212 expertise-floor baseline).

## Context: what exists today

- Loans are bullet bonds on a single game-level `LoanLedger`
  (`models/loan.py:111-276`, stored `engine/game.py:210`); repayment =
  `principal*(1+rate)` at maturity only, auto-deducted end-of-season
  (`engine/turn.py:3998`, called at `turn.py:239`); shortfall ⇒ partial pay +
  `DEFAULTED` + collateral repossession (`turn.py:4032`).
- **There is no manual repay-bank-loan action at all** (`repay_shareholder_loan`
  is a different subsystem).
- **Rollover already exists**: `LoanLedger.rollover_loan` (`loan.py:214-252`)
  + `_action_rollover_loan` (`turn.py:4624`) refinance ONE active loan into a
  new 1–3yr loan (new principal = old repayment amount, no cash moves,
  `ROLLED_OVER` status + `rolled_over_from_loan_id` trace).
- Negotiation is inline single-counter (`_negotiate_standard_loan_rate`,
  `turn.py:4410-4517`): borrower accept/counter/walk; AI banker uses
  accept/counter spreads (`loan.py:7-9,68`); human banker routed via
  `set_active_player`.
- Bank reserve: each non-self loan splits into `own_committed = r*principal`
  (r = 5%, or 2% with ≥3 MBA managers — `turn.py:4082`, `constants.py:677-680`)
  and `external_funded`, the latter funded by a **synthetic depositor loan**
  with `lender_id=-1` at the posted funding rate (`turn.py:4117-4150`).
- Market rate primitive: `posted_funding_rates(year, season, cycle)` =
  `0.05 + cycle.rate_modifier` (+0.75pt 2yr, +1.5pt 3yr) (`loan.py:13-38`).

---

## Task 6.1 — Loan consolidation (item 2) — SMALL

Rollover of a single loan is done; add **multi-loan consolidation**:

- New action `consolidate_loans` (borrower-side, appears when ≥2 active loans
  with the same lender): multi-select loans, new principal = Σ selected
  `repayment_amount`, choose new 1–3yr term, re-quote rate on the consolidated
  principal via `banker_quote_rate`, single accept/counter/walk round.
- Mark each source loan `ROLLED_OVER` with `rolled_over_from_loan_id` set to
  the new loan (extend the trace to a list, or keep first-id + a note field).
- Reserve + active-loan-cap checks (`turn.py:4088-4201`) run on the NEW
  consolidated loan; the freed `own_committed` from retired loans releases
  first so consolidation never fails for reserve reasons it itself cures.
- UI: loans detail cards (`index.html:5424-5449`) get a "Consolidate…" entry
  when eligible.

## Task 6.2 — Early repayment with negotiable prepayment penalty (item 1) — MEDIUM

- New action `repay_loan_early` on any active loan the player borrowed:
  pay `principal + accrued interest to date + penalty` before maturity.
  Accrual: linear fraction of `interest_amount` by seasons elapsed / term.
- **Penalty is at the bank's discretion and negotiable**: default ask =
  2% of outstanding principal (tunable constant). Reuse the inline
  single-counter pattern from `_negotiate_standard_loan_rate` (`turn.py:4410`):
  borrower sees quote → accept / counter / walk; AI banker accept/counter via
  new spreads; human banker routed via `set_active_player`. Penalty paid to
  the lender (Banker dollops) on settlement; loan marked `REPAID` early.
- **External-leg rule (must be explicit):** early repayment does NOT retire
  the bank's synthetic depositor obligation (`lender_id=-1`) early — the bank
  keeps paying its funding leg to maturity. The penalty exists to compensate
  exactly this carry, so AI-banker minimum acceptable penalty ≈ remaining
  funding-leg interest minus reinvestment at the current posted rate (floor 0).
- Releases the loan's `own_committed` reserve immediately on repayment.
- UI: "Repay early…" on the loan card; show quote breakdown
  (principal / accrued interest / penalty).

## Task 6.3 — Fixed deposits (item 8) — MEDIUM-LARGE

- New product: any non-Banker player places dollops on fixed deposit with the
  bank for 1–3 years at **posted market rate − 2pt** (floor 0.5%), using
  `posted_funding_rates` for the market leg. Model as an inverted loan on the
  existing ledger (depositor = lender, bank = borrower) or a new `Deposit`
  dataclass — prefer reusing `LoanLedger` mechanics (status lifecycle,
  serialisation `game.py:1660-1683` already round-trips loans).
- At maturity: auto-credit principal + interest from bank dollops
  (end-of-season pass alongside `_process_loan_repayments`); if the bank
  cannot pay, treat like borrower default (bank defaults — reputational/QoL
  hook optional, but do not silently haircut).
- **Early redemption penalty**: same negotiable mechanic as Task 6.2 (default
  ask 2% of principal, single counter round, banker discretion).
- **Reserve interaction (the constraint Ash flagged):** deposits MAY be
  counted toward the bank's reserve capacity for `own_committed` on new loans.
  If a deposit is currently backing reserve (i.e., bank free cash minus
  committed reserve would go negative without it), early redemption is
  **refused** with a clear reason — not penalised, refused. Track with a
  `reserve_locked` computed check at redemption time; no per-deposit flag.
- UI: bank panel gets "Fixed deposits" (place / view / redeem-early); loans
  tile shows deposits with maturity countdown, mirroring the loan cards.

---

Sim gate for the wave: 3 same-seed sims, all-AI; assert (a) no season-end
crash, (b) bank never goes cash-negative from deposit maturities, (c) net
worth dispersion within ±10% of the post-#212 baseline. Log a calibration
note if the Banker's mean net worth moves >3pt (deposits are a new profit
lever for players and a new liability for the bank).
