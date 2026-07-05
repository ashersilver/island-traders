# Brief — Continuing Education: Manager-Band Expertise Upkeep (2026-07-05)

**Status: APPROVED (Ash 2026-07-05) — implementation-ready.** P2b of the
economics-vision program. This is a **game-wide economic mechanic** — sim-gate
carefully and merge on its own. **Suggested owner:** Codex ; Claude (UI:
continuing-education coverage indicator + deprivation warning). **Base off:**
current `origin/pre-release`. **Follows:** `_README.md`. Interacts with
`economic-dependence-inputs-2026-07-05.md` (P2a) and the Educator's Expertise
output — see the calibration note.

## Goal (Ash 2026-07-05)

"Banker and Doctor need to consume 1 Expertise per season as continuing
education. As do all managerial-level employees — else their productivity drops
by 20% per season that they don't receive expertise." This makes **Expertise a
universal recurring consumable** and the Educator a *recurring* seller (its
deepest structural problem: today it trains once and is done with you).

## Mechanic

Auto-consumed at season upkeep (like sustenance/energy — a passive sink, not a
player action). Per island, each season:

1. **Demand** = count of **Manager-band** workers (`PROFESSION_BAND[p] ==
   WorkerBand.MANAGER`) in the island's workforce. Manager band already
   includes the lead professionals: Farmer, Miner, Engineer, Doctor, Nurse,
   Banker, Professor, Lecturer, LogisticsManager, MarineBiologist,
   MedicalResearcher, TechnicalDirector, etc.
2. **Supply**: consume 1 Expertise from island stock per manager, **highest-
   efficiency managers first** (protect your best staff when short).
3. Each manager tracks `seasons_without_ce` (new worker field):
   - Fed this season → reset to 0.
   - Not fed → increment.
4. **Continuing-education factor** per manager =
   `max(CE_FLOOR, 1 − CE_PENALTY_PER_SEASON × seasons_without_ce)`,
   with `CE_PENALTY_PER_SEASON = 0.20`, `CE_FLOOR = 0.40` (bottoms at −60%
   after 3 deprived seasons). Multiplies that worker's effective efficiency in
   the workforce/production calculation.
5. **Instant restore**: a manager who receives Expertise resets to 0 → full
   efficiency next season ("back in continuing education").

The Educator self-supplies from its own Expertise production before any is sold;
net external demand is what other islands must buy.

## Calibration note (the crux — read before tuning)

Starting Manager-band headcount ≈ **1–2 per island** (Doctor ~4, Educator ~7),
so opening demand ≈ **~16 Expertise/season** vs the Educator's base output
≈ **12/season** (1.2 × PRODUCER_PRODUCTIVITY_MULTIPLIER). Deliberately scarce —
that scarcity is the point (Expertise gains real value; the Educator must
expand output; islands compete). But it must not spiral every island to the
−60% floor. **The tuning lever is the Educator's Expertise output rate**
(`BASE_PRODUCTION["Educator"]["Expertise"]`), not the penalty. The sim gate
below is the arbiter: if managers sit below ~0.85 CE-factor on average across a
1000-game run, raise Educator Expertise output (and/or lower demand to
"1 per 2 managers") until the market clears. Quote the swept values in the PR.

Provide a sim flag `--ce-demand-per-manager {1.0,0.5}` so calibration can A/B
the per-manager vs per-2-managers reading without a code change.

## Files

models/profession.py (already has bands — no change), models/workforce.py or
worker model (`seasons_without_ce` field + CE factor), engine/game.py (season
upkeep: Expertise consumption + counter update, ordered after production so the
*next* season's productivity reflects this season's coverage), engine/production.py
or workforce efficiency (apply CE factor), constants.py (CE constants + possibly
Educator output bump), engine/ai.py (Expertise buy-buffer sized to manager
count), server UI (Claude), tests.

## Acceptance criteria

1. An island with 3 managers and 3 Expertise in stock consumes 3, all reset to
   0. With 1 Expertise, only the top-efficiency manager is fed; the other two
   increment and drop to ×0.80 next season.
2. A manager deprived 4 seasons sits at `CE_FLOOR` (0.40), not lower; feeding it
   once restores to 1.0 next season.
3. Educator self-consumes before selling; its own managers are covered when it
   produces ≥ its manager count.
4. Full pytest; **1000-game seed-42 sim** (share±σ + fallback telemetry):
   - Mean manager CE-factor ≥ **0.85** across the run (else tune per the note).
   - Educator share **+1–3pts** (intended — becomes a recurring seller);
     no other role moves >2pts beyond P2a's Miner bump.
   - Expertise produced & consumed both rise sharply; Expertise no longer sits
     as dead surplus. Quote the CE-factor distribution + Educator output value
     used in the PR.

## Out of scope

Technician-band upkeep (managers only for now), Expertise as a training input
(unchanged), the Educator's own input costs (P2a §3).
