"""Shareholder-loan bookkeeping — owner-to-island loans.

NOTE (2026-05-29): This module is owned by Codex per
`requirements/codex-tasks/shareholder-loans-model-2026-05-29.md`. The version
here is a Claude-side integration reference so the Phase-2b wiring compiles and
is testable before Codex's branch lands. On merge, Codex's module (with its own
unit tests) is authoritative — the public names below are the fixed seam both
sides code against.

Pure dict/number bookkeeping: no Player / engine imports, so it stays a leaf.
A shareholder loan moves cash investor -> island treasury and is recorded here
as a liability the island owes back to that investor. This module owns only the
math; cash movement (personal_cash / treasury) is the engine's job.
"""
from __future__ import annotations

from typing import Iterable

# Interest rate on owner shareholder loans. 0% for now (owner-financing);
# tunable later. Bank loans (models/loan.py) are a separate instrument.
SHAREHOLDER_LOAN_RATE: float = 0.0


def lend(loans: dict[str, float], lender_id: str, amount: float) -> None:
    """Record `amount` of new principal owed to `lender_id` (in place)."""
    if amount <= 0:
        raise ValueError("lend amount must be positive")
    key = str(lender_id)
    loans[key] = loans.get(key, 0.0) + float(amount)


def repay(loans: dict[str, float], lender_id: str, amount: float) -> float:
    """Reduce principal owed to `lender_id` by up to `amount`. Returns repaid."""
    if amount <= 0:
        raise ValueError("repay amount must be positive")
    key = str(lender_id)
    owed = loans.get(key, 0.0)
    repaid = min(float(amount), owed)
    remaining = owed - repaid
    if remaining <= 0:
        loans.pop(key, None)
    else:
        loans[key] = remaining
    return repaid


def total_owed(loans: dict[str, float]) -> float:
    """Sum of all principal owed by one island (its shareholder-loan liability)."""
    return sum(loans.values())


def receivable(island_loan_books: Iterable[dict[str, float]], lender_id: str) -> float:
    """Total principal owed to `lender_id` across many islands' loan books."""
    key = str(lender_id)
    return sum(book.get(key, 0.0) for book in island_loan_books)
