"""Equity cap tables and valuation helpers.

This module is intentionally a leaf: it depends only on the standard library
and takes plain numbers rather than engine or player objects.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass


TOTAL_SHARES: int = 100
AUCTIONED_SHARES: int = 60
PUBLIC_HOLDER: str = "public"
ISLAND_STARTING_CASH: float = 500.0
MIN_SHARE_PRICE: float = 0.01
EARNINGS_MULTIPLE: float = 3.0
VOLATILITY_PENALTY: float = 1.0


@dataclass
class CapTable:
    """Who owns how many shares of one island."""

    shares: dict[str, int]

    def __post_init__(self) -> None:
        self.shares = {str(holder): int(count) for holder, count in self.shares.items()}
        if any(count <= 0 for count in self.shares.values()):
            raise ValueError("share counts must be positive")
        if sum(self.shares.values()) != TOTAL_SHARES:
            raise ValueError(f"cap table must total {TOTAL_SHARES} shares")

    @classmethod
    def new_with_majority(cls, owner_id: str) -> "CapTable":
        """Owner gets the opening majority block; the rest remains public."""
        return cls(
            shares={
                str(owner_id): AUCTIONED_SHARES,
                PUBLIC_HOLDER: TOTAL_SHARES - AUCTIONED_SHARES,
            }
        )

    def fraction(self, holder_id: str) -> float:
        """Return holder's ownership fraction, or 0.0 when absent."""
        return self.held_by(holder_id) / TOTAL_SHARES

    def held_by(self, holder_id: str) -> int:
        """Return the number of shares held by holder_id."""
        return self.shares.get(str(holder_id), 0)

    def public_float(self) -> int:
        """Return the unsold public float."""
        return self.held_by(PUBLIC_HOLDER)

    def transfer(self, frm: str, to: str, n: int) -> None:
        """Move n shares from frm to to, preserving the fixed share total."""
        frm = str(frm)
        to = str(to)
        n = int(n)
        if n <= 0:
            raise ValueError("transfer count must be positive")
        if self.held_by(frm) < n:
            raise ValueError(f"{frm} lacks {n} shares")
        if frm == to:
            return

        self.shares[frm] -= n
        if self.shares[frm] == 0:
            del self.shares[frm]
        self.shares[to] = self.shares.get(to, 0) + n

        if sum(self.shares.values()) != TOTAL_SHARES:
            raise ValueError(f"cap table must total {TOTAL_SHARES} shares")

    def player_holders(self) -> dict[str, int]:
        """Return all non-public holders and their share counts."""
        return {holder: count for holder, count in self.shares.items() if holder != PUBLIC_HOLDER}

    def to_dict(self) -> dict[str, int]:
        """Return a JSON-friendly copy of the cap table."""
        return dict(self.shares)

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "CapTable":
        """Rebuild a cap table from a serialized share mapping."""
        return cls(shares=dict(data))


def liquidation_value(
    treasury: float,
    inventory_value: float,
    capital_book_value: float,
    liabilities: float,
) -> float:
    """Return treasury plus assets less liabilities, allowing insolvency."""
    return treasury + inventory_value + capital_book_value - liabilities


def fair_value(
    liq_value: float,
    net_worth_history: list[float],
    *,
    earnings_multiple: float = EARNINGS_MULTIPLE,
    volatility_penalty: float = VOLATILITY_PENALTY,
) -> float:
    """Return liquidation value plus any risk-adjusted going-concern premium."""
    diffs = [
        current - previous
        for previous, current in zip(net_worth_history, net_worth_history[1:])
    ]
    if not diffs:
        return liq_value

    growth = statistics.fmean(diffs)
    volatility = statistics.pstdev(diffs)
    cv = volatility / max(1.0, abs(growth))
    risk_factor = 1.0 / (1.0 + volatility_penalty * cv)
    going_concern = liq_value + max(0.0, growth) * earnings_multiple * risk_factor
    return max(liq_value, going_concern)


def share_price(fair_val: float) -> float:
    """Return fair value per share with a minimum tradable floor."""
    return max(MIN_SHARE_PRICE, fair_val / TOTAL_SHARES)
