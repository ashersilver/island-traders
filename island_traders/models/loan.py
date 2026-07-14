from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from ..constants import CURRENCY_SYMBOL
from ..engine.cycle import BusinessCycleSnapshot, fallback_phase_for_date

LOAN_COUNTER_FLOOR_SPREAD: float = 0.005
AI_BANKER_ACCEPT_SPREAD: float = 0.01
AI_BANKER_COUNTER_FLOOR: float = 0.0075
CAPITAL_FINANCE_PREMIUM_PTS: float = 0.05


def posted_funding_rates(
    year: int,
    season: int,
    cycle: BusinessCycleSnapshot | str | None = None,
) -> dict[int, float]:
    """Bank cost-of-funds curve for 1/2/3-year money.

    Rates move through the shared BusinessCycle table. Callers inside a Game
    should pass the current cycle snapshot; standalone callers fall back to a
    deterministic cycle position for the date.
    """
    if cycle is None:
        snapshot = fallback_phase_for_date(year, season)
        modifier = snapshot.rate_modifier
    elif isinstance(cycle, str):
        snapshot = fallback_phase_for_date(year, season)
        from ..engine.cycle import PHASES
        modifier = PHASES.get(cycle, PHASES[snapshot.phase]).rate_modifier
    else:
        modifier = cycle.rate_modifier
    base = 0.05 + modifier
    return {
        1: round(base, 4),
        2: round(base + 0.0075, 4),
        3: round(base + 0.015, 4),
    }


def borrower_risk_premium(borrower, loan_ledger: "LoanLedger", principal: float) -> float:
    """Small risk add-on above cost+spread based on borrower leverage."""
    debt = loan_ledger.outstanding_debt(borrower.player_id)
    premium = 0.0
    if debt > 0:
        premium += 0.01
    if principal > borrower.dollops:
        premium += 0.01
    if debt > max(borrower.dollops, 1.0):
        premium += 0.02
    return round(premium, 4)


def banker_quote_rate(
    borrower,
    loan_ledger: "LoanLedger",
    principal: float,
    term_years: int,
    year: int,
    season: int,
    cycle: BusinessCycleSnapshot | str | None = None,
) -> float:
    rates = posted_funding_rates(year, season, cycle=cycle)
    cost = rates.get(term_years, rates[1])
    return round(cost + 0.02 + borrower_risk_premium(borrower, loan_ledger, principal), 4)


def loan_counter_floor_rate(posted_rate: float) -> float:
    return round(posted_rate + LOAN_COUNTER_FLOOR_SPREAD, 4)


def ai_banker_accept_rate(posted_rate: float, risk_premium: float) -> float:
    return round(posted_rate + AI_BANKER_ACCEPT_SPREAD + risk_premium, 4)


def ai_banker_counter_rate(
    borrower_counter: float,
    opening_quote: float,
    posted_rate: float,
) -> float:
    floor = posted_rate + AI_BANKER_COUNTER_FLOOR
    return round(max(floor, (borrower_counter + opening_quote) / 2), 4)


def capital_finance_rate(
    year: int,
    season: int,
    cycle: BusinessCycleSnapshot | str | None = None,
) -> float:
    return round(
        posted_funding_rates(year, season, cycle=cycle)[3]
        + CAPITAL_FINANCE_PREMIUM_PTS,
        4,
    )


class CapitalFinanceError(Exception):
    """Raised when a capital order cannot be financed via the Bank.

    Carries a buyer-facing message; callers should fall back to cash settlement.
    """


class LoanStatus(Enum):
    ACTIVE = "active"
    REPAID = "repaid"
    DEFAULTED = "defaulted"
    ROLLED_OVER = "rolled_over"  # superseded by a new loan via rollover


@dataclass
class Loan:
    """Bullet bond: borrow principal now, repay principal + interest after the term."""
    loan_id: int
    borrower_id: int
    lender_id: int
    principal: float
    interest_rate: float          # e.g. 0.10 for 10%
    issued_year: int
    issued_season: int
    maturity_year: int
    maturity_season: int
    status: LoanStatus = LoanStatus.ACTIVE
    term_years: int = 1
    # If this loan was created by rolling over a previous one, the original
    # loan's id is recorded here for traceability.
    rolled_over_from_loan_id: int | None = None
    # Phase D — capital-reserve bookkeeping (all default 0.0 for
    # backward compat / for synthetic depositor loans where they don't
    # apply).  See economy-lifecycle-2026-05.md §3.
    own_committed: float = 0.0     # bank's own capital locked into this loan
    external_funded: float = 0.0   # depositor portion (principal − own)
    posted_at_issue: float = 0.0   # base/posted funding rate at issuance
    reserve_ratio_at_issue: float = 0.0  # r at the time the loan was issued
    collateral_item_id: str | None = None
    secured: bool = False

    @property
    def repayment_amount(self) -> float:
        return round(self.principal * (1 + self.interest_rate), 1)

    @property
    def interest_amount(self) -> float:
        return round(self.principal * self.interest_rate, 1)

    def is_due(self, year: int, season: int) -> bool:
        return (year, season) >= (self.maturity_year, self.maturity_season)

    def summary(self, borrower_name: str, lender_name: str) -> str:
        sym = CURRENCY_SYMBOL
        return (
            f"Loan #{self.loan_id}: {borrower_name} borrowed {self.principal:.1f} {sym} "
            f"from {lender_name} at {self.interest_rate*100:.0f}% "
            f"for {self.term_years} year(s) "
            f"(repay {self.repayment_amount:.1f} {sym} in Y{self.maturity_year+1} "
            f"S{self.maturity_season+1})"
            f"{' secured by ' + self.collateral_item_id if self.secured and self.collateral_item_id else ''} "
            f"[{self.status.value}]"
        )


@dataclass
class LoanLedger:
    loans: list[Loan] = field(default_factory=list)
    _next_id: int = 0

    def create_loan(
        self,
        borrower_id: int,
        lender_id: int,
        principal: float,
        interest_rate: float,
        issued_year: int,
        issued_season: int,
        term_years: int = 1,
        own_committed: float = 0.0,
        external_funded: float = 0.0,
        posted_at_issue: float = 0.0,
        reserve_ratio_at_issue: float = 0.0,
        collateral_item_id: str | None = None,
        secured: bool = False,
    ) -> Loan:
        maturity_year = issued_year + term_years
        maturity_season = issued_season
        loan = Loan(
            loan_id=self._next_id,
            borrower_id=borrower_id,
            lender_id=lender_id,
            principal=principal,
            interest_rate=interest_rate,
            issued_year=issued_year,
            issued_season=issued_season,
            maturity_year=maturity_year,
            maturity_season=maturity_season,
            term_years=term_years,
            own_committed=own_committed,
            external_funded=external_funded,
            posted_at_issue=posted_at_issue,
            reserve_ratio_at_issue=reserve_ratio_at_issue,
            collateral_item_id=collateral_item_id,
            secured=secured,
        )
        self.loans.append(loan)
        self._next_id += 1
        return loan

    def active_loans_for(self, player_id: int) -> list[Loan]:
        return [
            l for l in self.loans
            if l.status == LoanStatus.ACTIVE
            and (l.borrower_id == player_id or l.lender_id == player_id)
        ]

    def rollover_loan(
        self,
        loan_id: int,
        new_rate: float,
        new_term_years: int,
        year: int,
        season: int,
    ) -> Loan:
        """Refinance an active loan into a new one (Issue #6).

        The old loan is marked ROLLED_OVER and a new loan is created with
        principal equal to the old loan's repayment_amount (principal + accrued
        interest), at the new rate/term, issued at the current year/season.
        No cash changes hands at rollover — the new loan's "advance" exactly
        covers the old loan's repayment.

        Raises ValueError if the loan is unknown, not ACTIVE, or the new term
        is outside the supported 1-3 year range.
        """
        if new_term_years < 1 or new_term_years > 3:
            raise ValueError(f"new_term_years must be 1-3, got {new_term_years}")
        old = next((l for l in self.loans if l.loan_id == loan_id), None)
        if old is None:
            raise ValueError(f"No loan with id {loan_id}")
        if old.status != LoanStatus.ACTIVE:
            raise ValueError(f"Loan {loan_id} is {old.status.value}, cannot roll over")
        new_principal = old.repayment_amount
        old.status = LoanStatus.ROLLED_OVER
        new_loan = self.create_loan(
            borrower_id=old.borrower_id,
            lender_id=old.lender_id,
            principal=new_principal,
            interest_rate=new_rate,
            issued_year=year,
            issued_season=season,
            term_years=new_term_years,
        )
        new_loan.rolled_over_from_loan_id = old.loan_id
        return new_loan

    def outstanding_debt(self, player_id: int) -> float:
        return sum(
            l.repayment_amount for l in self.loans
            if l.status == LoanStatus.ACTIVE and l.borrower_id == player_id
        )

    def loans_receivable(self, player_id: int) -> float:
        return sum(
            l.repayment_amount for l in self.loans
            if l.status == LoanStatus.ACTIVE
            and l.lender_id == player_id
            and l.borrower_id != player_id
        )

    def due_loans(self, year: int, season: int) -> list[Loan]:
        return [
            l for l in self.loans
            if l.status == LoanStatus.ACTIVE and l.is_due(year, season)
        ]

    def all_loans(self) -> list[Loan]:
        return list(self.loans)
