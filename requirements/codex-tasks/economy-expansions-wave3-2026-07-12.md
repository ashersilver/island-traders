# Brief set: Wave 3 economy expansions (#42, #64, #51, #159)

**Date:** 2026-07-12 · **Repo:** island-traders (`pre-release`) · **Owner:** Codex
**Build one at a time in this order** (smallest first, and #51 depends on #43's delivery model).
Each is an independent PR with its own same-seed sim + full pytest.

**Shared verification gate (every feature):** full pytest green; same-seed 80g×4 sim
(seeds 42,1,7,99) before/after; no role share moves > ±2σ from the pre-release baseline
*at build time* (the expertise-floor merge #212 shifted it — re-baseline, don't trust the
older numbers); bankruptcy ~0%; any newly-added resource must show non-trivial
produced/consumed/traded flow (no dead lines). New `ResourceType` members go in
`models/resource.py`; recipes in `constants_capacity.py`; capital in `CAPITAL_CATALOGUE`.

---

## 1. #42 — Fertiliser (smallest; do first)
**Ask:** a Fertiliser plant + Engineer + Patent converts Oil → Fertiliser; Fertiliser
raises Grain and Produce yields.
- New `ResourceType.FERTILISER = "Fertiliser"`; BASE_PRICES entry (propose ~mid, between Oil and Produce).
- New capital `farmer.fertiliser_plant` (or `common.`): recipe Oil → Fertiliser, gated on an
  Engineer in workforce AND a Patent held (patent-gate mechanism already exists — reuse the
  educator.library pattern).
- Yield effect: consuming Fertiliser in a Grain/Produce production run multiplies output
  (propose +25–40%, tune in sim). Model as an optional input that boosts the recipe, not a
  hard requirement, so farms without it are unaffected.
- Watch: Farmer share is baseline ~12–14% and the floor merge nudged it up — don't let
  Fertiliser push Farmer past the gate. Fertiliser should be a *tradable* good the Farmer
  buys, giving the Manufacturer/Miner (Oil seller) a demand sink.

## 2. #64 — Transporter Warehousing + spoilage
**Ask:** Logistics island offers refrigerated + bulk storage for a fee; unrefrigerated Food
spoils after one season.
- Two capital items on the Transporter: `transporter.bulk_warehouse` and
  `transporter.cold_warehouse`, each adding storage *capacity* the Transporter rents to other
  islands for a per-season fee (mirror the lease/staffing fee-flow patterns).
- Spoilage: perishables (start with Food; consider Fish/Produce/Meat) held across a season
  boundary without a cold-storage contract lose a % (propose 25–50%). Implement as a
  season-boundary decay step keyed off which holders have active cold-storage coverage.
- Storage is a *service* the Transporter sells → new Transporter revenue line (its share is
  the lowest, ~12%, so this is balance-positive if tuned). Don't let spoilage cause famine
  cascades — cap decay and keep Food buyable.
- Note: warehouse *capacity* exists today ONLY for Manufacturer Spares; this is the general
  Transporter-side capability, a different mechanism.

## 3. #51 — Air Freight (depends on the #43 delivery model)
**Ask:** a freight aircraft + ≥2 trained Pilots lets some heavy capital arrive the *same*
turn it's ordered, consuming Oil + Freight, and requires freight insurance from the Banker.
Sea shipping keeps freight negligible.
- `transporter.cargo_plane` capital already exists (2-season delivery). Add: a Pilot
  profession (technical training, need ≥2 active) as the gate to operate it.
- Delivery acceleration: when a capital order's manufacturer/buyer has an operable cargo
  plane, collapse `delivery_seasons` to 0 for eligible heavy items, consuming Oil + Freight
  per delivery. This is the concrete build of #43's "cargo-aircraft-accelerated delivery"
  remaining scope — **close the air-freight portion of #43 with this PR.**
- Freight insurance: require an active Banker freight-insurance policy for air delivery
  (ties into the Wave 2 insurance work — sequence #51 AFTER the insurance brief lands, or
  stub the requirement behind a flag).
- Balance watch: same-turn heavy-capital delivery is a strong power; price the Oil+Freight
  +insurance cost so it's a real tradeoff vs waiting 2 seasons.

## 4. #159 — Lumber Mill (largest; do last)
**Ask:** Lumber mill run by 2 Forestry Technicians + a Lumber Production Foreman; any island
plants a forest (2 years to mature); raw Timber ships in one season to a mill; Lumber used in
construction + future products; mill byproducts boost Reagents yield.
- New resources: `ResourceType.TIMBER` (raw) and `ResourceType.LUMBER` (milled); optionally a
  byproduct (sawdust/pulp) feeding Reagents.
- New professions: Forestry Technician + Lumber Production Foreman (Manager band).
- Forest as a capital-with-timer: plantable by any island, matures after ~8 seasons (2y) into
  a Timber-yielding line — needs a grow-timer mechanic (the capital `delivery_seasons` /
  acquired_tick machinery is the closest existing pattern to extend).
- Mill: capital converting Timber → Lumber, gated on the two professions; Timber shippable
  (1-season) if mill is off-island.
- Byproduct → Reagents yield boost (analogous to Fertiliser→Grain in #42; build #42 first and
  reuse that optional-input-boost pattern).
- This is a multi-PR-sized feature on its own — Codex may split it (resources+professions →
  forest timer → mill → byproduct). Flag the split in the PR description if so.
