# Brief: Industrial/Equipment Insurance + Doctor Certification (GitHub #196 + #19)

**Date:** 2026-07-12
**Repo:** island-traders (`pre-release`)
**Owner:** Codex (economy feature)
**Priority:** Wave 2 of the 2026-07-12 issue-triage plan — one coherent feature.

Build #196 and #19 together: they share the same insurance subsystem and the
same Doctor↔Banker dependency, and #19 is the natural gate on the payout risk
#196 introduces.

## Current state (verified 2026-07-12)
- `island_traders/models/insurance.py`: `InsurancePolicy` with `policy_type`
  in {"life","medical"}, premium, term (tick-based expiry), per-head coverage,
  pro-rata cancel refund (#5). Sold by the Banker via `SELL_INSURANCE` /
  bought via `BUY_INSURANCE` / managed via `MANAGE_INSURANCE`.
- Equipment failure already exists: `engine/game.py` `_process_equipment_failures`
  rolls a Weibull failure per in-service, **uninsured, out-of-warranty** unit
  (note the code ALREADY checks an insured flag — wire industrial insurance into
  that existing check rather than adding a parallel one).
- No industrial/equipment policy type. No Doctor certification gate — the Banker
  sells life/medical directly (`_action_sell_insurance`, turn.py:840).

## Part A — Industrial / Equipment Insurance (#196)
1. Add `policy_type == "industrial"` to `InsurancePolicy`. It covers a specific
   capital item (add `covered_item_id: str | None`) OR the holder's whole
   capital fleet — pick per-item to keep pricing legible; premium scales with
   the insured item's catalogue cost.
2. **Payout on destruction:** when `_process_equipment_failures` destroys a unit
   that has a valid industrial policy, the Banker pays the holder a claim
   (fraction of item book value — propose 0.6–0.8, tune in sim) instead of the
   holder eating the loss. The failure-roll code already special-cases insured
   units for the *probability*; extend it to emit a *claim* on destruction.
3. Premium pricing: per-season premium as a % of insured book value; must be a
   losing proposition for the Banker only if failures are unlucky (actuarially
   ~fair + margin). Expose in the existing sell/buy/manage insurance flows and
   the insurance UI — do not invent a new action verb.

## Part B — Doctor certification gate (#19)
The issue: high-value policies require a Doctor to certify the risk before the
Banker can issue. Model it as a lightweight prerequisite, NOT a new heavy wizard:
1. Life and medical policies above a premium/coverage threshold (propose:
   any medical policy, or any policy covering > N heads) require an active
   **certification** from the Healthcare island before `SELL_INSURANCE` completes.
2. Certification = a cheap Doctor-side action producing a short-lived token
   (e.g. `HealthCertification(holder_id, expires_at_tick)`), consumed at issue.
   Creates a real Doctor→Banker revenue/dependency loop (Doctor charges a
   certification fee; Banker can't underwrite big medical risk without it).
3. Keep it optional-by-config if it risks deadlocking all-AI sims — gate behind
   a constant like `INSURANCE_CERTIFICATION_REQUIRED` defaulted per sim outcome.

## Verification bar
- Full pytest green + new tests: industrial policy payout on failure; premium
  charged; certification required above threshold and blocks issue without it;
  certification fee flows Doctor←holder.
- **Same-seed 80g×4 sim (seeds 42,1,7,99) before/after**, report role-share
  deltas. Gate: no role moves > ±2σ from the current baseline (Farmer 12.0 /
  Miner 14.7 / Transporter 12.4 / Educator 16.6 / Banker 15.9 / Manufacturer
  15.7 / Doctor 12.8 — NOTE this baseline shifts if PR #212's expertise floor
  merges first; re-baseline against whatever is on pre-release at build time).
  Bankruptcy must stay ~0%. Industrial insurance should give the Banker a new
  revenue line without spiking its share.

## Non-goals
- No reinsurance, no premium-financing, no multi-peril bundling.
- Don't touch the life/medical pricing that already exists beyond adding the
  certification gate.
