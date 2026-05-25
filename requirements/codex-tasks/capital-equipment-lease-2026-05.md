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

## Spec — revised 2026-05-25 with three locked-in decisions

| Decision | Answer |
|---|---|
| When can a lease be initiated? | **Both investing phase AND mid-game seasons.** Mid-game uses the same flow as `PURCHASE_CAPITAL` (a new sibling action — see "Action wiring" below). |
| End-of-term buyout payment | **25% of the original `cost`**, paid as a balloon at the end of `term_years`. If the lessee doesn't pay the buyout, the Bank reclaims the item. |
| Lease rate | **Posted 3-year funding rate + 2% margin**, locked at lease inception. Applies in both investing-phase and mid-game inceptions. Treated as a secured loan against the asset. |

### CapitalItem opt-in

Add `lease_terms: dict | None = None` to `CapitalItem` (in `island_traders/models/capacity.py`). When set, the item is lease-eligible. Shape (residual fraction lives on the item so future items can override):

```python
lease_terms = {
    "term_years":         3,
    "residual_fraction":  0.25,   # buyout = cost * residual_fraction
    "rate_margin":        0.02,   # added to posted N-year funding rate
}
```

For `educator.technical_workshop` (cost `60.0`), the math at inception:

```python
funding_rate   = posted_funding_rates(year, season)[term_years]   # posted 3-yr rate
lease_rate     = funding_rate + lease_terms["rate_margin"]         # +2 % margin
buyout         = round(cost * lease_terms["residual_fraction"], 1) # 60 * 0.25 = 15.0 Dp
# Annual payment amortizes the depreciable portion (cost minus residual) over
# the term, plus interest on the depreciable portion at the locked lease rate.
annual_payment = round(
    (cost - buyout) / term_years * (1 + lease_rate), 1
)   # 60-15 = 45; 45/3 = 15; ×(1+~0.06) ≈ 15.9 Dp/year
```

So for the Workshop with a ~4 % posted 3-yr rate (current default) → `annual_payment ≈ 15.9 Dp`, `buyout = 15.0 Dp`. Three annual payments + buyout = **~62.7 Dp**, a ~4.5 % premium over outright purchase (60 Dp) — fair for a financed asset with the walk-away option.

**Treat the rate as locked at inception.** A lease created in Y0/S0 keeps its inception rate through all subsequent payments, regardless of how the posted rate moves over the lease term. Matches the existing loan-rollover convention.

**Mid-game and investing-phase leases use the same math.** The only difference is *when* `year, season` are sampled for the posted-rate lookup — at investing-phase that's the game-start tick (Y0/S0); mid-game it's the current tick. Identical formula, identical locking behaviour.

### New `Lease` model + `LeaseLedger`

Add `island_traders/models/lease.py`:

```python
class LeaseStatus(Enum):
    ACTIVE              = "active"               # ongoing, current on payments
    AWAITING_BUYOUT     = "awaiting_buyout"      # all annual payments made; buyout due
    REPOSSESSED         = "repossessed"          # missed annual payment; item held by Bank
    BUYOUT_DEFAULTED    = "buyout_defaulted"     # term ended without buyout; Bank reclaims
    COMPLETED           = "completed"            # buyout paid; ownership transferred
    CANCELLED           = "cancelled"            # lessee surrendered early; no further obligation

@dataclass
class Lease:
    lease_id:           int
    item_id:            str
    lessee_id:          int        # Player.player_id
    lessor_id:          int        # Banker.player_id (or -1 sentinel for "the Bank")
    started_year:       int
    started_season:     int
    term_years:         int
    annual_payment:     float
    buyout_payment:     float        # computed at inception, locked
    locked_lease_rate:  float        # posted N-yr rate + margin, at inception
    payments_made:      int          # 0..term_years; AWAITING_BUYOUT when == term_years
    last_payment_year:  int          # year of the last successful annual payment
    status:             LeaseStatus
    # Repossession is two-flavoured: an annual-payment default during the
    # term (REPOSSESSED, item-returns-on-catchup), and a buyout default at
    # term end (BUYOUT_DEFAULTED, item gone — no catchup path).
    repossessed_year:   int  = -1
    repossessed_season: int  = -1
```

The two repossession states matter because their **recovery paths differ**:

- `REPOSSESSED` (mid-term default) → lessee can pay the back-payment(s) in a later season, item returns next season (per user spec: "returns the season after the outstanding payments get settled").
- `BUYOUT_DEFAULTED` (end-of-term walk-away) → terminal; the lease completes with the Bank owning the asset, lessee has no recourse. They had three annual payments of use.

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

1. **Repossession returns**: any lease in `REPOSSESSED` whose `repossessed_year/season` is at least 1 season in the past AND the lessee has paid the back-payment(s) this season — flip to `ACTIVE`, return the item to `capital_inventory`. (One-season delay represents the Bank's redeploy logistics.)
2. **Annual-payment processing** (at the start of each year, i.e. season 0):
   - For each `ACTIVE` lease where `last_payment_year < current_year` and `payments_made < term_years`:
     - If the lessee is AI: auto-pay if `dollops >= annual_payment`; auto-default to `REPOSSESSED` otherwise.
     - If the lessee is human: prompt — `confirm("Lease payment due for X. Pay Y Dp now?")`. Coordinate the prompt mechanism via PR (a forced pre-action-menu prompt is fine; a `TurnAction.PAY_LEASE` is also fine — pick one and document).
     - On payment: debit lessee `annual_payment`, credit lessor, advance `payments_made` and `last_payment_year`. **If `payments_made == term_years`, status flips to `AWAITING_BUYOUT`** — the lease isn't done, the buyout is now due.
     - On non-payment: `repossess` — remove the item from `capital_inventory`, mark `REPOSSESSED`, record `repossessed_year/season`.
3. **Buyout processing** (same season-0 hook, after annual-payment processing):
   - For each `AWAITING_BUYOUT` lease (the lease's natural maturity year is `started_year + term_years`):
     - AI lessee: auto-pay if `dollops >= buyout_payment`; otherwise lease flips to `BUYOUT_DEFAULTED` (terminal; item leaves `capital_inventory`, Bank reclaims, no catchup path).
     - Human lessee: prompt — `confirm("Lease buyout due for X. Pay Y Dp now to take ownership, otherwise the Bank reclaims it. Pay?")`.
     - On payment: debit lessee `buyout_payment`, credit lessor, status → `COMPLETED`, ownership transfers (item stays in `capital_inventory`, lease ends, no further obligation).
     - On non-payment: status → `BUYOUT_DEFAULTED`, item removed from `capital_inventory`.

**Investing Phase**: add a per-eligible-item buy-vs-lease choice. Default: buy outright (existing flow). New choice: lease — deduct **year-1 annual payment** at lease inception, add item to `capital_inventory`, create the lease in the ledger with `status=ACTIVE`, `payments_made=1`, `last_payment_year=0`. AI default at investing-phase: buy if `dollops >= cost + sum(other mandatory items)`, else lease if `dollops >= annual_payment + others`, else skip the item (won't trigger for mandatory items per the existing investing logic).

**Mid-game lease initiation** (new — per user spec, "should be available for the seasons too"): add a sibling action `TurnAction.LEASE_CAPITAL` analogous to the existing `PURCHASE_CAPITAL`. Same per-role-catalogue picker, but the option only appears for items whose `lease_terms` is set. On confirmation: deduct year-1 annual payment now, schedule the item via `capital_in_transit` if `delivery_seasons > 0` (workshop is `delivery_seasons=0` so it arrives immediately), create the lease with `started_year/season = current tick`. Use the **posted 3-year rate at the action's tick** for the locked lease rate.

Alternatively: extend `PURCHASE_CAPITAL` with an inline confirm("Pay X Dp outright, or lease at Y Dp/year for 3 years with 15 Dp buyout?"). Codex's call which approach — coordinate via PR. The action-split approach is cleaner for the existing UI dispatch but adds a new entry to `TurnAction`.

### Server payload + UI (Claude's domain — flag this, do not code)

The investing-phase server payload needs to expose `lease_terms` for each item so the client can offer the choice. The dashboard needs a Leases panel parallel to the Loans panel. Both are **out of scope for this brief** — flag in your RELEASE_NOTES that the UI work follows on a Claude branch.

For this Codex brief: just ensure the server `get_game_state` payload includes a `leases_detail` field per player (analogous to `loans_detail`) so the Claude UI work has data to render. **User requested leases be listed under the Loans panel** — a single `leases_detail` array keeps that simple (Claude UI follow-up just adds a section to the existing Loans popup). Shape:

```json
"leases_detail": [
    {
        "lease_id": 1,
        "item_id": "educator.technical_workshop",
        "item_name": "Technical Workshop",
        "role": "lessee" | "lessor",
        "counterparty_id": <int>,
        "annual_payment": 15.9,
        "buyout_payment": 15.0,
        "payments_made": 1,
        "term_years": 3,
        "seasons_to_next_payment": <int>,
        "status": "active" | "awaiting_buyout" | "repossessed" | "buyout_defaulted" | "completed",
        "next_payment_year": <int>,
        "next_payment_season": "Spring",
        "next_payment_type": "annual" | "buyout"
    }
]
```

### CLI helpers (out of scope)

The CLI prompt path can leave lease decisions to the existing prompt mechanisms. No new IO methods.

### Action enum

Two related additions:

- **`TurnAction.LEASE_CAPITAL`** — mid-game lease initiation, sibling of `PURCHASE_CAPITAL`. Lists the player's role catalogue, filtered to items with `lease_terms`. On confirmation, creates the lease at the current tick using the math above.
- **`TurnAction.PAY_LEASE`** *(optional discoverable action)* — lists this player's due annual / buyout payments and prompts payment. Alternative: a forced pre-action-menu prompt at the start of each season-0 turn when a payment is due. Codex's call — coordinate via PR.

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

1. `test_lease_creation_at_investing_phase` — creating a lease deducts year-1 annual payment, adds item to `capital_inventory`, records ledger entry with `payments_made=1`, `status=ACTIVE`.
2. `test_lease_creation_mid_game_via_lease_capital_action` — `TurnAction.LEASE_CAPITAL` (or extended `PURCHASE_CAPITAL`) creates a lease at the current tick; `started_year/season` reflect that tick; `locked_lease_rate` uses the posted 3-year rate at the action's tick.
3. `test_annual_payment_in_advance_at_year_start` — payment due at season 0 of year N for a lease started year N-1; `last_payment_year` advances on success.
4. `test_missed_annual_payment_triggers_repossession` — payment skipped or insufficient cash → item removed from `capital_inventory`, lease flips to REPOSSESSED with `repossessed_year/season` set.
5. `test_repossession_return_one_season_after_catchup_payment` — pay back-payment in S1; item returns to `capital_inventory` at S2.
6. `test_final_annual_payment_flips_to_awaiting_buyout_not_completed` — after `term_years` annual payments, lease → `AWAITING_BUYOUT` (NOT `COMPLETED`); item still in `capital_inventory` but lease is not yet done.
7. `test_buyout_payment_completes_lease_with_ownership_transfer` — paying `buyout_payment` (= `cost * 0.25` = 15 Dp for the Workshop) flips status to `COMPLETED`; item stays in `capital_inventory` permanently.
8. `test_buyout_default_terminally_removes_item` — failing to pay the buyout flips status to `BUYOUT_DEFAULTED`; item leaves `capital_inventory`; no catchup path exists from this state.
9. `test_lease_rate_locked_at_inception_independent_of_later_posted_rates` — change `posted_funding_rates` between Year 0 and Year 1; verify that a lease created in Y0 uses the Y0-locked rate for its Y1 payment math (no re-quoting).
10. `test_lease_rate_uses_posted_3yr_funding_plus_2pct_margin` — `locked_lease_rate == posted_funding_rates(year, season)[3] + 0.02`. `annual_payment == round((cost - buyout) / 3 * (1 + lease_rate), 1)`. `buyout == round(cost * 0.25, 1)`.
11. `test_due_leases_filters_by_year_and_season` — `due_leases(Y, S=0)` returns ACTIVE leases past `last_payment_year` AND `AWAITING_BUYOUT` leases at maturity.
12. `test_ai_lessee_auto_pays_when_solvent` — AI lessee pays both annual and buyout automatically when `dollops` cover the payment.
13. `test_ai_lessee_defaults_when_insolvent` — AI lessee with insufficient cash triggers `REPOSSESSED` for annual, `BUYOUT_DEFAULTED` for the buyout.
14. `test_leases_detail_payload_shape` — `get_game_state(...)["players"][i]["leases_detail"]` matches the documented shape including `buyout_payment` and `next_payment_type`.
15. `test_investing_phase_lease_choice_creates_lease_not_purchase` — when a player chooses lease at investing time, `capital_inventory` adds the item AND the ledger has the lease (only year-1 annual payment deducted, not full `cost`).
16. `test_legacy_loan_path_unaffected_by_lease_subsystem` — Bank loans still work exactly as before; no regression to `posted_funding_rates`, `banker_quote_rate`, or loan repayment math.

Full suite must remain green. Target: `404 + ~16 = ~420 passing` (or more if you add extra coverage).

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
