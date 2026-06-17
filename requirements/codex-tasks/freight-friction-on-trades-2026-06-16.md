# Brief — #85 Freight friction on trades: make Transport a service economy (2026-06-16)

**Suggested owner:** Codex (engine market/trading economy).
**Base off:** current `origin/pre-release`.
**Tracking issue:** [#85](https://github.com/ashersilver/island-traders/issues/85).
File the work as `Closes #85`. Design context:
`requirements/economics-review-2026-06-10.md` §P4 (root cause D4).
**Pairs with:** Claude surfaces the freight cost/fee in the trade UI (cost
preview, "X Freight consumed / Y Dp fee to Transporter"). Second of {engine,
UI} to merge wires the integration; the first leaves a stub.

---

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees.** You work in the **primary checkout**
  (`/Users/ashleysilver/Documents/projects/island-traders`). Claude works in a
  **separate worktree** on a `claude/*` branch. Do not edit Claude's worktree or
  run `git reset/checkout/stash` against it. Coordinate via pushed branches +
  PRs only.
- **Branch creation.** `git fetch`; confirm current
  (`git merge-base --is-ancestor origin/pre-release HEAD`); cut a fresh branch
  off `origin/pre-release`, e.g. `codex/freight-friction-85-2026-06-16`. Never
  commit straight onto `pre-release` or `master`.
- **PRs only — no fast-forwards.** Every change reaches `pre-release` through a
  PR Claude merges. Do **not** push/fast-forward to `pre-release`. `Closes #85`.
  Update `RELEASE_NOTES.md` and bump `APP_VERSION` `.N` in `constants.py`.
- **Git discipline.** No `--no-verify`, no `--amend`, no force-push; new commits
  only. Run the **full** `pytest` suite before handoff.
- **Handoff.** "branch X at commit Y — ready to integrate" + UI-stub note.

---

## The requirement (#85 / economics-review §P4)

Trade is currently **frictionless** — buying from the market or another island
costs no transport — so the Transporter sells an *ingredient* (Freight as a
production input) rather than a *service*, and logistics play no strategic role.

**Change:** market and inter-island trades must **consume Freight** (or pay a
freight **fee routed to the Transporter**) per unit shipped. This turns Transport
into a service economy and makes logistics strategic. Relates to Air Freight
(#51) and Warehousing (#64) — keep the model extensible toward those.

---

## Existing machinery to build on (read first)

- **There is already a freight-on-delivery precedent for capital equipment.**
  `_action_purchase_capital` references `freight_per_unit` shipped
  (`island_traders/engine/turn.py:887`). **Mirror this model** for general
  trades rather than inventing a new one — consistency matters.
- **Market trade execution** (the seams to add friction to):
  - formula market: `Market.execute_buy` (`models/market.py:157`),
    `Market.execute_sell` (`market.py:180`);
  - order book: `Market.buy_from_offers` (`market.py:471`),
    `Market.sell_to_bids` (`market.py:504`);
  - bid/ask already exist (`ask_price`/`bid_price`, `market.py:132`/`:135`,
    `MARKET_MAKER_SPREAD`) — freight friction is **separate** from the spread.
- **Turn-level callers:** `_action_market_buy` (`turn.py:2901`),
  `_action_market_sell` (`turn.py:3006`) — these call the market primitives and
  are where a player's Freight is debited / the fee is charged.
- **Peer-to-peer (inter-island) deals:** `TradingEngine.accept_deal`
  (`engine/trading.py:213`) moves resources between two players — inter-island
  trades must also pay freight.
- **Freight as a resource** is `ResourceType.Freight`; the Transporter produces
  it (`BASE_PRODUCTION["Transporter"]`, `constants.py:144`) and consumes Oil.

## Design / approach

1. **Add a freight-cost rule per shipped unit.** New constants in
   `constants.py` (next to `MARKET_MAKER_SPREAD`): e.g.
   `FREIGHT_UNITS_PER_TRADE_UNIT` and/or `FREIGHT_FEE_PER_UNIT` (Dp), plus a
   policy flag for which resources are "bulky" vs "light" if you want
   per-resource weighting (keep v1 simple — a flat per-unit rule is fine; leave
   a hook for weighting). Document the chosen model in
   `requirements/economics-review-2026-06-10.md` (or a short addendum).
2. **Two payment modes (support both, pick a default):**
   - **Consume Freight:** the trading party must hold enough `Freight` units;
     the trade debits them. If they don't hold Freight, they must
     **pay a fee** instead.
   - **Pay a fee routed to the Transporter:** Dp fee per unit, credited to the
     Transporter player(s). If there are multiple Transporters, split or route
     to the active one (mirror however capital-equipment freight is routed at
     `turn.py:887`).
   The default per the issue is "consume Freight OR pay a fee" — implement the
   fee path as the fallback when the trader has no Freight, and credit the fee
   to the Transporter so it is genuinely a service revenue stream.
3. **Apply at every shipping seam:** formula buy/sell, order-book fills, and
   inter-island `accept_deal`. **Exempt** trades that don't ship (e.g. a player
   buying their own produced output is not a shipment; selling Freight itself
   should not pay freight-on-freight — guard against recursion).
4. **Who pays?** Define and document: buyer pays inbound freight (typical) —
   but keep it one clear rule. The fee/units come out at execution time so price
   history and net worth stay coherent.
5. **No Transporter in the game?** If no player holds the Transporter role
   (small games), fall back to the fee being burned (or waived) — document it;
   don't crash.

## Constraints & gotchas

- **Don't double-charge the spread.** Freight friction is *additive to* and
  *separate from* `MARKET_MAKER_SPREAD`; keep them distinct in the cost
  breakdown so the UI can show both.
- **Recursion guard:** shipping Freight or buying Freight must not itself incur
  freight. Add an explicit exemption + a test.
- **AI + sim impact.** The rule AI and the calibrated sim both route trades
  through these seams — freight friction **will move win rates** (that's the
  point: Transporter should gain). After implementing, run
  `python -m island_traders.simulation.runner --games 1000 --seed 42` and
  retune `config/event_charts.yaml` / prices if a role falls out of the target
  band. Report before/after win-rate spread in the PR.
- **`ResourceBundle` is immutable** (`models/resource.py:42`) — debit Freight
  via the existing give/receive helpers, not in-place mutation.
- **Net worth coherence:** a fee paid to the Transporter is a transfer (zero-sum
  across players); consuming Freight is consumption. Verify totals stay sane.

## Tests to add (`tests/test_engine`, `tests/test_models`, `tests/test_server`)

1. Formula buy and order-book fill each debit the correct Freight units (or
   charge the fee when the trader holds no Freight); Transporter is credited the
   fee.
2. Inter-island `accept_deal` pays freight; a same-island/no-ship case is
   exempt.
3. Recursion guard: trading Freight pays no freight-on-freight.
4. No-Transporter fallback does not crash and follows the documented rule.
5. Sim smoke: seeded 1000-game run completes; record win-rate spread before/
   after and confirm Transporter share rises without blowing the band.

## Definition of done

- Freight friction applied at all shipping seams (formula, order book,
  inter-island), with consume-Freight + fee-to-Transporter modes and the
  recursion/no-Transporter guards.
- Constants documented; sim re-run and (if needed) retuned, with before/after
  win-rate spread in the PR.
- New tests green; **full suite green**.
- `APP_VERSION` bump + `RELEASE_NOTES.md` entry.
- PR `Closes #85`; one-line note on UI integration (wired vs stub).
- Hand back: "branch X at commit Y — freight friction live" with the cost-
  breakdown payload fields (freight units consumed / fee charged) for the UI.
