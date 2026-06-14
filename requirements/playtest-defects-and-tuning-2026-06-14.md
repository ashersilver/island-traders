# Brief — Playtest defects + tuning (post-v0.1.3, 2026-06-14)

**Suggested owner:** Codex (engine / economy / AI / turn-orchestration).
**Base off:** current `origin/pre-release` (`0.1.4-dev.2026-06-14.1`).
**Source:** live playtest, room `d43c464b` ("Trading Hole"), v0.1.4-dev.2026-06-14.1,
3-year game; full game log attached to the session. Maintainer observations folded in.

This bundles **two defects** (one P0/blocking, one recurring) and **three tuning
items**. Keep them as separate commits/PRs where practical so each is judgeable
and revertible. One tracking GitHub issue covers the batch (`playtest`,
`area: economy`, `area: workforce`).

---

## DEFECT 1 (P0 — blocking) — Productive islands lose their workforce → no Oil → chain-wide food crisis

**Symptom (maintainer):** "If an AI plays Mining, no Oil gets produced and the game
dries up. Agriculture can't produce Food and the rest of the dynamics get lost in
the food crisis."

**Confirmed in the log.** Across the entire 3-year game, **zero Oil, Ore, or Metal
was ever produced** (`grep 'Produced: .*(Oil|Ore|Metal)'` → no hits). End-of-game
leaderboard active-worker ratios:

| Role | Active/total workers | Eff | Risk profile |
|---|---|---|---|
| Educator (Professa) | 50/50 | 45.5% | **0% risk** |
| Doctor (Hippocrates) | 50/50 | 20.0% | **0% risk** |
| Banker (Goldman) | 50/50 | 20.0% | **0% risk** |
| Manufacturer (Forge) | **4/40** | 18.8% | 5% fatal / 10% injury |
| Transporter (Cargo) | **1/37** | 30.0% | 3% / 7% |
| Farmer (Agricola) | **5/32** | 37.2% | 4% / 8% |
| **Miner (Digger)** | **0/36** | **0.0%** | **8% fatal / 14% injury** |

The split is exact: **the four roles carrying `WORKPLACE_RISK` are hollowed out;
the three zero-risk roles keep a full workforce and top the board.** 53 worker
fatalities were logged; the Miner reached **0 active workers / 0% efficiency** and
produced nothing → no Oil. The Farmer needs **1 Oil per Grain/Produce run**
(`FARMER_SEASONAL_CONVERSION`), so no Oil → no Grain/Produce → no Food → the chain
starves. This is the cascade.

### Root causes (file:line)

1. **`WORKPLACE_RISK` is too punishing and applied only to producers.**
   `island_traders/constants.py:776-784` — Miner `{injury 0.14, fatality 0.08}`,
   Farmer `{0.08, 0.04}`, Manufacturer `{0.10, 0.05}`, Transporter `{0.07, 0.03}`;
   Educator/Banker/Doctor all `{0.0, 0.0}`. An **8%/season fatality rate compounds
   to a gutted Miner workforce** over a 12-season game even before the 14% injury
   (absent-this-season) drain. The asymmetry hands a structural advantage to the
   three safe roles (see also Tuning 2 / win-rate spread).

2. **No AI replacement-training.** `island_traders/engine/ai.py` has loan,
   insurance-*offer*, product-line, and recapitalize logic, but **no training
   planner** — there is no path by which an AI replaces dead/retired skilled
   workers. In the log, every training request came from
   Farmer/Educator/Banker/Transporter professions; **no Miner / OilExtractionWorker
   / MiningTechnician was ever trained.** So as skilled miners die, efficiency
   decays toward the unskilled floor (~20%) and then to 0 when the active pool
   empties. The AI needs to detect skill deficits in its *production-critical*
   professions and file training requests (it already computes
   "skill deficits against your staffing plan" — wire that to action).

3. **AI producers don't carry insurance.** Only `_ai_offer_insurance`
   (`ai.py:435`, Banker side) exists; there's no AI *buy* path, so high-risk roles
   never mitigate fatalities (Life insurance reduces effective fatality_rate —
   `constants.py:818`). High-risk AI roles should buy Life/Medical insurance when
   solvent.

### Asks
- **Re-tune `WORKPLACE_RISK` down** to survivable levels (suggest halving fatality
  rates and capping the compounding, e.g. Miner ≤ 0.04 fatal / 0.10 injury), and
  consider a small non-zero baseline for the "safe" roles so the productive roles
  aren't uniquely penalized. Re-run calibration after.
- **Add an AI training planner**: when a production-critical profession is below
  its staffing plan and the island can afford it, file a training request (reuse
  the existing deficit computation + `turn.py` training-request path).
- **AI buys insurance** for high-risk roles when solvent (pairs with the existing
  Banker offer path).
- Verify injured-worker "absent this season" accounting isn't *also* permanently
  shrinking the active pool (4/40 active is extreme for injuries alone — confirm
  injured workers actually return).

### Acceptance
- A 1000-game sim shows **Oil/Ore/Metal produced > 0 in the large majority of
  games**, no role trending to 0 active workers, and the food chain not collapsing
  (Food consumed≈produced, no mass starvation in liveness telemetry).
- Win-rate spread improves (the three safe roles stop dominating purely on
  workforce survival — see Tuning 2).

---

## DEFECT 2 (recurring) — Timed season "stops trading" well before the countdown ends

**Symptom (maintainer, recurring):** "This game stopped trading with ~180 seconds
to go again — we must get to the bottom of it." (Earlier partial fix: #123 timer
re-sync; the *trading-stops-early* problem persists.)

**Two candidate root causes — please instrument to disambiguate before fixing:**

- **(H1) Season advances when all turn-threads finish, bypassing the timer.**
  Parallel mode (`app.py:1465`) runs each player on its own turn-thread; the
  season timer (`_season_timer`, `app.py:3633`) only *force-ends* / drives the UI
  countdown — it does **not** hold the season open. The mark-ready path correctly
  guards timed seasons (`app.py:3786-3800`, `season_timer_end <= 0`), but if the
  underlying turn manager advances the season once **all** threads (all AI + any
  ready humans) complete, a timed season can flip early with the countdown still
  showing time.
- **(H2) AIs finish their turn early and go inert, so the market dies for the rest
  of the human's countdown.** If AI players complete and stop posting/answering
  bids and asks, a human still inside the timed window has **no counterparties** —
  "trading stopped" = market went quiet, not necessarily that the season ended.
  This fits "~180s to go" (AIs done early in a longer-than-120s season).

### Asks
- **Add timestamped server logging** around season start, each player-turn
  completion, `_season_timer` fire, `_delayed_interrupt`, and `season_timeout`
  broadcast (epoch + `season_timer_end`), so a single repro shows whether the
  season *ended* early (H1) or merely *went quiet* (H2). The attached turn log has
  no wall-clock; we need that to close this.
- If **H1**: in a timed season, keep the season open until `season_timer_end`
  even when all turns have completed (idle/park loop), so humans can keep trading.
- If **H2**: keep AI players responsive to new bids/asks for the remainder of a
  timed season (re-engage on market events), or document that AIs trade only
  during their turn and adjust the UX expectation.

---

## DEFECT 3 (frontend — Claude-owned) — season countdown freezes while a native dialog is open

**Symptom (maintainer):** "Every time an alert appears on the screen the timer
stops — the timer should continue."

**Root cause (confirmed).** The season countdown is driven by
`setInterval(updateSeasonTimerUI, 250)` (`server/static/index.html:4534`), and
`updateSeasonTimerUI` recomputes remaining time from the server epoch deadline
each tick (`remain = max(0, round((seasonTimerEnd − effectiveNowMs())/1000))`,
index.html:4541). The remaining alerts/dialogs are **native blocking calls**
(`alert()`, `confirm()`, `prompt()`) which halt the JS main thread, so *no*
`setInterval` can fire while one is open → the countdown visually freezes.

**Not a server problem.** `seasonTimerEnd` is an epoch deadline; the season still
ends on schedule server-side, and on dismissal the next tick snaps the display to
the correct (lower) value. The bug is purely the *visual* freeze of a blocking
dialog (distinct from the deliberate host-pause freeze at index.html:1270, and
distinct from DEFECT 2).

**Native-dialog sites to replace** (index.html): `prompt()` for training
counter-offers (2618, 2620); `confirm()` for leave (1791); `alert()` for errors /
guarantee-price explainer / log download (1664, 1692, 1778, 1786, 1798, 2045,
5513, 5520, 5534).

**Fix.** Replace blocking `alert/confirm/prompt` with the app's existing
non-blocking custom modal/toast pattern so the event loop (and the countdown)
keeps running while a message is on screen. **Frontend-only; Claude owns this** —
listed here so the batch is complete. Does not need Codex.

---

## TUNING 1 — Training food demand is ~10× the per-capita base rate

**Maintainer:** "The additional food requirement for training is 1×Food per
trainee per season, which is much higher than the food requirement for the base
population."

**Confirmed.** `STAFFING_FOOD_PER_STAFF_PER_SEASON = 1.0`
(`constants.py:766`) drives the campus load ("+N Food demand", `turn.py:2094`).
Base population eats via the kitchen basket: `PEOPLE_PER_MEAL = 10` fed per
`food_per_season = 10` (`constants.py:39,46`) → **0.1 Food/person/season**. So a
trainee on campus costs **10× a normal resident's food** — and a food-starved
island hosting 9–11 trainees (seen in the log) takes a +9–11 Food hit it can't
cover. **Ask:** bring the per-trainee campus food closer to the per-capita base
(e.g. ~0.1–0.25 Food/trainee/season, or justify the premium). Note
`TRAINEE_FOOD_ACCOM_PER_SEASON = 5.0` is a *Dp* fee (`constants.py:708`) — distinct
from the *Food-unit* demand above; both exist.

## TUNING 2 — Win-rate spread + money supply (carried from v0.1.3 calibration)

Baseline at v0.1.3 (`--games 1000 --seed 42`): Farmer 20.3 / Miner 17.9 /
Transporter 15.8 / Banker 13.9 / Doctor 13.6 / Educator 10.4 / **Manufacturer 8.1**;
avg wealth tight 3106–3623 Dp; money supply 10,500 → 5,816.8 (**−44.6%**). Target
≈ 14.3% each. **Note:** Defect 1's casualty re-tune will move these numbers (the
sim's hot Farmer/Miner are the *opposite* of the live game, where they collapsed —
reconcile after fixing Defect 1, then re-tighten). Money-supply contraction is a
known faucet item: evaluate a small activity-linked stimulus, a higher household
re-spend propensity, or auditing the `MARKET_MAKER_SPREAD = 0.08` sink. Change one
lever at a time; report before/after win% + money supply.

## TEST AFFORDANCE — `startfood=N` join parameter (helps isolate tuning)

**Maintainer:** during testing, let Agriculture start with e.g. 200 Food so food
production doesn't cloud the test. Proposed: a join-time URL parameter, e.g.
`?role=Farmer&startfood=200`, that seeds a joining player's starting inventory for
that resource. Scope it as a **test/debug affordance** (guard behind a flag so it
can't be used in a real game). **This is small and frontend/server-side — Claude
can build it directly to unblock testing** rather than waiting on this brief; noted
here so Codex knows it exists.

---

## Handoff
APP_VERSION bump + RELEASE_NOTES per merge. Defect 1 is the priority (it makes
solo/AI-mixed games unplayable). Hand off per defect/tuning item with
"branch X at commit Y — ready to integrate" + before/after calibration tables; the
integrator (Claude) re-runs an independent `--games 1000 --seed 42` before merging.
