# Island Ledger & Ownership Model

Status: **draft requirements**
Source: synthesised from design conversation (2026-05-07 inbox items)

---

## Problem statement

The current model stores all resources, cash, and role names directly on a `Player`
object. This is a simple approximation that works for single-role players but breaks
down as soon as:

- A player wins multiple roles at auction (pooling cash and inventory across unrelated
  businesses is economically wrong and strategically confusing).
- The Banker needs an institutional cash pool that is separate from the player-owner's
  personal wealth.
- A role changes hands mid-game (role resale, late entry) — there is nowhere to
  preserve the island's inventory, equipment, loans, and workforce independently of the
  departing owner.
- Financial reporting needs to distinguish "what does this island earn / owe" from
  "what is the player-owner worth overall".

The fix is to introduce an **Island Ledger** — a first-class entity that holds an
island's operating state — and to model player wealth as *ownership stakes* in one or
more island ledgers plus a personal cash reserve.

---

## 1. Entities

### 1.1 Island Ledger (`IslandLedger`)

Each role / island has exactly one ledger. It holds:

| Field | Type | Description |
|---|---|---|
| `role_name` | str | Canonical role identifier ("Miner", "Banker", …) |
| `working_capital` | float (Dp) | Operating cash — used to pay inputs, wages, loan service |
| `inventory` | dict[ResourceType, int] | Physical stock on the island |
| `capital_equipment` | list[CapitalItem] | Equipment owned, with condition and age |
| `capital_leases` | list[CapitalLease] | Leased equipment obligations, terms, and buyout values |
| `workforce` | WorkforceRoster | Current workers, tiers, training pipeline |
| `loans` | list[Loan] | Outstanding borrowings (principal, rate, maturity) |
| `insurance_policies` | list[Policy] | Active coverage |
| `patents` | list[Patent] | Active patent boosts (Educator output) |
| `owner_player_id` | str \| None | Lobby player_id of controlling player; None = AI-controlled |

Starting working capital per island: **300 Dp** (added to the island ledger at game
start, before auction deductions). This is separate from the player's personal cash.

### 1.2 Player Account (`PlayerAccount`)

A player's financial position is:

```
personal_cash        — Dp balance immediately available to the owner
bank_deposits        — owner's cash deposited with the Bank at 5% p.a.
owned_island_stakes  — list of (IslandLedger, ownership_fraction)
net_wealth           = personal_cash
                     + bank_deposits
                     + sum(ledger.working_capital × fraction
                           + market_value(ledger.inventory)
                           + book_value(ledger.capital_equipment)
                           - lease_liability(ledger.capital_leases)
                           - sum(loan.outstanding for loan in ledger.loans)
                       for ledger, fraction in owned_island_stakes)
```

For the standard game all ownership fractions are 1.0 (sole owner), so the formula
simplifies. Fractional ownership is reserved for future partnership / roleless-player
mechanics.

---

## 2. Cash flows

All cash movements must go through an explicit transfer between named accounts.
Silent pooling is forbidden.

| Event | From | To |
|---|---|---|
| Player buys production input | Island working capital | Market / Seller island ledger |
| Player sells output | Buyer island ledger | Island working capital |
| Player takes a loan | Bank institutional pool | Island working capital |
| Loan repayment | Island working capital | Bank institutional pool |
| Owner surplus deposit | Player personal cash | Bank deposit account |
| Deposit interest | Bank institutional pool | Player deposit account |
| Deposit withdrawal | Bank deposit account | Player personal cash |
| Dividend / withdrawal | Island working capital | Player personal cash |
| Capital injection | Player personal cash | Island working capital |
| Auction bid payment | Player personal cash | House (removed from game) |
| Starting capital grant | House (injected) | Player personal cash (700 Dp) |
| Island starting capital grant | House (injected) | Island working capital (300 Dp) |

---

## 3. Banker institutional cash pool

The Banker island ledger starts with a larger working capital to enable meaningful
early-game lending. Proposed starting pool: **2,000 Dp** (enough for 3–4 substantial
loans in a 7-player game).

Loans drawn from the Bank reduce `Bank.working_capital`. Repayments (principal +
interest) increase it. If `Bank.working_capital` falls below a minimum reserve
threshold the Banker cannot issue new loans until repayments restore headroom.

After initial bidding, any owner cash not spent on winning bids is automatically
placed on deposit with the Bank in an owner deposit account at **5% per annum**.
The Bank may use deposited owner capital as lendable funding and may lend it to
island borrowers at an agreed rate. Loans are always owed by an **island ledger**,
not by the owner personally; the borrowing island's working capital receives the
loan proceeds and services the debt.

The player who owns the Banker role keeps their personal cash entirely separate from
the Bank's pool. Profits accrue to the island ledger as retained earnings; the player
may declare a dividend to move earnings to personal cash (subject to whatever
game rules govern dividends — TBD).

---

## 3.1 Capital equipment ownership and leasing

Capital equipment is a category of physical production assets, not a single
tradeable resource. Examples include tractors, fishing boats, foundries,
research labs, hospital wards, and similar catalogue items.

An island can acquire capital equipment in two ways:

1. **Outright purchase** — the island pays the full catalogue cost from working
   capital and owns the item immediately, subject to any delivery delay.
2. **Lease** — the island leases the item over **3 years**. Lease payments are
   obligations of the island ledger. At the end of the lease, the equipment is
   returned or bought out for its book value.

Book value is calculated with straight-line depreciation over **5 years** from
the original catalogue cost. For example, an item leased for 3 years has a
remaining book value of 40% of original cost at the end of the lease, unless
the implementation later adds item-specific residual rules.

---

## 4. Ownership transfer (role resale)

When a player sells a role to another player:

1. **Agree price** — seller names an asking price; buyer confirms. Both players must
   be online and confirm within the season window.
2. **Transfer** — `IslandLedger.owner_player_id` is updated; the buyer's personal
   cash decreases by the agreed price; the seller's personal cash increases.
3. **Island state is preserved** — inventory, equipment, workforce, loans, patents,
   and active insurance policies transfer intact with the island. The new owner
   inherits all obligations.
4. **Loans follow the island** — the new owner becomes responsible for all
   outstanding loan service on the island ledger. This should be prominently
   disclosed in the sale confirmation screen.
5. **Post-transfer** — the sold island tab appears on the buyer's dashboard; it
   disappears from the seller's. An event log entry is broadcast to all players.

A player who sells their only role becomes **roleless**. Roleless players retain
their personal cash and can participate in the role aftermarket, deposit cash with
the Banker (on-call deposits), or observe until they acquire a new role.

---

## 5. UI implications

- **Tab per island**: the existing per-role tab model maps directly to per-island-ledger tabs. The tab shows the ledger's working capital, not the player's total personal cash.
- **Player wealth display**: the header should show *net wealth* (personal cash + island equity − island debt). A tooltip or expanded panel breaks it down by ledger.
- **Multi-island Consolidated tab**: aggregates across all owned ledgers for players controlling multiple islands. Cash and inventory are shown separately per island; the consolidated tab shows totals only.
- **Capital injection / withdrawal flow**: a simple form: "Move X Dp from personal cash to [island] working capital" or vice versa, subject to available balances.

---

## 6. Migration from current model

Current `Player` fields and their destination after this change:

| Current field | Destination |
|---|---|
| `Player.dollops` | Split: part → `PlayerAccount.personal_cash`; island working capital separate |
| `Player.inventory` | → `IslandLedger.inventory` (one ledger per role) |
| `Player.roles` | → `PlayerAccount.owned_island_stakes` |
| `Player.workforce` | → `IslandLedger.workforce` |
| `Player.loans` | → `IslandLedger.loans` |
| `Player.insurance_policies` | → `IslandLedger.insurance_policies` |

The migration should be implemented in two phases to avoid a big-bang rewrite:

**Phase 1** — introduce `IslandLedger` as a parallel data structure alongside the
existing `Player`, and route production/trading through it without removing the old
fields. Tests can run against both paths.

**Phase 2** — remove the old `Player` fields and update all engine callers once
Phase 1 tests are green.

---

## 7. Open questions

- What is the starting personal cash for a player vs the island starting capital?
  Decision: **700 Dp personal** auction budget. After bidding, unspent owner
  cash is deposited with the Bank at 5% p.a. Each island also receives **300 Dp
  island working capital**, granted directly to the island ledger and never
  touched by auction bidding.
- Should loan obligations transfer to the buyer in a role resale, or must they be
  cleared first? Decision: they transfer with the island and must be disclosed
  prominently at sale.
- Should fractional ownership be in scope for v1 (e.g. two players co-owning one
  island)? Proposed: out of scope for v1; reserved for future partnership rules.
- Can a player inject unlimited personal cash into an island, or is there a cap?
  Proposed: unlimited, but each injection is a visible transaction on the ledger.
