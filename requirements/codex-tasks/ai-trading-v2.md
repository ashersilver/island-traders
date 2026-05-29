# Codex Task — AI Trading v2 (loans, INVEST, dynamic pricing)

**Owner:** Codex
**Pairs with:** the shipped `codex/ai-trading` work (commit `4a65a9a`, 2026-05-17) which already covered offers / bids / arbitrage / deal-valuation. This brief is the *second pass* — finance-side actions the original brief deliberately deferred.
**Status of the original brief:** complete and merged. The five behaviours it scoped (lists offers, places bids, Transporter air tickets, cross-island arbitrage, deal valuation via last-deal / best-offer / formula) are all in `island_traders/engine/ai.py` and covered by `tests/test_engine/test_ai.py` (6 passing).

## Goal

Teach the heuristic AI to participate in the finance + investment lifecycle it currently ignores. Right now the AI:

- **Banker** sells base-premium insurance proactively (`_ai_offer_insurance`) but **never offers loans**, never renews policies, never cancels.
- **Borrowers** never accept loan offers, never use `TAKE_LOAN`, and never `ROLLOVER_LOAN` near maturity.
- **Every island** ignores `INVEST` — opening-catalogue items they passed on in the Investing Phase stay unclaimed forever in AI-only games.
- **Pricing** is a static `AI_OFFER_MARKUP` against the formula price — no season-on-season adjustment.

The first three of those are visible quality-of-play issues in AI-only sim runs and the upcoming balance calibration. The fourth is a smaller polish item.

## Branching

- **Base:** `pre-release` at `ddb3151` ("Merge claude/bug-action-menu-race", 2026-05-24). Run `git fetch origin && git checkout -b codex/ai-trading-v2 origin/pre-release` to start.
- **Branch name:** `codex/ai-trading-v2`
- **Target for merge:** `pre-release` — **do not merge yourself.** Push the branch, open a PR, and stop. Claude will review and signal merge timing (see "When to wait" below).

## What has shipped since the original AI-trading brief

The original brief was drafted 2026-05-15. Substantial work has landed since then — relevant context so you don't repeat fixed work or step on Claude's domain:

- **Economy Lifecycle Phases A–D** — worker retirement (Phase B), universal capital lifespan + maintenance (Phase C), Banker capital-reserve / MBA-leverage model (Phase D1). The MBA gate is **critical for loan logic** — see "MBA reserve gate" below.
- **Order override rule** (2026-05-21) — a new bid or ask now **cancels** the player's prior orders on that resource. There is no cumulative depth per (player, resource) on the book. AI offer/bid logic must therefore not assume it can stack orders.
- **Market matcher fix** (2026-05-21) — bids and asks now cross on price (not exact equality) and support partial fills. AI logic should not require exact matches.
- **60% workforce cap** — `Player.available_unskilled` returns `max(0, ⌊0.60 × population⌋ − workforce.count)`. AI recruitment plans must respect this.
- **UX review phases 1–6** — purely client-side except for Codex's Phase 1 server payload (action metadata / `training_pipeline` / hidden `Finance` from market / structured `decision_hints.target`). **Hide Finance from any market state your code reads** (it's already filtered out of `get_game_state`, but the engine still has the enum value).
- **Training-return bug fix** (2026-05-24) — self-trained workers now properly graduate. Doesn't change AI behaviour, but if your AI starts requesting training, the returns will work.
- **WS reconnect race fix** (2026-05-24) — `GameManager._ws_lock` + identity-aware `unregister_ws`. Pure server-side; doesn't affect engine.

**Baseline:** suite is **360 passing** on `ddb3151`. Final tally after this branch should be 360 + however many tests you add.

## Scope — five concrete items

### 1. AI Banker proactively offers loans

Pattern: mirror the existing `_ai_offer_insurance` helper. After production, the Banker AI scans other AI players (skip humans, skip self) and offers a loan to any borrower whose `dollops` is below a "capital-short" threshold and whose `outstanding_debt` is below a sane ceiling.

**Loan parameters to issue:**
- Principal: enough to cover ~1 season of input cost for the borrower's primary role (rough heuristic from `PRODUCTION_INPUTS` × current market prices is fine).
- Term: 1 year (the cheapest case — `posted_funding_rates` already returns indicative 1/2/3-year rates; pick the 1-year).
- Rate: use `banker_quote_rate(...)` from `island_traders/models/loan.py`. Don't undercut — use the function's output.

**MBA reserve gate.** Before issuing, check the Banker can afford the reserve portion. The reserve ratio is `0.50` with fewer than 3 MBA Banker Managers, `0.20` at/above. Helpers exist:

- `TurnManager._mba_banker_count(banker) -> int`
- `TurnManager._banker_reserve_ratio(banker) -> float`

These live on `TurnManager` — you may want to lift them to a helper module if the AI shouldn't depend on `TurnManager`, or accept a small `engine/turn.py` touch (acceptable — coordinate via the PR description).

Use the existing `_action_offer_loan` engine path if you can call it directly; otherwise replicate its constraint check. Look at `turn.py` around line 1811 for the canonical issuance flow (capital deduction, ledger entry, etc.).

**Acceptance test:** in a 2-AI sim (Banker + Farmer) where Farmer starts with `dollops` low enough to be capital-short, the Banker issues a loan within the first 2 seasons. Confirm with `loan_ledger.active_loans_for(farmer.player_id)`.

### 2. AI borrowers take loans when capital-short

Pattern: in `take_turn`, before the production block, if `player.dollops < some_threshold` and there's no active loan from this player as borrower, the AI uses `TAKE_LOAN` or accepts an offered loan.

Acceptance test: in a 2-AI sim where a Banker is offering loans, a capital-short Farmer ends up with a loan in their ledger.

### 3. AI rolls over loans near maturity when it can't repay

When a borrower's loan is due in ≤ 1 season AND the borrower can't afford the `repayment_amount`, dispatch `ROLLOVER_LOAN` via the engine action. The rollover semantics already shipped (#6): old loan → `ROLLED_OVER`, new loan inherits repayment as principal at the fresh `banker_quote_rate`.

Acceptance test: time-travel a sim to one season before maturity with the borrower's dollops below the repayment threshold; the AI rolls over rather than letting the loan default or drain.

### 4. AI uses INVEST mid-game for unclaimed catalogue items

`TurnAction.INVEST` (`_action_invest` in `turn.py`) lets a player take an opening-catalogue item they didn't claim during the Investing Phase. AI islands currently never use it, leaving free / cheap capital improvements on the table.

Heuristic: at the start of the turn, if `player.dollops > 2 × cheapest_unclaimed_catalogue_item.cost`, claim the cheapest item whose role matches the player's role. Cap at one Invest action per turn (the engine permits multiple but one is enough — avoid AI binge-spending).

Use `island_traders/models/capacity.py::items_for_role` + `CAPITAL_CATALOGUE` to enumerate the catalogue; cross-reference with `player.capital_inventory` to find unclaimed items.

Acceptance test: in a single-season AI sim, an AI Farmer with starting `dollops = 1500` (≥ 2× any catalogue item) claims at least one catalogue item via INVEST.

### 5. Dynamic offer markup based on previous-season fill rate *(optional — drop if scope tight)*

`AI_OFFER_MARKUP` is constant. Replace with a per-(player, resource) state that **decreases** the markup when last season's offer didn't clear, **increases** it when it did. Bounded — e.g. `[0.85, 1.30]` × formula price.

The state can live on `AIStrategy` (per-instance dict) — it doesn't need to persist across game saves.

Acceptance test: in a sim where an AI lists an offer in S0 that doesn't clear, the S1 re-listing price is lower than the S0 price.

## Out of scope

- Any file under `island_traders/server/static/` — Claude's UI domain.
- `island_traders/server/app.py` and `ws_adapter.py` — Claude's server / wiring domain.
- The order matching engine in `island_traders/models/market.py` — read-only; flag any bug you find via the PR rather than landing it.
- The loan / insurance models themselves — extend the AI's *use* of them, don't change the contracts. The `loan.py` math is balanced against the Phase D1 reserve gate; touch only with coordination.
- Game balance: don't tune `INSURANCE_BASE_PREMIUM`, `MBA_RESERVE_RATIO_*`, `posted_funding_rates`, or any economy constants. Calibration is the separate `balance-calibration-2026-05.md` task and will follow this one.
- Sim runner CLI flags / output format — extend if you genuinely need it, but flag in PR.

## Tests required

Add to `tests/test_engine/test_ai.py` (or a new `test_ai_finance.py` if cleaner):

1. `test_ai_banker_offers_loan_to_capital_short_ai_borrower` — covers item 1.
2. `test_ai_banker_does_not_offer_loan_when_reserve_short` — Banker with <0.50 × principal in dollops doesn't issue.
3. `test_ai_borrower_accepts_loan_when_capital_short` — covers item 2.
4. `test_ai_rollover_loan_when_cannot_repay_at_maturity` — covers item 3.
5. `test_ai_invests_in_unclaimed_catalogue_item` — covers item 4.
6. (If you do item 5) `test_ai_lowers_offer_markup_after_unfilled_season` — covers dynamic pricing.

Run the full suite. **Bar is the full suite green plus the new tests.**

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

Expected: ≥ `360 + N` passing where N is the number of new tests you add.

## When to stop

Push the branch when **all** of these are true:

- Items 1–4 implemented (item 5 optional — flag in PR if you skipped it).
- All new tests written and passing.
- Full `pytest` suite green.
- `RELEASE_NOTES.md` has a new `### codex/ai-trading-v2` section under `## Unreleased` describing what landed + the new test count.
- Signed-off commits (`git commit --signoff`).

**Do not:**

- Modify any client-side file or the WS reconnect plumbing.
- Touch game-balance constants.
- Merge the branch into `pre-release` yourself.
- Tag a release or modify `master`.
- Start sim calibration — that's the separate brief at `requirements/codex-tasks/balance-calibration-2026-05.md` and **should run after this lands** so AI behaviour is settled first.

## What to push

```bash
git push -u origin codex/ai-trading-v2
```

Open a PR from `codex/ai-trading-v2` → `pre-release` with:

- Summary of the 4 (or 5) items.
- New test count: 360 → N.
- An explicit note on whether item 5 (dynamic pricing) is in or deferred.
- The `RELEASE_NOTES.md` excerpt for reviewer convenience.

## When to wait for merge

After pushing:

1. **Wait** for Claude to review the PR.
2. **Wait** for Claude to merge — there's been a steady cadence of Claude UI work landing on `pre-release`, and the convention is one merge at a time.
3. If Claude requests changes, land them as follow-up commits on the same branch (`codex/ai-trading-v2`) — don't open a second branch.
4. Once merged, this brief is done. The next Codex task is `balance-calibration-2026-05.md` (release blocker for v0.1.0).

## Reference

- **Existing AI strategy:** `island_traders/engine/ai.py::AIStrategy`
- **Existing insurance helper (pattern to mirror for loans):** `_ai_offer_insurance` (line ~39)
- **Existing deal-evaluation helpers:** `_last_deal_price`, `_valuation_price`, `_deal_value_for_acceptor`, `_review_pending_deals`
- **Loan model:** `island_traders/models/loan.py` — `posted_funding_rates`, `borrower_risk_premium`, `banker_quote_rate`, `LoanLedger.create_loan / rollover_loan / active_loans_for / outstanding_debt / due_loans`
- **Engine loan actions:** `island_traders/engine/turn.py` — `_action_offer_loan` (line ~1811), `_action_take_loan`, `_action_rollover_loan`
- **MBA reserve helpers:** `TurnManager._mba_banker_count`, `_banker_reserve_ratio` (line ~1763)
- **INVEST action:** `TurnAction.INVEST`, `_action_invest` in `turn.py`
- **Capital catalogue:** `island_traders/constants_capacity.py::CAPITAL_CATALOGUE` + `island_traders/models/capacity.py::items_for_role`
- **Existing AI tests (do not break):** `tests/test_engine/test_ai.py` (6 tests)
- **Sim runner:** `island_traders/simulation/runner.py` — `--seeds` flag is useful for cross-seed verification
- **Related TODO entries:** `TODO.md` → "AI Trading Behaviour" section (note: the four hand-off items there are largely covered by the original brief; this v2 picks up the finance + invest gap)
