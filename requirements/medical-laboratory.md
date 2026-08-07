# Medical & Laboratory Island Refinement

Status: **draft requirements** (2026-05-15)
Source: GitHub Issues #19, #25, #26 (2026-05-15 playtest)
Touches: roles, resources, professions, capital equipment installation flow,
insurance pricing, RULES.md

---

## Summary

What is today the **Healthcare / Doctor** island becomes the
**Medical & Laboratory Island**.  Two related changes:

1. The role adds a new tradeable output — **Laboratory Tests** — used by
   other islands for compliance / quality / discovery work.
2. A new profession — **Ecologist** — appears across islands and is
   required for environmental assessments of new capital equipment.
3. Insurance pricing acquires a Doctor-certification mechanic (annual
   physicals halve premiums; insured workers don't lose productivity from
   injury) and a new profession on the Banking Island — **Actuary** — is
   required to underwrite policies.

These three interlock: Lab Tests gate environmental assessments,
environmental assessments gate capital installations, Doctors / Actuaries
gate insurance economics.

---

## 1. Role rename: Medical & Laboratory Island

The current `"Doctor"` engine role keeps its internal identifier (saved
games + JSON wire format unchanged) but its **player-facing label**
becomes:

| Field | Today | Tomorrow |
|---|---|---|
| `display_name` | "Healthcare" | "Medical & Laboratory" |
| `island` | "Healthcare Island" | "Medical & Laboratory Island" |
| `short_name` | "Healthcare" | "Medical & Laboratory" |

The internal `ROLES["Doctor"]` key and `Player.roles` references stay as
`"Doctor"` — pure cosmetic rename at the display layer (same pattern as
the `Purchase Capital → Purchase Equipment` UX win).

---

## 2. New output: Laboratory Tests

A new tradeable resource alongside Health Services and Vaccine.

| Field | Value |
|---|---|
| `ResourceType` enum | `LABORATORY_TESTS = "LaboratoryTests"` |
| Base price | 35 Dp *(matches Health Services as a service product)* |
| Producer | Medical & Laboratory Island |
| Inputs | `Knowledge` *(or Expertise post-rename)* + small `LaboratoryEquipment` |
| Output speed | **Immediate** — produced on demand each season, not stockpiled like Vaccines |

Suggested initial recipe (subject to calibration):

```python
ProductionRecipe(
    role="Doctor", output="LaboratoryTests",
    inputs={"LaboratoryEquipment": 0.2, "Knowledge": 0.5},
    manager_per_unit=0.5,    # Doctor + (future Pathologist?)
    technician_per_unit=1.0, # Medical Orderly carrying samples + tests
    worker_per_unit=0.0,
)
```

### Who consumes Lab Tests?

The new product is the central glue that makes #19, #25, and #26
interlock:

| Consumer | What they buy | Why |
|---|---|---|
| **Mining Island** | "Metal Assay" Lab Test | Required to smelt Ore + Oil → Metal.  Today smelting is automatic; the assay becomes a per-batch gate. |
| **Agricultural Island** | "Soil Analysis" Lab Test | Seasonal requirement for production.  Quality crop yields depend on it. |
| **Any island installing capital equipment** | "Environmental Assessment" Lab Test | Required during capital install (see §3 Ecologists). |
| **Banking Island** | "Health Certificate" Lab Test | Half-price insurance premium (see §5). |

> **All of these are Lab Tests — the same resource.**  The "type"
> (Metal Assay vs Soil Analysis vs Environmental vs Health) is just a
> contextual label.  The engine doesn't need separate enum variants;
> each consumer pays for "1 Lab Test" from inventory.  This keeps the
> resource list manageable while letting the *narrative* explain the
> different uses.

> **Open question:** if a player wants per-purpose Lab Tests (separate
> Metal vs Soil vs Environmental tokens), we can subclass later.  Start
> simple.

---

## 3. New profession: Ecologist

*(Implements Issue #25.)*

A new Technician-band profession on **any** island that installs capital
equipment.  Not exclusive to any one role.

| Profession | Band | Training duration | Notes |
|---|---|---|---|
| `Ecologist` | Technician | **1 season away** with Technical Workshop; **2 seasons away** + 1 settling season @ 50% without | Standard technician pipeline (see `education-model.md`). |

### Environmental Assessment workflow

When a player **installs new capital equipment** (the existing Purchase
Equipment / Investing Phase capital catalogue), the install does NOT
come online immediately if the island lacks an Ecologist on staff or
fails the assessment.

1. **Trigger:** capital item arrives in inventory (immediate item or
   end of its delivery delay).
2. **Assessment:** the receiving island needs:
   - At least 1 trained Ecologist on the workforce, AND
   - 1 "Environmental Assessment" Lab Test purchased from the Medical &
     Laboratory Island in the same season.
3. **Outcome:**
   - If both available, equipment comes online next season.
   - If either missing, equipment sits idle (not contributing to capacity)
     until both arrive.
4. **Cost:** standard Lab Test price (≈ 35 Dp) + the Ecologist's salary
   absorbed in island operating costs.

> **Open question:** should the Ecologist requirement apply only to
> *large* capital items (e.g. cost ≥ 80 Dp) or to every item?
> Recommendation: only items with `installation_review_required=true` —
> a new field on the capital catalogue, defaulting `false` for cheap
> items (Vault, Charter Boat, etc.) and `true` for the big-ticket
> infrastructure (Foundry, Hospital Ward, Refinery).

> **Open question:** what happens if an Ecologist isn't trained
> anywhere in the game?  The Educator's University must offer the
> profession from Year 1 to keep this from being a deadlock.  Add
> `Ecologist` to `UNIVERSITY_CAPACITY` with a reasonable annual cap
> (suggest: 6/year — enough for one per island per year).

---

## 4. New profession: Actuary

*(Implements Issue #24.)*

A new Technician-band profession on the **Banking Island**, required to
issue any insurance policy.

| Profession | Band | Training duration | Notes |
|---|---|---|---|
| `Actuary` | Technician | **1 season away** with Technical Workshop; **2 seasons away** + 1 settling season @ 50% without | Standard technician pipeline (see `education-model.md`). |

### Effect on insurance pricing

Today's insurance flow (`SELL_INSURANCE` action): Banker quotes a premium;
buyer accepts.  After this change:

- The Banker can only issue policies if they have an Actuary on staff.
- **Actuarial evaluation cost** is added to the base premium (suggest
  5 Dp per policy as an internal cost — paid from the Bank's institutional
  cash pool, not the buyer).
- If the Banker has zero Actuaries, the `SELL_INSURANCE` action returns
  "  Cannot issue policy: no Actuary on staff."

> The Bank's Insurance capacity is constrained by the number of
> Actuaries.  Existing `banker.underwriting_desk` capital item could
> express this in the capacity model (e.g. each Underwriting Desk
> provides slots for one additional Actuary's output).

---

## 5. Doctor certification of insurance

*(Implements Issue #19.)*

Three interconnected mechanics linking Doctors to the insurance market:

### 5.1 Annual physical halves premium

When a worker is covered by Life or Medical Insurance, they may undergo
an **annual physical** to maintain a reduced premium:

- Buying 1 Lab Test ("Health Certificate") from the Doctor at policy
  issuance halves the premium for that policy's first year.
- A repeat Lab Test at the policy's **anniversary** (1 year after issue,
  which equals the policy expiry under the current 4-season term)
  maintains the half-rate at renewal.
- If the anniversary physical is missed, renewal premium reverts to the
  full base premium.

### 5.2 No productivity loss for insured workers

Currently, when a workplace injury fires (per `engine/workforce_events.py`),
the affected worker loses production capacity for some seasons.
After this change:

- If the worker is on an island holding **Medical Insurance**, the
  injury still happens *narratively* but does **not** reduce the
  worker's productivity.
- Maps to the existing `MEDICAL_INSURANCE_INJURY_REDUCTION` constant
  (currently 0.5 = halves absence).  This change effectively makes the
  reduction 1.0 (full coverage) when the policy is active.

### 5.3 Death benefit pays for training replacement

If an insured worker dies (workplace fatality event):

- The **Life Insurance policy pays out** equal to the **training cost** of
  replacing that worker at the same profession (e.g. 4 seasons of an
  Educator's training fee for a Doctor; less for a Technician).
- Payout goes **from the Bank's institutional pool to the island's
  working capital** (not to the worker's heirs — the island uses it to
  fund the replacement hire).
- The island then decides whether to train someone new or absorb the
  loss.

> Builds on the existing `LIFE_INSURANCE_DEATH_BENEFIT` constant (today
> a flat 60 Dp).  Should become a function of the deceased worker's
> profession and training tier rather than a flat number.

---

## 6. Implementation order (proposed)

Phased so each piece is independently mergeable:

### Phase A — Role rename + Lab Tests resource (smallest)
1. Display rename `Healthcare → Medical & Laboratory`.  **Shipped
   2026-08-06** (`Refs #26`) — engine `ROLES["Doctor"]` display fields plus
   RULES.md / ISLAND_BRIEFINGS.md.  `ROLE_INFO` in `server/app.py` derives
   from `ROLES`, so the client picked it up with no frontend change.
2. Add `ResourceType.LABORATORY_TESTS`.  **Deferred to Phase B — see below.**
3. Add the Lab Test production recipe.  **Deferred to Phase B.**
4. Update STARTING_INVENTORY so the Doctor opens with a small Lab Test
   stockpile.  **Deferred to Phase B.**

> ~~Zero behavioural impact on other islands yet — Lab Tests just exists as a
> tradeable.~~
>
> **This premise does not hold, measured 2026-08-06.**  A prototype of steps
> 2–4 (Lab Tests at 35 Dp, a `doctor.pathology_lab` capacity item deliberately
> left out of `MANDATORY_MINIMUM_INVESTMENT`, `BASE_PRODUCTION` 6/season) moved
> the Doctor from **24.0% → 34.0%** win rate and **17.0% → 18.7%** wealth share
> over 200 games at seed 42.  Supply-chain liveness showed **614 Lab Tests
> produced, 0 consumed, 0 traded**.
>
> The cause is structural, not a tuning error: scoring is on net worth, so an
> output with no consumers is a pure wealth faucet — the AI buys the plant,
> produces, and banks inventory nothing ever draws down.  Gating production
> behind an opt-in capital item does **not** avoid this, because the AI buys
> the item.
>
> **Therefore supply and demand must land together.**  Fold steps 2–4 into
> Phase B so the Mining assay and Agricultural soil-analysis consumers exist
> in the same branch that starts producing Lab Tests.  Phase A reduces to the
> display rename, which is genuinely inert.
>
> Note for whoever picks up Phase B: adding Lab Tests as a *hard* input to
> Metal smelting and Farmer production risks re-creating the cascading-collapse
> dynamic that #47 / PR #212 removed (no Pathology Lab anywhere → no Metal →
> Manufacturer starves).  Prefer a soft gate — a yield penalty or a
> graceful-degradation floor in the style of `EXPERTISE_DEGRADATION_*` — over a
> hard stop, and re-run the calibration sweep before merging.

### Phase B — Mining / Agriculture Lab Test consumers
1. Mining's Ore → Metal smelting requires 1 Lab Test per batch.
2. Farmer's seasonal production requires 1 "Soil Analysis" Lab Test.
3. RULES.md updated.

> **Attempted 2026-08-07 and NOT merged.** Working prototype on branch
> `feature/lab-tests-phase-b` (commit `5717766`). Read this before trying
> again — the mechanism works; the *demand* side is the hard part.
>
> **What the prototype got right, and is worth reusing verbatim:**
>
> - `ProductionEngine.assay_plan()` — a **soft** gate. Coverage-scaled yield:
>   `coverage = min(1, on_hand / needed)`, `yield x = floor + (1-floor) *
>   coverage`. Verified: Metal 40 with 0 tests → ×0.75, with 2 → ×0.875, with
>   4 → ×1.0. It never blocks, so it avoids the cascade that putting Lab Tests
>   into `OUTPUT_PRODUCTION_INPUT_STEPS` would cause — **that table skips the
>   output entirely when an input is short**, which is the exact
>   Manny-Fracture dynamic #47 / PR #212 removed. Do not use it for assays.
> - The `ASSAY_REQUIREMENTS` table shape, `doctor.pathology_lab` capacity
>   item, and the `LaboratoryTests` recipe.
>
> **Why it was not merged.** Over 40 games at seed 42:
> **2,318 Lab Tests produced, 0 consumed, 289 traded** — and the Doctor went
> to **43.5%** win rate (from ~24%). The same wealth-faucet failure the
> Phase A note above describes, and for a subtler reason:
>
> **A soft gate creates only *optional* demand.** Skipping the assay costs a
> Miner 25% of one Metal run — perhaps 60-80 Dp — while a Lab Test lists at
> 35 Dp. The margin is thin, it is a second-order effect the AI's purchase
> logic does not weigh, and so the AI barely buys (289 traded ≈ 0.09 per
> island-season) and holds none at the moment it produces (0 consumed). The
> Doctor meanwhile produces on every tick and banks the unsold stock as net
> worth. Adding `AIStrategy._assay_shortfall()` to
> `_inputs_for_ai_purchase` was not enough to close it.
>
> **This is the structural tension to solve first:** a *hard* gate creates
> real demand but risks the cascade; a *soft* gate is safe but creates demand
> too weak for the AI to act on, so supply outruns it and the faucet returns.
>
> Options, roughly in order of promise:
>
> 1. **Cap supply to demand.** Make the Doctor's Lab Test capacity track
>    actual archipelago assay demand rather than a flat 12/season, so
>    unsold stock cannot accumulate no matter how weak demand is. Cheapest
>    fix and it removes the faucet directly.
> 2. **Make the penalty bite harder** (floor ~0.5 on Metal) so skipping the
>    assay is clearly worse than the 35 Dp, then re-check that the AI
>    actually buys. Needs the flow table to show non-zero *consumed*.
> 3. **Price Lab Tests well below the yield they protect** — the demand has
>    to be obviously profitable, not marginally so.
> 4. **Ship Phase B without the Doctor producing to stock**: make Lab Tests
>    produced *on order* only (a service the consumer requests), which
>    sidesteps inventory-as-wealth entirely. Biggest change, cleanest model.
>
> **Acceptance criterion for the next attempt:** the supply-chain liveness
> table must show LaboratoryTests **consumed > 0 and roughly tracking
> produced**, and no role may move more than ±2 pp across three seeds. If
> consumed is 0, the faucet is back regardless of what the win rates say.

### Phase C — Ecologist profession + Environmental Assessment gate
1. Add `Profession.ECOLOGIST` (Technician, 2-season apprenticeship).
2. Add `installation_review_required: bool` field to `CapitalItem`.
3. Hook into capital-equipment activation: held until Ecologist + Lab Test
   present.
4. Add `Ecologist` to `UNIVERSITY_CAPACITY`.

### Phase D — Actuary profession + insurance underwriting gate
1. Add `Profession.ACTUARY` (Technician, 2-season).
2. `SELL_INSURANCE` requires at least 1 Actuary on Banker's workforce.
3. Banker pays actuarial evaluation cost (5 Dp) from institutional pool.

### Phase E — Doctor-certification insurance economics (#19)
1. Annual physical (Lab Test) halves premium.
2. Insured workers don't lose productivity from injury (`injury_reduction
   → 1.0` when covered).
3. Death benefit becomes profession-based replacement cost.

Each phase is roughly one feature branch.

---

## 7. Open questions

1. **Are Lab Tests a single resource or per-purpose tokens?**
   Recommendation: single resource; the consumer's narrative differs but
   the engine doesn't need separate enum variants.  Reconfirm once
   playtested.
2. **Should the Medical & Laboratory Island require the Doctor to hold
   a `Pathologist` profession** (or similar) in addition to Doctors and
   Nurses, to gate Lab Test production?  Recommendation: defer — start
   with the existing Doctor profession + Medical Orderly handling Lab
   Tests, add Pathologist later if balance demands.
3. **Death benefit funding source** — should the Bank's institutional
   pool always be able to pay, or can it be drained?  Probably should
   tie into the `island-ledger.md` Banker pool work that's still
   pending.
4. **Environmental Assessment certificate validity** — does a single
   assessment cover one capital item only, or does an Ecologist's
   review certify all installs that season?  Recommendation:
   per-item, so the Lab Test demand is meaningful.

---

## 8. Impact summary

This is a larger refactor than the Banker rebalance, but each phase is
modest:

| Phase | Touch surface |
|---|---|
| A: Rename + Lab Tests | ~5 files (role.py, resource.py, constants.py, capacity.py, server) |
| B: Cross-island consumers | ~3 files (Mining + Farmer production logic) |
| C: Ecologist + Environmental gate | ~6 files (profession.py, capacity.py, capital install hook in turn.py, RULES.md) |
| D: Actuary + underwriting | ~4 files (profession.py, insurance underwriting code, RULES.md) |
| E: Doctor-certification economics | ~5 files (insurance pricing, workforce_events.py, RULES.md) |

Each phase yields a working feature; recommend not combining.
