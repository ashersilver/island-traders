# Codex Task — Equity model module (`equity.py`) + valuation math (2026-05-29)

**Owner:** Codex
**Origin:** [Equity / balance-sheet separation plan](../equity-balance-sheet-separation.md). This brief is **Phase 1, the model layer only** — the self-contained cap-table + valuation module that Claude will wire into the engine and UI. Building it as a standalone, fully-unit-tested module lets Codex and Claude work in parallel without touching the same files.

## Goal

Create a new module `island_traders/models/equity.py` containing:

1. The equity constants.
2. A `CapTable` dataclass — who owns how many shares of one island.
3. Pure valuation functions — liquidation value, fair value per share — that take **plain numbers** as input (no `Player`, no `Game`, no engine imports). This keeps the module dependency-free and trivially testable.

Claude consumes this module from `game.py` / `app.py`; **you do not wire it in.** Build the module + its tests, push the branch, stop.

## Branching

- **Base:** `pre-release` (current head, `b040219` or later).
- **Branch name:** `codex/equity-model-module-2026-05-29`
- **Target:** `pre-release`. **Do not merge yourself.** Push and stop; Claude reviews and integrates.

## Spec

### Constants (define in `equity.py`, not `constants.py`, to keep the module self-contained for now; Claude may relocate them on integration)

```python
TOTAL_SHARES: int = 100          # every island has exactly 100 shares
AUCTIONED_SHARES: int = 60       # majority block sold at the opening auction
PUBLIC_HOLDER: str = "public"    # pseudo-holder for the un-sold float
ISLAND_STARTING_CASH: float = 500.0   # treasury each island is seeded with
MIN_SHARE_PRICE: float = 0.01
EARNINGS_MULTIPLE: float = 3.0   # years of net-worth growth capitalised into fair value
VOLATILITY_PENALTY: float = 1.0  # how harshly erratic earnings are discounted
```

### `CapTable`

```python
@dataclass
class CapTable:
    # holder_id -> share count.  Holder ids are strings: a player id rendered
    # as str, or PUBLIC_HOLDER for the float.  Always sums to TOTAL_SHARES.
    shares: dict[str, int]

    @classmethod
    def new_with_majority(cls, owner_id: str) -> "CapTable":
        """Owner gets AUCTIONED_SHARES; the rest is the public float."""
        # owner_id -> 60, PUBLIC_HOLDER -> 40

    def fraction(self, holder_id: str) -> float:
        """holder's share count / TOTAL_SHARES (0.0 if absent)."""

    def held_by(self, holder_id: str) -> int:
        """share count for holder (0 if absent)."""

    def public_float(self) -> int:
        """shares still held by PUBLIC_HOLDER."""

    def transfer(self, frm: str, to: str, n: int) -> None:
        """Move n shares frm -> to. Raise ValueError if frm lacks n shares.
        Drop any holder that reaches 0. Total must stay == TOTAL_SHARES."""

    def player_holders(self) -> dict[str, int]:
        """All non-public holders and their shares."""
```

Invariant to assert in tests: after any `transfer`, `sum(shares.values()) == TOTAL_SHARES`.

### Valuation (pure functions — plain-number inputs only)

```python
def liquidation_value(
    treasury: float,
    inventory_value: float,      # caller marks inventory to market
    capital_book_value: float,   # caller computes from depreciation
    liabilities: float,          # loans + lease buyouts + shareholder loans
) -> float:
    """treasury + inventory_value + capital_book_value - liabilities.
    May be negative (insolvent island)."""

def fair_value(
    liq_value: float,
    net_worth_history: list[float],   # one entry per past year (oldest first)
    *,
    earnings_multiple: float = EARNINGS_MULTIPLE,
    volatility_penalty: float = VOLATILITY_PENALTY,
) -> float:
    """max(liq_value, going_concern).

    growth      = mean of year-over-year diffs of net_worth_history
    volatility  = population stdev of those diffs
    cv          = volatility / max(1.0, abs(growth))
    risk_factor = 1.0 / (1.0 + volatility_penalty * cv)   # in (0, 1]
    going_concern = liq_value + max(0.0, growth) * earnings_multiple * risk_factor

    With < 2 history points there are no diffs: growth=0, volatility=0,
    so fair_value falls back to liq_value.  Never below liq_value."""

def share_price(fair_val: float) -> float:
    """max(MIN_SHARE_PRICE, fair_val / TOTAL_SHARES)."""
```

## In scope
- `island_traders/models/equity.py` (the above).
- `tests/test_models/test_equity.py` — thorough unit tests (see below).

## Out of scope (Claude owns these — do not touch)
- `models/player.py`, `engine/game.py`, `server/app.py`, `server/static/index.html`.
- Wiring the auction to deduct bids / seat the cap table.
- `net_worth` on the player, dividends, buyouts, cross-island buy-ins.
- Relocating constants into `constants.py`.

## Tests to include (`tests/test_models/test_equity.py`)
- `new_with_majority` seats 60/40 and totals 100.
- `fraction` / `held_by` / `public_float` correctness, including absent holders.
- `transfer` moves shares, drops zeroed holders, preserves the 100 total, and raises on over-transfer.
- `liquidation_value` arithmetic incl. a negative (insolvent) case.
- `fair_value`:
  - empty / single-element history → equals `liq_value`.
  - steady positive growth → returns > `liq_value` (premium applied).
  - same average growth but **higher volatility** → returns a **lower** fair value than the steady case (risk discount bites).
  - negative growth → falls back to `liq_value` (no premium, never below floor).
- `share_price` floors at `MIN_SHARE_PRICE` and divides by `TOTAL_SHARES`.

## Seam note (parallel-merge rule)
This module is a **leaf** — nothing in the tree imports it yet, so it cannot conflict with Claude's parallel equity-integration work. Per the durable merge-order rule: Codex merges this leaf module first; Claude (merging second) adds the imports/wiring. Keep the public names above stable so Claude's integration compiles against them.
