# Brief — Continuing Education: Manager-Band Expertise Upkeep (2026-07-05)

**Status: APPROVED (Ash 2026-07-05, corrected 2026-07-05) — implementation-ready.**
P2b of the economics-vision program. Game-wide upkeep mechanic — sim-gate and
merge on its own. **Suggested owner:** Codex ; Claude (UI: continuing-education
coverage indicator). **Base off:** current `origin/pre-release`. **Follows:**
`_README.md`. Interacts with `economic-dependence-inputs-2026-07-05.md` (P2a).

## Goal (Ash 2026-07-05, corrected)

**1 Expertise per manager per YEAR** as continuing education. A manager who
hasn't received their annual Expertise loses **5% productivity per season**
until covered. **Evenly balanced across managers** — no per-manager allocation
logistics: an island with 7 managers that receives 5 Expertise across the year
runs at a shortfall of `(7−5)/7`, so the per-season penalty is
**5% × (7−5)/7**. Purpose: make Expertise a *recurring* consumable and the
Educator a recurring seller (its deepest structural problem — today it trains
you once and is done).

## Mechanic (even-balanced, rolling-annual, per island)

Auto-applied at season upkeep (a passive sink like sustenance/energy — not a
player action). **One aggregate state per island, never per-worker** — this is
the "evenly balanced" simplification.

State per island: `ce_ytd` = Expertise consumed for continuing education over
the **trailing `len(SEASONS)` seasons** (a rolling 4-slot ring, so it updates
without a hard year boundary); `ce_penalty` = accumulated productivity penalty.

Each season:
1. `N` = Manager-band worker count (`PROFESSION_BAND[p] == WorkerBand.MANAGER`
   — includes Farmer, Miner, Engineer, Doctor, Nurse, Banker, Professor,
   Lecturer, LogisticsManager, MarineBiologist, MedicalResearcher, etc.).
2. Annual need = `N × CE_ANNUAL_PER_MANAGER` (=N). Remaining = `max(0, N − ce_ytd)`.
3. Auto-consume `used = min(Expertise in stock, remaining)` from inventory;
   roll `used` into this season's ring slot (so `ce_ytd` reflects the trailing year).
4. Uncovered fraction `f = max(0, (N − ce_ytd) / N)`.
5. Accrue/recover:
   - `f > 0` → `ce_penalty = min(CE_MAX, ce_penalty + CE_PENALTY_PER_SEASON × f)`
   - `f == 0` → `ce_penalty = max(0, ce_penalty − CE_RECOVERY_PER_SEASON)`
6. **Every Manager-band worker's effective efficiency ×= `(1 − ce_penalty)`** —
   uniform across the island's managers. Non-manager bands unaffected.

Constants: `CE_ANNUAL_PER_MANAGER = 1`, `CE_PENALTY_PER_SEASON = 0.05`,
`CE_RECOVERY_PER_SEASON = 0.05`, `CE_MAX = 0.20` (a wholly-neglected manager
corps bottoms at −20% — the old single-season figure becomes the annual worst
case; all tunable).

Worked example (Ash's): 7 managers, 5 Expertise across the year → `f = 2/7` →
each short season adds `5% × 2/7 ≈ 1.4%` to `ce_penalty` (up to `CE_MAX`); a
season that reaches full 7/7 coverage instead recovers it 5%.

## Calibration note (demand is now MODEST — read before tuning)

With the **annual** cadence, opening demand ≈ `N` per island per year ≈
**~16 Expertise/year total (~4/season)** against the Educator's ~12/season
(~48/year) output — Expertise is **comfortably in surplus**. This is a gentle
recurring upkeep, **not** a scarcity crisis (contrast an earlier per-season
draft that would have starved everyone). So the calibration risk inverts: make
sure Expertise actually **clears the market** (doesn't pile up as dead surplus)
and that the Educator's recurring Expertise revenue is material. If managers
still drift below ~0.90 mean CE-factor, that's a distribution problem (islands
not buying), not a supply one — the AI Expertise buy-buffer is the lever.

**Accrual model: CUMULATIVE (locked, Ash 2026-07-05).** The penalty accumulates
across short seasons per step 5 above — implement it, not a flat per-season
drag. (A `--ce-model flat` sim flag is optional/nice-to-have for calibration
comparison only; the shipped behaviour is cumulative.)

## Files

models/player.py (island-level `ce_ytd` ring + `ce_penalty`; **no per-worker
CE state**), engine/game.py (season upkeep: Expertise consume + accrue/recover,
ordered after production so next season reflects coverage), engine/production.py
or workforce efficiency (apply the uniform CE multiplier to Manager-band
contribution), constants.py (CE constants), engine/ai.py (Expertise buy-buffer
≈ annual manager need), server UI (Claude), tests.

## Acceptance criteria

1. 7 managers, 5 Expertise over the trailing year → `f = 2/7`; a short season
   adds ≈1.4% to `ce_penalty`; a fully-covered season (7/7) recovers it 5%.
2. A neglected corps (0 Expertise) accrues 5%/season to the `CE_MAX` 0.20 floor
   and no further; resuming full coverage recovers at 5%/season.
3. **Even-balanced**: one island-level penalty applies to all Manager-band
   workers; a test asserts there is no per-worker CE state and that two managers
   on the same island always share the same CE multiplier.
4. Full pytest; **1000-game seed-42 sim** (share±σ + fallback telemetry):
   Educator **+1–3pts** (recurring Expertise sales); no other role >2pts beyond
   P2a's Miner bump; Expertise **clears** (consumed ≈ produced; surplus shrinks
   vs baseline); mean manager CE-factor **≥ 0.90**. Quote the CE-factor
   distribution and Expertise produced/consumed/traded in the PR.

## Out of scope

Technician/Worker-band upkeep (managers only), Expertise as a training input
(unchanged), the Educator's own lab input costs (P2a §3).
