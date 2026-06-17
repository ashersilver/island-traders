# Brief — #157 Capital purchases at game start: island capital + secured 3-year loans (2026-06-16)

**Suggested owner:** Codex (engine economy + server setup wiring).
**Base off:** current `origin/pre-release`.
**Tracking issue:** [#157](https://github.com/ashersilver/island-traders/issues/157).
File the work as `Closes #157`.
**Pairs with:** Claude builds/extends any **start-of-game purchase UI** that
surfaces "paid from island capital" vs "covered by a secured loan". If the
opening capital-selection UI already exists, the second of {engine PR, UI PR} to
merge wires the integration; the first leaves a stub. Note in the PR which
state you left.

---

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees.** You work in the **primary checkout**
  (`/Users/ashleysilver/Documents/projects/island-traders`). Claude works in a
  **separate worktree** on a `claude/*` branch. Do not edit Claude's worktree or
  run `git reset/checkout/stash` against it. Coordinate via pushed branches +
  PRs only.
- **Branch creation.** `git fetch`; confirm current
  (`git merge-base --is-ancestor origin/pre-release HEAD`); cut a fresh branch
  off `origin/pre-release`, e.g. `codex/capital-at-start-157-2026-06-16`. Never
  commit straight onto `pre-release` or `master`.
- **PRs only — no fast-forwards.** Every change reaches `pre-release` through a
  PR Claude merges. Do **not** push/fast-forward to `pre-release`. `Closes #157`.
  Update `RELEASE_NOTES.md` and bump `APP_VERSION` `.N` in `constants.py`.
- **Git discipline.** No `--no-verify`, no `--amend`, no force-push; new commits
  only. Run the **full** `pytest` suite before handoff.
- **Handoff.** "branch X at commit Y — ready to integrate" + a one-line UI-stub
  note.

---

## The requirement (verbatim, #157)

> When selecting capital purchases at the beginning of a game, the purchases
> must be made from the **Island capital**, not from the **Players' capital**.
> If there are insufficient funds the purchases can be made with **3-year
> loans** from the bank, at the **preferred rate**, **secured against the assets
> being purchased**.

This separates *island* (operating) capital from the *player's* personal wallet
for start-of-game capital formation, and introduces an asset-secured loan at the
bank's preferred (best) rate when island funds fall short.

---

## Existing machinery to build on (read first)

- **Game setup** seeds each player's wallet: `Game.setup`
  (`island_traders/engine/game.py:142`) sets `dollops` from
  `TOTAL_STARTING_DOLLOPS / num_players` (or the per-spec override) at
  `game.py:172`. There is **no separate "island capital" pool today** — wallet
  == island cash. The equity scaffolding nearby (`cap_table`, `holdings`,
  `game.py:191`+) and the web "full flip" (`app.py`, treasury reseed) are the
  closest existing notion of island-vs-personal money — **read how the web path
  already splits treasury vs personal cash before inventing a new field**, and
  reuse it if it fits.
- **Capital purchase action** already exists and already issues a loan for the
  shortfall: `_action_purchase_capital`
  (`island_traders/engine/turn.py:611`) spends dollops (`turn.py:697`) and, when
  cash is short, takes a loan with a `term_years` quote (`turn.py:751`, `:782`).
  **You are largely retargeting the cash source and pinning the terms**, not
  building purchasing from scratch.
- **Loan issuance** primitives: `_offer_loan` / `_take_loan` and the funding
  rate table `posted_funding_rates(year, season)` keyed by `term_years`
  (`turn.py:3465`, `:3556`); `LoanLedger` and the loan model
  (`island_traders/models/loan.py`). The "preferred rate" should be the best
  posted funding rate for a **3-year** term (`posted_funding_rates(...)[3]`).
- **Capital catalogue / mandatory minimums:** `CAPITAL_CATALOGUE`
  (`constants_capacity.py`, imported `game.py:44`) and
  `MANDATORY_MINIMUM_INVESTMENT` (constants) define what each island can/must
  buy and the costs.

## Design / approach

1. **Introduce (or reuse) an island-capital pool** distinct from the player's
   personal wallet for start-of-game purchases. If the web equity flip already
   maintains an island treasury, route purchases through that; otherwise add an
   explicit `island_capital` figure seeded at setup and document the split in
   `requirements/island-ledger.md`. **Decide one source of truth** and make the
   start-of-game purchase deduct from it, not from `player.dollops`.
2. **Shortfall → secured 3-year loan at preferred rate.** When the island pool
   can't cover a selected purchase, auto-arrange a bank loan:
   - `term_years = 3`, rate = best posted funding rate for 3 years,
   - principal = the shortfall (or full item cost, per the model you choose —
     document it),
   - **secured against the purchased asset**: record the collateral link on the
     loan (extend `loan.py` with a `collateral` / `secured_asset_id` field) so a
     later default/insurance path can reference it. Securing also justifies the
     preferred rate.
3. **Keep it start-of-game scoped.** This is the opening capital-formation step.
   Mid-game `_action_purchase_capital` keeps its current behaviour unless you
   deliberately unify them — if you do, gate the "island capital + secured loan"
   terms to the setup window so mid-game purchases aren't silently changed.
4. **Server/state:** expose, in the start-of-game payload, the island capital
   available, the per-item cost, and — when a loan is needed — the quoted
   3-year preferred-rate terms, so the UI can show "X from island capital,
   Y on a 3-year secured loan at Z%". Mirror the structured loan detail already
   emitted at `app.py:3019` (`loans_detail`).

## Constraints & gotchas

- **Don't double-count wealth.** `total_wealth` already nets loans
  (`game.py:374`, `:792`). A secured loan funding an asset must net out so a
  player isn't richer or poorer purely from financing the purchase — verify
  net worth is unchanged at the instant of a fully-financed purchase.
- **Preferred rate must be deterministic** for a given (year, season, term=3)
  so tests and the sim are reproducible (`posted_funding_rates`).
- **AI players** also form opening capital — make sure the rule AI's setup path
  uses the same island-capital + secured-loan route (or is explicitly exempt and
  documented), so the simulation stays comparable across roles.
- **Equity interactions.** The web equity flip reseeds treasury and converts
  bids to personal cash. Make sure "island capital" here doesn't collide with
  that treasury concept — reuse it rather than introducing a parallel pool if
  possible.

## Tests to add (`tests/test_engine`, `tests/test_server`)

1. Start-of-game purchase fully covered by island capital deducts from the
   island pool, **not** `player.dollops`.
2. Shortfall triggers a **3-year** loan at the **preferred** posted rate, with
   collateral recorded against the purchased asset; principal == shortfall (or
   per documented model).
3. Net worth is unchanged at the moment of a fully-financed purchase (loan nets
   against asset value).
4. Server: start-of-game state exposes island capital, item cost, and the
   quoted secured-loan terms; the purchase round-trips through the WS handler.
5. Sim smoke: a seeded run completes with the new setup path and win-rate spread
   stays in band (no role accidentally advantaged by free financing).

## Definition of done

- Start-of-game capital purchases draw from island capital; shortfalls become
  3-year preferred-rate loans secured against the asset; collateral recorded on
  the loan model.
- Net-worth accounting verified neutral at purchase; AI setup path consistent.
- New tests green; **full suite green**; seeded sim smoke checked.
- `APP_VERSION` bump + `RELEASE_NOTES.md` entry; `island-ledger.md` updated if
  you add an island-capital field.
- PR `Closes #157`; one-line note on UI integration (wired vs stub).
- Hand back: "branch X at commit Y — island-capital + secured-loan setup live"
  with the start-of-game payload field names for the UI.
