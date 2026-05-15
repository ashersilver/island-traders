# Island Traders — Rules of the Game

## Overview

Island Traders is a resource-trading board game for **2 to 7 players**. Each player governs an island built around a different economic sector. Every season you produce resources, trade with other players, develop your workforce, and negotiate deals. After a set number of years the player with the highest total wealth wins.

The game can be played as a **physical board game** (using printed cards, tokens, and dice) or as a **digital game** (using the Island Traders software with optional online chat).

---

## Contents

### Physical edition
- 7 Role Cards (one per island)
- 7 Island Event Chart tables (one per island)
- 1 Market Price Board
- Season Scorecards
- Resource tokens — **Food, Fish, Ore, Metal, Oil, Freight, Knowledge, Goods,
  Health Services, Vaccine, Finance, Passenger Seats, Patents**
- Capital-equipment tokens — Farm Machinery, Mining Equipment, Lab Equipment,
  Medical Devices, Transport Equipment
- Dollop coins
- Worker tokens by **band** — Manager, Technician, Worker — and by training
  level (Untrained, Basic, Skilled, Expert)
- Worker-Away tokens (for tracking workers in training)
- Loan and Insurance contract cards (small slips noting principal/rate/term
  or premium/expiry, signed by both parties)
- 1 ten-sided die (d10) or a shuffled Event Card deck per island

### Digital edition
All of the above is handled by the software.  Print the physical assets at
any time with:

```
island-traders-export --output ./printables
```

(equivalent to `python -m island_traders.export.printables --output ./printables`)

---

## The Seven Islands

Each player takes one role. Roles are not pre-assigned — the game begins with a
**sealed-bid auction** (see Auction Phase below) and a single player may win
**more than one** island.

| Role | Island | Produces | Needs to Produce |
|---|---|---|---|
| **Farmer** | Agriculture, Fisheries & Foods Island | Food, Fish | Farm Machinery, Oil |
| **Miner** | Mining & Oil Island | Ore, **Metal**, Oil | Oil, Freight, Mining Equipment |
| **Transporter** | Transportation & Shipping Island | Freight, **Passenger Seats** | Oil, Fish (crew provisions) |
| **Educator** | Education & Training Island | Knowledge, **Patents** | Laboratory Equipment, Finance |
| **Banker** | Banking Island | Finance, **Insurance**, **Loans** | Knowledge |
| **Manufacturer** | Manufacturing Island | Goods + capital equipment lines (Farm Machinery, Mining Equipment, Medical Devices, Transport Equipment, Lab Equipment) | **Metal**, Oil, Freight |
| **Doctor** | Healthcare Island | Health Services, Vaccine | Knowledge, Laboratory Equipment |

> **Multi-role play:** A single player can win multiple islands in the auction
> (they manage each island independently). If two or more humans want to
> *share* one role by agreement (e.g. dividing buying vs. selling
> responsibilities) they nominate one active player for production each season.
> All sharing agreements are recorded on the Chat Board.

> **Metal as an intermediate:** The Manufacturer no longer consumes raw Ore.
> Mining smelts Ore + Oil into Metal on-island, and the Manufacturer's product
> lines consume Metal.  Mining can also sell raw Ore directly if a player
> prefers.

---

## Starting Conditions

Each player begins the game with:

- **700 Dollops** (auction budget; see Auction Phase below).  The currency symbol is **Dp**.
- After the auction, any unspent Dollops are the player's **personal cash**
  that they bring to their island(s).
- A **starting stockpile** of the resources each island needs for roughly its
  first two seasons of production (so a player has time to establish trade
  links before running out of inputs).
- A **starting workforce** appropriate to the role.  Every island starts with
  **at least 1 Manager + 2 Technicians** plus general unskilled labour.
- A **base production capacity** representing the island's existing physical
  infrastructure (buildings, machinery, established routes and equipment),
  which guarantees a minimum level of output even before the workforce is
  fully skilled up.

| Role | Workers | Composition | Base Capacity | Population |
|---|---|---|---|---|
| Farmer | 6 | 1 Farmer, 1 Farming Technician, 1 Veterinarian, 3 Unskilled | 60% | ~100 |
| Miner | 5 | 1 Miner, 1 Mining Technician, 1 Oil Extraction Worker, 2 Unskilled | 50% | ~100 |
| Transporter | 4 | **1 Logistics Manager, 1 Flight Crew, 1 Seaman, 1 Warehouse Manager** | 65% | ~100 |
| Educator | 4 | 1 Professor, 2 Tutors, 1 Unskilled | 55% | ~100 |
| Banker | 4 | 1 Banker, 1 Banking Analyst, 1 Banking Clerk, 1 Unskilled | 70% | ~100 |
| Manufacturer | 5 | 1 Engineer, 1 Assembly Worker, 1 Mechanic, 2 Unskilled | 50% | ~100 |
| Doctor | 6 | 2 Doctors, 2 Nurses, 2 Medical Orderlies | 55% | ~100 |

> **Workforce rule:** Every island starts with at least 1 Manager and 2
> Technicians.  Managers run the strategy and the production line; Technicians
> are the skilled operational backbone.  Untrained workers can be recruited
> from the island population and then trained up to either tier (see Training).

> **Base Capacity** is the minimum effective production factor guaranteed by
> the island's physical plant. When a workforce's efficiency falls below this
> threshold (e.g. workers away at training), the island still produces at the
> base capacity rate. As the workforce gains experience and training it will
> eventually surpass the base capacity.

> **Population** is distinct from the workforce.  Each island starts with ~100
> residents.  The workforce is a subset of these people.  New residents are
> born at the end of each year but are **not** automatic workers — they must be
> actively **recruited** (see Recruit Workers action on your turn).

> **Healthcare Island full capacity** = 4 Doctors + 20 Nurses + 20 Medical
> Orderlies + unskilled aides.  Starting at 2 Doctors + 2 Nurses + 2 Medical
> Orderlies means the clinic operates at partial capacity until additional
> staff are recruited and trained.

---

## Setting Up: Auction, Island Guarantee, and Investing

Before Year 1 begins, three short phases assign islands and let owners
configure their starting capital.

### 1. The Role Auction

The seven islands are awarded by a **sealed-bid auction**:

- Each human player starts with **700 Dollops** of auction budget.
- Players submit bids on any subset of the seven roles.  A single player can
  bid on (and win) **more than one role** — useful when there are fewer than
  7 humans, or when a player is happy to run two islands.
- The highest bid on each role wins that role.  Ties are broken by bid
  timestamp (whoever bid earliest wins).
- Winners pay their bid amount; losers pay nothing.  Unspent budget remains
  the player's personal cash going into the game.
- **Idle humans** (no winning bid) automatically claim any role nobody bid
  on.  **Idle AIs** absorb the next leftover.  Any roles still unclaimed get
  generic AI island operators ("Banker Island (AI)", etc.).

> **`require_all_human`** is a room option for groups of 7 that want every
> role to be held by a human.  If the auction leaves any role unclaimed the
> auction restarts.

### 2. The Post-Auction Island Guarantee

If, after the auction, a **human player has no island** AND at least one **AI
player won 2 or more islands**, the islandless human gets one chance to buy
an island from that AI before Year 1 starts.  This is a safety valve — the
AI must sell if a human picks one of its extras.

The price is computed by formula so it isn't an open negotiation:

1. Let `S` = the player's starting auction budget (700 Dp by default).
2. Let `P` = the AI's winning bid for this specific role.
3. Let `floor` = 20% of the buyer's current cash.
4. Compute the auction-price formula based on `P/S`:
   - If `P` is between **11% and 15%** of `S` (inclusive) → formula = **2 × P**
   - If `P` is **above 15%** of `S` → formula = **1.05 × P**
   - Otherwise (below 11%) → formula = `P`
5. **Final price = max(formula, floor)**.

The buyer can accept any one offer or decline all.  If they accept, the full
island state — inventory, equipment, workforce, loans, leases, obligations —
transfers with the role.  Buyers are processed sequentially in join order;
each gets a 90-second timer.  If a sole AI sells its only extra and now has
just one island, it is no longer eligible — subsequent islandless humans in
the queue see no offers and proceed to Investing roleless.

A roleless human can still play (sit out the first year or buy in via a
future role aftermarket — feature pending).

### 3. The Investing Phase

Every island owner is given a **capital catalogue** and a budget (whatever's
left of their starting capital after the auction).  Each item in the
catalogue is named equipment with a cost, a delivery delay, and the
production capacity it adds.

- The **mandatory minimum investment** for each role is pre-selected — these
  are the items the island needs to produce at all in Year 1.
- Optional upgrades can be added (subject to budget).
- A 3-minute timer ends the phase.  AI players auto-submit; humans click
  Ready when finished.

After the Investing Phase resolves, Year 1 begins.

---

## Structure of Play

### The Year
A game lasts **1 to 5 years** (agreed before play begins; 3 years is standard). Each year consists of **four seasons** played in order:

1. Spring
2. Summer
3. Autumn
4. Winter

### The Season
At the start of each season:

1. **Training returns** — any workers who were sent to the Education Island last season return home with upgraded training.
2. **Event rolls** — each island draws or rolls on its **Event Chart** to determine this season's outcome modifier.
3. **Player turns** — each player takes their turn in the agreed order (decide at setup; rotate each year if desired).
4. **Market reset** — at the end of the season, market demand signals reset and prices are recorded.

### Your Turn
On your turn you may take **any number of actions** in any order:

| Action | Description |
|---|---|
| **Produce** | Consume your inputs and generate your island's resources.  Output is modified by the season's event result and your workforce efficiency. |
| **Market Buy** | Purchase resources from the central market at the current dynamic price. |
| **Market Sell** | List resources for sale on the central market. |
| **Propose Deal** | Offer a peer-to-peer trade directly to another player — any combination of resources, quantities, and a Dollop sweetener. |
| **Purchase Capital** | Buy named capital equipment from the Manufacturer (e.g. Farm Machinery, Mining Equipment, Lab Equipment).  Complex items have a 2-season delivery delay. |
| **Apply Patent** | Activate a Patent from inventory on one of your outputs — permanent –20% input cost on that output (max 3 active patents per output). |
| **Request Training** | Send workers to the Education Island for one season (requires Educator and Transporter agreement).  Choose the target profession. |
| **Review Training** | *(Educator only)* Approve or reject incoming training requests. |
| **Arrange Transport** | *(Transporter only)* Accept or counter-offer transport jobs for workers going to college. |
| **Recruit Workers** | Draw unskilled workers from your island's population into your workforce (1 recruit per 2 unskilled residents). |
| **Sell Insurance** | *(Banker only)* Sell a Life or Medical insurance policy to another player at a negotiated premium. |
| **Buy Insurance** | Buy a policy from a Banker at the offered premium. |
| **Manage Insurance** | Review your active policies.  Cancel a policy mid-term for a pro-rata refund (premium × seasons remaining ÷ total term). |
| **Offer Loan** | *(Banker only)* Offer a loan to another player at a quoted rate. |
| **Take Loan** | Borrow from a Banker.  The Banker quotes a rate = posted funding rate + minimum 2% spread + borrower risk premium. |
| **Roll Over Loan** | Refinance an active loan at or before maturity.  The old loan's repayment becomes the new loan's principal at a fresh rate and term (1–3 years).  No cash moves at rollover. |
| **View Loans** | See your outstanding loans, repayment amounts, and maturity dates. |
| **Inventory** | View your current resources, Dollops, workforce breakdown, and total wealth. |
| **View Market** | See current prices and available supply for all resources. |
| **View Players** | See all players' current Dollops and wealth. |
| **End Turn** | Pass to the next player. |

> **Simultaneous play (online):**  In the digital game every human player
> takes their turn on their own clock — turns run concurrently, not in strict
> order.  A configurable **pre-season review window** lets everyone inspect
> last season's results before trading opens, and a **season timer** caps each
> action phase.  The host can **Pause** the game at any time; all timers
> freeze and an overlay shows on every client until the host resumes.

---

## Production

### How Production Works

When you **Produce**, your island generates resources according to the formula:

```
Output = Base Production × Event Yield Modifier × Workforce Factor
```

- **Base Production** is fixed per role.  The Farmer additionally varies by
  season (Spring/Summer favour Fish; Autumn is the bumper Food harvest).
  The Manufacturer chooses one product line per season (Farm Machinery, Mining
  Equipment, Lab Equipment, Medical Devices, Transport Equipment, or general
  Goods) and uses the inputs/produces the outputs of that line.
- **Event Yield Modifier** is determined by your island's Event Chart roll this season (0.0 = nothing, 1.0 = normal, 1.8 = bumper crop).
- **Workforce Factor** = Fill Rate × Average Worker Efficiency (see Workforce below).

Before producing, you must have your **production inputs** in inventory.  These are consumed when you produce:

| Role | Inputs consumed each season |
|---|---|
| Farmer | 1 Farm Machinery + 1 Oil |
| Miner | 1 Oil + 1 Freight + 1 Mining Equipment |
| Transporter | 2 Oil + 1 Fish *(crew provisions)* |
| Educator | 1 Lab Equipment + 1 Finance |
| Banker | 1 Knowledge |
| Manufacturer | Varies by product line: typically **Metal** + Oil + Freight |
| Doctor | 1 Knowledge + 1 Lab Equipment |

If you do not have the required inputs, you cannot produce this season.  You
can buy inputs from the market, negotiate with other players, or use the
**Purchase Capital** action to buy named equipment from the Manufacturer.

### Capital Equipment

Capital equipment is **named, depreciating** machinery — tractors, fishing
boats, foundries, research labs, hospital wards, and so on.  Each item lives
in the Manufacturer's catalogue.  Unlike resource tokens (which are consumed
each season), capital equipment is an owned **asset**.

- **Purchase** — pay the catalogue cost from your working capital and own the
  item outright, subject to any delivery delay.
- **Mid-game buying** — use the **Purchase Capital** action.  Simple items
  arrive immediately; complex items have a **2-season delivery delay**.
- **Book value** — straight-line depreciation over **5 years** from the
  purchase cost.  A 3-year-old item has 40% of its original cost on the
  balance sheet.
- **Leases** *(future)* — a 3-year lease arrangement is on the roadmap.  At
  the end of the lease the item can be returned or bought out at book value.

### Patents

The Educator produces **Patents** alongside Knowledge.  Each Patent applied
via the **Apply Patent** action gives a permanent **–20% input cost** on one
output the player produces, up to **3 active patents per output**.

---

## The Market

### Dynamic Prices
The market price of each resource changes based on supply and demand:

- When **supply is high** relative to demand → price falls (floor: 20% of base price).
- When **supply is scarce** relative to demand → price rises (ceiling: 500% of base price).
- **Disaster events** can cause sudden price spikes for affected resources.

Base prices (in Dollops per unit):

| Resource | Base Price | Source |
|---|---|---|
| Food | 10 Dp | Farmer |
| Fish | 8 Dp | Farmer |
| Ore | 15 Dp | Miner |
| Metal | 25 Dp | Miner *(smelted from Ore + Oil)* |
| Oil | 20 Dp | Miner |
| Freight | 12 Dp | Transporter |
| Knowledge | 18 Dp | Educator |
| Lab Equipment | 28 Dp | Manufacturer |
| Farm Machinery | 32 Dp | Manufacturer |
| Mining Equipment | 42 Dp | Manufacturer |
| Medical Devices | 50 Dp | Manufacturer |
| Transport Equipment | 65 Dp | Manufacturer *(no freight surcharge)* |
| Goods | 30 Dp | Manufacturer |
| Health Services | 35 Dp | Doctor |
| Vaccine | 40 Dp | Doctor |
| Finance | 20 Dp | Banker |
| Passenger Seats | 15 Dp | Transporter *(charter flight / ship berth)* |
| Patents | 80 Dp | Educator *(one-time +20% input efficiency)* |

> The Manufacturer now produces several distinct capital-equipment **product lines**
> rather than a single generic "Capital Equipment".  Each island uses the
> equipment that matches its production (e.g. the Farmer needs Farm Machinery,
> the Doctor needs Lab Equipment + Medical Devices).

### Peer-to-Peer Deals
Players can bypass the market and trade directly at any privately negotiated price. A deal specifies:

- **Offer**: resource type + quantity (can be zero for a pure Dollop payment)
- **Request**: resource type + quantity (can be zero)
- **Dollop sweetener**: additional Dollops from proposer to target (or negative = target pays proposer)

The target player accepts or rejects. If accepted, both sides are committed — the resources and Dollops transfer immediately.

---

## Workforce

### Worker Efficiency
Every worker on your island has two properties that together determine their **efficiency** (output contribution as a fraction of their maximum potential):

1. **Experience** — gained automatically by working each season (+5% efficiency per season worked). Experience raises efficiency but only up to the worker's current training plateau.
2. **Training Level** — raised by attending the Education Island (see Training below). Each training level raises the efficiency ceiling:

| Training Level | Title | Efficiency Ceiling |
|---|---|---|
| 0 | Untrained | 40% |
| 1 | Basic | 65% |
| 2 | Skilled | 85% |
| 3 | Expert | 100% |

> **Key principle:** Experience without training hits a ceiling. A highly experienced untrained worker tops out at 40% efficiency. Training unlocks the next ceiling, after which experience fills it.

### Workforce and Production
Each island has a seasonal workforce requirement. If your active workforce (workers currently on the island, not away at training) is below the requirement, your production scales down proportionally.

Seasonal requirements:

| Role | Spring | Summer | Autumn | Winter |
|---|---|---|---|---|
| Farmer | 4 | 6 | **8** | 2 |
| Miner | 5 | 5 | 5 | 4 |
| Transporter | 4 | 5 | 6 | 3 |
| Educator | 4 | 2 | 4 | 4 |
| Banker | 3 | 3 | 4 | 3 |
| Manufacturer | 5 | 5 | 5 | 4 |
| Doctor | 30 | **35** | 30 | **44** |

> Farmers need most workers at harvest (Autumn). Healthcare Island peaks in Summer (injuries) and Winter (illness). Full capacity = 4 Doctors + 20 Nurses + 20 unskilled workers (44 total).

### Worker Professions
Workers are not generic — each belongs to a **profession** that reflects their specialisation.  Every profession also has a **band** — *Manager*, *Technician*, or *Worker* — which determines training pathway and role on the island.  A worker's tier is shown as their profession name plus training level (e.g. *Doctor (Basic)*, *Flight Crew (Skilled)*).  Unskilled workers have no profession until they graduate from university or finish an apprenticeship.

| Profession | Band | Island | Notes |
|---|---|---|---|
| Farmer | Manager | Agriculture | Crop and fishery specialist |
| Farming Technician | Technician | Agriculture | Day-to-day farm operations |
| Veterinarian | Technician | Agriculture | Livestock health |
| Miner | Manager | Mining & Oil | Mining engineer / geologist |
| Mining Technician | Technician | Mining & Oil | Drilling and ore handling |
| Oil Extraction Worker | Technician | Mining & Oil | Crude oil drilling |
| Refinery Specialist | Technician | Mining & Oil | Refinery / smelter operations |
| **Logistics Manager** | Manager | Transport | Strategic fleet & route planning |
| Engineer | Manager | Transport / Manufacturing | Fleet & infrastructure engineering |
| **Flight Crew** | Technician | Transport | Air freight operations |
| **Seaman** | Technician | Transport | Sea freight operations |
| **Warehouse Manager** | Technician | Transport | Ground-ops supervisor *(name is industry convention; classified as Technician)* |
| Professor | Manager | Education | University teaching (max 1 graduate/season) |
| **Lecturer** | Manager | Education | Faculty teaching staff |
| **Tutor** | Technician | Education | Apprentice-trained teaching staff |
| Banker | Manager | Banking | Lending, deposits, insurance |
| **Banking Analyst** | Technician | Banking | Risk and pricing analysis |
| **Banking Clerk** | Technician | Banking | Operations and account servicing |
| Assembly Worker | Technician | Manufacturing | Factory floor production |
| Doctor | Manager | Healthcare | Medical diagnosis and treatment |
| Nurse | Manager | Healthcare | Patient care and vaccine administration |
| **Medical Orderly** | Technician | Healthcare | Ward and theatre support |
| Mechanic | Technician | Multi-island | –20% downtime per Mechanic, capped –60% |

Professions marked **bold** are recent additions; see the Quick Reference at
the end for which professions each island starts with.

### Population Growth
At the end of each year, each island's population grows by up to **2% per year**. The actual growth rate is **inversely proportional to the island's wealth** — richer islands grow slower (reflecting the demographic transition observed in real economies). New workers arrive untrained.

---

## Training

Training workers requires negotiation between **three parties**: the island sending workers, the **Educator**, and the **Transporter**. It is a multi-turn process:

### Capacity Limits
The University has **per-profession annual quotas**.  Each profession has a fixed number of graduate places per year.  Some professions also have a stricter per-season cap.

| Profession | Band | Annual cap | Seasonal cap |
|---|---|---|---|
| Doctor | M | 2 | — |
| Nurse | M | 10 | — |
| Engineer | M | 2 | — |
| Farmer | M | 2 | — |
| Miner | M | 2 | — |
| Banker | M | 2 | — |
| Professor | M | 4 | **1 per season** |
| Farming Technician | T | 4 | — |
| Veterinarian | T | 1 | — |
| Assembly Worker | T | 10 | — |
| Mining Technician | T | 4 | — |
| Oil Extraction Worker | T | 2 | — |
| Refinery Specialist | T | 2 | — |
| Mechanic | T | 4 | — |

Once a profession's annual quota is full, no further requests for that
profession can be submitted until the following year.

> **Note on the newly-named professions** (Logistics Manager, Flight Crew,
> Seaman, Warehouse Manager, Lecturer, Tutor, Banking Analyst, Banking Clerk,
> Medical Orderly): these arrive on the starting workforce of their home
> island.  Training caps for these professions will be added in a future
> balance pass — until then, growth happens by recruiting unskilled workers
> and training them into the established legacy professions, or by hiring
> from the population pool directly.

### Step 1 — Request Training
On your turn, choose **Request Training**. You specify:
- The **target profession** for your workers to graduate into (must have remaining university quota)
- How many workers to send (they must be on your island and not already at Expert level)
- Which Educator player will train them
- How many Dollops you offer the Educator
- How many Dollops you offer the Transporter for moving the workers

Unskilled workers sent to university enter the target profession at Basic level. Workers who already hold that profession advance one level (Basic → Skilled → Expert).

Your workers are **not yet absent** at this point.

### Step 2 — Educator Approval
The Educator reviews the request on their turn and either **approves** (accepts the Dollop payment) or **rejects** it.

- If rejected, your workers stay home and you keep your Dollops.
- If approved, the Dollops transfer to the Educator and the request moves to Step 3.

### Step 3 — Choose Transport

When submitting the request you choose one of three transport modes:

| Mode | Cost | Arrival |
|---|---|---|
| **Charter flight** | 20% of educator fee (paid upfront) | Same season — workers depart immediately on educator approval |
| **Cargo vessel** | Free for up to 2 passengers | Workers arrive at Education Island **one season late** — total absence is 2 seasons |
| **Hire Transporter** | Negotiated with the Transporter player | Same season once Transporter agrees |

> Cargo is cheapest but means your workers are away for two seasons instead of one. Use it in seasons where you can afford the extra absence (e.g. Winter).

### Step 4 — Educator Approval
The Educator reviews the request on their turn and either **approves** or **rejects** it. On approval, funds transfer immediately.

- For **flight** and **cargo** modes, workers depart as soon as the Educator approves (no separate Transporter step).
- For **Transporter** mode, the request moves to the Transporter for agreement.

### Step 5 — Departure & Return
Once all parties have agreed, your workers **depart**. They do not count toward your workforce while away.

At the **start of their return season** they come home with training level increased by one. Their experience is unchanged — they develop from where they left off, but the efficiency ceiling is higher.

> **Tip:** Send workers by cargo in Winter (low seasonal demand) to absorb the two-season absence at minimal production cost.

---

## Vaccines

The Healthcare Island produces **Vaccines** in addition to Health Services. Each unit of Vaccine represents a course of vaccination for one worker or resident.

- **Production:** The Doctor island produces 1 Vaccine per season alongside its Health Services output (no extra inputs required beyond the standard Knowledge + Capital).
- **Effect:** A Vaccine applied to a worker improves their wellness for **4 seasons**, conferring a small efficiency bonus and reducing the likelihood of illness-related absences.
- **Trading:** Vaccines can be sold on the market or traded peer-to-peer like any other resource.
- **Base price:** 40 Dp per unit.

> In future expansions the wellness mechanic will interact with the workplace injury and illness system to reduce downtime on labour-intensive islands.

---

## Loans

The Banker is the lender of record for the game's economy.  Loans are
**bullet bonds** — the borrower receives the full principal up front and
repays principal + interest in a single payment at maturity.  No periodic
coupons.

### Borrowing

A player takes a loan via the **Take Loan** action:

1. The borrower names a principal and a term in years (1, 2, or 3).
2. The Banker computes a quote:
   ```
   rate = posted funding rate (term-dependent) + 2% minimum spread
        + borrower risk premium
   ```
   The risk premium grows with the borrower's existing debt load and the
   ratio of requested principal to their cash on hand.
3. The borrower confirms or declines.  On confirmation, the Bank advances
   the principal; the borrower owes `principal × (1 + rate)` at maturity.

> **Banker self-bid:** A player who won the Banker role can offer loans to
> themselves on another island they own.  The cash effectively shuffles
> between the player's ledgers but the loan still appears in the system
> (and is repaid at maturity from the borrowing island's cash).

> **External funding:** If a customer wants more than the Banker's cash on
> hand, the Bank borrows the shortfall externally at the posted funding
> rate.  This appears as a separate loan with `lender_id = -1`.

### Repayment and Default

At the season when a loan matures the borrower must repay `principal + interest`
out of their working capital.  If they can't, they pay everything they have
and the loan is marked **DEFAULTED** (the lender absorbs the shortfall).

### Roll Over (Refinance)

At or before maturity a borrower can **Roll Over** an active loan:

- The old loan's repayment amount becomes the new loan's principal.
- The Banker quotes a fresh rate for a new 1–3 year term.
- **No cash changes hands at rollover** — the new advance exactly covers the
  old repayment.
- The old loan is marked `ROLLED_OVER`; the new loan starts at the current
  season.

Use Roll Over to lock in a better rate, extend an obligation past a tight
season, or restructure a stack of small loans into one longer-dated one.

---

## Insurance

The Banker sells two products: **Life Insurance** and **Medical Insurance**.
Both are **annual policies** valid for 4 seasons from purchase.

| Product | Base Premium | What it covers |
|---|---|---|
| Life Insurance | 25 Dp / worker | Pays a 60 Dp death benefit per fatality on the covered island |
| Medical Insurance | 25 Dp / worker | Halves the injury-absence rate (–50%) for covered workers |

### Buying and Selling

- **Sell Insurance** *(Banker only)*: Pick a buyer, set a premium (default =
  base), buyer confirms.  Premium goes to the Bank.
- **Buy Insurance**: Any player can buy an active policy from a Banker at the
  offered premium.

### Managing Active Policies

Use **Manage Insurance** to review and cancel policies mid-term:

- The policy holder picks an active policy.
- Cancelling deactivates it immediately.
- A **pro-rata refund** is paid by the Banker to the holder:

  ```
  refund = premium_paid × (seasons remaining ÷ total term in seasons)
  ```

  Example: A 40 Dp policy with 4 seasons total, cancelled with 2 seasons
  remaining → refund = 40 × (2/4) = 20 Dp.

### High-Hazard Roles

Farmer, Miner, Transporter, and Manufacturer are flagged as high-hazard.
Workers on those islands are more likely to suffer injury or fatality events
and stand to gain more from coverage.

---

## Island Event Charts

At the start of each season every island rolls on its own Event Chart. The result modifies that island's production for the season. Examples:

| Island | Event | Effect |
|---|---|---|
| Farmer | Bumper Harvest | Yield ×1.8, +2 bonus units |
| Farmer | Drought | Yield ×0.3, Food price spike |
| Farmer | Crop Failure | Production halted |
| Farmer | Flood | Production halted, 1-season infrastructure damage, **disaster** |
| Miner | Rich Vein | Yield ×2.0 |
| Miner | Mine Collapse | Production halted, 2-season damage |
| Miner | Earthquake | Production halted, **disaster** affecting all islands |
| Banker | Bull Market | Yield ×1.7, +2 bonus Capital |
| Banker | Bank Crisis | Production halted, Capital price spike, **disaster** |
| Doctor | Disease Outbreak | Yield ×0.3, Health Services price spike, **disaster** |

**Disaster events** affect all islands simultaneously and trigger market price shocks that last one or more seasons.

**Physical play:** Roll a d10 against the percentages on your island's printed Event Chart, or draw from a shuffled 20-card event deck (weights convert to card counts: 50% = 10 cards, 15% = 3 cards, etc.). Reshuffle at the start of each year.

### Calibrating the Charts
The event weights are configurable in `config/event_charts.yaml`. Use the simulation runner to test balance:

```
python -m island_traders.simulation.runner --games 500 --years 3 --seed 42
```

Adjust weights until win rates are roughly equal across all roles.

---

## Winning the Game

At the end of the last year, each player's **net wealth** is calculated:

```
Net Wealth = Dollops
           + (Units of each resource × current market price)
           + capital equipment book value
           + loans receivable
           - loans outstanding
```

Capital equipment book value uses straight-line depreciation over 5 years from catalogue cost. The player with the highest net wealth wins. Loans are counted at the full repayment amount due, including interest, so borrowed Dollops are not double-counted as free wealth.

In the event of a tie, the player who made the most successful deals (accepted by the other party) wins. If still tied, share the victory.

---

## Online Play — Chat and Negotiations

When playing online, the game provides a **chat system** for negotiating deals.

### Chat Rooms
- Any player can create a chat room and invite any subset of other players.
- A player may be in **as many rooms simultaneously** as they wish — one per ongoing negotiation.
- All chat history is saved to the game database and can be reviewed after the game.

### Formal Agreements
When players reach a verbal agreement in chat, it should be formalised:

1. One player posts a **Proposal** in the chat room, describing the agreed terms in plain language.
2. Each named party **accepts** or **rejects** on their next turn.
3. Once all parties accept, the agreement is **ratified** and posted automatically to the **Chat Board**.
4. If any party rejects, the deal falls through and the board is not updated.

Agreements can be linked to game engine actions (training requests, resource deals) so that ratification triggers the action automatically.

### The Chat Board
The Chat Board is a **shared public record** visible to all players. It lists every ratified agreement in chronological order with the agreed terms. Use it to:

- Hold players accountable for verbal commitments
- Track the history of alliances and trades
- Refer back to multi-season agreements (e.g. "Farmer agrees to supply Manufacturer with 2 Ore per season for the next 2 years")

---

## Example of Play

**Setup:** 4 players — Alice (Farmer), Bob (Banker), Carol (Educator), Dave (Transporter). Playing 3 years.

**Spring, Year 1:**
- *Event rolls:* Alice: Normal Harvest. Bob: Stable Markets. Carol: Normal Semester. Dave: Normal Operations.
- *Alice's turn:* Alice has 2 Capital in inventory. She produces 4 Food + 3 Fish. She sells 3 Food to the market for 30 Dp.
- *Bob's turn:* Bob produces 3 Capital with no inputs needed. He sells 2 Capital to the market for 50 Dp.
- *Carol's turn:* Carol buys 1 Capital from the market (25 Dp). She produces 4 Knowledge. She proposes a deal to Alice: "3 Knowledge for 20 Dp." Alice accepts.
- *Dave's turn:* Dave needs Oil to produce Freight — none on the market yet. He ends his turn.

**Summer, Year 1 — Alice requests training:**
- Alice opens a chat room with Carol and Dave. They negotiate: Alice will send 2 workers to college. She offers Carol 40 Dp and Dave 10 Dp. Carol and Dave accept in the chat. Alice formalises the agreement as a Proposal; both sign it.
- On her turn, Alice selects **Request Training**: 2 workers, offers 40 Dp to Carol, 10 Dp to Dave.
- Carol (AI or human) approves. Dave approves. Workers depart — Alice now has 4 active workers instead of 6.
- Alice produces with reduced workforce (fill rate 67%), yielding fewer Food/Fish this season.

**Autumn, Year 1:**
- At season start: Alice's 2 workers return with Basic training (level 1). Their efficiency ceiling rises from 40% to 65%.
- Alice is now stronger for the rest of the game.

---

## Quick Reference

**Turn actions:** Produce · Market Buy · Market Sell · Propose Deal · Purchase
Capital · Apply Patent · Request Training · Review Training · Arrange
Transport · Recruit Workers · Sell / Buy / Manage Insurance · Offer / Take /
Roll Over Loan · View Loans · Inventory · View Market · View Players · End Turn

**Setup phases (in order):** Auction → Island Guarantee → Investing → Year 1

**Wealth formula:** Dollops + Σ(resource units × current price) + depreciated equipment book value + loans receivable − loans outstanding

**Production formula:** Base × Event Modifier × max(Base Capacity, Fill Rate × Avg Efficiency)

**Resources (current set):**
Food · Fish · Ore · **Metal** · Oil · Freight · Knowledge · Goods ·
Lab Equipment · Farm Machinery · Mining Equipment · Medical Devices ·
Transport Equipment · Health Services · Vaccine · Finance · Insurance ·
Loans · **Passenger Seats** · **Patents**

**Capital equipment lines** (Manufacturer): Goods (general), Farm Machinery,
Mining Equipment, Medical Devices, Transport Equipment, Lab Equipment.
Each island uses the line matching its production.

**Workforce baseline:** Every island starts with ≥1 Manager + ≥2 Technicians.

**Starting auction budget:** 700 Dp per human.

**Island Guarantee price:** `max(20% × buyer's cash, formula)`, where formula
= 2×P / 1.05×P / P for P/S in [11–15%] / >15% / <11% respectively (S = 700).

**Loan rate:** posted funding rate + 2% spread + borrower risk premium.
Bullet bond — pay principal × (1+rate) at maturity, or Roll Over.

**Insurance refund (Manage Insurance):** `premium × seasons_remaining ÷ total_term`.

**Training transport:**
- ✈️ Flight: 20% of educator fee, immediate departure
- 🚢 Cargo vessel: free for ≤ 2 passengers, +1 season delay
- 🚤 Transporter: negotiated fee, immediate departure

**University quotas:** per profession (Doctor 2/yr, Nurse 10/yr, Professor
4/yr max 1/season … see Training Capacity table).

**Recruit Workers:** 1 unskilled recruit per 2 unskilled residents
(population − employed workforce).

**Birth rate:** 2% per year × (1 − wealth ratio) — richer islands grow slower.

**Market floor/ceiling:** 20% – 500% of base price.

**Vaccines:** Healthcare produces 1/season; each unit improves worker wellness for 4 seasons.

**Patents:** Educator produces 1/season; each Patent applied gives –20% input
cost on the chosen output (max 3 per output).
