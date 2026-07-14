# Expertise Degradation Floor — activation + calibration note (GitHub #47)

**Date:** 2026-07-12
**Decision (Ash):** missing expertise should *floor* production at a low rate, not hard-stop at zero.

## What changed
- `EXPERTISE_DEGRADATION_ENABLED` flipped `False → True` (constants.py).
- Floor values lowered to `unique_specialist 0.05 / manager 0.10 / technician 0.20`
  (were the unused spec values `0.10 / 0.25 / 0.50`).

An island that fully loses an expertise band now produces at the floored rate
instead of stopping dead. The floor is a *safety net*: `_labour_productivity_factor`
takes `max(natural, floor)`, so it only binds when natural productivity would be
lower.

## Calibration finding (the important part)
80-game × 4-seed sim (seeds 42,1,7,99), same-seed before/after:

| Role | Flag OFF (baseline) | Flag ON | Δ |
|---|---|---|---|
| Farmer | 12.0% | 13.7% | +1.7 |
| Miner | 14.7% | 16.3% | +1.6 |
| Transporter | 12.4% | 14.2% | +1.8 |
| Educator | 16.6% | 12.0% | **−4.6** |
| Banker | 15.9% | 15.1% | −0.8 |
| Manufacturer | 15.7% | 12.0% | **−3.7** |
| Doctor | 12.8% | 16.6% | **+3.8** |

Bankruptcy 0.00% both runs; brownouts 1.3% → 2.6%.

**Floor value is immaterial to balance in the 0.05–0.50 range** — the gentle
(0.05/0.10/0.20) and spec (0.10/0.25/0.50) floors produced *identical* role
shares to 0.1% across all four seeds. The redistribution is inherent to enabling
the floor at all, NOT a function of the floor height, so it cannot be tuned away
by lowering the floors. (Chose the gentle values anyway as the most conservative
"just prevent zero" reading.)

Mechanism: the old hard-stop let one island's expertise failure cascade to its
consumers; that cascade is what gave high-variance roles their scarcity premium.
The floor short-circuits the cascade and re-prices the economy — a *lateral*
rebalance (max-min spread ≈4.6pt both ways), not a worsening, but it swaps the
advantaged roles (Educator/Manufacturer ↔ Doctor/Miner).

## Status & follow-up
The floor ships per the gameplay decision. The 3-role, ~4pt shift exceeds the
repo's ±2σ regression gate, so it is tracked as a **calibration follow-up**
(GitHub issue linked from the PR): re-tune role economics / event charts so
shares return toward the baseline band *with the floor on*, or explicitly bless
the new distribution as the intended post-floor balance. Not a blocker — no
bankruptcies, no dead resource lines — but it should not be left unowned.
