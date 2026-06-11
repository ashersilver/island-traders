# Functional review — how the rules reflect high-level economics (2026-06-10)

Reviewer: Claude. Scope: the active rule set as of `0.1.0-dev.2026-06-05.9`
(`models/market.py`, `models/loan.py`, `engine/turn.py`, `engine/game.py`,
`constants.py`, the capacity model, equity phases 1–3). Companion playability
suggestions at the end, each mapped to an issue.

---

## 1. What the rules model well

**Comparative advantage & gains from trade.** Each island is a forced
monopolist of its outputs and structurally short of its inputs
(`BASE_PRODUCTION` / `PRODUCTION_RECIPES` / `STARTING_INVENTORY` staging two
seasons of inputs). Interdependence is by construction, which is the right
foundation for a trading game — autarky is impossible, so every game generates
trade pressure.

**Price discovery.** A hybrid microstructure: a formula market-maker
(`current_price = base × (1 + 0.3·(d−s)/(s+d+1))`, clamped to 0.2×–5×) plus a
genuine player order book (`post_offer`/`post_bid`, auto-matching,
tight-spread detection, season-expiring bids, and now pushed `market_event`s).
Disasters apply multiplicative `PriceShock`s — textbook supply shocks.

**Capital deepening & depreciation.** Capital items raise output capacity,
carry delivery lags and service lives (default 20 seasons; the combine
harvester realistically shorter at 8), and book value feeds wealth. The
investing phase is a capex-allocation decision under a budget. This is a real
production function: output is limited by min(labour bands, capital capacity,
inputs) — a Leontief-style constraint with identifiable binding factors
(`_player_capacity` exposes exactly which).

**Human capital (the standout system).** Training has duration (seasons away
+ a 75%-productivity settling season), tuition, travel (PassengerSeats),
per-head medical cover, university capacity limits, and — once #76 lands —
a materials cost (Reagents) for science tracks. That's a Becker-style
human-capital investment with explicit opportunity cost. Repurposing
(including back to Unskilled) adds labour reallocation.

**Credit & corporate finance.** A term structure of posted funding rates,
lending capacity tied to Banker staffing (a capital-adequacy flavour),
loan rollover on the backlog (#6), shareholder loans distinct from bank debt,
and an equity layer (cap tables, public float, share price derived from
fair value of liquidation wealth + history, buyouts). Few board games attempt
a balance sheet this complete; net-worth scoring makes leverage meaningful.

**Risk & insurance.** Stochastic events (outages, disasters, casualties) with
insurance underwritten by the Banker, priced per head. Workforce casualties
create real volatility in productive capacity.

**Demographics as a consumption sector.** Population eats (1 meal per 10
residents/season, a substitutable basket), grows by a birth rate that is
*higher for poorer islands* (`BASE_BIRTH_RATE × (1 − wealth_ratio)`). The
inverse-wealth fertility is both a defensible nod to the demographic
transition and a built-in catch-up mechanic. Sustenance shortfalls post real
demand signals into the market.

## 2. Where the economics is distorted (and what it does to play)

### D1. The formula market is an infinite external sector (the big one)
`execute_sell` mints Dollops from nothing; `execute_buy` burns them. The
market-maker will buy **any quantity at ≥0.2× base, forever**. Consequences:

- There is **no aggregate demand constraint**. The dominant strategy is
  mercantilist: maximise production, dump on the formula market, ignore other
  players. Player-to-player negotiation — the social core of a trading game —
  is strictly optional.
- The **money supply is unanchored**: net Dollops in circulation grows with
  every sale into the void. "Mining is making a killing" is partly this — a
  glut never truly saturates because the buyer of last resort has infinite
  cash, only a price discount.
- Credit barely matters: why borrow working capital when the mint is open?

### D2. No labour cost (wages)
Workers are trained, fed, injured, and killed — but never paid. Labour's only
costs are training fees and meals. So hoarding trained staff is free, idle
workforces cost nothing, and there is no household income — population
consumes meals but generates no purchasing power.

### D3. Final demand is structurally thin
Food has a real recurring sink (sustenance). Intermediate inputs have
production demand. But the *end* products — Goods, HealthServices, Vaccine,
PassengerSeats beyond training travel — have no recurring consumer. This is
why the Manufacturer and Doctor depend on event-driven or player-optional
demand, and why calibration keeps fighting their viability.

### D4. Geography is flavour, not friction
Freight is a production input but **trade itself is frictionless** — buying
from the market or another island costs no transport. The Transporter
therefore sells an ingredient, not a service, and distance/logistics play no
strategic role.

### D5. Price-signal asymmetry — and a muted signal overall
`reset_period_signals` clears **demand** each season but not **supply**:
supply is a never-expiring stock (the market-maker's standing inventory),
demand a one-season flow. Gluts therefore depress the formula price
persistently (a one-time bulk dump suppresses the price until the pile is
physically bought out) while scarcity signals — including a starving
population's posted shortfall demand — evaporate at season end even when the
underlying need persists. Prices ratchet downward over a game.

**Additionally, the formula's response is far narrower than designed:**
`(d−s)/(s+d+1)` is bounded in (−1, 1), so with `PRICE_ELASTICITY = 0.3` the
factor can only reach **0.70–1.30**. The configured clamps of **0.2×–5.0×**
are unreachable via supply/demand alone (only disaster shocks can hit them) —
no famine can raise a price more than +30%, no glut lower it more than −30%.
Prices carry little information and speculation can't pay.

*Fix options (compose well, pair with P1):* (1) decay both counters 50%/season
instead of wiping one; (2) spoilage on perishable market stock
(Food/Fish/Produce −25%/season); (3) raise elasticity (~0.8) or use a
nonlinear curve so the existing clamps come back into play; (4) carry unfilled
sustenance shortfall over as backlog demand. If the stock-vs-flow split is
intentional inventory pricing, it still needs (2) and (4) to be coherent.

### D6. Interest rates float free of the economy
`posted_funding_rates` vary by term and date but link to nothing — no
relationship to money supply, inflation, or default risk. Harmless today
(credit is underused per D1), but it becomes visible the moment D1 is fixed.

## 3. Playability suggestions (prioritised)

**P1 — Give the market-maker a spread and finite depth.** Buy at ask, sell at
bid (e.g. ±10–15% around formula), and cap per-season market-maker volume per
resource (depth N units; beyond that, no fill — find a counterparty). The
spread is a clean money sink; finite depth makes player-to-player deals the
*better* price, which is what makes a trading game social. *(Largest single
playability lever; new issue.)*

**P2 — Payroll.** A small per-season wage per active worker, scaled by band
(e.g. Worker 1 Dp, Technician 2, Manager 4 — calibrate). Makes workforce size
a genuine tradeoff, punishes hoarding, gives Mining-style "reassign everyone
senior" decisions a cost, and is a steady money sink to offset the mint.
*(New issue; pairs with the contracted-away accounting fixed in `.7`.)*

**P3 — Consumer demand for end products.** Per-capita recurring consumption of
Goods (rising with island wealth — an Engel-curve step), HealthServices demand
generated by casualties/outbreaks, and Vaccine uptake preventing flu (#49).
Closes the loop: population earns (P2) → spends (P3) → end-product islands get
a pull market. Directly addresses Manufacturer/Doctor viability. *(New issue;
synergises with Quality of Life #48.)*

**P4 — Freight friction on trades.** Market and inter-island trades consume
Freight (or pay a freight fee routed to the Transporter). Turns the
Transporter into a service economy and makes logistics strategic. *(New
issue; relates to Air Freight #51 and Warehousing #64.)*

**P5 — Monitor the money supply.** Extend the sim metrics (#73) and the
game-over summary with total Dollops in circulation per season. Don't tune
blind: P1/P2 change faucets and sinks; one chart tells you if the economy
inflates or starves. *(Fold into #73.)*

**P6 — Finish the order book UX (#63).** Resting orders, withdraw, "on offer"
column — already specced. With P1, the book becomes the primary market, so
this rises in priority.

**P7 — Show the scoring drivers.** Net worth is the win condition but its
components (treasury, personal cash, equity value, loans receivable/owed)
are scattered. A "why is my net worth X" panel makes the endgame legible —
players can't optimise what they can't see. *(UI; new issue.)*

**Quick wins already filed:** Meat orphan (#74, prefer Option A — gives the
kitchens a second protein and the Farmer a value line), Vaccine→flu (#49),
Banker AI lending (#72 — matters more after P1).

## 4. Suggested sequencing

1. **P5 first** (measurement — cheap, informs everything).
2. **P1 + P2 together** (one calibration pass for both: spread+depth tames the
   faucet, payroll adds the sink).
3. **P3** once P2 exists (wages fund consumption).
4. **P4, P6, P7** as a follow-up wave; P4 after the Transporter's role in P3
   demand is visible.

Each lands with a sim calibration check (win-rate spread across roles +
the new money-supply chart).
