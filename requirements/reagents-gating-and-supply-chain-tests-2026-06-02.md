# Requirement — Decouple reagents from generic training + add supply-chain liveness tests (2026-06-02)

**Status:** Spec for review. Not built. From the 2026-06-02 "why didn't the
bottleneck fail a test?" discussion.

## A. Reagents should gate science/research only — not all teaching

**Problem.** `PRODUCTION_INPUTS["Educator"] = {"Reagents": 1}` gates *every*
Educator output (Expertise, Courses, Patents) behind one lab input. Since Course
slots drive ALL training, reagents indirectly block training a Banker, Actuary,
Mechanic, or Flight Crew — which is hollow (those are classroom courses, not
chemistry). Reagents are sensible for **research (Patents)** and **science-track
courses** (Doctor/lab professions) only.

**Why it's not a one-liner.** The active production model consumes one input set
per *role* wholesale (`PRODUCTION_INPUTS` + `BASE_PRODUCTION`), not per-output.
To make reagents gate only *some* outputs, we need per-output input granularity
(the capacity model `PRODUCTION_RECIPES` already has per-output inputs; the
*active* producer doesn't).

**Proposed change.**
- Remove `Reagents` from the blanket `PRODUCTION_INPUTS["Educator"]` so Expertise
  and generic Courses produce without lab reagents.
- Keep reagents as the input for **Patents** (research) — and, when a
  science-course track is modelled, for science-tier course/training only.
- Define a small **science-profession set** (e.g. Doctor, Nurse, lab/medical and
  hard-engineering professions) whose *training* consumes reagents; generic
  professions (Banker, Actuary, Mechanic, Flight Crew, Clerk…) do not.
- **[CONFIRM]** the science/non-science taxonomy with the user before building.

**Balance note.** Removing the Educator's only hard input makes it more
self-sufficient (it was already a calibration outlier). Pair this with a
calibration re-check; may need a small Educator output trim to compensate.

## B. Supply-chain liveness test (so the next bottleneck *does* fail)

The sim only tracks win rates + wealth, so a starved supply chain shifts results
silently instead of failing. Add:

1. **Sim metric:** per-role counter of "seasons a role could have produced but
   was blocked solely by missing *purchasable* inputs" (i.e. `can_produce`
   false due to an input that another island produces). Expose it in the
   `runner` output (CSV + summary).
2. **Liveness test:** a pytest that runs a short multi-role game (all-AI, a few
   years) and asserts **no role is input-starved beyond a threshold** (e.g. no
   role blocked > X% of seasons by a tradeable input). This converts "the
   Educator quietly made nothing for 8 seasons" from an invisible into a
   red test.
3. Optionally a one-off **chain-reachability** check: for each role's required
   inputs, assert some island actually *produces* that input (catches the
   "Reagents had no producer" / "Courses had no production path" class of bug at
   import time, not playtest time).

Item B3 is cheap and high-value — it would have caught both the Courses-not-
produced and the Reagents-no-capital-item bugs immediately.

## Sequencing
B3 (static reachability check) first — cheapest, catches a whole bug class.
Then A (reagent decoupling, needs the taxonomy decision + a calibration touch).
B1/B2 (dynamic liveness) can follow or be handed to Codex.
