# Brief — Unissued shares as recapitalization + AI cash-shortfall financing (2026-06-11)

**Suggested owner:** Codex (equity model + rule-based AI).
**Base off:** current `origin/pre-release`.
**Issues:** file two — "Equity: 40% is unissued, not external-held; owner buy =
primary issuance" (`area:economy`) and "AI: finance cash shortfalls (borrow /
recapitalize)" (`area:ai`). From maintainer playtest feedback 2026-06-11.

Two related requests; the equity change also gives the AI a self-funding lever.

---

## Part 1 — Ownership rules change (the 40% is unissued)

**Maintainer statement:** "The initial bidding is for 60% of the share capital
but the remaining 40% is not issued — it is **not** held by external
shareholders. When the owner purchases additional stock, the money gets added to
**cash** and to **shareholder capital**."

### Current model
`models/equity.py`: `TOTAL_SHARES = 100`, `AUCTIONED_SHARES = 60`. The owner gets
60; a `PUBLIC_HOLDER = "public"` holder holds the other 40 (`public_float()`).
`CapTable.new_with_majority` seeds owner 60 / public 40.

`_handle_buy_out_float` (`server/app.py:2415`): the owner buys float shares at
`share_price(fair_value(...))`, paid from `personal_cash`, and **the cash leaves
the game** ("paid to imaginary public holders", L2475-2479):
```
player.personal_cash -= cost          # leaves circulation
player.cap_table.transfer(PUBLIC_HOLDER, owner_key, shares)
player.holdings[owner_key] += shares
```

### Required change — treat the 40% as authorized-but-unissued treasury stock,
and make a buy a **primary issuance** (a capital injection into the island):
1. **Rename the concept** `PUBLIC_HOLDER`/`public_float`/"public-float" →
   unissued/treasury (e.g. `UNISSUED_HOLDER = "unissued"`,
   `CapTable.unissued()`), and update the player payload keys + UI labels
   (`server/app.py` `public_float_pct/_shares`; `static/index.html` "Buy
   shares…"/"public float" copy, `openBuyFloat`). It is **not** external equity.
2. **Buy = primary issuance.** On an owner buy of `shares` at `cost`:
   ```
   player.personal_cash -= cost     # investor injects capital
   player.dollops       += cost     # → island CASH (treasury)   ← THE CHANGE
   transfer UNISSUED -> owner        # → issued SHARE CAPITAL up
   player.holdings[owner] += shares
   ```
   i.e. the cost no longer leaves the game; it recapitalizes the island. This is
   the "money added to cash and shareholder capital" the maintainer described.

### Modeling decisions (resolve explicitly; recommended defaults given)
- **Valuation denominator — keep `TOTAL_SHARES = 100` as *authorized*.** Per-share
  value stays `fair_value(liq)/100` as today; unissued shares are owned by no one
  and contribute to no player's `net_worth` until issued. *(Default: least
  disruptive to the existing net-worth scoring; do NOT switch the denominator to
  issued-only without a calibration pass — it would reprice every island.)*
- **Money supply.** Today's "cash leaves the game" makes buy-float a **sink**
  (money supply = `Σ dollops + personal_cash`; the cost left `personal_cash` with
  nothing added). The new flow is **money-supply-neutral** (personal_cash→dollops),
  and injects working cash into the island — a small structural help to the
  −52.8% contraction. Note this in the release notes.
- **Auction bid** still leaves the game (the winning bid pays former owners at
  game start) — out of scope; only the *in-game* buy changes.
- **Net-worth neutrality check.** After a buy, the owner's `net_worth` should be
  ~unchanged (personal_cash down by `cost`; island `dollops` up by `cost` → higher
  liquidation → higher share price → holdings worth more). Add a test asserting
  this within rounding.

---

## Part 2 — AI finances cash shortfalls ("Minerva runs out of cash")

**Maintainer statement:** a cash-strapped AI island "runs out of cash and doesn't
either take a loan from the bank nor lend itself any money."

### Current gap
`engine/ai.py` loan logic is **entirely Banker-side**: `_ai_offer_loans` /
`_ai_issue_loan` have a Banker AI *issue* loans to others. There is **no
borrower-initiated path** — a cash-short non-Banker AI passively waits for a
Banker to offer, and never self-funds. So if no AI Banker offers (none seated, at
debt ceiling, risk-screened out), the island just stays broke and stalls.

### Required behavior — when an AI island can't fund its needs this season
(can't afford inputs/payroll/maintenance, `dollops` below a working-capital
threshold), it should proactively, in priority order:
1. **Take a bank loan** if a Banker (AI or human) has lending capacity: add a
   borrower-side request the Banker can auto-accept (mirror the existing
   `_ai_issue_loan` terms / `_borrower_debt_ceiling`), so financing happens even
   without the Banker spontaneously offering.
2. **Recapitalize via unissued shares** (Part 1): if the owner has
   `personal_cash` and the island has unissued shares, buy enough to top up the
   treasury — the "lend itself money" path the maintainer wants. Reuse the Part 1
   primary-issuance flow.
3. Only then cut its cloth (skip the unaffordable action) — current fallback.

Keep it bounded (don't borrow past the debt ceiling; don't drain personal_cash
below a reserve). Surface a log line like the other AI actions.

---

## Acceptance
- Buy-unissued: a test asserting `dollops += cost`, shares issued, money-supply
  unchanged, and net-worth ~unchanged. UI/payload relabeled; no "public/external"
  language remains.
- AI financing: a test where a cash-short AI with an available Banker takes a loan
  (and one where, with no Banker capacity but spare personal_cash + unissued
  shares, it recapitalizes) instead of stalling.
- Full suite green; `--games 1000 --seed 42` sanity (expect fewer cash-stalled
  islands; note any money-supply shift from the neutralized buy + the injections).
- APP_VERSION bump + RELEASE_NOTES (call out the ownership rule change as
  player-facing).
