# Calibration sweep — findings & next steps (2026-06-02)

**Method:** `simulation.runner --games 200 --years 3 --seeds 42,1,7,99`
(engine economy: 50 workers/island, Courses production, Reagents-from-Medical,
kitchen tiers; scoring = `total_wealth`). Target: win rate ≈ 1/7 (14.3%) each.

## Baseline (before this sweep)
| Role | Win% |
|---|---|
| Educator | **88.1%** |
| Doctor | 7.4% |
| Miner | 3.6% |
| Transporter / Manufacturer / Farmer | ~0–0.5% |
| Banker | **0.0%** |

The event charts were themselves badly skewed: Educator avg yield **1.21** (85%
"good" events) while Miner/Manufacturer/Doctor were brutal (avg **0.53–0.69**).

## After a moderate, non-distorted chart retune (committed)
Trimmed the over-generous (Educator→0.88, Transporter→0.95, Banker→1.0) and
softened the over-harsh (Miner→0.92, Manufacturer→0.95, Doctor→0.90, Farmer→1.0):

| Role | Win% |
|---|---|
| Educator | **53.1%** |
| Doctor | 34.0% |
| Miner | 10.8% |
| Manufacturer | 1.1% |
| Transporter | 0.8% |
| Farmer | 0.2% |
| Banker | **0.0%** |

Top role nearly halved (88→53), Miner/Doctor pulled up. **But charts can't get
further:** pushing the Educator chart down to avg 0.62 and the Farmer up to 1.25
(an extreme, unrealistic distortion) *still* left Educator ~44% and Farmer ~1%.

## Why charts can't equalise it — it's structural
1. **Output value gap.** Win condition is `total_wealth`, dominated by what each
   island produces × its price. Educator (Patents 47.5, Expertise 17.1, Courses
   23.75) and Doctor (Vaccine 36.75, HealthServices 31.5) print high-value goods;
   Farmer (Food 13.5, Fish 10.8) and Transporter (Freight 16.5, Seats 18.7) make
   cheap goods. A yield modifier can't close a 3–4× per-unit value gap.
2. **Banker has no commodity.** It earns only via loan interest spread, which the
   greedy sim AI (`engine/ai.py`) barely exercises — so the Banker accumulates
   almost nothing and wins 0% regardless of its (generous) chart.
3. **Patents compounding.** Educator Patents at 7.5/season × 47.5 Dp ≈ 356
   Dp/season of pure inventory value — a structural money-printer.

## Recommended next steps (need design sign-off — gameplay-affecting)
Do the **structural** rebalance first, then re-run this sweep to fine-tune charts
on the balanced base:

1. **Trim high-value-output roles:** lower Educator Patents output and/or price;
   reduce Expertise volume. Lower Doctor Vaccine/HealthServices volume or price.
2. **Lift low-value roles:** raise Farmer Food/Fish and Transporter Freight/Seats
   output or price so a busy farm can rival a lab.
3. **Banker earning model / AI:** teach the sim AI Banker to actually lend
   (interest income), or give the Banker a scored asset. Until then the Banker is
   structurally unwinnable in sim. *(Good `ai.py` task — candidate for Codex.)*
4. **Re-calibrate charts** afterward — the moderate set committed here is a
   reasonable starting point once values are balanced.

## Status
- Committed: the moderate chart retune (a genuine improvement; top role halved).
- Deferred (needs sign-off): the structural rebalance above. Calibrating charts
  to 1/7 is **blocked** on it.
