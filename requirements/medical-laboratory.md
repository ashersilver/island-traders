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
| `Ecologist` | Technician | **2 seasons** | Trained at the Educator's University like any apprenticeship. |

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
| `Actuary` | Technician | 2 seasons | Trained at the Educator's University. |

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
1. Display rename `Healthcare → Medical & Laboratory`.
2. Add `ResourceType.LABORATORY_TESTS`.
3. Add the Lab Test production recipe.
4. Update STARTING_INVENTORY so the Doctor opens with a small Lab Test
   stockpile.

Zero behavioural impact on other islands yet — Lab Tests just exists as a
tradeable.

### Phase B — Mining / Agriculture Lab Test consumers
1. Mining's Ore → Metal smelting requires 1 Lab Test per batch.
2. Farmer's seasonal production requires 1 "Soil Analysis" Lab Test.
3. RULES.md updated.

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
