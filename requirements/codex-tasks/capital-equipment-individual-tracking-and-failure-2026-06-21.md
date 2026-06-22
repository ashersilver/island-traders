# Brief — Individual capital tracking + #188 failure model + generic spares (2026-06-21)

**Suggested owner:** Codex (capital/economy). **Relates to:** #185 (order form, mockup
updated), #188 (machinery failure probability), #130/#124 (durable capital + warranty/
failure), #51 (air freight). **Base off:** current `origin/pre-release`.

## Why

The #185 order form and #188 failure model require capital to be modelled **per
individual unit**, failing on #188's **per-quarter Weibull** schedule, carrying the
**conditions chosen at purchase**, and backed by a **generic, non-tradable Spares** good
that Manufacturing produces and that **travels with the equipment on delivery**. The
engine today models capital as aggregate counts with FIFO matching and a once-a-year
age-*bucket* failure roll — it cannot express any of the above.

## Current state (ground truth)

- **Constants** (`island_traders/constants.py:498-513`): `DEFAULT_MAINTENANCE_FRACTION=0.03`,
  `EQUIPMENT_WARRANTY_ANNUAL_RATE=0.20`, `EQUIPMENT_FAILURE_PROB_BY_AGE_YEAR={1:.05,2:.15,3:.40}`,
  `EQUIPMENT_FAILURE_REPAIR_FRACTION=0.50`, `EQUIPMENT_REPAIR_SHIP_FREIGHT=1`,
  `EQUIPMENT_REPAIR_AIR_FREIGHT=2`.
- **Player capital state** (`models/player.py:171-194`): `capital_inventory` (counts),
  `capital_acquired_ticks` (per-unit tick lists), `capital_in_transit`
  (`{item_id, arrives_at_tick}`), `unmaintained_capital`, `capital_warranties` (counts),
  `failed_capital` (counts), `capital_repair_in_progress`. Methods `add_capital`,
  `add_capital_warranty`, `mark_capital_failed`, `complete_capital_repair`,
  `remove_capital`, `effective_capital_inventory`, `deliver_in_transit` (`:265-342`).
- **Engine** (`engine/game.py:481-748`): `_process_capital_maintenance` (FIFO expiry →
  per-season maintenance → season-0 warranty premiums → **year-end** failures),
  `_failure_probability_for_age` (age-*year* bucket, `:631`), `_process_equipment_failures`
  (rolls only at `season == len(SEASONS)-1`, warranty-exempt, `:639`),
  `_attempt_capital_repair` (50% fee, air vs ship freight, repair-in-progress, `:707`).
- **Purchase/delivery**: enqueue at `engine/turn.py:807-817` (lease `:843-849`); arrival via
  `Player.deliver_in_transit` (`models/player.py:330`).
- **Market trades EVERY `ResourceType`** (`models/market.py:550` `for rtype in ResourceType`,
  `all_prices :129`) — so a non-tradable good needs an explicit filter, not just a new enum.
- **Production**: `PRODUCTION_RECIPES` (`constants_capacity.py:406`),
  `ProductionRecipe(role, output, inputs, *_per_unit, description)`.
- **Persistence**: serialize at `engine/game.py:~948`, load + `_migrate_capital_in_transit`
  at `:1154`; server payloads `server/app.py:2125-2192`.

## Scope

### 1. #188 failure probabilities + roll cadence (smallest first slice)
- Add `EQUIPMENT_FAILURE_PROB_BY_QUARTER: dict[int,float]` Q1..Q20 from #188 (0.0470 →
  0.1902); for age > Q20 hold the last value.
- Replace `_failure_probability_for_age(age_seasons)` with a per-quarter lookup:
  `quarter = age_seasons + 1`, clamp to the table.
- **Move the failure roll to every season** (per quarter) using each unit's current quarter,
  instead of the single year-end roll. *Behavioural change — flag for calibration.*
- Change `EQUIPMENT_FAILURE_REPAIR_FRACTION` 0.50 → **0.35** (the "$35 per $100" basis from
  #188); repair fee = 35% of the unit's purchase value.
- Add disaster/sabotage **multiplier hooks** (`failure_prob * disaster_mult * sabotage_mult`),
  default 1.0, set by events/strikes. Stub at 1.0 with clearly-named seams.

### 2. Per-unit capital tracking (core refactor)
- New `CapitalUnit` dataclass: `unit_id`, `item_id`, `acquired_tick`, `purchase_value`
  (basis for repair fee + warranty), conditions-at-purchase `maintenance_term_years`,
  `predictive_maintenance: bool`, `guarantee_seasons` (=1, per resolved #185 decision),
  `warranty: bool`, `spares_attached: int`, `expedited_eligible: bool`; runtime `status`
  (in_service | unmaintained | failed | repairing) + `repair_completes_at_tick`.
- Store `Player.capital_units: dict[str, list[CapitalUnit]]`; derive `capital_inventory`
  counts and `effective_capital_inventory()` from units so downstream capacity/production
  code keeps working (keep compatibility accessors).
- Rewrite `add_capital` / `mark_capital_failed` / `complete_capital_repair` /
  `remove_capital` / `add_capital_warranty` and the game.py maintenance/failure/repair
  routines to iterate **units** (age + conditions per unit) rather than counts + FIFO.
- **Migration**: synthesize units from existing `capital_inventory` + `capital_acquired_ticks`
  (warrantied per `capital_warranties`, failed per `failed_capital`, default conditions) in
  the load path; extend the existing migration helpers.

### 3. Conditions captured at purchase → delivery
- Extend `capital_in_transit` entries with an `order` payload:
  `{maintenance_term_years, predictive_maintenance, guarantee_seasons, spares_kits,
  expedited_eligible, financing, purchase_value}` sourced from the #185 form.
- Populate it at the purchase enqueue (`turn.py:807-817`) and via a new server order endpoint.
- `deliver_in_transit` builds the `CapitalUnit` from the order payload on arrival **and
  transfers attached spares** from Manufacturer → buyer.

### 4. Generic, non-tradable Spares (manufacturing + transfer)
- Add `ResourceType.SPARES = "Spares"` — **one generic spares good**, not per-item.
- Add `ProductionRecipe(role="Manufacturer", output="Spares", inputs={...}, *_per_unit=...)`
  (e.g. Metal + labour) so spares are produced with the normal labour/input machinery.
- **Non-tradable**: introduce `NON_TRADABLE_RESOURCES = {ResourceType.SPARES}` (or a
  `TRADABLE_RESOURCES` allow-list) and replace every `for rtype in ResourceType` /
  `all_prices` enumeration in `market.py` (`:129`, `:550`), AI trading (`engine/ai.py`),
  valuation, and `resource_flow` so Spares never gets an order book/price and AI never
  trades it. **Audit all `ResourceType` iterations.**
- Spares ordered with equipment (`spares_kits`) are reserved from / produced by the
  Manufacturer at order time and transferred to the buyer **on delivery** (→ `spares_attached`).
  Define behaviour when the Manufacturer lacks spares at delivery (back-order vs manufacture).

### 5. Repair flow with spares
- `_attempt_capital_repair`: fee = 35% × `purchase_value`. If the unit has `spares_attached`
  (or the buyer holds generic Spares), **consume 1 spares → −50% repair cost**; otherwise the
  Manufacturer manufactures spares at **+50%** at failure (the "+50% if manufactured at
  failure" term). Same-season air repair still requires `expedited_eligible` + spares +
  cargo-aircraft air-freight capacity (#185/#51).

### 6. Maintenance/warranty pricing alignment (follow-up, ties to #188 table)
- Replace the flat `EQUIPMENT_WARRANTY_ANNUAL_RATE=0.20` premium with the #188 **term table**
  (Baseline vs Predictive Maintenance, per $100 of `purchase_value`, scaled). The
  `predictive_maintenance` flag picks the cheaper column. Can land after the failure/spares core.

### 7. AI, server, UI, persistence
- **AI** (`engine/ai.py:424-434, 725-920`): choose maintenance term/predictive, spares kits,
  warranty per unit; produce Spares as Manufacturer; never trade Spares.
- **Server** (`app.py:2125-2192`): per-unit capital payload (quarter/age, conditions, spares,
  status) + new #185 order endpoint.
- **UI** (`static/index.html`): wire the #185 order form to the endpoint; show per-unit /
  spares / quarter in capacity panels; update spectator payload.
- **Persistence** (`game.py` serialize/load): serialize `capital_units` + Spares; migrate
  old saves.

## Risks / calibration
- The per-quarter roll fires 4×/year vs the old annual roll → materially more failures.
  Re-run `--games 1000 --seed 42`; expect Manufacturer repair revenue up and owner costs up;
  recalibrate #188 figures if the win-rate spread widens.
- Per-unit refactor changes the save format → migration + tests are mandatory.
- The non-tradable filter must catch **every** `ResourceType` iteration or Spares leaks into
  trade/valuation.

## Acceptance
- A unit ages in quarters and rolls failure on the #188 table (seeded test: Q12 ≈ 10.88%).
- Order conditions persist per unit from order → delivery → failure/repair.
- Manufacturer produces Spares; Spares never appears in any market book/price/AI trade;
  spares transfer with equipment on delivery; repair consumes spares for −50% (or +50%
  manufactured-at-failure).
- Old saves migrate cleanly; `--games 1000 --seed 42` before/after reported (win%, money
  supply, Manufacturer revenue, failure counts).
- APP_VERSION bump + RELEASE_NOTES.

## Suggested phasing
1. Constants + #188 quarterly table + repair fraction 0.35 + per-quarter roll (keep counts).
2. `CapitalUnit` refactor + migration + rewire maintenance/failure/repair to units.
3. Order conditions through transit → delivery; #185 order endpoint.
4. Spares `ResourceType` + recipe + non-tradable filter + delivery transfer + repair integration.
5. Pricing alignment (term table), AI, UI, full calibration.
