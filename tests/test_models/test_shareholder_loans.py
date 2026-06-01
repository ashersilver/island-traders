from __future__ import annotations

import pytest

from island_traders.models.shareholder_loans import (
    SHAREHOLDER_LOAN_RATE,
    lend,
    receivable,
    repay,
    total_owed,
)


def test_lend_adds_principal_and_accumulates_for_same_lender():
    loans: dict[str, float] = {}

    lend(loans, "alice", 25.0)
    lend(loans, "alice", 15.5)

    assert loans == {"alice": 40.5}


def test_lend_rejects_non_positive_amounts():
    loans: dict[str, float] = {}

    with pytest.raises(ValueError):
        lend(loans, "alice", 0.0)
    with pytest.raises(ValueError):
        lend(loans, "alice", -1.0)
    assert loans == {}


def test_lend_coerces_lender_id_to_string():
    loans: dict[str, float] = {}

    lend(loans, 7, 10.0)

    assert loans == {"7": 10.0}


def test_repay_reduces_principal_and_returns_amount_paid():
    loans = {"alice": 40.0}

    paid = repay(loans, "alice", 12.5)

    assert paid == 12.5
    assert loans == {"alice": 27.5}


def test_lend_then_repay_same_amount_leaves_empty_dict():
    loans: dict[str, float] = {}

    lend(loans, "alice", 40.0)
    paid = repay(loans, "alice", 40.0)

    assert paid == 40.0
    assert loans == {}


def test_repay_more_than_owed_caps_payment_and_drops_key():
    loans = {"alice": 10.0}

    paid = repay(loans, "alice", 25.0)

    assert paid == 10.0
    assert loans == {}


def test_repay_absent_lender_returns_zero_and_does_not_mutate():
    loans = {"alice": 10.0}

    paid = repay(loans, "bob", 5.0)

    assert paid == 0.0
    assert loans == {"alice": 10.0}


def test_repay_rejects_non_positive_amounts():
    loans = {"alice": 10.0}

    with pytest.raises(ValueError):
        repay(loans, "alice", 0.0)
    with pytest.raises(ValueError):
        repay(loans, "alice", -1.0)
    assert loans == {"alice": 10.0}


def test_repay_coerces_lender_id_to_string():
    loans = {"7": 10.0}

    paid = repay(loans, 7, 4.0)

    assert paid == 4.0
    assert loans == {"7": 6.0}


def test_total_owed_sums_multiple_lenders():
    assert total_owed({"alice": 10.0, "bob": 12.5, "carol": 2.5}) == 25.0


def test_receivable_sums_lender_across_island_books():
    books = [
        {"alice": 10.0, "bob": 5.0},
        {"alice": 7.5},
        {"carol": 99.0},
    ]

    assert receivable(books, "alice") == 17.5
    assert receivable(books, "bob") == 5.0
    assert receivable(books, "missing") == 0.0


def test_receivable_coerces_lender_id_to_string():
    books = [{"7": 3.0}, {7: 100.0}, {"8": 2.0}]

    assert receivable(books, 7) == 3.0


def test_shareholder_loan_rate_is_zero_percent():
    assert SHAREHOLDER_LOAN_RATE == 0.0
