# Codex Task — AI Trading Behaviour

**Goal:** Make the heuristic AI player behave actively on the market so
that human players don't have to push trades onto AI islands.  AI islands
should place bids on their inputs, list offers for their outputs, and
evaluate cross-island arbitrage opportunities.

## Background

Live-play feedback (2026-05-15): "the AI behavior is too passive / narrow
after production.  Current workaround is to propose a trade that forces
the AI to accept a deal instead of relying on it to list useful offers."

The heuristic `AIStrategy` (in `island_traders/engine/ai.py`) is consulted
when an AI island takes its turn.  Today it produces and may take a few
defensive actions, but it doesn't proactively place bids/offers on the
market.  Humans must propose deals to get anything moving.

This causes two related problems in 7-player or multi-AI games:

1. AI islands hoard inventory rather than circulating it
2. The Transporter AI specifically may produce `PassengerSeats`
   (air tickets) but never list them for sale, which **silently blocks
   training** (training requires PassengerSeats to ferry workers to the
   Education Island)

## Branch

- **Base:** `pre-release` (latest at HEAD on `origin`)
- **Branch name:** `codex/ai-trading` (use the `codex/` prefix to keep
  branches visually distinct from Claude's `claude/` work)
- **Target for merge:** `pre-release`

## Files in scope

- `island_traders/engine/ai.py` — **primary work surface** (the
  `AIStrategy` class)
- A new `island_traders/engine/ai_trading.py` is fine if you want to
  extract the trading logic into its own module (recommended)
- `island_traders/models/market.py` — read-only unless you find a real
  bug; flag any change you'd make rather than landing it
- `tests/test_engine/test_ai.py` — add tests
- `tests/test_engine/test_ai_trading.py` — new test file if you split
  the module
- `tests/test_simulation/` — extend if you want a regression guard on
  market activity rates
- `RELEASE_NOTES.md` — add a `### codex/ai-trading` section before merge

## Files OUT of scope (Claude is actively working on these)

- `island_traders/server/` (entire directory)
- `island_traders/engine/turn.py` — only touch if you need a tiny
  hook for AI trade actions; coordinate first
- `island_traders/models/loan.py`, `models/insurance.py`,
  `models/profession.py`
- `island_traders/constants.py` (unless you find an outright bug)
- `RULES.md`, `README.md`

If you discover something that requires touching files in the OUT-of-scope
list, please leave a note in `RELEASE_NOTES.md` and coordinate before
merging.

## Concrete behaviours to add

### 1. AI lists offers for surplus outputs
After production each season, an AI island should list **most of its
fresh output** (e.g. 70-90% of new production) for sale on the market
at a reasonable price.  Reasonable = formula price ± a small markup;
land at a value that other AIs are likely to lift.

Acceptance test: in a 7-AI simulation, by season 2 every producing island
should have at least one standing offer.

### 2. AI places bids for inputs it's short on
When an AI inspects its inventory and sees an input it'll need next
season (per `PRODUCTION_INPUTS`), it should place a bid at or near
the formula price.

Acceptance test: in a 7-AI simulation, an AI Farmer with 0 Farm
Machinery should place a bid for at least 1 Farm Machinery on its turn.

### 3. Transporter AI lists PassengerSeats
**Specific high-value sub-task** — the Transporter AI must list
PassengerSeats (air tickets) for sale.  Training requires them, and
they're currently produced-then-hoarded.

Acceptance test: a regression test confirming that after one season of
production, an AI Transporter has a standing PassengerSeats offer.

### 4. Cross-island arbitrage / opportunistic deals
AI islands should evaluate "would I make money by buying X cheap and
reselling it" trades.  Example from the playtest: Mining can trade Ore
+ cash to Education, and Education may resell the Ore for profit or
hold it until worthwhile bids appear.

Heuristic suggestion: compute expected resale price = last-deal price
(or best current offer if no deals yet — see the "Item valuation" TODO).
If a bid - cost > threshold, take the trade.

Acceptance test: a unit test demonstrating that the AI takes a deal
when it's profitable and rejects it when it isn't.

### 5. Deal valuation uses last-deal / best-offer
Today the AI uses formula price to evaluate deals.  Switch to:
- **Last deal price** if there's been a recent trade for the resource
- Otherwise **current best offer price**
- Fall back to formula price only if neither exists

This is a TODO item already captured in `TODO.md` under "Financial
Model" — implementing it here is fine.

## Acceptance criteria

- ✅ A 1000-game AI-only simulation (`--games 1000 --seed 42`) shows
  active market participation — verifiable via the price-history CSV
  containing trade rows on resources other than the producer's own
  output.
- ✅ A regression test confirms the Transporter AI lists PassengerSeats
  by season 2.
- ✅ A regression test confirms an AI with no input inventory places
  bids on its required inputs.
- ✅ All existing tests pass (`.venv/bin/python -m pytest tests/`, target
  235 passing or better).
- ✅ `RELEASE_NOTES.md` has a new `### codex/ai-trading` section with a
  before/after market-activity comparison.

## Optional extras (nice to have)

- A `--diagnostics` flag on the simulation runner that prints per-role
  market-participation stats (bids placed, offers listed, deals matched).
- AI Banker that proactively offers loans to capital-short borrowers.
- AI Educator that buys Knowledge / Expertise from other educators
  *(only relevant in multi-Educator games, which today's auction
  doesn't typically produce — but it's a nice forward-compat hook).*

## What to do if stuck

- **Don't change market matching semantics** — the near-match
  auto-clearing TODO (±1 Dp / ±3%) is a separate piece of work and is
  Claude's domain.  Stay on the bid/offer placement side.
- **Don't extend `engine/turn.py` significantly** — if you need new
  AI action types, propose them in `RELEASE_NOTES.md` and coordinate
  rather than landing them solo.
- **If the simulation reveals new structural issues** (e.g. some role
  becomes dominant once AI trades actively), document the finding in
  `RELEASE_NOTES.md` "Known follow-ups" and stop short of touching
  `constants.py` or balance numbers.

## Hand-off

When the branch is ready:

1. `git add -A && git commit ...`
2. `git push -u origin codex/ai-trading`
3. Either open a PR to `pre-release` or merge locally and push
   `pre-release` directly (the established workflow this session has
   been local merges + push).
4. Conflict-free with Claude's work — the only shared file is
   `RELEASE_NOTES.md`, and adding a new section header at the top of
   the `## Unreleased` block never conflicts.

## Reference

- AI strategy: `island_traders/engine/ai.py`
- Market model: `island_traders/models/market.py` (bid/ask state,
  matching logic)
- Trading engine: `island_traders/engine/trading.py`
- Existing test for AI: `tests/test_engine/test_ai.py`
- Sim runner with multi-seed support: `island_traders/simulation/runner.py`
  (the `--seeds` flag Codex added in `codex/sim-calibration` is ideal
  for verifying behaviour holds across seeds)
- Related TODO items: `TODO.md` → "AI Trading Behaviour" section,
  "Market & Trading" section, "Item valuation" under Financial Model
