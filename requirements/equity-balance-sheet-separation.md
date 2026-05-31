# Plan: Separate Player Balance Sheet from Island Balance Sheet (Equity Model)

**Status:** Draft plan for review (2026-05-29). No code yet.
**Goal:** Make the auction a purchase of a *majority equity stake* in an island,
separate a player's personal wealth from their island's operating finances, and
open the door to buying out minority holders and buying into other players'
islands — kept deliberately simple.

---

## 1. The problem with today's model

`Player` (in `island_traders/models/player.py`) is **both** the investor and the
island. One object holds:

- `dollops` — used as the island's operating cash (buys inputs, pays wages &
  maintenance, receives sale proceeds) **and** as the player's personal wealth /
  score, with no distinction.
- `inventory`, `workforce`, `population`, `capital_inventory`,
  `production_capacity`, `active_patents`, `insurance_policies` — all island
  operating assets.

So "how much is the player worth" and "how much cash does the island have to
operate" are the same number. There is no notion of ownership share, so there's
nothing to auction a stake *in*, nothing to pay a dividend *to*, and no way for
one player to hold a slice of another's island.

---

## 2. Core idea (simple + elegant)

Split the single number into **two balance sheets** joined by a **cap table**:

```
Player (investor)                 Island (enterprise)
─────────────────                 ───────────────────
cash            (personal $)      treasury        (operating $)   ← today's "dollops"
holdings: {island_id: shares}     inventory, workforce, population,
                                  capital, production, patents, ...
                                  shareholders: {holder: shares}   ← the cap table
```

- Every island has a fixed **`TOTAL_SHARES = 100`**.
- Every island starts with its **own cash position** (`ISLAND_STARTING_CASH`,
  proposed **500 Dp**) — the treasury is seeded independently, *not* from the
  auction bid.
- The auction sells a **majority block** (**60 shares = 60%**). The winning bid
  is paid from the player's personal cash **to the imaginary former
  shareholders** who are selling that 60% — i.e. the bid is a sunk acquisition
  cost; it **leaves the game**, it does not seed the treasury. The remaining
  **40 shares** stay as a **public float** (pseudo-holder `"public"`).
- The player keeps whatever personal cash is left after the bid and can later
  **buy out the public float at fair value**, **lend cash to their company**
  (shareholder loan into treasury), or **bid for shares in other islands**.
- A player's **net worth (score)** = `cash + Σ(shares_held × fair_value_per_share)`
  across every island they hold (net of any shareholder loans owed/owing),
  instead of today's single `dollops`.

The elegance: **today's `Player.dollops` becomes `Island.treasury` almost
unchanged** — all the existing buy/sell/wage/maintenance code keeps operating on
the island's money, which is now seeded at `ISLAND_STARTING_CASH`. We *add* a
small personal `cash` account and a cap table on top. The island keeps doing
what it already does; we just relabel whose money is whose and record who owns
the island.

---

## 3. Money flow

### At game start (auction = buying a 60% stake from former owners)
1. Each island is seeded with its own **`treasury = ISLAND_STARTING_CASH`**
   (proposed 500 Dp), independent of any bid.
2. Player starts with **personal `cash` = starting capital** (today's
   `STARTING_CAPITAL`, e.g. 1500 Dp).
3. The winning auction bid (e.g. 400 Dp) is **paid out of personal `cash` to the
   imaginary former shareholders** of the 60% block. That money **leaves the
   game** — it does *not* enter the treasury. The player keeps the remainder
   (e.g. 1500 − 400 = 1100 Dp) as personal cash.
4. The player now owns 60 shares; 40 remain as the public float. The investing
   phase spends from `treasury` (the seeded 500 Dp) exactly as today.

### During the year
- The island operates entirely from `treasury` — inputs, sales, wages,
  maintenance, loans, insurance all stay treasury-side, unchanged.
- The player may, from personal `cash`, **lend to their company** (a shareholder
  loan that tops up `treasury` and records a liability owed back to the player —
  see Phase 2b) or **buy out public-float shares** at fair value (Phase 3).

### Dividends — declared in Winter, paid at start of Spring (Phase 2)
- A controlling player may **declare a dividend `D` during the Winter season**;
  it is **paid out at the beginning of the following Spring** from `treasury`.
  (Declaration and payment are deliberately split so the treasury must still
  hold the cash when Spring arrives.)
- `D` is split **pro-rata by shares**: each *player* shareholder's personal
  `cash` grows by `D × shares/TOTAL_SHARES`.
- **The public float's slice disappears** (`D × 40/100` is simply not paid out —
  outside shareholders are imaginary). *Locked: dividends to outside
  shareholders vanish.*

---

## 4. Valuation — liquidation value, fair value, share price

Two valuations, both per-share, both reusing existing engine data.

### 4.1 Liquidation value (the floor — what the island is worth if wound up now)
```
liquidation_value = treasury
                  + inventory_marked_to_market      (existing market prices)
                  + capital_book_value              (existing depreciation calc)
                  − outstanding_liabilities         (loans, lease buyouts,
                                                     shareholder loans)
```

### 4.2 Fair value (the going-concern price for buyouts & buy-ins)
The user's ask: fair value rests on **either** liquidation value **or** the
island's **growth in net worth**, adjusted for the **volatility** of that net
worth. We already track `wealth_history` per island, so growth and volatility
come for free:

```
nw[t]            = net worth at end of year t   (= liquidation_value snapshots)
growth           = mean(nw[t] − nw[t-1])        over available years  (earnings proxy)
volatility       = stdev(nw[t] − nw[t-1])       over available years
cv               = volatility / max(1, |growth|)        (coefficient of variation)
risk_factor      = 1 / (1 + VOLATILITY_PENALTY × cv)    (∈ (0, 1]; calmer = closer to 1)

going_concern    = liquidation_value + max(0, growth) × EARNINGS_MULTIPLE × risk_factor
fair_value       = max(liquidation_value, going_concern)
share_price      = max(MIN_SHARE_PRICE, fair_value / TOTAL_SHARES)
```

Reading it plainly: an island is never worth less than its liquidation value;
a profitable, *steady* island is worth more (its growth is capitalized at
`EARNINGS_MULTIPLE`); a profitable but *erratic* island gets that premium
discounted by `risk_factor`. Early in the game (1–2 years of history) `growth`
and `volatility` are thin, so `fair_value` sensibly falls back toward
liquidation value.

`share_price` is the single number used for scoring, public-float buyouts, and
cross-island bids. Tunables: `EARNINGS_MULTIPLE` (how many years of growth you
pay for, e.g. 3), `VOLATILITY_PENALTY` (how harshly erratic earnings are
discounted, e.g. 1.0), `MIN_SHARE_PRICE`.

---

## 5. Transactions the model enables (phased)

| Phase | Capability | Mechanism |
|---|---|---|
| 1 | Auction buys a 60% stake; island seeded with own cash; personal vs island books separated; net worth = cash + equity | cap table + `fair_value`; bid paid from cash → former shareholders (leaves game) |
| 2 | **Dividends** declared in Winter, paid start of Spring | controlling player declares `D`; paid pro-rata from treasury to player shareholders; public-float slice vanishes |
| 2b | **Shareholder loans** — lend personal cash to your company | move cash `player → treasury`; record liability (counts against liquidation value, owed back to the player) |
| 3 | **Buy out the public float** | pay `shares × fair_value_per_share` from personal `cash` → shares move `public → player`; cash leaves the game (paid to imaginary holders) |
| 4 | **Buy into another player's island** | bid for available public-float shares of *any* island at its `fair_value`; thereafter receive that island's dividends. Optional: peer-to-peer share sales by mutual agreement (reuse the existing P2P `deal` ledger) |

Phase 1 alone delivers the headline ask ("auction = majority equity stake,
separate balance sheets"). Phases 2 / 2b / 3 / 4 are independent, additive
follow-ups.

---

## 6. Data model changes

**New `island_traders/models/equity.py`:**
```python
TOTAL_SHARES = 100
AUCTIONED_SHARES = 60          # majority block sold at auction
PUBLIC_HOLDER = "public"

@dataclass
class CapTable:
    shares: dict[str, int]     # holder_id -> shares; "public" = float
    def fraction(self, holder_id) -> float: ...
    def transfer(self, frm, to, n) -> None: ...
```

**`Island`** — recommended: **rename the existing `Player` dataclass to
`Island`** (it already *is* the island), and add:
```python
treasury: float                # was `dollops`; seeded at ISLAND_STARTING_CASH
cap_table: CapTable
shareholder_loans: dict[str, float] = {}   # player_id -> principal owed (Phase 2b)
```

**New small `Player` / `Investor`:**
```python
@dataclass
class Player:
    player_id: int
    name: str
    is_human: bool
    cash: float                          # personal wealth (score component)
    holdings: dict[str, int]             # island_id -> shares (mirror of cap tables)
    def net_worth(self, islands) -> float: ...
```

> *Open question C:* rename `Player → Island` (clean, but a large mechanical
> diff touching production/turn/market/tests), **or** keep the class named
> `Player` and just add `treasury`/`cap_table` + a thin separate `Investor`
> record (smaller diff, fuzzier naming). Recommendation: do the rename — it's
> mechanical and leaves the codebase honest. Stage it as its own commit before
> any behavior change so the rename diff is reviewable in isolation.

---

## 7. Scoring / win condition

`GameSummary` and every "wealth" readout switch from `player.dollops` to
`player.net_worth(islands)`. This is the main externally visible behavior change
and should be called out in release notes and RULES.md. A player who pays a low
winning bid keeps more personal cash but capitalizes a weaker island — a real
strategic tension that didn't exist before.

---

## 8. Touch points (impact survey)

- `models/player.py` → split into `Island` + `Player`/`Investor` (+ `equity.py`).
- `engine/game.py` → construct islands + investors; wire auction proceeds into
  treasury + cap table; year-end dividend step (Phase 2); net-worth scoring.
- `engine/turn.py`, `engine/production.py`, `engine/trading.py`,
  `models/market.py` → mechanical `player.dollops` → `island.treasury` rename;
  no logic change in Phase 1.
- `server/app.py` → auction already takes a bid; add cap-table + treasury to the
  player/game-state payload; new actions for buyout/buy-in (Phases 3–4).
- `server/static/index.html` → show two balances (personal cash + island
  treasury) and a small cap-table / "shareholders" readout; net-worth on the
  scoreboard.
- Tests → broad but mostly mechanical rename; new tests for cap-table math,
  share price, dividend split, buyout pricing.

---

## 9. Decisions

### Locked (from the 2026-05-29 review)
- **Island starts with its own cash** (`ISLAND_STARTING_CASH`, proposed 500 Dp),
  seeded independently of the bid.
- **The winning bid is a sunk cost** paid from personal cash to imaginary former
  shareholders; it leaves the game and does **not** seed the treasury.
- The player **keeps leftover personal cash** and can buy out the float, lend to
  the company, or bid on other islands with it.
- **Dividends: declared in Winter, paid at the start of Spring.**
- **Dividends to outside (public-float) shareholders disappear.**
- **`TOTAL_SHARES = 100`**, auction block **60%**.
- **Fair value** for buyouts/buy-ins = `max(liquidation value, risk-adjusted
  going-concern value)` per §4.2 (growth in net worth, discounted by its
  volatility).
- **Phased rollout approved.**

### Still to confirm (tunables, not blockers)
- **D1.** `ISLAND_STARTING_CASH = 500`, `STARTING_CAPITAL` for the player
  (today 1500)? These two plus the auction dynamics set the whole opening
  economy — worth a sim sweep.
- **D2.** `EARNINGS_MULTIPLE` (≈3?) and `VOLATILITY_PENALTY` (≈1.0?) for the
  fair-value formula.
- **D3.** Class rename `Player → Island` (recommended; staged as its own
  no-behavior-change commit) vs. keep the name and bolt equity on.
- **D4.** First cut = Phase 1 only, or Phase 1 + Phase 2 dividends together?
  (Recommend Phase 1 alone to land the separation cleanly, then dividends.)

---

## 10. Recommended first cut

Ship **Phase 1** behind a clean rename:

1. Commit 1 — pure rename `Player → Island` (`dollops → treasury`), no behavior
   change, all tests green.
2. Commit 2 — add `equity.py` (`CapTable`, `TOTAL_SHARES = 100`,
   `AUCTIONED_SHARES = 60`, `ISLAND_STARTING_CASH = 500`), a separate
   `Player`/`Investor` with `cash` + `holdings`; seed each island treasury at
   `ISLAND_STARTING_CASH`; wire the auction to deduct the bid from personal
   `cash` (paid to imaginary former owners — leaves the game, **not** into
   treasury) and seat 60/40 in the cap table.
3. Commit 3 — switch scoring to `net_worth` (using §4.2 `fair_value`), surface
   both balances (personal cash + island treasury) and the cap table in the UI.

Dividends (Phase 2), buyouts (Phase 3), and cross-island buy-ins (Phase 4) then
land as independent follow-ups, each small on its own.
