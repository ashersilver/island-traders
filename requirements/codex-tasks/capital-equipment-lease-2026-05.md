# Codex Task — Capital Equipment Lease Subsystem (2026-05-25)

**Owner:** Codex
**Origin:** Bug 1 / training-staffing follow-up (2026-05-25). Players who can't commit a full equipment cost from starting capital should have a lease option from the Bank. Today they can fake it with the existing 1/2/3-year loans (`banker_quote_rate`), but that's not a real lease — it doesn't model repossession, term-structured ownership transfer, or per-year-in-advance payment discipline.

## Goal

Add a generalized **capital-equipment lease** subsystem that models:

- **Bank as lessor**: lease payments flow to the Banker player (institutional pool when that's wired up; for now, the Banker's personal cash).
- **3-year term** by default, with annual payments **in advance** (first payment at lease inception during the Investing Phase; subsequent payments at the start of each year).
- **Lease rate** = posted funding rate + 2% margin (`banker_quote_rate` semantics).
- **Repossession** when a payment is missed. The leased item is removed from the lessee's `capital_inventory` immediately; the Banker holds it.
- **Catch-up return** — if the lessee pays the missed payment in a later season, the item returns to their `capital_inventory` **next season** (one-season delay represents repossession-and-redeployment logistics).
- **Investing-phase choice** between *buy outright* (existing flow) and *lease 3-year* for any lease-eligible capital item.

Applies to any `CapitalItem` flagged as lease-eligible. Start with `educator.technical_workshop` (which the training-staffing follow-up made mandatory-minimum); generalize so future high-cost items (Banker computing centre, Doctor pathology lab, Manufacturer line items) can opt in.

## Branching

- **Base:** `pre-release` at `8e669ed` ("Merge codex/training-staffing-2026-05 + bootstrap follow-up (PR #33)") or later.
- **Branch name:** `codex/capital-equipment-lease-2026-05`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## What has shipped since you last touched capital (mini-changelog)

- **Phase C capital lifecycle** — universal capital lifespan + maintenance was already in place.
- **AI Trading v2** + **balance calibration** (`4e56ead`, `0aae64f`).
- **Sustenance basket model** (`e2d044f`).
- **Auction reconnect/pause-at-expiry fix** (`6faf551`).
- **Training-staffing redesign + bootstrap** (`8e669ed`, this branch's predecessor). Key consequence: `educator.technical_workshop` is now in `MANDATORY_MINIMUM_INVESTMENT["Educator"]`. The lease subsystem in this brief is the right home for the "lease vs buy" choice the user wanted at investing-phase.
- **Baseline test count: 403 passing** on `8e669ed`.

## Spec

### CapitalItem opt-in

Add `lease_terms: dict | None = None` to `CapitalItem` (in `island_traders/models/capacity.py`). When set, the item is lease-eligible. Shape:

```python
lease_terms = {
    "term_years":    3,      # default; spec keeps the door open for 1/2 if useful
    "annual_payment": 25.0,  # Dp per year (in advance); design starting point
    "min_credit_band": "any",  # forward-compat hook; ignore for now
}
```

For `educator.technical_workshop` (cost `60.0`, lease 3 years), suggested annual payment is `cost / term_years × (1 + 0.06)` ≈ `21.2 Dp/year` — i.e. roughly the principal amortization plus a 6% lease-margin built in. Use the existing `banker_quote_rate` style (posted funding rate + 2% margin) computed at lease inception so the rate scales with the prevailing rate environment:

```python
funding_rate = posted_funding_rates(year, season)[term_years]
lease_rate   = funding_rate + 0.02   # +2% lease margin
annual_payment = round(cost / term_years * (1 + lease_rate), 1)
```

Treat the rate as **locked at lease inception** (same convention as the loan rollover work).

### New `Lease` model + `LeaseLedger`

Add `island_traders/models/lease.py`:

```python
class LeaseStatus(Enum):
    ACTIVE       = "active"        # ongoing, current on payments
    REPOSSESSED  = "repossessed"   # missed payment; item held by Bank
    COMPLETED    = "completed"     # all term_years payments made; ownership transfers
    CANCELLED    = "cancelled"     # lessee surrendered before term; no further obligation

@dataclass
class Lease:
    lease_id:          int
    item_id:           str
    lessee_id:         int        # Player.player_id
    lessor_id:         int        # the Banker player_id (or -1 placeholder for "the Bank")
    started_year:      int
    term_years:        int
    annual_payment:    float
    payments_made:     int        # 0..term_years; lease completes when == term_years
    last_payment_year: int        # year of the last successful payment
    status:            LeaseStatus
    repossessed_year:  int  = -1  # year repo was triggered (for return-after-payment timing)
    repossessed_season: int = -1
```

`LeaseLedger`:

```python
class LeaseLedger:
    def create_lease(item_id, lessee_id, lessor_id, year, term_years, annual_payment) -> Lease
    def active_leases_for(player_id) -> list[Lease]
    def repossessed_leases_for(player_id) -> list[Lease]
    def due_leases(year, season) -> list[Lease]   # active + payment due this season
    def all_leases() -> list[Lease]
    def make_payment(lease_id, year, season) -> Lease       # advances payments_made + last_payment_year
    def repossess(lease_id, year, season) -> Lease          # status -> REPOSSESSED
    def reinstate(lease_id, year, season) -> Lease          # status -> ACTIVE (after catch-up)
    def complete(lease_id) -> Lease                         # status -> COMPLETED on final payment
```

### Engine integration

**Season-start hook** (extend `Game.run` or add `_process_lease_payments(year, season)`):

1. **Repossession returns**: any lease in `REPOSSESSED` whose `repossessed_year/season` is at least 1 season in the past AND the lessee has paid the back-payment this season — flip to `ACTIVE`, return the item to `capital_inventory`. (One-season delay represents the Bank's redeploy logistics.)
2. **Annual-payment processing** (only at the start of each year, i.e. season 0):
   - For each `ACTIVE` lease where `last_payment_year < current_year` and `payments_made < term_years`:
     - If the lessee is AI: auto-pay if dollops sufficient; auto-default if not.
     - If the lessee is human: prompt with `confirm("Lease payment due for X. Pay Y Dp now?")`. (Use a new `TurnAction.PAY_LEASE` if you want a discoverable action, or surface as a forced prompt before the action menu — coordinate via PR.)
     - On payment: debit lessee `annual_payment`, credit lessor, advance `payments_made`. If `payments_made == term_years`, set status `COMPLETED` and **transfer ownership** (item remains in `capital_inventory`, lease ends).
     - On non-payment: `repossess` — remove the item from `capital_inventory`, mark lease `REPOSSESSED`, record `repossessed_year/season`.

**Investing Phase**: add a per-eligible-item choice for the human player. Default: buy outright (existing flow). New choice: lease (deduct first year's `annual_payment` instead of full `cost`, create the lease in the ledger). AI default: buy if `dollops >= cost`, else lease if `dollops >= annual_payment`, else skip.

### Server payload + UI (Claude's domain — flag this, do not code)

The investing-phase server payload needs to expose `lease_terms` for each item so the client can offer the choice. The dashboard needs a Leases panel parallel to the Loans panel. Both are **out of scope for this brief** — flag in your RELEASE_NOTES that the UI work follows on a Claude branch.

For this Codex brief: just ensure the server `get_game_state` payload includes a `leases_detail` field per player (analogous to `loans_detail`) so the Claude UI work has data to render. Shape:

```json
"leases_detail": [
    {
        "lease_id": 1,
        "item_id": "educator.technical_workshop",
        "item_name": "Technical Workshop",
        "role": "lessee" | "lessor",
        "counterparty_id": <int>,
        "annual_payment": 21.2,
        "payments_made": 1,
        "term_years": 3,
        "seasons_to_next_payment": <int>,
        "status": "active" | "repossessed" | "completed",
        "next_payment_year": <int>,
        "next_payment_season": "Spring"
    }
]
```

### CLI helpers (out of scope)

The CLI prompt path can leave lease decisions to the existing prompt mechanisms. No new IO methods.

### Action enum

Add `TurnAction.PAY_LEASE = "pay_lease"`. Wire dispatch in `_human_turn` to a new `_action_pay_lease(player, result, year, season_index)` that lists this player's `due_leases` and prompts payment.

(Alternative: skip the action; just force-prompt at season start. Codex's call — but coordinate via PR comment.)

## Files in scope

- `island_traders/models/lease.py` (new) — Lease + LeaseLedger.
- `island_traders/models/capacity.py` — `CapitalItem` gets `lease_terms` field.
- `island_traders/constants_capacity.py` — populate `lease_terms` on `educator.technical_workshop` (and call out the pattern for future items).
- `island_traders/engine/game.py` — wire the per-season lease-payment hook; ensure `LeaseLedger` exists on `Game`.
- `island_traders/engine/turn.py` — `TurnAction.PAY_LEASE`, `_action_pay_lease`, dispatch wiring.
- `island_traders/server/app.py` — `leases_detail` in `get_game_state`; investing-phase payload includes `lease_terms`.
- `island_traders/engine/ai.py` — default AI behavior (buy-then-lease-then-skip; auto-pay on lease payment).
- `RELEASE_NOTES.md` — `### codex/capital-equipment-lease-2026-05` section.
- `tests/test_engine/test_lease.py` (new) — comprehensive coverage.

## Out of scope

- `island_traders/server/static/` — Claude UI domain. Server payload only.
- Lease termination penalties / early-payoff discounts / refinance — keep this v1 simple.
- Lease assignment / transfer between players — v2 if ever.
- Save migration for in-flight leases (no save file has them yet; just initialize empty `LeaseLedger` on load).

## Tests required

In `tests/test_engine/test_lease.py`:

1. `test_lease_creation_at_investing_phase` — creating a lease deducts year-1 payment, adds item to `capital_inventory`, records ledger entry.
2. `test_annual_payment_in_advance_at_year_start` — payment due at season 0 of year N for a lease started year N-1; `last_payment_year` advances on success.
3. `test_missed_payment_triggers_repossession` — payment skipped or insufficient cash → item removed from `capital_inventory`, lease flips to REPOSSESSED.
4. `test_repossession_return_one_season_after_catchup_payment` — pay back-payment in S1; item returns to `capital_inventory` at S2.
5. `test_final_year_payment_completes_lease_with_ownership_transfer` — after `term_years` payments, lease → COMPLETED; item stays in `capital_inventory` outright.
6. `test_lease_rate_uses_posted_funding_plus_2pct_margin` — `annual_payment` math matches `cost / term_years × (1 + funding_rate + 0.02)`.
7. `test_due_leases_filters_by_year_and_season` — `due_leases(Y, S=0)` returns the right set across multiple leases at different stages.
8. `test_ai_lessor_auto_pays_when_solvent` — AI lessee pays automatically when `dollops >= annual_payment`.
9. `test_ai_lessor_defaults_when_insolvent` — AI lessee with `dollops < annual_payment` triggers repossession.
10. `test_leases_detail_payload_shape` — `get_game_state(...)["players"][i]["leases_detail"]` contains the documented shape.
11. `test_investing_phase_lease_choice_creates_lease_not_purchase` — when a player chooses lease at investing time, `capital_inventory` adds the item and ledger has the lease (no full-cost deduction).

Full suite must remain green. Target: `403 + 11 = 414 passing` (or more if you add extra coverage).

## When to stop and hand off

Push the branch when:

- Lease model + ledger + engine integration implemented per spec.
- Per-season hook wired into `Game.run`.
- AI default behavior in place.
- Server `leases_detail` payload + `lease_terms` in investing payload.
- 11+ tests, full suite green.
- `RELEASE_NOTES.md` has a `### codex/capital-equipment-lease-2026-05` section flagging the Claude UI follow-up.
- Signed-off commits.

**Do not:**

- Touch `server/static/` (Claude UI work follows).
- Promote `pre-release` or tag.
- Modify any other lease-eligible items beyond `educator.technical_workshop` — keep this v1 narrow to one item; the pattern generalizes mechanically.

## What to push

```bash
git push -u origin codex/capital-equipment-lease-2026-05
```

Open a PR with summary, new test count, and a note that the UI work is a separate Claude follow-up.

## When to wait for merge

After pushing:

1. **Wait** for Claude to review (lease accounting interacts with Banker dollops, Phase D1 reserve model, and per-season hook ordering — wants a careful pass).
2. **Wait** for Claude to merge.
3. Claude may follow up with a UI branch surfacing `leases_detail` in a dashboard panel.

## Reference

- **Existing loan model** (template for the lease ledger): `island_traders/models/loan.py` — `LoanLedger`, `Loan`, `posted_funding_rates`, `banker_quote_rate`. Mirror the patterns.
- **Loan repayment hook** (template for the per-season lease hook): `TurnManager._process_loan_repayments` in `engine/turn.py`.
- **Existing TurnAction enum + dispatch:** `engine/turn.py::TurnAction` + `_human_turn` dispatch table.
- **Investing-phase server flow:** `island_traders/server/app.py::_investing_payload`, `submit_investment`, `_apply_investment_selection` (or similar — grep for `MANDATORY_MINIMUM_INVESTMENT` to find the surface).
- **Test pattern:** `tests/test_engine/test_loans.py` — analogous structure for lease tests.
- **Capital item structure:** `island_traders/models/capacity.py::CapitalItem`.
- **Mandatory-minimum list** (where the workshop now lives): `island_traders/constants_capacity.py::MANDATORY_MINIMUM_INVESTMENT`.
- **Bootstrap follow-up commit referencing this brief:** `06de1ac` on `pre-release`.
