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
- Resource tokens (Food, Fish, Ore, Oil, Freight, Knowledge, Capital, Goods, Health Services, Vaccine)
- Dollop coins
- Worker tokens (Untrained, Basic, Skilled, Expert)
- Worker-Away tokens (for tracking workers in training)
- 1 ten-sided die (d10) or a shuffled Event Card deck per island

### Digital edition
All of the above is handled by the software. Print the physical assets at any time with:

```
python -m island_traders.export.printables --output ./printables
```

---

## The Seven Islands

Each player takes one role. In games with fewer than 7 players, some roles are unplayed (or a single player may hold more than one role by agreement).

| Role | Island | Produces | Needs to Produce |
|---|---|---|---|
| **Farmer** | Agriculture, Fisheries & Foods Island | Food, Fish | Capital |
| **Miner** | Mining & Oil Island | Ore, Oil | Oil, Freight |
| **Transporter** | Transportation & Shipping Island | Freight | Oil |
| **Educator** | Education & Training Island | Knowledge | Capital |
| **Banker** | Banking Island | Finance | — |
| **Manufacturer** | Manufacturing Island | Goods, Capital Equipment | Ore, Oil, Freight |
| **Doctor** | Healthcare Island | Health Services, Vaccine | Knowledge, Capital |

> **Multi-role play:** If there are more than 7 players, multiple players may share a role by mutual agreement. They divide responsibilities freely — for example one handles buying inputs and another manages sales. The active player for production rotates each season. All agreements between team members are recorded on the Chat Board.

---

## Starting Conditions

Each player begins the game with:

- **100 Dollops** (the game's currency, symbol **Dp**)
- A **starting stockpile** of the resources their island needs to produce in the first season (pre-game inventory)
- A **starting workforce** of several workers, some trained and some untrained, appropriate to their role
- A **base production capacity** representing the island's existing physical infrastructure (buildings, machinery, established routes and equipment), which guarantees a minimum level of output even before the workforce is fully skilled up

| Role | Starting Workers | Starting Professions | Base Capacity | Population |
|---|---|---|---|---|
| Farmer | 6 | 3 Farmer, 3 Unskilled | 60% | ~100 |
| Miner | 5 | 2 Miner, 1 Oil Extraction, 2 Unskilled | 50% | ~100 |
| Transporter | 4 | 2 Engineer, 2 Unskilled | 65% | ~100 |
| Educator | 3 | 2 Professor, 1 Unskilled | 55% | ~100 |
| Banker | 3 | 2 Banker, 1 Unskilled | 70% | ~100 |
| Manufacturer | 5 | 2 Assembly Worker, 3 Unskilled | 50% | ~100 |
| Doctor | 6 | 2 Doctor, 4 Nurse | 55% | ~100 |

> **Base Capacity** is the minimum effective production factor guaranteed by the island's physical plant. When a workforce's efficiency falls below this threshold (e.g. workers away at training), the island still produces at the base capacity rate. As the workforce gains experience and training it will eventually surpass the base capacity.

> **Population** is distinct from the workforce. Each island starts with ~100 residents. The workforce is a subset of these people. New residents are born at the end of each year but are **not** automatic workers — they must be actively **recruited** (see Recruit Workers action on your turn).

> **Healthcare Island full capacity** = 4 Doctors + 20 Nurses + 20 unskilled workers (44 total). Starting at 6 trained professionals (2 Doctors + 4 Nurses) means the clinic operates at partial capacity until additional staff are recruited and trained.

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
| **Produce** | Consume your inputs and generate your island's resources. Output is modified by the season's event result and your workforce efficiency. |
| **Market Buy** | Purchase resources from the central market at the current dynamic price. |
| **Market Sell** | List resources for sale on the central market. |
| **Propose Deal** | Offer a peer-to-peer trade directly to another player — any combination of resources, quantities, and a Dollop sweetener. |
| **Request Training** | Propose to send workers to the Education Island for one season (requires Educator and Transporter agreement). Choose the target profession. |
| **Review Training** | *(Educator only)* Approve or reject incoming training requests. |
| **Arrange Transport** | *(Transporter only)* Accept or counter-offer transport jobs for workers going to college. |
| **Recruit Workers** | Draw unskilled workers from your island's population into your workforce (1 recruit per 2 unskilled residents). |
| **Inventory** | View your current resources, Dollops, workforce breakdown, and total wealth. |
| **View Market** | See current prices and available supply for all resources. |
| **View Players** | See all players' current Dollops and wealth. |
| **End Turn** | Pass to the next player. |

---

## Production

### How Production Works

When you **Produce**, your island generates resources according to the formula:

```
Output = Base Production × Event Yield Modifier × Workforce Factor
```

- **Base Production** is fixed per role (e.g. the Farmer produces 4 Food + 3 Fish per season).
- **Event Yield Modifier** is determined by your island's Event Chart roll this season (0.0 = nothing, 1.0 = normal, 1.8 = bumper crop).
- **Workforce Factor** = Fill Rate × Average Worker Efficiency (see Workforce below).

Before producing, you must have your **production inputs** in inventory. These are consumed when you produce:

| Role | Inputs consumed each season |
|---|---|
| Farmer | 1 Capital Equipment |
| Miner | 1 Oil + 1 Freight |
| Transporter | 2 Oil |
| Educator | 1 Capital Equipment |
| Banker | None |
| Manufacturer | 2 Ore + 1 Oil + 1 Freight |
| Doctor | 1 Knowledge + 1 Capital Equipment |

If you do not have the required inputs, you cannot produce this season. You can buy inputs from the market or negotiate with other players before attempting to produce.

---

## The Market

### Dynamic Prices
The market price of each resource changes based on supply and demand:

- When **supply is high** relative to demand → price falls (floor: 20% of base price).
- When **supply is scarce** relative to demand → price rises (ceiling: 500% of base price).
- **Disaster events** can cause sudden price spikes for affected resources.

Base prices (in Dollops per unit):

| Resource | Base Price |
|---|---|
| Food | 10 Dp |
| Fish | 8 Dp |
| Ore | 15 Dp |
| Oil | 20 Dp |
| Freight | 12 Dp |
| Knowledge | 18 Dp |
| Capital Equipment | 28 Dp |
| Goods | 30 Dp |
| Health Services | 35 Dp |
| Vaccine | 40 Dp |
| Finance | 20 Dp |

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
Workers are not generic — each belongs to a **profession** that reflects their specialisation. A worker's tier is shown as their profession name plus training level, for example *Doctor (Basic)* or *Nurse (Skilled)*. Unskilled workers have no profession until they graduate from university.

| Profession | Island | Notes |
|---|---|---|
| Farmer | Agriculture Island | Crop and fishery specialists |
| Miner | Mining & Oil Island | Ore extraction |
| Oil Extraction Worker | Mining & Oil Island | Crude oil drilling |
| Refinery Specialist | Mining & Oil Island | Refinery operations |
| Engineer | Transportation Island | Fleet and infrastructure maintenance |
| Assembly Worker | Manufacturing Island | Factory floor production |
| Banker | Banking Island | Financial operations |
| Professor | Education Island | University teaching (max 1 graduate/season) |
| Doctor | Healthcare Island | Medical diagnosis and treatment |
| Nurse | Healthcare Island | Patient care and vaccine administration |
| Veterinarian | Agriculture Island | Livestock health |

### Population Growth
At the end of each year, each island's population grows by up to **2% per year**. The actual growth rate is **inversely proportional to the island's wealth** — richer islands grow slower (reflecting the demographic transition observed in real economies). New workers arrive untrained.

---

## Training

Training workers requires negotiation between **three parties**: the island sending workers, the **Educator**, and the **Transporter**. It is a multi-turn process:

### Capacity Limits
The University has **per-profession annual quotas**. Each profession has a fixed number of graduate places per year. Some professions also have a stricter per-season cap.

| Profession | Annual cap | Seasonal cap |
|---|---|---|
| Doctor | 2 | — |
| Nurse | 10 | — |
| Engineer | 2 | — |
| Farmer | 2 | — |
| Veterinarian | 1 | — |
| Assembly Worker | 10 | — |
| Miner | 2 | — |
| Oil Extraction Worker | 2 | — |
| Refinery Specialist | 2 | — |
| Banker | 2 | — |
| Professor | 4 | **1 per season** |

Once a profession's annual quota is full, no further requests for that profession can be submitted until the following year.

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

**Turn actions:** Produce · Market Buy · Market Sell · Propose Deal · Request Training · Review Training · Arrange Transport · Recruit Workers · Inventory · View Market · View Players · End Turn

**Wealth formula:** Dollops + Σ(resource units × current price) + depreciated equipment book value + loans receivable − loans outstanding

**Production formula:** Base × Event Modifier × max(Base Capacity, Fill Rate × Avg Efficiency)

**Resources:** Food · Fish · Ore · Oil · Freight · Knowledge · Capital Equipment · Goods · Health Services · Vaccine · Finance

**Capital Equipment** — produced by Manufacturer (2/season alongside 3 Goods); needed by Farmer, Educator, Doctor as production input

**Finance** — produced by Banker (3/season, no inputs); tradeable financial instrument

**Training transport:**
- ✈️ Flight: 20% of educator fee, immediate departure
- 🚢 Cargo vessel: free for ≤ 2 passengers, +1 season delay
- 🚤 Transporter: negotiated fee, immediate departure

**University quotas:** per profession (Doctor 2/yr, Nurse 10/yr, Professor 4/yr max 1/season … see table)

**Recruit Workers:** 1 unskilled recruit per 2 unskilled residents (population − employed workforce)

**Birth rate:** 2% per year × (1 − wealth ratio) — richer islands grow slower

**Market floor/ceiling:** 20% – 500% of base price

**Vaccines:** Healthcare produces 1/season; each unit improves worker wellness for 4 seasons
