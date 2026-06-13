# Brief — Equipment warranties + failure model (2026-06-12)

**Suggested owner:** Codex (economy + capital model). **Builds on / unblocks #124.**
**Base off:** current `origin/pre-release`. Fold into the #124 line or as a
follow-up that lands with it.
**Issues:** new ("Equipment warranties + failure", `area: economy`); relates to
**#124** (durable capital) and **#51** (Air Freight / Cargo aircraft).

## Why (the #124 calibration fix)

#124 makes equipment durable capital (bought once, not consumed each season).
Calibration snapshot (`--games 1000 --seed 42`, draft `33c9c1f`): the structural
fixes work (Metal smelts from Ore; Farmer no longer starves on machinery), **but
the Manufacturer collapses to 0% win / 1,283 Dp** because its recurring market
vanished — FarmMachinery production cratered 74k→5.6k. This mechanic restores the
Manufacturer's recurring revenue (warranty premiums + repair fees) and, as a
bonus, creates real **Transporter freight demand** (spares delivery).

## The mechanic (maintainer design, 2026-06-12)

### 1. Warranty (recurring revenue)
On purchasing a piece of equipment (any `CAPITAL_CATALOGUE` item), the owner may
buy a **warranty** from the Manufacturer, priced at **~20% of the purchase price
per year, recurring** (charged each year the warranty is held, paid to the
Manufacturer's treasury). A warranted item **does not fail** — repairs are
covered. New constant e.g. `EQUIPMENT_WARRANTY_ANNUAL_RATE = 0.20`.

### 2. Failure model (uninsured equipment)
If the owner declines the warranty, the item can fail. Failure probability rises
with the item's age (Poisson-style age-increasing hazard); the maintainer's
target annual failure probabilities by age:

| Equipment age | Annual failure probability |
|---|---|
| Year 1 | 5% |
| Year 2 | 15% |
| Year 3 | 40% |

(Constant e.g. `EQUIPMENT_FAILURE_PROB_BY_AGE_YEAR = {1: 0.05, 2: 0.15, 3: 0.40}`;
for items older than the table, hold at the last value or extend.) Hook into the
existing per-season capital step `Game._process_capital_maintenance`
(`engine/game.py`), using `capital_acquired_ticks` for age.

### 3. On failure (uninsured)
When an uninsured item fails, the owner must, **in the season it fails**:
1. Pay the **Manufacturer 50% of the item's purchase value** (repair/parts fee →
   Manufacturer treasury). Constant `EQUIPMENT_FAILURE_REPAIR_FRACTION = 0.50`.
2. Get the spares delivered + repaired, choosing one of:
   - **Air (Cargo aircraft, #51):** pay **2 Freight** → spares delivered and the
     repair completed **the same season** (no downtime). Requires the Air Freight
     / Cargo-aircraft capability (#51); until that exists, this option is
     unavailable.
   - **Ship:** pay **1 Freight** → delivered and repaired the **following season**
     (the item is **down — contributes 0 capacity — for the intervening season**).
   The Freight is demand routed to the Transporter (a fee/credits to the
   Transporter, consistent with the P4 freight-friction direction).

A failed item the owner can't pay for (no cash / no Freight) stays **down** until
resolved (don't crash; mark unusable, like the existing unmaintained-capital
flag).

## Economic effect (what this restores)
- **Manufacturer:** recurring warranty premiums (~20%/yr on the installed base)
  + 50%-of-value repair fees on uninsured failures → a steady market that
  replaces the lost per-season equipment consumption. Should lift it off 0%.
- **Transporter:** 1–2 Freight per failure (and per repair) → recurring freight
  demand, helping its viability and exercising #51.
- **Owners:** a genuine risk decision — pay 20%/yr for certainty, or self-insure
  against a rising failure hazard with a painful 50% + Freight + downtime hit.
- Distinct from Banker insurance (which covers workforce casualties); this is
  Manufacturer-sold equipment cover.

## Modeling decisions (resolve; defaults recommended)
- **Roll cadence:** the probabilities are *annual*. Recommended default: evaluate
  failure **once per year at year-end** per uninsured item using its age bucket,
  resolving the failure effects in that season. (Alternative: per-season hazard
  summing to the annual figure — only if year-end feels too lumpy.)
- **"Freight credits":** use the existing `Freight` resource (the owner spends
  Freight, paid to the Transporter), not a new currency, unless #51 introduces a
  distinct air-freight unit — then the air option consumes that.
- **AI:** the warranty buy/decline and the air-vs-ship repair choice need AI
  defaults (e.g. warrant high-value/critical items, self-insure cheap ones; pick
  air if it has the Freight + a Cargo aircraft exists, else ship). Reuse the
  #108 financing path if it can't afford a repair.

## Acceptance
- Tests: warranty premium debits owner → credits Manufacturer annually; an
  uninsured item fails per the age probabilities (seeded RNG); on failure the
  owner pays 50% to the Manufacturer + Freight to the Transporter and the item is
  down for the ship option / same-season for air.
- `--games 1000 --seed 42`: **Manufacturer recovers off 0%** and the win-rate
  spread re-tightens toward 1/7; Transporter freight demand rises. Report
  before/after win% + money supply.
- APP_VERSION bump + RELEASE_NOTES (player-facing: equipment can be warrantied;
  uninsured equipment can fail and needs paid repair + spares delivery).
