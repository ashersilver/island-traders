from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from ..constants import CURRENCY_SYMBOL


class LoanStatus(Enum):
    ACTIVE = "active"
    REPAID = "repaid"
    DEFAULTED = "defaulted"


@dataclass
class Loan:
    """Bullet bond: borrow principal now, repay principal + interest after 4 seasons."""
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
            f"(repay {self.repayment_amount:.1f} {sym} in Y{self.maturity_year+1} "
            f"S{self.maturity_season+1}) [{self.status.value}]"
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
    ) -> Loan:
        maturity_year = issued_year + 1
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

    def outstanding_debt(self, player_id: int) -> float:
        return sum(
            l.repayment_amount for l in self.loans
            if l.status == LoanStatus.ACTIVE and l.borrower_id == player_id
        )

    def loans_receivable(self, player_id: int) -> float:
        return sum(
            l.repayment_amount for l in self.loans
            if l.status == LoanStatus.ACTIVE and l.lender_id == player_id
        )

    def due_loans(self, year: int, season: int) -> list[Loan]:
        return [
            l for l in self.loans
            if l.status == LoanStatus.ACTIVE and l.is_due(year, season)
        ]

    def all_loans(self) -> list[Loan]:
        return list(self.loans)
