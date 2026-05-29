# Codex Task — Graceful degradation on missing expertise (2026-05-27)

**Owner:** Codex
**Origin:** GitHub issue #47 *"Game Option: Missing Workforce option"* + 2026-05-27 Manny Fracture / Manufacturer playtest report. Quote: *"The Mining player (Manny Fracture) had 0 active workers for virtually the entire 5-year game, meaning no Oil was ever produced or sold despite my bids of up to 50 Dp/unit. Without Oil — a required input — all production lines (FarmMachinery, MiningEquipment, LaboratoryEquipment, MedicalDevices, TransportEquipment) remained locked at max 0 capacity."*

Today: missing the role's required expertise → production is zero → cascade across the whole island graph. There's no "limp along at reduced capacity" path. Issue #47 asks for a graceful floor so a starved island can still produce *something* while the training pipeline catches up.

## Goal

Add a per-input-category degradation floor so islands missing their normal expertise still produce a fraction of normal output rather than zero. The 2026-05-26 scoping conversation locked in "variable by expertise category" — different floors per band:

- **Manager-tier missing** (e.g. Farmer Specialist, Banker, Doctor, Educator Professor) → **25 % floor**: survive-don't-thrive. Keeps the pressure to train without making training optional.
- **Technician-tier missing** (e.g. Farming Technician, Mining Technician, Nurse, Lecturer) → **50 % floor**: uncomfortable but functional.
- **Unique specialist missing** (the role's *primary* Manager — Doctor on Healthcare, Banker on Banking, Educator's Professor) → **10 % floor**: these *should* hurt hard; without the named specialist the island is barely operating.
- **Worker-tier (Unskilled) missing** → no floor change. Unskilled work is already partly substitutable by skilled workers; this band stays binary.

Floors compose multiplicatively — e.g. a Farmer with no Farmer Specialist AND no Farming Technician produces `0.10 × 0.50 = 0.05` of normal (effectively dead but still on the books).

## Branching

- **Base:** `pre-release` at `0.1.0-dev.2026-05-27.4` head or later.
- **Branch name:** `codex/graceful-degradation-2026-05-27`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec

### Configuration

New table in `island_traders/constants.py`:

```python
# Production floor when an island is missing required expertise.  Each
# band-tier has a fractional floor that multiplies the would-be-zero
# output.  Floors compose multiplicatively across bands.
# Per-role overrides go in EXPERTISE_DEGRADATION_ROLE_OVERRIDES below.
# (2026-05-27 graceful-degradation brief, GitHub #47.)
EXPERTISE_DEGRADATION_FLOORS: dict[str, float] = {
    "unique_specialist": 0.10,  # role's primary Manager (Doctor/Banker/Educator's Professor)
    "manager":           0.25,  # other Manager-tier shortages
    "technician":        0.50,  # Technician-tier shortages
    "unskilled":         1.00,  # no floor change — existing behaviour
}

# Per-role override if a specific island needs a different floor than the
# defaults above.  Empty by default; populate during playtest calibration
# if specific roles feel wrong.
EXPERTISE_DEGRADATION_ROLE_OVERRIDES: dict[str, dict[str, float]] = {}
```

### Where to apply

In `engine/production.py:_labour_productivity_factor` (or wherever the labour productivity multiplier is computed):

```python
def _labour_productivity_factor(self, player, season_name, product_line=None) -> float:
    # ... existing computation ...
    factor = player.workforce.labour_productivity_factor(...)
    if factor <= 0.0:
        # Apply the graceful-degradation floor so a starved island isn't
        # frozen at zero.  Compute per-band shortfall and take the product
        # of the relevant floors.
        floor = self._expertise_degradation_floor(player, season_name)
        return floor
    return factor
```

`_expertise_degradation_floor` walks the player's role(s), checks each required band (Manager / unique specialist / Technician), and returns the *product* of the matching floor values from `EXPERTISE_DEGRADATION_FLOORS`. Default to 1.0 if no shortages.

### Logging

When the floor kicks in, the season summary must say so explicitly:

```
[PRODUCTION] AyaySir (Mining) operating at 10% floor — no active Miner
  specialist on roster.  Reduced output: 1 Ore, 0 Metal, 1 Oil (vs full
  10/5/10).  Train a Miner via Education Island to restore full output.
```

This is the player-facing signal that they're degraded and what to do about it.

### Files to touch

- `island_traders/constants.py` — new tables.
- `island_traders/engine/production.py` — `_expertise_degradation_floor` helper + call site in `_labour_productivity_factor`.
- `island_traders/engine/production.py` — explicit log line when the floor applies.
- `island_traders/server/app.py` — surface `degradation_floor: float` on the per-output capacity payload so the dashboard can chip it ("Operating at 25 % floor — Farmer Specialist missing").
- Tests: new `tests/test_engine/test_graceful_degradation.py`.

### UI follow-up (Claude separate)

- "Operating at X % floor" chip on the per-output capacity panel.
- "Train missing X" recommendation linked to the training-request modal.

## Tests

- `tests/test_engine/test_graceful_degradation.py` (new):
  - Mining with 0 Miner specialists but 2 Mining Technicians produces at 10 % floor (unique-specialist gone, technicians present).
  - Mining with 0 Miner and 0 Technicians produces at 10 % × 50 % = 5 % floor.
  - Mining with full roster produces at 100 % (no floor applied).
  - Doctor with no Doctor specialist but 4 Nurses produces at 10 % × 1.00 (Nurses are Manager-tier substitutes — confirm Doctor's primary specialist logic).
  - Educator with no Professor but plenty of Lecturers + TDs produces at 10 % floor.
  - Logging: the "[PRODUCTION] ... operating at X % floor" line appears in `result.actions_taken` or `io.print` history.
  - Calibration sweep stays within band.

## Acceptance criteria

- All four band-tier floors implemented per the spec.
- Per-role override mechanism in place (even if empty by default).
- Floor visible in both the server payload (`degradation_floor`) and the game log.
- Simulation 5-year run with no Educator training shows all islands still producing > 0 (no permanent zero-cap state).
- Full test suite green at new baseline (475 + new).
- Calibration sweep within band. The brief expects Farmer / Miner / Manufacturer / Doctor (the high-expertise-need roles) to gain win-rate ground from being able to limp; if any role drifts more than +2 pp out of [12 – 18 %], tune the floors *down* a notch before landing.

## Out of scope

- Hiring workers from other islands (covered by GitHub #50 separately).
- Per-resource degradation (e.g. "Farmer without Farming Technician produces Grain at 50 % but Fish at 80 %") — keep the multiplicative-floors model simple for this brief; per-resource tuning can come later.
- Replacement-via-Unskilled mechanics (Unskilled never substitutes for Skilled in this brief).
- AI behaviour changes (the AI continues to train as usual; this fix just affects production output).

---

## 2026-05-27 implementation findings (added by Claude during scaffolding)

Claude scaffolded the engine helper + constants + payload field + brief
acceptance tests, but **the floor application is gated off
(`EXPERTISE_DEGRADATION_ENABLED = False`) pending a proper
recalibration pass**.  Findings:

- Brief-spec floors (0.10 unique / 0.25 manager / 0.50 technician)
  caused a major calibration shock in the 4-seed sweep:
  - Farmer 12.9% → **22.5%**, Miner 13.1% → **4.4%**, Transporter 14.9% → 16.8%, Educator 18.0% → 12.4%, **Banker 14.8% → 2.8%**, Manufacturer 12.8% → **23.1%**, Doctor 13.6% → 18.1%.
- Halving the floors to 0.05/0.10/0.25 produced **identical** (byte-for-byte) results.  Further reducing to 0.02/0.05/0.10 also produced identical results.
- **Root cause**: existing calibration depends on
  cascading-collapse positive-feedback loops — when one role's
  workforce empties, its consumers also stop, freezing the whole
  market.  This freeze gives high-risk roles (especially Miner) their
  scarcity premium when they recover.  Any non-zero floor — even a 1%
  trickle — breaks the freeze chain because downstream consumers can
  always find SOME input.  The displacement of scarcity premium is
  what crashes Miner and Banker win rates.
- **Implications for proper calibration**: this brief's acceptance
  criterion "calibration sweep within band" is **not achievable** with a
  floor mechanism alone.  Two paths:
  1. Pair the floor with rebalancing of workplace_risk fatality rates
     and/or starting workforce sizes so islands don't naturally drift
     to zero workforce.
  2. Combine with the `disaster-mitigation-and-workforce-resilience-2026-05-27`
     brief (Life-insurance fatality reduction, per-tick cap) so the
     attrition pressure that causes the cascade is reduced — making the
     floor a true safety net for edge cases rather than a regular
     occurrence that shifts the entire market.

**Ready to enable**: flip `EXPERTISE_DEGRADATION_ENABLED = True` in
`constants.py` and re-run the 4-seed sweep.  The helper, payload, log
line, and UI follow-up scaffolding are all in place.  Calibration is
the remaining work.
