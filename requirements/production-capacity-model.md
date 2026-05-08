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

- Each player starts with **zero production capacity**. Their starting Dollops
  balance is whatever they have left after winning their role at auction.
- Each role is presented a **catalogue of buyable capital equipment** (see §6).
- A **mandatory minimum default investment** is pre-selected per role (enough
  to produce at least each output once). The player can override but the screen
  warns if they leave themselves unable to produce any output.
- Investments are **private** — players see only their own role's choices.
- A **timer** runs (always — "unlimited" games use a very large value). The
  remaining time is displayed and **flashes when ≤ 60 s remaining**.
- Mid-game purchases are allowed during normal turns. Complex equipment
  (anything tagged "(2 seasons)" in the catalogue) takes **2 seasons to arrive**
  after purchase.

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

**(b) Capital equipment catalogue** — the buyable items that gate parallel
production capacity (the items players purchase in the Investing Phase or
during normal turns).

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

| Island | Manager (university) | Technician (apprenticeship) | Worker |
|---|---|---|---|
| Farmer | Farmer | Farming Foreman, Mechanic | Farmhand |
| Miner | Mining Engineer / Geologist | Mining Foreman, Refiner, Mechanic | Pit Worker |
| Transporter | Engineer | Pilot, Logistics Foreman, Mechanic | Stevedore |
| Educator | Professor | Lecturer / Tutor / Trainer | Admin |
| Banker | Banker | Analyst, Banking Clerk | Receptionist |
| Manufacturer | Engineer | Factory Foreman, Assembly Tech, Mechanic | Assembler |
| Doctor | Doctor / Nurse | Medical Orderly | Aide |

**University grad seasons** (Education pipeline):
- Doctor: 2 seasons
- Nurse: 1 season
- Other Managers (Farmer, Engineer, Banker, Professor, etc.): 2 seasons

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
**Outputs:** Food, Fish, Apprentice Farming Foreman *(see §8)*

| Output | Oil | Food | Fish | Manager | Technician | Worker |
|---|---|---|---|---|---|---|
| 1 Food | 3 | — | 1 | 0.1 | 0.4 | 1 |
| 1 Fish | 2 | 1 | — | 0.1 | 0.4 | 1 |

| Capital item | Cost | Effect |
|---|---|---|
| Tractor | 60 Dp | +5 Food capacity |
| Harvester (2 seasons) | 90 Dp | +3 Food, –1 Technician need |
| Fishing Boat | 50 Dp | +4 Fish capacity |
| Storage Building | 40 Dp | +10 inventory cap |

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

| Output | CapitalEquipment | Finance | Research-stock | Manager | Technician | Worker |
|---|---|---|---|---|---|---|
| 1 Knowledge | 0.25 | 0.25 | gives multiplier | 1 (Professor) | 0.5 (Lecturer) | 0.5 |
| 1 Patent | 0.5 | 0.5 | required input | 2 (Professor) | 1 (Researcher) | — |

| Capital item | Cost | Effect |
|---|---|---|
| Lecture Hall | 50 Dp | +4 Knowledge capacity, +N Education slots |
| Library | 40 Dp | +2 Knowledge, +1 Patent |
| Research Lab (2 seasons) | 100 Dp | +3 Patent capacity, +Research stock |
| Computer Cluster (2 seasons) | 80 Dp | +1 Patent, –0.2 CapitalEquipment per output |
| Apprenticeship Programme | 60 Dp | +N Apprenticeship slots (separate from Education) |

**Research** is an internal lever, not a sellable resource: it accumulates
when the Educator runs research-grade equipment and Professors, and it
multiplies per-unit Knowledge yield + is consumed when producing Patents.

### 🏦 Banker
**Outputs:** Finance, InsurancePolicies

| Output | Money (Dp) | Knowledge | CapitalEquipment | Manager | Technician |
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

The University coordinates the curriculum, but **the apprentice stays on their
home island** for the duration and continues working at their existing level
(no productivity loss while training).

- Apprentice consumes a **separate Apprenticeship slot pool** at the Educator
  (gated by Apprenticeship Programme capital + Lecturer/Trainer Technicians).
- After N seasons (typically 2), the worker promotes from Worker → Technician
  on their home island.
- An island that already employs Technicians of the relevant kind (Farmer,
  Engineer, Mechanic) can run **in-house apprenticeships** as a sellable
  output (cheaper / faster than the University route). Buyers receive an
  Apprentice token that joins their workforce as a Technician after a 2-season
  probation.

Examples:
- Farmer island sells "Apprentice Farming Foreman" tokens.
- Manufacturer sells "Apprentice Mechanic" or "Apprentice Engineer".

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

## 11. Mechanic profession

A new Technician-tier profession that spans Farmer, Miner, Manufacturer,
Transporter.

- Each Mechanic on staff reduces equipment-loss probability from adverse
  events by **20 %** (additive, capped at **60 % total reduction**).
- Mechanics are produced by Educator's Apprenticeship pipeline OR by
  Manufacturer in-house apprenticeships.

---

## 12. Equipment Insurance

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

## 13. Starting inventory pattern (already implemented)

Each island starts with:

1. **One round's worth of outputs** to sell in the opening round.
2. **One round's worth of production inputs** to produce again next round.

Anything further must be purchased on the market. Implemented in
`constants.STARTING_INVENTORY`.

---

## 14. AI auction bidding

AI players must participate in the role auction (not just take whatever's
left).

- Per-role bid heuristic that values higher-margin roles (Banker,
  Manufacturer) more aggressively.
- AI must pay the bid amount from their starting Dollops if they win.
- AI bids capped at a fraction of starting Dollops to leave operating capital.
- A second bidding round runs if any roles are unclaimed or tied.

---

## 15. Implementation order (proposed)

1. Worker bands + per-island titles + starting mix (model + UI labels).
2. Production capacity data structures (per-output capital item registry +
   per-unit input + labour requirements tables).
3. Investing Phase — server flow + UI panel + mandatory-minimum defaults +
   timer.
4. Production Capacity sidebar panel + Constraint Popup.
5. Patents (Educator output + buyer-side persistent boost + cap).
6. Apprenticeship pipeline (separate slot pool + Lecturer/Trainer tier).
7. Education pipeline (Manager training, season-cost variations: Doctor 2,
   Nurse 1, others 2).
8. Mechanic profession + reliability boost.
9. Equipment Insurance from Banker.
10. AI auction bidding.
11. Simultaneous-play architecture (timer + Ready button replaces End Turn).

---

## 16. Future: Auction Margin Lending (Banker + IMF)

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

## 17. Future: Roleless Players — Role Aftermarket + Bank Deposits

When the auction allows multiple-role wins (per the recent fix), it's possible
for some players (especially in 7-human games) to end up with **zero roles**.
They are not eliminated — they have two paths to keep playing:

### 17.1 Role aftermarket (secondary sales)

- Roleless players can **wait** for another player to put one of their roles
  up for sale.
- Sellers can **list a role** on a "roles for sale" board with an asking
  price (or accept a private offer).
- Buyer pays seller, role transfers — buyer inherits the role's capital
  inventory and workforce. Treat this as transferring the entire island.
- **Open questions:**
  - Does selling a role include the loans owed by the role's owner, or do
    those stay with the seller? Default: loans stay with the original
    borrower (separate ledger entries).
  - Does the buyer take over patents purchased on that island? Default: yes
    (they go with the role).
  - Minimum / maximum sale price rules? Default: free market, no caps.

### 17.2 Bank deposits ("call money")

While roleless (or even alongside running an island), a player can park their
Dollops in the Bank as **on-call deposits**:

- Player and Banker negotiate a deposit **interest rate** (per-season or
  annualised).
- The Banker can **on-lend** these deposits — they expand the Banker's
  lending capacity beyond their own balance sheet.
- Deposits are **on call**: depositor can withdraw at any time during their
  next-round action window. (May earn no interest if held for a partial
  season — TBD on accrual rules.)
- If the Banker can't honour an immediate withdrawal because they've lent it
  all out, the deposit becomes a forced loan from the depositor to the
  Banker (at the agreed rate) until the Banker's loans repay — or the IMF
  margin facility (§16) backstops it.

### 17.3 Implementation pieces required

- New player state: `deposits: list[Deposit]` with `(banker_id, principal,
  rate, opened_tick)` records.
- New TurnActions: `DEPOSIT_FUNDS`, `WITHDRAW_FUNDS`, `LIST_ROLE_FOR_SALE`,
  `BUY_ROLE`.
- WS messages for the role aftermarket board.
- UI: a "spectator dashboard" for roleless players showing the deposit
  position, the role listings board, and pending offers.
- Banker dashboard gains a **deposit liabilities** section + deposit interest
  cost on their P&L.

### 17.4 Open design questions

1. Can a player be both an island owner *and* a depositor (i.e. park spare
   cash in the bank for income)? Probably yes — keeps the mechanic open to
   everyone.
2. Does the Banker have to accept a deposit, or is it automatic at a
   published rate?
3. Negative balance for the Banker (over-lent) — allowed at all? Capped?
4. Default risk: can the Banker default on deposits? If so, what's the
   resolution flow (fire-sale of bank capital? IMF backstop?).

## 18. Open / TBD items

- Patent boost wording for UI ("–20% input cost on …")
- Whether a player can take actions after pressing Ready
- Apprenticeship slot capacity values per Educator capital item
- Equipment Insurance: per-season vs. per-year billing cycle
- Production calculator UX (extended feature, not blocking initial release)
