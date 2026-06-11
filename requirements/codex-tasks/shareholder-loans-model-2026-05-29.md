# Codex Task — Shareholder-loan model leaf (`shareholder_loans.py`) (2026-05-29)

**Owner:** Codex
**Origin:** [Equity Phase 2b + flip brief §7](../equity-phase2b-flip-2026-05-29.md).
This is the **pure model leaf** for owner-to-island shareholder loans. Claude
wires it into the engine/server/UI in parallel. Building it as a standalone,
dependency-free module (plain dicts/numbers — **no `Player`/engine imports**)
keeps it a leaf, so it cannot conflict with Claude's wiring.

## Goal

Create `island_traders/models/shareholder_loans.py` with a constant and four
pure helper functions that operate on a plain `dict[str, float]` mapping
`lender_id -> principal owed`. A shareholder loan moves cash from an investor
into the island treasury and is recorded as a liability the island owes back to
that investor; this module owns only the **bookkeeping math**, not the cash
movement (Claude moves `personal_cash`/`treasury`).

Build the module + its tests, push the branch, **stop** (do not merge / open a PR).

## Branching

- **Base:** `pre-release` (current head, `b449bcc` or later).
- **Branch name:** `codex/shareholder-loans-model-2026-05-29`
- **Target:** `pre-release`. **Do not merge yourself.** Push and stop; Claude
  reviews and integrates (Codex's leaf merges first, Claude's wiring second).

## Spec — `island_traders/models/shareholder_loans.py`

```python
from __future__ import annotations
from typing import Iterable

# Interest rate on owner shareholder loans. 0% for now (owner-financing);
# tunable later. Bank loans (models/loan.py) are a separate instrument and are
# NOT affected by this module.
SHAREHOLDER_LOAN_RATE: float = 0.0


def lend(loans: dict[str, float], lender_id: str, amount: float) -> None:
    """Record `amount` of new principal owed to `lender_id` (in place).

    Raises ValueError if amount <= 0. Coerces lender_id to str. Adds to any
    existing principal for that lender."""


def repay(loans: dict[str, float], lender_id: str, amount: float) -> float:
    """Reduce principal owed to `lender_id` by up to `amount` (in place).

    Repays min(amount, currently_owed). Drops the key entirely when it reaches
    0. Returns the amount actually repaid. Raises ValueError if amount <= 0.
    A lender not present owes 0 -> repays 0."""


def total_owed(loans: dict[str, float]) -> float:
    """Sum of all principal owed by one island (its shareholder-loan liability)."""


def receivable(island_loan_books: Iterable[dict[str, float]], lender_id: str) -> float:
    """Total principal owed to `lender_id` across many islands' loan books.

    `island_loan_books` is an iterable of per-island `loans` dicts. Returns the
    sum of what each book owes `lender_id` (the lender's receivable asset)."""
```

### Behavioural notes
- All amounts are floats; treat ids as strings (`str(id)`).
- `lend` then `repay` of the same amount must leave `loans` exactly as it
  started (empty dict if it was empty) — i.e. the key is removed at 0, not left
  as `{"x": 0.0}`.
- Never let principal go negative; `repay` caps at the owed amount.
- Keep it pure: mutate the dict passed in (for `lend`/`repay`), return numbers
  for `total_owed`/`receivable`. No imports beyond `typing`.

## In scope
- `island_traders/models/shareholder_loans.py` (the above).
- `tests/test_models/test_shareholder_loans.py` — thorough unit tests.

## Out of scope (Claude owns — do NOT touch)
- `models/player.py` (the `shareholder_loans` field lives there; Claude adds it).
- `engine/game.py`, `server/app.py`, `server/static/index.html`.
- Moving any actual cash (`personal_cash` / `dollops` / treasury) — that's
  Claude's wiring. This module is bookkeeping only.
- `equity.py` (already merged; unchanged).

## Tests to include (`tests/test_models/test_shareholder_loans.py`)
- `lend` adds principal; multiple `lend`s for the same lender accumulate.
- `lend` with amount <= 0 raises; non-str id is coerced.
- `repay` reduces principal; **lend X then repay X leaves an empty dict** (key
  dropped, not `{"x": 0.0}`).
- `repay` more than owed repays only what's owed and returns that; over-repay
  doesn't go negative; repaying an absent lender returns 0.
- `repay` with amount <= 0 raises.
- `total_owed` sums multiple lenders.
- `receivable` sums one lender's principal across several island books, ignoring
  books that don't owe them.
- `SHAREHOLDER_LOAN_RATE == 0.0`.

## Seam note (parallel-merge rule)
This module is a **leaf** — nothing imports it until Claude's wiring lands, and
Claude does **not** edit this file. Per the durable merge-order rule, Codex
merges this leaf first; Claude (merging second) adds the `shareholder_loans`
field to `Player` and calls these helpers. Keep the public names/signatures
above stable so Claude's wiring compiles against them.
