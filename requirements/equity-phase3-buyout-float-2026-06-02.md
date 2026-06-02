# Spec — Equity Phase 3: Buy out the public float (2026-06-02)

**Status:** Spec, ready to build. Builds on the merged Phase 1/2b equity flip.
**Owner:** Claude (web-side equity stack — `app.py` + `index.html`; the cap-table
math already exists in `equity.py`). Small, self-contained.
**Scope:** A controlling player buys some/all of **their own island's** 40%
public float at fair value. (Buying into *other* players' islands is **Phase 4**,
out of scope here. Dividends are **Phase 2**, separate.)

---

## 1. What it does

The auction seats 60% to the owner and 40% to a pseudo-holder `"public"`. Phase 3
lets the owner spend **personal cash** to buy public-float shares, increasing
their stake toward 100%.

- **Price:** the island's live **fair value per share** —
  `equity.share_price(equity.fair_value(liquidation_value, wealth_history))` —
  the same number already computed in `get_game_state` as `share_price`.
- **Payment:** `shares × share_price` is deducted from the buyer's
  `personal_cash` and **leaves the game** (paid to the imaginary public holders)
  — exactly like the auction bid. It does **not** enter the treasury.
- **Cap table:** `cap_table.transfer(PUBLIC_HOLDER, str(owner_id), shares)`
  (already implemented and validated in `equity.py`). Update `holdings` to match.

### Net-worth & strategic effect
At the moment of purchase it's ~net-worth-neutral (cash → equity at fair value).
The payoff is **future**: with a larger stake, more of the island's future
growth and (Phase 2) dividends accrue to the owner instead of evaporating to the
float. Buying out the float is how a player converts spare cash into a bigger
slice of a rising island — the elegant end of the equity arc.

---

## 2. Rules / guards
- Only the **controlling owner** of an island may buy that island's float
  (server checks the requesting player owns the majority block).
- `0 < shares ≤ cap_table.public_float()`.
- Buyer must afford it: `personal_cash ≥ shares × share_price` (round to 1 dp,
  consistent with the rest of the equity code).
- When the float reaches 0, the owner holds 100%; the action disappears.
- Price is quoted **live** at action time (re-read share_price); the client may
  show a quote but the server re-computes and is authoritative.

---

## 3. Where it plugs in

**Engine / model:** no new model code needed — `CapTable.transfer` and
`share_price`/`fair_value` already exist. Optionally add a tiny helper on the
manager to perform the buyout atomically.

**Server (`island_traders/server/app.py`):**
- New WS action `buy_out_float` (mirrors `training_counter_response` plumbing):
  message `{type:"buy_out_float", shares:int}`.
- Handler: resolve engine player from lobby id; verify ownership; compute
  `price = share_price(fair_value(total_wealth(...), wealth_history))`; clamp
  `shares` to `public_float`; check `personal_cash`; then
  `personal_cash -= shares*price`, `cap_table.transfer("public", str(pid),
  shares)`, `holdings[str(pid)] += shares`. Broadcast fresh state.
- Add a `float_buyout_quote` to the player payload (or reuse `share_price` +
  `public_float_pct`): the client needs price/share and shares available.

**UI (`island_traders/server/static/index.html`):**
- In the sidebar "Ownership" area, when you control the island and
  `public_float_pct > 0`, add a **"Buy shares"** control: shows public float %,
  price/share, your personal cash, and a quantity picker (1…float), with a
  live "cost = shares × price" and an affordability disable. Sends
  `buy_out_float`. On success the ownership %, personal cash, and net worth
  update from the next state broadcast.

---

## 4. Tests
- Buying `n` float shares: `cap_table` moves `public→owner` by `n` (totals still
  100), `holdings` updated, `personal_cash` drops by `round(n×price,1)`, treasury
  unchanged.
- Over-buy (n > float) is clamped or rejected; can't buy with insufficient cash.
- Non-owner cannot buy that island's float.
- Buying the entire float → owner at 100%, `public_float()==0`.
- Net worth immediately after purchase ≈ before (cash converted to equity at
  fair value, within rounding).

---

## 5. Follow-ons (not this spec)
- **Phase 4** — buy into *other* islands' floats (same mechanic, any island;
  plus optional peer-to-peer share sales via the deal ledger).
- **Phase 2** — dividends (Winter declare → Spring pay); a larger stake bought
  here then pays off in dividend share.
- Optional mid-game **Lend to / Repay** shareholder-loan actions.
