"""Equity model — cap table + valuation math for the balance-sheet split.

NOTE (2026-05-29): This module is owned by Codex per
`requirements/codex-tasks/equity-model-module-2026-05-29.md`. The version here
is a Claude-side integration reference so the Phase-1 wiring (player fields,
net-worth scoring) compiles and is testable before Codex's branch lands. On
merge, Codex's module (which carries its own unit tests) is authoritative — the
public names below are the fixed seam both sides code against.

Pure data + math: no imports from Player / Game / engine, so it stays a leaf.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

# --- Constants -------------------------------------------------------------
TOTAL_SHARES: int = 100            # every island has exactly 100 shares
AUCTIONED_SHARES: int = 60         # majority block sold at the opening auction
PUBLIC_HOLDER: str = "public"      # pseudo-holder for the un-sold float
ISLAND_STARTING_CASH: float = 500.0  # treasury each island is seeded with
MIN_SHARE_PRICE: float = 0.01
EARNINGS_MULTIPLE: float = 3.0     # years of net-worth growth capitalised in fair value
VOLATILITY_PENALTY: float = 1.0    # how harshly erratic earnings are discounted


# --- Cap table -------------------------------------------------------------
@dataclass
class CapTable:
    """Who owns how many shares of one island. Always sums to TOTAL_SHARES.

    Holder ids are strings: a player id rendered as ``str``, or
    ``PUBLIC_HOLDER`` for the float.
    """

    shares: dict[str, int] = field(default_factory=dict)

    @classmethod
    def new_with_majority(cls, owner_id: str) -> "CapTable":
        """Owner gets ``AUCTIONED_SHARES``; the rest is the public float."""
        owner_id = str(owner_id)
        public = TOTAL_SHARES - AUCTIONED_SHARES
        shares = {owner_id: AUCTIONED_SHARES}
        if public > 0:
            shares[PUBLIC_HOLDER] = public
        return cls(shares=shares)

    def fraction(self, holder_id: str) -> float:
        return self.held_by(holder_id) / TOTAL_SHARES

    def held_by(self, holder_id: str) -> int:
        return self.shares.get(str(holder_id), 0)

    def public_float(self) -> int:
        return self.shares.get(PUBLIC_HOLDER, 0)

    def transfer(self, frm: str, to: str, n: int) -> None:
        frm, to = str(frm), str(to)
        if n <= 0:
            raise ValueError("transfer count must be positive")
        have = self.shares.get(frm, 0)
        if have < n:
            raise ValueError(f"{frm} holds {have} shares, cannot transfer {n}")
        self.shares[frm] = have - n
        if self.shares[frm] == 0:
            del self.shares[frm]
        self.shares[to] = self.shares.get(to, 0) + n

    def player_holders(self) -> dict[str, int]:
        """All non-public holders and their shares."""
        return {h: n for h, n in self.shares.items() if h != PUBLIC_HOLDER}

    def to_dict(self) -> dict[str, int]:
        return dict(self.shares)

    @classmethod
    def from_dict(cls, data: dict[str, int] | None) -> "CapTable":
        return cls(shares=dict(data or {}))


# --- Valuation (pure functions, plain-number inputs only) ------------------
def liquidation_value(
    treasury: float,
    inventory_value: float,
    capital_book_value: float,
    liabilities: float,
) -> float:
    """treasury + inventory + capital book value − liabilities. May be negative."""
    return treasury + inventory_value + capital_book_value - liabilities


def fair_value(
    liq_value: float,
    net_worth_history: list[float],
    *,
    earnings_multiple: float = EARNINGS_MULTIPLE,
    volatility_penalty: float = VOLATILITY_PENALTY,
) -> float:
    """max(liq_value, going_concern). Falls back to liq_value with thin history."""
    diffs = [
        net_worth_history[i] - net_worth_history[i - 1]
        for i in range(1, len(net_worth_history))
    ]
    if not diffs:
        return liq_value
    growth = statistics.fmean(diffs)
    volatility = statistics.pstdev(diffs) if len(diffs) > 1 else 0.0
    cv = volatility / max(1.0, abs(growth))
    risk_factor = 1.0 / (1.0 + volatility_penalty * cv)
    going_concern = liq_value + max(0.0, growth) * earnings_multiple * risk_factor
    return max(liq_value, going_concern)


def share_price(fair_val: float) -> float:
    return max(MIN_SHARE_PRICE, fair_val / TOTAL_SHARES)
