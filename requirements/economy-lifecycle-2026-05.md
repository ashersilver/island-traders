# Economy Lifecycle & Cross-Island Dependency

Status: **draft requirements** (2026-05-18)
Source: product-owner direction 2026-05-18 (AskUserQuestion decisions)
Touches: workforce model, capital model, loan engine, constants,
starting rosters/inventory, RULES.md, education/Course pipeline,
balance calibration

---

## Summary

Make islands structurally interdependent and mortal so wealth has to be
*maintained*, not just accumulated. Five interlocking mechanics:

1. **Worker lifecycle / retirement** — workers age and retire (removed);
   replacements cost time + money.
2. **Capital lifecycle** — every capital item has a service life (must
   be repurchased from the **Manufacturer**) and a per-season
   maintenance cost.
3. **Banker MBA gate** — the Banking Island cannot issue loans unless
   it has **≥3 Manager-band Bankers holding an MBA credential**; the MBA
   is trained via the University (2 Professors + 3 Courses, 2 seasons).
4. **Economy rebalance** — per-player starting cash ≈ **1500 Dp**;
   bigger Mining Oil and Agriculture Food starting stocks.
5. **Bootstrap seeding** — starting rosters are seeded with ages (some
   Managers/Technicians near retirement) so islands can produce from
   turn 1 but face an early replacement cliff. This is also an explicit
   **balance-tuning lever** as the model is calibrated.

### Decisions locked (2026-05-18)

| Question | Decision |
|---|---|
| Starting cash | **~1500 per player** (~10,500 total) |
| Retirement scope | **General age system**; Agriculture activated this phase; bootstrap-seed several islands with near-retirement management so they don't sit idle 2 seasons; use near-retirement seeding as a balancing lever |
| MBA model | **Credential flag on existing Banker Managers**, trained via the existing University + Course pipeline |
| Capital wear | **General**: all capital has lifespan + per-season maintenance |

### Interaction with the open release blocker (important)

The current balance blocker is Banker 54.6% / Farmer 42.5% /
Transporter & Doctor 0% (`requirements/codex-tasks/balance-calibration-2026-05.md`).
These mechanics push directly on the over-dominant roles:

- MBA loan gate + universal capital maintenance → strong **Banker**
  nerf.
- Agriculture retirement + combine replacement/maintenance → **Farmer**
  cost pressure.
- ~1500/player cash offsets the new maintenance/replacement drains so
  the weak roles (Transporter/Doctor) aren't simply starved out.

**Resequencing:** calibrating the *current* economy is wasted effort
because this feature changes it materially. The
`balance-calibration-2026-05` Codex task should run **after** Phases A–D
below land (or at minimum be re-baselined against them). This is noted
in that brief's follow-up section.

---

## 1. Worker lifecycle / retirement

### Model

Add to `Worker` (`island_traders/models/workforce.py`):

- `age_seasons: int = 0` — seasons this worker has existed (incremented
  in `gain_experience()` / `apply_season_work()` alongside
  `experience_seasons`).
- Retirement is reached when `age_seasons >= working_life(worker)`.

`working_life(worker)` by band (defaults — **tunable**, flagged):

| Band | Working life | Rationale |
|---|---|---|
| Manager | 40 seasons (10 y) | long professional career |
| Technician | 32 seasons (8 y) | |
| Worker (Unskilled) | 24 seasons (6 y) | |

Constants: `WORKING_LIFE_SEASONS: dict[WorkerBand, int]` in
`constants.py`.

### Retirement processing

At season roll-over (engine `Game._process_*` cycle, alongside
`_process_training_returns`): any worker with
`age_seasons >= working_life` is **removed** from the workforce (reuse
`Workforce.remove_workers`, same path as fatalities) with a
`[RETIREMENT]` log line. The seat is gone — the island must
**Recruit + Train** a replacement (cost + lead time = the dependency
and the balance pressure).

> A retiring worker mid-training (in_training) still retires on return /
> is dropped from the batch — edge case: drop from batch and log.

### Bootstrap seeding (the lever)

Starting rosters get seeded `age_seasons` so islands aren't all
identical and don't sit idle. Phase A seeds **Agriculture**:

| Worker | Seeded age | Effect |
|---|---|---|
| Farmer (Manager) | `working_life − 4` | retires end of Year 1 (≈1 yr out) |
| Horticulturalist (Technician) | `working_life − 8` | retires end of Year 2 (≈2 yr out) |

Other islands: default new-ish ages for now; the spec reserves a
per-role seeding table (`STARTING_WORKER_AGES`) so the product owner can
dial each island's early replacement cliff as a calibration knob.

---

## 2. Capital lifecycle (lifespan + maintenance)

### Model

Add to `CapitalItem` (`island_traders/models/capacity.py`):

- `service_life_seasons: int = 20` — seasons of useful life after it
  comes online (default 5 y; **tunable**). 0 / negative = never expires
  (e.g. Vault-type items if desired).
- `maintenance_per_season: float = 0.0` — Dp charged each season per
  owned unit while in service. Default rule of thumb: **≈3 % of `cost`
  per season** unless overridden.

Per-unit acquisition ticks already exist
(`Player.capital_acquired_ticks`) — reuse them to compute age and expiry
per unit; no new bookkeeping structure needed.

### Engine behaviour

- **Maintenance:** each season, before/with production, charge
  `Σ maintenance_per_season × units_in_service` from the owner's Dp.
  Insufficient Dp → the unit is flagged *unmaintained* and contributes
  **0 capacity** that season (graceful, not destroyed) + a warning.
- **Expiry:** when a unit's age ≥ `service_life_seasons` it is removed
  from `capital_inventory` (it no longer contributes capacity) with a
  `[CAPITAL EXPIRED]` log. The island must repurchase from the
  **Manufacturer** (this is the core Agriculture→Manufacture dependency
  intent, applied game-wide).

### Combine harvester

Maps to the existing **`farmer.harvester`** capital item (the combine).
Phase A override: `service_life_seasons = 8` (replace in ~2 yr) and a
visible `maintenance_per_season` (default ≈ `0.03 × 90 ≈ 3 Dp`/season,
**tunable**). Generic defaults apply to all other items.

> The Agriculture starting roster already implies a starting
> `farmer.harvester`; if it is not currently in `Farmer`'s starting
> capital, Phase A adds one already part-aged so it must be replaced
> ~Year 2 (aligned with the Horticulturalist's retirement → a real
> double squeeze that forces Manufacturer trade).

---

## 3. Banker MBA gate

### Credential

`Worker.has_mba: bool = False` — meaningful only for **Manager-band
workers whose profession is `Banker`**.

### Training the MBA

A distinct University request (not a normal profession change):

- Target = the MBA credential on existing Banker Managers (they keep the
  `Banker` profession; `has_mba` flips true on completion).
- Gate: **2 Professors** of University capacity **+ 3 Courses** consumed
  per MBA batch (class-size rule still applies for >12, but MBA cohorts
  are tiny). Manager-tier pipeline (Course-gated), **2 seasons away**.
- Reuses the Phase 1–3 plumbing
  (`_training_capacity_status`/`_consume_training_capacity`,
  `away_seasons`) with an MBA-specific branch:
  `courses_needed = 3` per batch and a `professors_required = 2`
  capacity check.

### Loan gate

`_action_offer_loan` (and the AI loan path) is blocked unless the
Banking Island's **active workforce has ≥3 Manager-band `Banker`
workers with `has_mba == True`**. Message:
`"Cannot issue loans: Banking Island needs ≥3 MBA-qualified managers (has N)."`

### Bootstrap (so Banking isn't bricked at turn 1)

Banker starting roster today is 1 Banker + 1 Analyst + 1 Clerk + 1
Unskilled. To lend from turn 1 it must start with **3 Banker Managers,
all `has_mba=True`, seeded near retirement** (per the bootstrap-lever
philosophy) so Banking can lend immediately but must train MBA
replacements within ~1–2 years or lose lending. Updates
`STARTING_WORKERS_BY_PROFESSION["Banker"]` and the age/MBA seeding
tables.

---

## 4. Economy rebalance (constants)

| Constant | Today | New (tunable) |
|---|---|---|
| `STARTING_DOLLOPS` (CLI/test) | 700.0 | **1500.0** (per player) |
| `TOTAL_STARTING_DOLLOPS` | 700.0 | **10500.0** (= 1500 × 7) |
| `DEFAULT_STARTING_CAPITAL` (server, per player) | 700.0 | **1500.0** |
| `STARTING_INVENTORY["Miner"]["Oil"]` | 4 | **8** *(bigger Oil stock — tunable)* |
| `STARTING_INVENTORY["Farmer"]["Food"]` | (absent) | **15** *(≥15 per direction)* |

> `game.py:80` derives per-player default as
> `TOTAL_STARTING_DOLLOPS / num_players`; setting TOTAL=10500 keeps
> 1500/player for any player count divisible into it. Confirm whether
> 1500/player should hold regardless of player count (recommend: yes —
> make per-player the primary constant and derive total).

---

## 5. Implementation phasing (independently mergeable)

Each phase is its own feature branch + RELEASE_NOTES section + tests.

### Phase A — Economy constants + Agriculture/Mining stocks (smallest)
1500/player cash; Miner Oil 4→8; Farmer Food →15. Zero new mechanics —
pure constant + starting-inventory change. Immediately rebalances and is
the safest first merge.

### Phase B — Worker lifecycle + Agriculture bootstrap
`age_seasons`, `WORKING_LIFE_SEASONS`, retirement removal at roll-over,
`STARTING_WORKER_AGES` seeding (Agriculture: Farmer −4, Horticulturalist
−8). Tests: ages tick, worker removed at life, mid-training edge case.

### Phase C — Capital lifecycle
`service_life_seasons` + `maintenance_per_season` on `CapitalItem`;
maintenance debit + unmaintained→0-capacity; expiry removal;
`farmer.harvester` 8-season override + starting aged combine. Tests:
maintenance charged, expiry removes capacity, repurchase path.

### Phase D — Banker MBA gate
`has_mba`, MBA training branch (2 Professors + 3 Courses, 2 seasons),
loan gate (≥3 MBA managers), Banking bootstrap roster (3 MBA managers
near retirement). Tests: loan blocked < 3 MBA, MBA training consumes 3
Courses, gate clears at 3.

### Phase E — RULES.md + calibration handoff
Document all four mechanics in RULES.md; re-baseline / hand the
`balance-calibration-2026-05` brief to Codex **against Phases A–D**.

> **Claude/Codex split (proposed):** Claude implements Phases A–D
> (engine + tests, sequential, they share `constants.py`/workforce/
> capital/turn surfaces — risky to parallelise). Codex owns Phase E
> calibration (config + balance) once A–D land, plus the RULES.md doc
> pass can be a parallel Codex docs task. Coordinate via RELEASE_NOTES.

---

## 6. Open defaults to confirm (non-blocking — sensible defaults chosen)

1. **Working-life numbers** (Manager 40 / Tech 32 / Worker 24 seasons) —
   first cut; expect calibration to move these.
2. **Maintenance basis** (≈3 % of cost/season) and **default service
   life** (20 seasons) — tunable.
3. **Mining Oil** 4→8 and **combine maintenance** ≈3 Dp/s — first cut.
4. **1500/player regardless of player count?** Recommend yes (make
   per-player the canonical constant).
5. **Retiring mid-training** worker → dropped from batch + logged
   (recommended) vs. allowed to graduate then retire.

These are flagged the same way `education-model.md` /
`medical-laboratory.md` flag tunables — calibrate after Phase A–D.
