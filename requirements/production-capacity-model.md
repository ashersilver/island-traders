# Production Capacity Model & Investing Phase

Status: **draft requirements** (not yet implemented)
Source: synthesised from design conversation + planning spreadsheet (now gitignored)

This document captures the next major design iteration for Island Traders. It
introduces an explicit production-capacity model (capital equipment + workforce
+ operating inputs), a dedicated **Investing Phase** at the start of every game,
a three-band worker classification, and a redesigned **Educator** with patents
and apprenticeships.

---

## 1. Game flow (updated)

1. Lobby / room setup (number of years, season-timer duration, etc.)
2. Role bidding (auction)
3. **Investing Phase** *(new)*
4. Year 1 Spring → Summer → Autumn → Winter
5. Year 2 …
6. Game over → wealth ranking

---

## 2. Investing Phase

A new phase between role bidding and Year 1 Spring.

- Each island starts with **zero purchased production capacity** and receives
  **300 Dp of island working capital** in its island ledger. This is separate
  from the owner's auction budget and bank deposits; see
  `requirements/island-ledger.md`.
- After bidding, any owner cash left from the auction budget is automatically
  placed on deposit with the Bank at **5% p.a.** The Investing Phase budget for
  an island is therefore its island working capital plus any explicit capital
  injection or loan proceeds, not silently pooled owner cash.
- Each role is presented a **catalogue of buyable capital equipment** (see §6).
- A **mandatory minimum default investment** is pre-selected per role (enough
  to produce at least each output once). The player can override but the screen
  warns if they leave themselves unable to produce any output.
- Investments are **private** — players see only their own role's choices.
- A **timer** runs (always — "unlimited" games use a very large value). The
  remaining time is displayed and **flashes when ≤ 60 s remaining**.
- Mid-game purchases and leases are allowed during normal turns. Complex
  equipment (anything tagged "(2 seasons)" in the catalogue) takes **2 seasons
  to arrive** after acquisition.

---

## 3. Season advance — two modes

Each game runs in **simultaneous play** (all players act in parallel during a
season, not strictly one-at-a-time).

A season ends when **either** of the following triggers fire — whichever comes
first:

1. **Timer expires** (default mode). Configurable countdown set at room
   creation (e.g. 600 s). The remaining time is always displayed and
   **flashes when ≤ 60 s remaining**. On expiry, all in-flight deals/decisions
   are auto-resolved with safe defaults and outstanding actions are committed.
2. **All players signal "Ready to proceed"**. The Ready button replaces the
   current "End Turn" button at the bottom of the screen. Once everyone has
   pressed Ready, the season advances immediately even if the timer has not
   expired.

A player who has pressed Ready can still observe but **cannot take new actions
this season** (TBD — confirm during implementation).

Inter-player deal proposals appear as a **queued "Pending Deals" list** the
recipient can review at any time during the season — they do not interrupt
flow.

---

## 4. Production capacity model

For each role, capacity is described by **two complementary tables**:

**(a) Per-unit input requirements** — what 1 unit of each output costs in
operating resources, Dollops (where applicable), and labour.

**(b) Capital equipment catalogue** — the physical asset category that gates
parallel production capacity (the items islands purchase or lease in the
Investing Phase or during normal turns). Capital equipment is not a single
resource type.

Capital equipment may be acquired by outright purchase or by a **3-year lease**.
At lease end, the equipment is returned or bought out for book value. Book value
uses straight-line depreciation over **5 years** from catalogue cost.

### Maximum producible (per output, per season)

```
max_producible(output) = min(
    equipment_capacity(output),    # gated by capital items the player owns
    workforce_capacity(output),    # Manager / Technician / Worker availability
    input_capacity(output)         # determined by inventory / market purchases
)
```

The **Production Constraint Popup** (§9) tells the player which of those three
caps is binding for each output and how many additional units of the binding
resource would lift it.

### A future "production calculator" (extended feature)

Provide an interactive calculator: the player enters trial values for each
input and the calculator returns predicted outputs. Useful for planning
purchases and deals without committing them.

---

## 5. Three worker bands

All workers across all islands fall into one of three bands. Per-island titles
differ but the mechanics are identical.

| Band | Source | Cost / Time |
|---|---|---|
| **Manager** | University Education | Long, expensive (≈ 2–4 seasons) |
| **Technician** | Apprenticeship via University | Mid-length (≈ 2 seasons), worker stays on home island |
| **Worker** | Hired from island population | Immediate, no training |

### Per-island worker titles

These titles are display/training vocabulary over the generic three-band
mechanic. A role may have more than one title in a band when its island has
distinct operating lines.

| Island | Manager | Technician | Worker | Notes |
|---|---|---|---|---|
| Medical | Doctor; Researcher | Lab Technician; Nurse | Orderly | Laboratory and clinical work share the island. |
| Mining | Mining Engineer; Extraction Engineer; Geologist | Technician; Drilling Specialist | Labourer | Top line is mining; second line is oil extraction. |
| Farming | Farm Manager; Captain (fishing) | Foreman; Fishing Foreman | Farmhand; Fisherman | Top line is farming; second line is fishing. |
| Banking | Banker; Actuary | Loan Officer; Broker | Clerk | Lending, insurance, and market services share staff. |
| Manufacturing | Engineer | Tradesman | Factory Worker | Covers ForgeHaven product lines. |
| Transportation | Captain; Pilot / Copilot | Petty Officer; Aircraft Service Technician | Sailor; Steward; Ground Crew | Sea and air operations share the island. |
| Educator | Professor; Technical Director | Lecturer; Mentor | Worker; Apprentice | Top line is academic; second line is technical/apprenticeship. |

**University grad seasons** (Education pipeline) — canonical table is in
`requirements/education-model.md` (Duration table):
- Doctor: **3 seasons** (ruled 2026-05-17)
- Nurse: 1 season
- Other Managers (Farmer, Engineer, Banker, Professor, Lecturer,
  Logistics Manager, Miner): 2 seasons

### Starting workforce mix (default)

`1 Manager + 2 Technicians + 3 Workers = 6 starting workforce` per island.

The Doctor island keeps a slightly different shape (1 Doctor + 1 Nurse +
3 Medical Orderlies + 1 Aide = 6) to reflect both Manager-tier roles being
medically trained.

---

## 6. Per-island capital catalogues (draft)

All items have **infinite lifetime** unless destroyed by an adverse event.
Items marked "(2 seasons)" take 2 seasons to arrive when purchased mid-game
(immediate availability during the Investing Phase).

### 🌾 Farmer
**Outputs:** Grain, Produce, Fish, Meat, Food, Apprentice Farming Foreman *(see §8)*

| Output | Grain | Produce | Fish/Meat | Oil | Manager | Technician | Worker |
|---|---|---|---|---|---|---|---|
| 1 Grain | — | — | — | 1/6 | 0.1 | 0.4 | 1 |
| 1 Produce | — | — | — | 1/2 | 0.1 | 0.4 | 1 |
| 1 Fish | — | — | — | 1/3 | 0.1 | 0.4 | 1 |
| 1 Meat | 4 | — | — | — | 0.1 | 0.4 | 1 |
| 1 Food | 1 | 1 | 1 | — | 0.1 | 0.4 | 1 |

| Capital item | Cost | Effect |
|---|---|---|
| Tractor | 60 Dp | +10 Grain, +6 Produce capacity |
| Harvester (2 seasons) | 90 Dp | +6 Grain, +4 Produce, –1 Technician need |
| Fishing Boat | 50 Dp | +4 Fish capacity |
| Livestock Barn | 70 Dp | +4 Meat capacity |
| Industrial Kitchen | 75 Dp | +6 packaged Food capacity |
| Storage Building | 40 Dp | +10 inventory cap |

Notes: Meat consumes **4 Grain** as feedstock.  Food is a convenience
product: a balanced packaged ration made from 1 Grain + 1 Produce + 1 Fish
**or** Meat.  Agriculture needs Horticulturalist depth for Produce and
Veterinarian depth for Meat if it wants those lines to scale efficiently.
After the second season of the year, Produce productivity drops by **25%**
without a Horticulturalist, and Meat productivity drops by **25%** without a
Veterinarian.

### ⛏️ Miner
**Outputs:** Ore, Oil, Apprentice Mining Foreman

| Output | Oil | Freight | Manager | Technician | Worker |
|---|---|---|---|---|---|
| 1 Ore | 0.5 | 0.5 | 0.1 | 0.5 | 1 |
| 1 Oil | — | 0.5 | 0.1 | 0.5 | 0.5 |

| Capital item | Cost | Effect |
|---|---|---|
| Excavator | 70 Dp | +4 Ore capacity |
| Crusher | 50 Dp | +2 Ore, –0.2 Oil per Ore |
| Oil Rig (2 seasons) | 110 Dp | +4 Oil capacity |
| Refinery (2 seasons) | 100 Dp | +2 Oil, enables RefinerySpecialist multiplier |

### 🚢 Transporter
**Outputs:** Freight, PassengerSeats, Apprentice Pilot

| Output | Oil | Food | Manager | Technician | Worker |
|---|---|---|---|---|---|
| 1 Freight | 0.5 | — | 0.1 | 0.25 | 1 |
| 1 PassengerSeat | 0.4 | 0.25 | 0.1 | 0.25 | 1 |

| Capital item | Cost | Effect |
|---|---|---|
| Cargo Ship | 80 Dp | +6 Freight capacity |
| Cargo Plane (2 seasons) | 130 Dp | +4 Freight (fast) |
| Passenger Liner | 90 Dp | +5 PassengerSeats |
| Passenger Plane (2 seasons) | 140 Dp | +5 PassengerSeats (fast) |

Notes: Transporter refines its own jet fuel from Oil. Food provisions services.

### 🎓 Educator
**Outputs:** Knowledge, Patents *(see §7)*
**Programmes (services, not tradeable resources):** Education, Apprenticeship

| Output | Lab / campus capital access | Finance | Research-stock | Manager | Technician | Worker |
|---|---|---|---|---|---|---|
| 1 Knowledge | 0.25 | 0.25 | gives multiplier | 1 (Professor) | 0.5 (Lecturer) | 0.5 |
| 1 Patent | 0.5 | 0.5 | required input | 2 (Professor) | 1 (Researcher) | — |

| Capital item | Cost | Effect |
|---|---|---|
| Lecture Hall | 50 Dp | +4 Knowledge capacity, +N Education slots |
| Library | 40 Dp | +2 Knowledge, +1 Patent |
| Research Lab (2 seasons) | 100 Dp | +3 Patent capacity, +Research stock |
| Computer Cluster (2 seasons) | 80 Dp | +1 Patent, –0.2 lab/campus capital access per output |
| Apprenticeship Programme | 60 Dp | +N Apprenticeship slots (separate from Education) |

**Research** is an internal lever, not a sellable resource: it accumulates
when the Educator runs research-grade equipment and Professors, and it
multiplies per-unit Knowledge yield + is consumed when producing Patents.

### 🏦 Banker
**Outputs:** Finance, InsurancePolicies

| Output | Money (Dp) | Knowledge | Banking capital access | Manager | Technician |
|---|---|---|---|---|---|
| 1 Finance | 5 Dp | 0.5 | 0.5 | 1 (Banker) | 0.25 |
| 1 InsurancePolicy | 8 Dp | 0.5 | 0.25 | 1 (Banker) | 0.5 (Analyst) |

| Capital item | Cost | Effect |
|---|---|---|
| Vault | 60 Dp | +4 Finance capacity |
| Trading Floor | 70 Dp | +3 Finance, +1 InsurancePolicy |
| Underwriting Desk | 50 Dp | +3 InsurancePolicies capacity |
| Reinsurance Treaty (2 seasons) | 100 Dp | –50% fatality payout cost |

The "Money" input represents capital reserve / hedge cost (Banker only).

### 🏭 Manufacturer
**Outputs:** the four product lines from `MANUFACTURER_PRODUCT_LINES` +
Apprentice Factory Foreman / Mechanic

| Capital item | Cost | Effect |
|---|---|---|
| Foundry | 80 Dp | enables FarmMachinery + MiningEquipment lines |
| Assembly Line | 70 Dp | +1 unit/season on any line |
| Precision Workshop (2 seasons) | 100 Dp | enables MedicalDevices line |
| Shipyard (2 seasons) | 120 Dp | enables TransportEquipment line |

### 🏥 Doctor
**Outputs:** HealthServices, Vaccine, Apprentice Medical Orderly

| Output | Knowledge | MedicalDevices | Manager (Doctor) | Manager (Nurse) | Technician |
|---|---|---|---|---|---|
| 1 HealthService | 0.25 | 0.25 | 0.5 | 0.5 | 1 |
| 1 Vaccine | 0.5 | 1 | 1 | 1 | — |

| Capital item | Cost | Effect |
|---|---|---|
| Hospital Ward | 60 Dp | +4 HealthServices capacity |
| Operating Theatre (2 seasons) | 100 Dp | +2 HealthServices, +1 Vaccine |
| Vaccine Lab (2 seasons) | 110 Dp | +2 Vaccine capacity |
| Cold Chain Storage | 40 Dp | Vaccine doesn't expire between seasons |

---

## 7. Patents

Sellable on the market or via direct deal. When bought by a Farmer / Miner /
Manufacturer / Doctor (etc.):

- Applies a **permanent productivity boost** to one chosen output: either
  – 20 % input requirement on that output (default mechanic).
- A buyer may hold up to **3 active patents per output** (cap to prevent
  runaway snowball).
- Each patent is **single-use per buyer** — buying the same patent twice has
  no effect; further boosts require additional patents (up to the cap).

Patents are produced by the Educator using Research stock + Professors + a
Research Lab or Computer Cluster.

---

## 8. Apprenticeships

> **Canonical model: see `requirements/education-model.md` →
> "Apprenticeship pipeline (Technician training)".**  The earlier
> "apprentice stays home / no productivity loss / in-house sellable
> token" model documented here was **superseded on 2026-05-17**.  This
> section is kept only as a pointer to avoid divergence.

In brief (full detail in `education-model.md`):

- Technician apprenticeship is gated by the Educator's **apprenticeship
  slot pool** (`educator.apprenticeship_programme` capital,
  `apprenticeship_slots`) **and Instructor (trainer) capacity** — *not*
  by Courses (Courses gate Manager-tier university training only).
- The apprentice spends **1 season at the Education Island**, then
  returns home and works at **75% productivity for exactly one season**
  before reaching 100%.
- **Dropped:** the "home-island Apprenticeship Facility" capital flag and
  the cross-island "in-house apprenticeship sellable token" mechanic.

---

## 9. Production Constraint Popup (per season)

Each player sees a popup at the start of every season (and on demand)
showing, **per output**:

1. **Resource inputs** — which inputs are short, and how many more units would
   uncap each output.
2. **Workforce** — Manager / Technician / Worker shortfalls vs. seasonal
   requirements, and how many more workers are needed.
3. **Capital equipment** — current capacity vs. what's needed; cost to lift
   the cap (purchase price of the next capital item).

Each constraint shows the **marginal cost** of relieving it (e.g. "buy 4 more
Oil at market price 12 Dp = 48 Dp" or "hire 1 more Worker at 8 Dp/season").

---

## 10. Production Capacity Panel (left sidebar)

A new sidebar section, distinct from the role panel (e.g. "Farmer"), Inventory,
and Insurance. Shows:

- The island's current capital-equipment portfolio (count of each item).
- The maximum producible per output given current capital + workforce.
- Items "in transit" (purchased mid-game, arriving in N seasons).

---

## 11. Product and Equipment Help

Every product/resource and every capital-equipment item should have associated
Help text available wherever it appears in the UI.

The Help copy should be a short paragraph, not just a label. It should explain:

- What the product or equipment does in game terms.
- The pros of owning or producing it, including outputs it enables, capacity
  it increases, revenue opportunities, or strategic advantages.
- The cons/costs of owning or producing it, including required inputs,
  workforce needs, delivery delays, depreciation, operating risk, or
  standard-of-living side effects.
- Any special logistics rules, such as commodity shipping delay or Freight
  requirements.

Implementation expectations:

- Help should be stored as structured catalogue data rather than hard-coded in
  the frontend.
- Product Help should attach to `ResourceType` / product-line definitions.
- Equipment Help should attach to `CapitalItem` definitions.
- The UI can surface Help through tooltips, info buttons, or a detail modal,
  but the wording should come from the shared catalogue data so CLI, server,
  printables, and browser views stay consistent.

Example:

> Freight — Transport by Shipping Container. Used to move commodities and plant
> between islands. Pros: unlocks shipping-heavy trades and equipment delivery.
> Cons: must be bought or produced ahead of need, and shortages can block
> commodity arrivals or Manufacturing equipment sales.

---

## 12. Future: Cross-Island Machinery Licences

Any island may eventually buy any machinery from the Manufacturing Island, not
only the machinery usually associated with that island's native role. Owning
the machinery grants access to the same production recipe as the specialist
island, but **does not grant the specialist's inputs, workforce, or social
licence for free**.

Rules to preserve:

- Manufacturing remains the source of the machinery/capital item.
- The buyer must still provide the recipe's normal operating inputs.
- If the cross-island recipe depends on shipped commodity inputs, the
  production clock includes that logistics delay. For example, a Bank island
  refinery must buy and receive Oil before it can run, so Petrochemicals take
  **one additional season** to produce.
- The buyer must staff the machinery with the required worker bands and, where
  relevant, specialist professions.
- Cross-island production should appear as an additional production line on
  the buyer's island, with its own capacity and constraints.
- The standard of living on the buyer's island may fall when heavy or dirty
  industry is added outside its normal economic base. That penalty should feed
  into population satisfaction, salary pressure, and migration/perk demand.

Example:

- The Bank island buys an Oil Refinery from Manufacturing.
- It can produce Petrochemicals using the same inputs as the normal refinery
  line, but must buy Oil and employ an Engineer plus 4 Technicians to operate
  it.
- Because the Oil must be purchased and transported to the Bank island,
  Petrochemicals complete one season later than a native, already-supplied
  refinery line.
- The Bank island's standard of living falls because refinery operations make
  the island less attractive to high-income financial workers.
- To retain staff, the Bank may need higher salaries and quality-of-life perks
  such as a small clinic, better transport, or similar amenities.

Implementation implications:

- Capital items need an `unlocks_recipe` / `foreign_recipe` capability, not
  only a role-scoped capacity effect.
- Production capacity must support recipes owned by capital equipment rather
  than only recipes implied by `Player.roles`.
- Workforce requirements must distinguish generic bands from specialist
  profession requirements.
- Standard-of-living modifiers should become first-class inputs to wages,
  recruitment, retention, and migration.

Commodity and equipment logistics:

- Purchased commodities such as Metal, Ore, Oil, Food, and Fish require
  shipping and arrive in the following season.
- Freight represents "Transport by Shipping Container" and should be labelled
  that way in player-facing explanations.
- Equipment purchases such as Mining Equipment include the Freight cost in the
  quoted equipment price, but the Manufacturer must still acquire and consume
  the Freight needed to move plant and machinery.
- This means a capital sale can be blocked by the Manufacturer lacking Freight
  even when the buyer can afford the equipment and the manufactured equipment
  resource exists.

Open design questions:

1. Should cross-island production require a licence/patent from the specialist
   island, or is the machinery purchase enough?
2. How much output efficiency is lost when production happens outside its
   native island cluster?
3. Do quality-of-life perks offset pollution/congestion directly, or only
   reduce salary pressure?

---

## 13. Mechanic profession

A new Technician-tier profession that spans Farmer, Miner, Manufacturer,
Transporter.

- Each Mechanic on staff reduces equipment-loss probability from adverse
  events by **20 %** (additive, capped at **60 % total reduction**).
- Mechanics are produced by Educator's Apprenticeship pipeline OR by
  Manufacturer in-house apprenticeships.

---

## 14. Equipment Insurance

A new insurance product sold by the Banker, alongside Life and Medical
insurance.

- **Payout:** market replacement value of the destroyed/damaged item at the
  moment of loss.
- The player must use the payout (plus any extra Dp) to **repurchase** the
  equipment — insurance covers cost, not replacement.
- **Premium** scales with insured value of the equipment portfolio.
- Coverage is per-season or per-year (TBD during implementation; align with
  existing Life / Medical model).

---

## 15. Starting inventory pattern (already implemented)

Each island starts with:

1. **One round's worth of outputs** to sell in the opening round.
2. **One round's worth of production inputs** to produce again next round.

Anything further must be purchased on the market. Implemented in
`constants.STARTING_INVENTORY`.

---

## 16. AI auction bidding

AI players must participate in the role auction (not just take whatever's
left).

- Per-role bid heuristic that values higher-margin roles (Banker,
  Manufacturer) more aggressively.
- AI must pay the bid amount from their starting Dollops if they win.
- AI bids capped at a fraction of starting Dollops to leave operating capital.
- A second bidding round runs if any roles are unclaimed or tied.

---

## 17. Implementation order (proposed)

1. Worker bands + per-island titles + starting mix (model + UI labels).
2. Production capacity data structures (per-output capital item registry +
   per-unit input + labour requirements tables).
3. Investing Phase — server flow + UI panel + mandatory-minimum defaults +
   timer.
4. Production Capacity sidebar panel + Constraint Popup.
5. Product/equipment Help catalogue + tooltip/modal UI.
6. Patents (Educator output + buyer-side persistent boost + cap).
7. Apprenticeship pipeline (separate slot pool + Lecturer/Trainer tier).
8. Education pipeline (Manager training, season-cost variations: Doctor 2,
   Nurse 1, others 2).
9. Mechanic profession + reliability boost.
10. Equipment Insurance from Banker.
11. Cross-island machinery licences + standard-of-living impact.
12. AI auction bidding.
13. Simultaneous-play architecture (timer + Ready button replaces End Turn).

---

## 18. Future: Auction Margin Lending (Banker + IMF)

> **Note**: Margin loans appear on the **island ledger**, not the player's
> personal account. See `island-ledger.md §2` for the cash-flow model and
> `island-ledger.md §3` for the Banker institutional pool mechanics.

Allow players to borrow against their starting capital when bidding so they
can outbid above their cash balance.

- Maximum bid budget = **150 % of starting capital**
  (e.g. 700 Dp starting → up to 1 050 Dp in total bids)
- The extra 50 % is automatically granted as a **margin loan from the Banker**
  at **10 % interest** per the standard 1-year bullet-bond mechanic.
- The Banker funds these margin loans with a back-to-back **5 % loan from the
  IMF** (an off-screen counter-party), using the borrower's **Island role as
  collateral** — i.e. if the Island defaults, the IMF can claim the role's
  capital portfolio.
- Spread (10 % – 5 % = 5 %) accrues to the Banker as guaranteed margin
  income; this is the Banker's reward for backing the auction system.
- Margin loans are visible on the borrower's balance sheet from Year 1
  Spring onwards and must be repaid like any other bullet bond.

Implementation hooks already present:
- Loan ledger + bullet-bond mechanic exists (`models/loan.py`)
- Banker sells loans (existing TurnManager action)

Outstanding design questions (defer to implementation):
- What happens if the player bids the full 1 050 Dp on losing bids?
  (Probably: only the winning bid amount becomes a margin loan.)
- Does the IMF rate change with the Banker's reinsurance treaty / capital
  reserves?
- Visibility: does the borrower see the IMF leg, or only the Banker loan?

## 19. Future: Roleless Players — Role Aftermarket + Bank Deposits

> **Canonical reference**: Ownership transfers, island ledger semantics,
> deposit accounts, and loan/lease obligations are defined in
> [`requirements/island-ledger.md`](island-ledger.md). This section covers
> only the *gameplay scenarios and pricing rules* specific to roleless players.
> See `island-ledger.md §2–4` for the underlying cash-flow and transfer
> mechanics.

When the auction allows multiple-role wins (per the recent fix), it's possible
for some players (especially in 7-human games) to end up with **zero roles**.
They are not eliminated — they have two paths to keep playing:

### 19.1 Post-auction human island guarantee

If the island auction finishes and a **human** player has no island, they get
an immediate chance to buy an island from an AI player that won extra islands.
This is a safety valve before normal play begins, not a normal free-market
resale.

Rules:

- The islandless human chooses one island from an AI player that controls more
  than one island.
- The AI must sell the selected extra island.
- The human buyer inherits the island ledger: capital equipment, inventory,
  workforce, loans, leases, obligations, and any other island state.
- The sale price is calculated from the AI's auction price and starting wealth.

Price formula:

- Let `starting_wealth` be the player's starting wealth / auction budget.
- Let `ai_price_paid` be the winning auction bid paid by the AI for that
  island.
- Let `base_floor = 20% of the human player's current wealth`.
- If `ai_price_paid` is between **11% and 15%** of `starting_wealth`, the
  auction-price formula is `2 × ai_price_paid`.
- If `ai_price_paid` is **more than 15%** of `starting_wealth`, the
  auction-price formula is `ai_price_paid × 1.05`.
- Otherwise, the auction-price formula is `ai_price_paid`.
- Final price = the higher of `base_floor` and the auction-price formula.

Open implementation details:

- Confirm whether "between 11% and 15%" is inclusive at both ends.
- Confirm whether the AI can choose which of its extra islands are eligible,
  or whether all non-primary AI islands must be available.
- Confirm what happens if no AI player has an extra island.

### 19.2 Role aftermarket (secondary sales)

- Roleless players can **wait** for another player to put one of their roles
  up for sale.
- Sellers can **list a role** on a "roles for sale" board with an asking
  price (or accept a private offer).
- Buyer pays seller; the entire island ledger transfers per
  `island-ledger.md §4` (inventory, equipment, workforce, loans, leases,
  patents, insurance, and obligations go with the island).
- Pricing: free market, no caps (seller sets asking price, buyer confirms).

### 19.3 Bank deposits ("call money")

> Deposit mechanics (5% p.a., automatic post-auction placement, on-call
> withdrawal, Banker on-lending, forced-loan fallback) are defined in
> `island-ledger.md §3`. This section covers only the roleless-player
> gameplay implications.

Roleless players and island owners may deposit personal cash with the Bank.
The deposit expands the Banker's lending capacity and earns the depositor
interest. See `island-ledger.md §3` for terms, accrual rules, and
withdrawal mechanics.

### 19.4 Implementation pieces required

- New player state: `deposits: list[Deposit]` with `(banker_id, principal,
  rate, opened_tick)` records.
- New TurnActions: `DEPOSIT_FUNDS`, `WITHDRAW_FUNDS`, `LIST_ROLE_FOR_SALE`,
  `BUY_ROLE`, `BUY_AI_EXTRA_ISLAND`.
- WS messages for the role aftermarket board.
- UI: a "spectator dashboard" for roleless players showing the deposit
  position, the role listings board, and pending offers.
- Banker dashboard gains a **deposit liabilities** section + deposit interest
  cost on their P&L.

### 19.5 Open design questions

1. Can a player be both an island owner *and* a depositor (i.e. park spare
   cash in the bank for income)? Probably yes — keeps the mechanic open to
   everyone.
2. Does the Banker have to accept a deposit, or is it automatic at a
   published rate?
3. Negative balance for the Banker (over-lent) — allowed at all? Capped?
4. Default risk: can the Banker default on deposits? If so, what's the
   resolution flow (fire-sale of bank capital? IMF backstop?).

## 20. Open / TBD items

- Patent boost wording for UI ("–20% input cost on …")
- Whether a player can take actions after pressing Ready
- Apprenticeship slot capacity values per Educator capital item
- Equipment Insurance: per-season vs. per-year billing cycle
- Production calculator UX (extended feature, not blocking initial release)
- Cross-island machinery: licence requirement, efficiency penalty, and perk
  offsets for standard-of-living penalties
- Final Help copy for each product/resource and capital-equipment item

## 21. Food demand model refinement

*(From the 2026-05-15 playtest inbox.)*

Target model: a healthy seasonal diet requires **Grain + Produce + either Fish
or Meat**.  Packaged **Food** is the convenience substitute for that balanced
ration and should reasonably command a premium because it saves governors from
managing three lines.  Populations can survive on an unbalanced diet, but they
should lose productivity and become more susceptible to illness.

Legacy implementation note: the current coded alert model still speaks in
Food/Fish terms while this richer nutrition model is being introduced.  It
should be replaced with a balance-aware sustenance model rather than merely
renamed, otherwise packaged Food and raw ingredients will double-count demand.

Previous playtest feedback was that
the **base starting population should be modelled as already self-fed**
(they live off the island's own subsistence agriculture or local
fisheries) — only **additional population** beyond the starting headcount
creates *incremental* sustenance demand on the market.

Concretely:

- Baseline self-sufficiency: each island's starting ~100 residents are
  notionally fed by their own kitchen gardens / fishery; no Food demand
  generated by them on the global market.
- Each new resident added by population growth (or recruited from another
  island via future migration mechanics) creates **+1 unit of marginal
  Food demand per season** (number to be tuned).
- Educated workers continue to drive Fish demand (per the existing
  educated-workforce signal); this layer is unchanged.

**Why:** today's model has the Farmer fighting an uphill battle because
every island appears "hungry" from turn 1, which masks growth-driven
demand signals.  Decoupling base sustenance from marginal demand makes
population growth a meaningful trade-flow trigger.

**Implementation pointer:** `models/player.py` — `population_food_demand`
(or equivalent) computation; refactor to subtract a `BASE_POPULATION_SELF_FED`
constant before scaling.  Add a constant in `constants.py`
(suggest: `BASE_POPULATION_SELF_FED = 100`).

### Sustenance runway warnings

Players should not discover population hunger only after a shortage lands.
The dashboard should surface a forward-looking warning for Food and Fish:

- show current runway in **seasons** (`on_hand / seasonal_need`);
- warn below 2 seasons of runway;
- mark it as urgent below 1 season;
- recommend a concrete purchase quantity equal to
  `max(0, 2 × seasonal_need - on_hand)`, covering next season plus a
  one-season safety buffer.

The message should read like a decision aid, not a ledger entry:
“Fish runway: 0.5 seasons. You have 1; projected population need is
2/season. Buy 3 Fish to cover next season plus a one-season buffer.”

### Starting Food reserve and shortage recovery

Each island should begin with enough **Food** to feed its starting population
for one full year.  If an island later runs out of Food:

1. in the first shortage season, productivity falls by **30%**;
2. once Food is replenished, the island recovers naturally by **10 percentage
   points per season** until the penalty clears;
3. alternatively, the island may hire a **Nurse** from Healthcare to restore
   productivity immediately on arrival.

Nurse deployment is a cross-island service:

- the affected island pays Healthcare for the Nurse and the airfare;
- Healthcare must procure the required **PassengerSeat**;
- the Nurse restores productivity on arrival;
- the Nurse remains away from Healthcare and returns at the end of the
  following season.

This creates an emergency trade loop among Agriculture, Healthcare, and
Transportation without making one missed Food purchase an unrecoverable death
spiral.

## 22. Capital maintenance and fleet condition

Capital should not become free forever after purchase.  Every plant,
equipment, and property item carries a small **seasonal maintenance cost** in
Dollops, abstracting routine spares, repairs, upkeep, and minor consumables.

### Core rule

```
seasonal_maintenance_due = Σ(capital_item.maintenance_cost × owned_count)
```

This should be shown persistently on the left-hand island panel as a visible
line item:

- `Seasonal maintenance: 14 Dp`
- optionally, `Cash after maintenance: 86 Dp`

The UX goal is not to punish the player by surprise; it is to make the
operating burden of expansion legible before they overbuild.

### Deferred maintenance

If maintenance is not paid:

1. first missed season: warning / deferred-maintenance state;
2. repeated misses: capital condition declines;
3. poor condition: productive capacity or outage risk worsens.

The exact decay curve remains to be tuned, but maintenance should never reduce
to zero merely because a specialist is present.

### Transportation-specific consequence

Transportation is the clearest expression of this model.  Its fleet should
require:

- **Oil** for fuel;
- **Food** for crew provisioning;
- **Mechanics** as a meaningful workforce capability;
- enough paid maintenance to keep fleet condition healthy.

Mechanics should interact with fleet condition rather than replace money:
adequate Mechanics may reduce breakdown risk, slow condition decay, or modestly
improve maintenance efficiency, but they should not erase the maintenance bill.
This gives Transportation a richer operating problem without inventing a spare
parts commodity solely to make the spreadsheet busier.
