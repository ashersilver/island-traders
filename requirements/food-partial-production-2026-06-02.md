# Requirement (later addition) — Partial food production on missing ingredients (2026-06-02)

**Status:** Backlog / later addition. **Not yet built.** Captured per the
2026-06-02 request; to be scheduled after the current batch + Phase 3.
**Area:** Kitchen food production (`engine/production.py` `run_kitchens` /
`_run_one_kitchen`; recipe is Grain + Produce + Protein, where Protein = Fish or
Meat). Applies to **all kitchen tiers** (Manufacturing + Industrial).

## The rule

Today a kitchen produces its full Food output only if it can pay the **whole**
recipe; otherwise it sits idle ("short on <ingredient>"). The new rule allows
**graceful partial production** when an ingredient is short:

1. **One non-protein ingredient missing** (i.e. Grain *or* Produce is absent /
   insufficient, but the protein slot — Fish or Meat — is available): the kitchen
   still produces **50%** of its Food output.
2. **Protein missing** (both Fish *and* Meat absent / insufficient): the kitchen
   produces only **30%** of its Food output, **rounded/truncated down** to a
   whole number of Food units.

So the protein slot is the most critical; a missing staple (Grain/Produce) is a
lighter penalty than a missing protein.

## Worked example (Industrial Kitchen, 20 Food/season)
- All ingredients present → 20 Food.
- Grain (or Produce) short, protein OK → `floor(0.50 × 20)` = **10 Food**.
- No protein at all (no Fish, no Meat) → `floor(0.30 × 20)` = **6 Food**.

(For the Manufacturing Kitchen at 10 Food: 50% → 5; 30% → `floor(3.0)` = 3.)

## Open questions to settle at build time
- **Partial-ingredient consumption:** when producing at 50%/30%, does the kitchen
  consume the full recipe for the *reduced* output (i.e. ingredients scaled to
  the partial Food made), or the full-batch amount? Assume **scaled to the
  partial output** unless decided otherwise.
- **Both a staple AND protein missing** (e.g. no Produce *and* no protein): the
  rule names the two cases separately. Proposed resolution — the **worst
  applicable** penalty wins, so missing protein (30%) dominates. Confirm.
- **Both staples missing** (no Grain *and* no Produce, protein present): the rule
  says "one ingredient other than Fish or Meat missing → 50%". Proposed: still
  50% (the staple slots collapse to a single 50% penalty), or escalate. Confirm.
- **Rounding:** truncate **down** to whole Food units in all partial cases
  (explicit for the 30% case; apply uniformly).
- Surface the partial run in the kitchen log (e.g. "Industrial Kitchen: produced
  10 Food (50% — short on Grain)") so the player understands the reduction.

## Tests (when built)
- Missing Grain (protein present) → 50% of tier output, floored; ingredients
  consumed for the reduced output.
- Missing both Fish and Meat → 30% of tier output, floored.
- Full ingredients → unchanged full output (regression).
- Manufacturing (10) and Industrial (20) tiers both honour the percentages.
