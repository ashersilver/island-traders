# Brief — AI revenue-opportunity advisory (2026-06-11)

**Suggested owner:** Codex (engine + AI strategy).
**Base off:** current `origin/pre-release`.
**Issue:** new (file as "AI: revenue-opportunity advisory", label `area:ai`).

## The problem (observed)

The Manufacturer AI doesn't realise it can make money selling FarmMachinery.
Root cause in `island_traders/engine/ai.py`:

- `_choose_product_line_profit` only scores product lines that have a **live
  market bid** (`bid_lines = [... if market.best_bid(output) is not None]`).
- `_has_human_equipment_demand` only fires when a **human** player's role
  consumes a Manufacturer output (or has training in flight).

So in any game where the Farmer is an AI (or simply hasn't posted a bid yet),
the Manufacturer sees no bid + no *human* demand and never notices that the
Farmer **structurally must** buy FarmMachinery every season to produce at all.
Demand is inferred from live bids + human consumers, never from the **structural
consumption map**. The B1/B2 liveness data confirms the symptom: end products
and equipment are produced but barely traded.

## What to build

A reusable **revenue-opportunity advisory** that ranks, for a given island, what
is most profitable to produce — driven by *structural* demand across all
islands, not just posted bids — and the workforce/inputs needed to capture it.
Consumed by both the rule-based AI **and** the LLM agents (via the server
payload, so `island-traders-agents` can surface it too).

### Core helper (engine)

`revenue_opportunities(player, market, all_players, season_name, ...) -> list[dict]`,
one entry per producible output for this island's role(s):

```
{
  "output": "FarmMachinery",
  "unit_price": <current market/bid price>,
  "unit_input_cost": <Σ recipe input prices (+ freight surcharge)>,
  "unit_margin": <unit_price − unit_input_cost>,
  "structural_demand_units": <Σ over all islands of their per-season need for
        this output from PRODUCTION_INPUTS / MANUFACTURER_PRODUCT_LINES /
        FARMER_SEASONAL_CONVERSION — i.e. who must consume it to produce>,
  "live_bid_units": <Σ resting bid quantity on the order book>,
  "recommended_qty": <min(production capacity, demand) this season>,
  "required_professions": [<from SKILLED_PROFESSIONS / LABOUR_REQUIREMENTS>],
  "inputs_to_stockpile": {<resource>: <qty for recommended_qty>},
}
```

Rank by `unit_margin × max(structural_demand_units, live_bid_units)` (a true
"expected profit" signal). Structural demand is the key new ingredient — it is
computed from the recipe tables (`PRODUCTION_INPUTS`,
`MANUFACTURER_PRODUCT_LINES`, `FARMER_SEASONAL_CONVERSION`), so the Manufacturer
learns the Farmer needs FarmMachinery whether or not a bid is posted.

### Wire into the rule AI

- Replace the bid-only gate in `_choose_product_line_profit` (and feed
  `_choose_product_line`) with `argmax` over `revenue_opportunities`. The AI
  should pick the highest expected-profit line even when demand is latent
  (no live bid yet) — fixing the FarmMachinery blind spot.
- Use `required_professions` / `inputs_to_stockpile` to inform the AI's training
  and input-buying decisions (it already has procurement heuristics from #29 —
  point them at the chosen opportunity's inputs).

### Expose to agents (server payload)

Add a `revenue_opportunities` array to the per-player game-state payload in
`island_traders/server/app.py` (next to `wealth_breakdown`). The LLM agents
(`island-traders-agents`) render it as a legible "what's most profitable + what
to stockpile" hint — see that repo's `MULTI_ROLE_PLAN.md` ("revenue-opportunity
feedback"). This is also the "predict workforce skills and resources to
stockpile" capability the maintainer asked for.

## Scope / out

- **In:** the advisory helper, rule-AI rewire for product-line selection, server
  payload field, tests. Applies to all producer roles, not just Manufacturer
  (Farmer/Doctor/Educator product choices benefit too).
- **Out:** changing prices or recipes (no rebalance — this is decision support).
  No change to the P1/P2 market mechanics (compose with them; if P1 lands first,
  `unit_price` should read the spread-adjusted bid/ask).

## Acceptance

- A test where an **AI** Farmer needs FarmMachinery and no bid is posted:
  `revenue_opportunities` for the Manufacturer ranks FarmMachinery > 0 structural
  demand, and the Manufacturer AI chooses to produce it.
- Margin/structural-demand values match a hand-computed fixture for one role.
- Server payload includes `revenue_opportunities`; UX-payload test updated if it
  pins keys.
- Full suite green; APP_VERSION bump + RELEASE_NOTES.
- Re-run `--games 1000 --seed 42`: equipment/end-product **traded** volume rises
  off the B1/B2 floor and the Manufacturer/Farmer win-rate gap narrows.
