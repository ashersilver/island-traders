# Brief — Loan Rate Negotiation & Capital-Financing Premium (2026-07-04)

**Status: APPROVED (Ash 2026-07-05) — implementation-ready.**
**§2 premium resolved: +5.0 percentage points, take-it-or-leave-it (Ash 2026-07-05).**
**Suggested owner:** Codex (engine) ; Claude (negotiation UI reuse).
**Base off:** `origin/pre-release` @ `9938d48`, APP_VERSION `0.1.5-dev.2026-06-22.18`.
**Follows:** `_README.md`. Interacts with `business-cycle-severity-events-2026-07-04.md`
(posted_funding_rates becomes cycle-driven; this brief consumes, doesn't define it).

## Problem

`_action_take_loan` (turn.py:4049) quotes `banker_quote_rate` = posted cost +
fixed 2% spread + risk premium, then a bare confirm — take it or leave it, no
negotiation, no Banker agency on the spread. Capital-order financing
(`issue_capital_finance_loan`) prices off the same standard curve, so financing
at the order desk is identical to walking into the bank — no convenience
premium, no reason to negotiate a real loan first.

## Design

### 1. Rate negotiation on standard loans

Extend the take-loan flow with **one counter round** (mirrors the existing
deal/counter-offer patterns — reuse `request_summary` + counter prompt UI):

1. Borrower picks principal + term (unchanged). Banker's opening quote =
   `banker_quote_rate` (cost + 2% + risk) — unchanged.
2. Borrower may **Accept / Counter / Walk away**. Counter must lie in
   `[posted_funding_rate + 0.005, opening_quote)`.
3. Banker responds:
   - **Human Banker**: gets a review prompt (principal, term, risk factors,
     floor shown) → Accept / Counter-once / Decline. Their counter must lie in
     `(borrower_counter, opening_quote]`. Borrower then accepts or walks.
   - **AI Banker**: accepts any counter ≥ `cost + 0.01 + risk_premium`;
     otherwise counters at the midpoint of borrower-counter and opening quote,
     floored at `cost + 0.0075`. Deterministic, uses the turn RNG for nothing.
4. Self-lending (borrower is the Banker) skips negotiation (unchanged path).
5. Everything else — MBA gating, reserve split, ledger — unchanged.

New constants: `LOAN_COUNTER_FLOOR_SPREAD = 0.005`,
`AI_BANKER_ACCEPT_SPREAD = 0.01`, `AI_BANKER_COUNTER_FLOOR = 0.0075`.

### 2. Capital-financing premium (take it or leave it)

Financing a capital order becomes the *convenience-priced* path:

- Rate = **posted 3-year funding rate + `CAPITAL_FINANCE_PREMIUM_PTS`**,
  default **5.0 percentage points** (posted 3yr 6.5% → financed 11.5%).
- **No negotiation** at the order desk — explicitly take-it-or-leave-it. The
  order modal shows: financed rate, equivalent posted 3-year rate, and the
  hint "negotiate a standard loan at the Bank for a better rate".
- Term stays as today (`min(3, max(1, maintenance_term_years))` else 2), but
  the premium applies regardless of term — it prices convenience, not tenor.
- Referral fee (2% to Banker) unchanged.

> **Resolved (Ash 2026-07-05):** confirmed as **+5 percentage points**
> (6.5% → 11.5%), take-it-or-leave-it. Constant remains tunable.

### 3. AI behaviour

`engine/ai.py`: heuristic borrowers accept the opening quote (no behaviour
change — keeps sim baseline comparable); LLM agents get the counter option via
the normal prompt payloads (`request_summary` carries floor/quote so the model
can reason). Sim flag `--negotiate-loans` (off by default) enables AI counters
at `cost + 0.015` for A/B calibration runs.

## Files

models/loan.py (constants, helper for AI accept/counter), engine/turn.py
(`_action_take_loan` negotiation loop, `issue_capital_finance_loan` premium),
server/ws_adapter.py + static UI (counter prompts — reuse existing counter
patterns), engine/ai.py (flagged behaviour), tests.

## Acceptance criteria

1. Borrower counter below floor is rejected client- and server-side; valid
   counter reaches the Banker; AI Banker accept/counter matches §1.3 exactly
   (unit tests on the boundary spreads).
2. Human-Banker decline ends the flow with no ledger entry.
3. Financed capital order books a loan at posted-3yr + 5.0pts; ack payload
   carries the rate; order modal shows both rates (UI check).
4. Full pytest; **1000-game seed-42 sim** with default flags: role shares all
   within ±1pt of baseline (AI accepts opening quotes; financing premium only
   binds when sim AI finances, which it currently doesn't) — this brief must
   NOT move the economy by itself. A/B run with `--negotiate-loans` quoted in
   the PR for information.

## Out of scope

Cycle-driven posted rates (P1.4), lending-capacity caps (already live via
MBA/reserve), insurance pricing.
