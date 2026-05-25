# Codex Task — Balance Calibration (release blocker, 2026-05-18; refreshed 2026-05-24)

**Goal:** Bring AI-only win rates back toward ~1/7 (≈14% per role) so a
point release of `pre-release` → `master` can ship. This is the single
**hard blocker** for the next release.

## ✅ Sequencing dependencies — original two satisfied; two new ones added

The two prerequisites this brief originally waited on have landed:

- **Economy Lifecycle Phases A–D** — per-player cash `700 → 1500`,
  Banker MBA loan-gate + universal capital maintenance (Banker nerf),
  Agriculture worker-retirement + combine replacement/maintenance
  (Farmer nerf), universal capital lifecycle. All merged.
- **AI Trading v1 + v2** — AI now lists offers, places bids,
  arbitrages spreads, prices off last-deal / best-offer, **plus**
  proactive Banker loan-offering with MBA reserve gate, AI borrowers
  taking loans when capital-short, AI rollover-near-maturity, AI use
  of `INVEST` mid-game for unclaimed catalogue items.

### ⏳ Additional prerequisites added 2026-05-25

Two follow-on Codex tasks landed (or briefed) after the original
calibration prerequisites were declared satisfied. **Both must land
before this calibration runs** so the tuning sees the final economy:

- **Sustenance basket model** (`claude/sustenance-basket-model`,
  merged `e2d044f`) — Grain / Produce / Meat now have non-zero demand
  (was zero); Food demand starts at population 1 (was 101). Major
  demand shift on the Farmer/sustenance side.
- **Training-staffing redesign + workshop trainee-cap**
  (`codex/training-staffing-2026-05`, merged through `409c810`) —
  per-concurrent-course staffing gates, Technical Workshop as
  mandatory minimum with a 6-trainee-per-workshop cap, new
  Technical Director profession. Changes training admission cadence
  and Educator opening capital allocation.
- **Capital-equipment lease subsystem** (`codex/capital-equipment-lease-2026-05`,
  brief at `requirements/codex-tasks/capital-equipment-lease-2026-05.md`,
  **not yet implemented**) — investing-phase and mid-game lease option
  for the Workshop (and future opt-in capital items) with 3-year term,
  annual payment in advance, 25 % buyout, posted-3yr-rate + 2 % margin.
  Changes equipment-acquisition cadence + lessor revenue stream.
- **Training UX improvements** (`codex/training-ux-improvements-2026-05`,
  brief at `requirements/codex-tasks/training-ux-improvements-2026-05.md`,
  **not yet implemented**) — Educator starts with 10 PassengerSeats;
  requester can self-supply tickets to reduce Educator fees; approval
  prompt shows full request details. Changes cross-island training
  cadence (closes Bug 1 PassengerSeats failure mode).

**Hold this calibration until both pending Codex tasks land.** Three
prior model shifts (Economy A-D, AI Trading, sustenance, training
staffing) plus the two pending shifts (lease + training UX) will all
move the equilibrium; tuning before they all settle is wasted work.

**Net:** the baseline numbers in the next section are pre-A-D,
pre-AI-v2, pre-sustenance, pre-training-staffing, pre-lease, and
pre-training-UX. **Re-run the baseline against current `pre-release`
first** once all prerequisites have merged, then tune from those new
numbers.

## Why this is urgent — last measured baseline (now stale)

The numbers below were measured on `pre-release` @ `36c74a4`,
**before** the Phase A–D economy rebalance, AI Trading v1/v2, the
training-return fix, and the WS reconnect-race fix all landed. Treat
this as the **historical baseline that triggered the brief**, not
ground truth. Your first task is to reproduce a fresh baseline against
current `pre-release` (`4e56ead`).

AI-only, 3 years/game, multi-seed (42/1/7/99, 200 games/seed),
**stale**:

| Role        | Mean Win% | Avg Wealth (seed 42, 300g) |
|-------------|-----------|----------------------------|
| Farmer      | **42.5%** | 409.8 Dp |
| Banker      | **54.6%** | 310.3 Dp |
| Miner       | 0.4%      | 71.7 Dp |
| Transporter | **0.0%**  | 40.5 Dp |
| Educator    | 1.0%      | 225.0 Dp |
| Manufacturer| 1.5%      | 143.5 Dp |
| Doctor      | **0.0%**  | 88.5 Dp |

Banker + Farmer took ~97% of all wins. Transporter and Doctor won zero
games across 800 games on every seed. Target is ~14% each.

This drifted because several large mechanical changes landed since the
last calibration without a re-balance pass: the agriculture role split
(Grain/Produce/Meat/Food + Horticulturalist), Education Phases 1–3
(Courses, Instructor, apprenticeship slot-pool + Instructor gate,
profession-dependent course duration, 75% settling ramp, itemised
training fee), the §21 balance-aware sustenance model, the
loan/insurance Banker economics, and the personnel-sidebar bundled
training UX.

**What is expected to shift in the fresh baseline** (your hypotheses
to verify, not facts to assume):

- **Banker should come down** materially. The Phase D1 MBA reserve
  gate now requires the bank to lock 50% of every loan's principal as
  its own capital (20% with ≥3 MBA Banker Managers). Capital
  maintenance also drains Banker cash via the universal lifecycle.
- **Farmer should come down** somewhat. Combine harvester replacement
  + maintenance + Agriculture-specific worker retirement (Phase B
  bootstrap) now drain Farmer cash.
- **Transporter and Doctor might still struggle** — the structural
  diagnoses in the next section still apply. AI v2 adds INVEST and
  loan acceptance, which gives them more levers, but doesn't
  manufacture demand for products no one currently buys.
- **All roles** now have higher starting cash (700 → 1500), which
  changes the early-game equilibrium and may shift relative
  trajectories more than expected.

## Important: this is probably NOT just event-chart tuning

`config/event_charts.yaml` weights tune yields/disasters. But
Transporter and Doctor sitting at **0% wins with 40–88 Dp avg wealth**
(vs Farmer 410) looks **structural** — those islands are not building
wealth at all, which event-yield multipliers alone won't fix. Likely
suspects to diagnose first:

- **Transporter**: produces Freight + PassengerSeats. Does AI demand for
  Freight/PassengerSeats actually exist post-refactor? The Phase 3
  training flow now uses Educator-supplied air tickets — did that remove
  the Transporter's main revenue? Check `_post_population_food_demand`,
  PassengerSeats demand, and whether AI ever buys Freight.
- **Doctor**: produces HealthServices + Vaccine; consumes Expertise +
  LaboratoryEquipment. After the Expertise rename + Course economics,
  does anyone buy HealthServices/Vaccine in the AI loop? Is the Doctor
  starved of Expertise inputs?
- **Banker**: 55% — the loan-interest-spread / insurance model may be
  over-powered relative to commodity producers.
- **Farmer**: 43% — the Grain/Produce/Meat→Food assembly + §21
  sustenance change may have over-valued food.

Diagnose with per-role wealth trajectories (the runner already writes
`simulation_results/run_roles.csv` and `run_prices.csv`) before
touching weights. Fixing 0%-win roles will likely need production /
pricing / AI-trading adjustments, not only `event_charts.yaml`.

## Branch

- **Base:** `pre-release` at `4e56ead` ("Merge codex/ai-trading-v2",
  2026-05-24) or later. Run `git fetch origin && git checkout -b
  codex/balance-calibration-2026-05 origin/pre-release` to start.
- **Branch name:** `codex/balance-calibration-2026-05`
  (the old `codex/sim-calibration` branch is stale/abandoned — 0
  commits ahead of pre-release, far behind; do NOT resume it, start
  fresh)
- **Target for merge:** `pre-release` — **do not merge yourself.**
  Push the branch, open a PR, and stop. Claude will review and signal
  merge timing (this is the release-blocker; the merge decision wants
  a careful Claude pass to confirm the new equilibrium before tagging
  `v0.1.0`).

## What has shipped since this brief was drafted (2026-05-18)

Mini-changelog so you don't have to do code archaeology:

- **Economy Lifecycle Phases A–D** (multiple merges) — described
  above; the structural rebalance this brief was waiting on.
- **AI Trading v1** (`4a65a9a`, 2026-05-17) — proactive bids, offers,
  arbitrage, last-deal pricing. Six new tests in
  `tests/test_engine/test_ai.py`.
- **AI Trading v2** (`87d5ffc`, 2026-05-24) — finance + invest
  lifecycle: Banker proactive loans with MBA reserve gate, AI take
  loans, AI rollover near maturity, AI use of `INVEST`. Five new
  tests.
- **UX review phases 1–6** (multiple merges, 2026-05-21..05-24) —
  almost entirely client-side; the only server change relevant to
  balance is **Finance is now hidden from market state** (the
  enum still exists; market quote / trade UI no longer touches it).
  AI v2 has matching defensive filters.
- **Training-return defect fix** (`399165e`, 2026-05-24) — self-
  trained workers now properly graduate. Before this fix the
  Educator's own workforce upgrade pipeline silently stalled, which
  would have suppressed Educator wealth in any sim covering >1 season
  of self-training.
- **WS reconnect race fix** (`ddb3151`, 2026-05-24) — server-only;
  doesn't affect AI-only sims.
- **Order override rule** (2026-05-21) — a new bid/ask **cancels**
  the player's prior orders on that resource. There is no cumulative
  depth per (player, resource) on the book. AI offer placement already
  respects this; flag if your diagnosis suggests otherwise.
- **Market matcher fix** (2026-05-21) — bids and asks cross on
  price (not exact equality) and support partial fills. AI logic
  already handles this.

**Baseline test count:** **365 passing** on `4e56ead`. Final tally
after this branch should be ≥ 365 + whatever balance-regression tests
you add (none strictly required, but a small "no role at 0% on seed
42" guard would be welcome).

## In scope

- `config/event_charts.yaml` — yield/disaster/outage weights
- `island_traders/constants.py`, `island_traders/constants_capacity.py`
  — production recipes, base prices, capital capacities, starting
  inventories (coordinate via RELEASE_NOTES if touching these; they are
  the structural levers)
- `island_traders/engine/ai.py` — AI trading/production strategy if a
  role structurally never trades a product it should. Tread carefully:
  AI Trading v1 + v2 just landed (6 + 5 tests, 11 total in
  `test_ai.py`); keep them green. Markup constants
  (`AI_OFFER_MARKUP`, `AI_ARBITRAGE_MIN_MARGIN`,
  `AI_MIN_LOAN_PRINCIPAL`, `AI_DEBT_CEILING_MULTIPLIER`) at the top of
  the file are tuning levers if AI behaviour is the root cause.
- `island_traders/simulation/runner.py` — fine to extend stats
- `tests/` — keep green; add a balance regression guard if practical
- `RELEASE_NOTES.md` — `### codex/balance-calibration-2026-05` section
  with before/after tables

## Out of scope (do not start without coordination)

- `island_traders/engine/turn.py` training/apprenticeship flow —
  Education Phase 3 (`_action_request_training`,
  `_training_capacity_status`, `_consume_training_capacity`, the
  self-training loop) plus the `claude/training-return-bug` fix that
  ensures self-trainees actually graduate. If a balance fix needs to
  touch this surface, flag it in `RELEASE_NOTES.md` and coordinate
  before merging.
- `island_traders/server/` — entire directory is Claude's domain
  (recently hardened against the WS reconnect race; don't touch the
  `_ws_lock` / `unregister_ws` plumbing).
- `island_traders/models/loan.py`, `models/insurance.py`,
  `models/market.py` matching semantics — read-only unless you find
  an outright bug; flag rather than land.
- `requirements/` specs and `RULES.md` (a separate doc-reconciliation
  task owns `RULES.md` staleness — see "Related" below).

## Workflow

1. **Fresh baseline** (the stale table above is pre-A-D + pre-AI-v2;
   you need new numbers against `pre-release` at `4e56ead`+):
   ```bash
   PYTHONPATH=. .venv/bin/python -m island_traders.simulation.runner \
       --games 1000 --years 3 --seed 42
   PYTHONPATH=. .venv/bin/python -m island_traders.simulation.runner \
       --games 200 --years 3 --seeds 42,1,7,99
   ```
   Record both win-rate tables in `RELEASE_NOTES.md` (under the
   branch's `### codex/balance-calibration-2026-05` section) before
   touching anything else — this is the "post-A-D+AI-v2 baseline" that
   replaces the historical-stale table.
2. **Diagnose** the structurally-broken roles from `run_roles.csv` /
   `run_prices.csv`. The hypotheses in "What is expected to shift"
   above are starting points — verify them rather than assume them.
3. **Fix structurally first** (production recipes, base prices, AI
   markup constants), then fine-tune `event_charts.yaml`. Iterate on
   `--seed 42`, then verify on 1/7/99.
4. **Final run:** `--games 5000 --seed 42` plus the multi-seed sweep.
   Both tables go into `RELEASE_NOTES.md` as the "post-tune" numbers.

## Acceptance criteria

- ✅ Every role mean win% within **±5pp of 14.3%** on a 1000-game
  `--seed 42` run, AND on the 4-seed sweep (42/1/7/99).
- ✅ **No role at 0%** and none above ~25% on any verification run.
- ✅ Full test suite green: `PYTHONPATH=. .venv/bin/python -m pytest -q`
  (≥ **365** — current `pre-release` baseline at `4e56ead`).
- ✅ `RELEASE_NOTES.md` has a `### codex/balance-calibration-2026-05`
  section with **three** win-rate tables: the historical-stale
  baseline (for context), the fresh post-A-D+AI-v2 baseline (your
  diagnostic starting point), and the final post-tune numbers.

## If event-chart tuning genuinely can't fix it

Don't force unrealistic weights. If a role is structurally broken,
**stop and write the diagnosis** in RELEASE_NOTES under "Known
follow-ups" and coordinate before changing core economic formulas — but
note the release is blocked until win rates are acceptable, so a real
structural fix is expected here, not a deferral.

## When to stop and hand off

Push the branch when **all** of these are true:

- A fresh `--seed 42` 1000-game run AND the 4-seed sweep (42/1/7/99,
  200g each) both satisfy the acceptance criteria above.
- `RELEASE_NOTES.md` has the new `### codex/balance-calibration-2026-05`
  section with the three win-rate tables (historical-stale,
  fresh-pre-tune-baseline, final-post-tune).
- Full `pytest` suite green (≥ 365 passing).
- Signed-off commits (`git commit --signoff`).

```bash
git push -u origin codex/balance-calibration-2026-05
```

Open a PR from `codex/balance-calibration-2026-05` → `pre-release`
with the three tables in the PR body for reviewer convenience.

**Do not:**

- Merge into `pre-release` yourself — this is the release-blocker and
  Claude wants a final read on the equilibrium before tagging
  `v0.1.0`.
- Tag `master` or push a release tag.
- Modify any file in the "Out of scope" list above without flagging
  in the PR first.

## After this lands

Once the calibration PR merges to `pre-release`, the v0.1.0 ship path
opens:

1. Claude promotes `pre-release` → `master` (separate small PR).
2. Tag `v0.1.0` on `master`.
3. RULES.md doc-reconciliation (the "Related" item below) can land
   either before or after the tag — it's a docs-only follow-up, not
   release-blocking.

## Related (NOT this task — flag separately)

`RULES.md`'s training chapter is stale vs shipped Phase 1–3 (still
describes single-season training, no apprenticeship slot-pool /
Instructor gate, no profession-dependent duration, no 75% settling,
"Tutor" not "Instructor"). This is a separate doc-reconciliation task;
mentioned here only so it isn't conflated with balance work.

## Reference

- Runner: `island_traders/simulation/runner.py` (`--games/--years/
  --seed/--seeds/--charts`, writes `simulation_results/`).
- Event chart format: `island_traders/engine/events.py`.
- Calibration rationale: `requirements/release-process.md`, README
  "Tuning the event charts".
