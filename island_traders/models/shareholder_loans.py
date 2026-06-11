"""Shareholder loan bookkeeping helpers.

This module is a pure model leaf. It records principal owed by an island to
shareholder lenders, but it does not move cash between players or treasuries.
"""
from __future__ import annotations

from typing import Iterable


SHAREHOLDER_LOAN_RATE: float = 0.0


def lend(loans: dict[str, float], lender_id: str, amount: float) -> None:
    """Record new principal owed to lender_id in place."""
    if amount <= 0:
        raise ValueError("loan amount must be positive")
    lender = str(lender_id)
    loans[lender] = loans.get(lender, 0.0) + amount


def repay(loans: dict[str, float], lender_id: str, amount: float) -> float:
    """Repay up to amount of principal owed to lender_id in place."""
    if amount <= 0:
        raise ValueError("repayment amount must be positive")

    lender = str(lender_id)
    owed = loans.get(lender, 0.0)
    paid = min(amount, owed)
    if paid == 0:
        return 0.0

    remaining = owed - paid
    if remaining == 0:
        del loans[lender]
    else:
        loans[lender] = remaining
    return paid


def total_owed(loans: dict[str, float]) -> float:
    """Return all shareholder-loan principal owed by one island."""
    return sum(loans.values())


def receivable(island_loan_books: Iterable[dict[str, float]], lender_id: str) -> float:
    """Return principal owed to lender_id across many island loan books."""
    lender = str(lender_id)
    return sum(loans.get(lender, 0.0) for loans in island_loan_books)
