# Brief — #49 Vaccines help avoid Flu Season (2026-06-18)

**Suggested owner:** Codex (engine: season events + production modifier +
vaccine consumption).
**Base off:** current `origin/pre-release`.
**Tracking issue:** [#49](https://github.com/ashersilver/island-traders/issues/49).
File the work as `Closes #49`.
**Pairs with:** Claude surfaces the flu state in the UI (a Winter flu banner /
per-island infection + vaccine-coverage indicator, and a "vaccinate" affordance
if one is needed). Second of {engine PR, UI PR} to merge wires the integration;
the first leaves a stub.

---

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees.** You work in the **primary checkout**
  (`/Users/ashleysilver/Documents/projects/island-traders`). Claude works in a
  **separate worktree** on a `claude/*` branch. Do not edit Claude's worktree or
  run `git reset/checkout/stash` against it. Coordinate via pushed branches +
  PRs only.
- **Branch creation.** `git fetch`; confirm current
  (`git merge-base --is-ancestor origin/pre-release HEAD`); cut a fresh branch
  off `origin/pre-release`, e.g. `codex/vaccines-flu-49-2026-06-18`. Never
  commit straight onto `pre-release` or `master`.
- **PRs only — no fast-forwards.** Every change reaches `pre-release` through a
  PR Claude merges. Do **not** push/fast-forward to `pre-release`. `Closes #49`.
  Update `RELEASE_NOTES.md` and bump `APP_VERSION` `.N` in `constants.py`.
- **Git discipline.** No `--no-verify`, no `--amend`, no force-push; new commits
  only. Run the **full** `pytest` suite before handoff.
- **Handoff.** "branch X at commit Y — ready to integrate" + a UI-stub note.

---

## The requirement (#49, verbatim)

> Introducing **Winter flu season** reducing productivity by **up to 20%**
> depending upon the strain. A single **vaccine per 20 people** of the
> population reduces the **infection rate by 80%** for one season.

So: every **Winter**, a flu strain hits all islands and cuts production by some
severity in `(0, 20%]`. An island that administers **1 Vaccine per 20
residents** (i.e. `ceil(population / 20)` doses) cuts its flu loss by **80%**
for that season. This makes the **Doctor's Vaccine** line genuinely demanded and
gives players a real seasonal decision.

---

## Existing machinery to build on (read first)

- **Per-player season events** already carry a productivity/yield modifier:
  `EventResult` (`island_traders/engine/events.py:11`) has
  `yield_modifier: float = 1.0` (plus `outage`, `damage_seasons`,
  `price_shock_multiplier`). These are drawn per island from YAML
  `EventChart`s and passed into the season as
  `event_results: dict[int, EventResult]`.
- **The season entry point** is `TurnManager.run_season(year, season_index,
  event_results)` (`island_traders/engine/turn.py:141`); `event_results` is
  built by the caller via `SeasonEventResolver` (see `engine/game.py`). Each
  player's event is read in `_run_season_sequential` / `_run_season_parallel`
  (`turn.py:330`, `:341`) and applied in `_apply_event`
  (`turn.py:315`); production consumes the yield modifier in
  `ProductionEngine.produce` (`engine/production.py:450`, which already takes an
  `EventResult`).
- **Population** lives on `Player.population` (`models/player.py:164`, default
  100). `ceil(population / 20)` is the dose requirement.
- **Vaccine** is `ResourceType.VACCINE`, produced by the Doctor
  (`BASE_PRODUCTION["Doctor"]`, `constants.py:168`) and already has consumer
  demand (`CONSUMER_VACCINE_SEASONAL_UNITS`, `constants.py:310`). Use the
  inventory give/consume helpers on `Player` to administer doses.
- **Seasons** are `SEASONS = [..., "Winter"]` (`constants.py`); the season index
  is available throughout `run_season`.

## Design / approach

1. **Constants** (`constants.py`):
   - `FLU_SEASON: str = "Winter"`
   - `FLU_MAX_PRODUCTIVITY_LOSS: float = 0.20` (max severity)
   - `VACCINE_PEOPLE_PER_DOSE: int = 20`
   - `VACCINE_INFECTION_REDUCTION: float = 0.80` (mitigation at full coverage)

2. **Strain severity (per Winter, archipelago-wide).** At the start of each
   Winter, roll one **strain severity** in `(0, FLU_MAX_PRODUCTIVITY_LOSS]`.
   Make it **deterministic for a given seed** — reuse the same RNG the
   simulation/season resolver already uses (so `--seed 42` runs reproduce). A
   handful of discrete strains (e.g. mild/moderate/severe) is fine and is easier
   to surface in the UI than a continuous float; document whichever you pick. A
   global strain (same severity for everyone) matches "flu season"; per-island
   infection variation is out of scope unless trivial.

3. **Per-island mitigation by vaccination.** For each player, during the Winter
   season, before/at production:
   - `needed = ceil(player.population / VACCINE_PEOPLE_PER_DOSE)`
   - `doses = min(needed, vaccines_on_hand)`; **consume** those doses from
     inventory (this is the demand signal).
   - `coverage = doses / needed` (0..1).
   - `mitigation = coverage * VACCINE_INFECTION_REDUCTION` (so full coverage →
     0.80 reduction; half coverage → 0.40). Document if you prefer all-or-nothing
     (only full coverage mitigates) — but proportional is the natural reading and
     rewards partial stockpiles.
   - `effective_loss = strain_severity * (1 - mitigation)`.
   - Apply `effective_loss` as a productivity hit: fold it into the player's
     Winter `EventResult.yield_modifier` (multiply by `1 - effective_loss`) so it
     **stacks** with any existing island event for that season, and production
     picks it up through the normal path (no second production code path).

4. **Where to wire it.** Cleanest is at the top of `run_season` (or where
   `event_results` is assembled in `game.py`): when `SEASONS[season_index] ==
   FLU_SEASON`, compute the strain once, then for each player compute coverage,
   consume doses, and adjust that player's `EventResult`. Keep it **additive**
   to the existing event flow. Whoever administers doses should be logged
   (the player sees "Flu season: strain −X%, vaccinated Y/Z → −W% this season").

5. **Telemetry / state.** Expose enough for the UI + sim: the season's strain
   severity, and per-player `flu_doses_needed`, `flu_doses_administered`,
   `flu_effective_loss`. Surface in the `game_state` payload (per-player block in
   `server/app.py`) and in the season event log. (Claude builds the UI banner /
   indicator against these fields.)

## Constraints & gotchas

- **AI + sim.** The rule AI and the calibrated sim drive the same season loop.
  A 0–20% Winter hit and new Vaccine demand **will move win rates** (Doctor
  should gain; everyone loses some Winter output). Re-run
  `python -m island_traders.simulation.runner --games 1000 --seed 42`, report
  win-rate spread before/after in the PR, and retune `config/event_charts.yaml`
  only if a role falls out of band. Give the rule AI a simple vaccinate
  heuristic (buy/hold doses ahead of Winter) so it isn't strictly penalised.
- **Determinism.** Roll the strain from the existing seeded RNG so seeded sims
  reproduce; don't introduce a fresh `random` without seeding.
- **Don't double-apply.** Fold flu into the existing `yield_modifier` rather than
  adding a parallel production reduction; verify a Winter with both an island
  event *and* flu composes correctly (multiplicative).
- **Consume vaccines exactly once**, only in Winter, and only up to `needed`
  (don't over-consume a stockpile). `ResourceBundle` is immutable
  (`models/resource.py`) — use the give/receive helpers.
- **Save/load.** If you persist the current strain (e.g. mid-Winter resume),
  add it to `Game` save/load (`game.py`) + a round-trip test. If strain is
  recomputed deterministically each Winter, note that instead.
- **Population source.** Use `player.population`, not workforce count, for the
  dose requirement (the spec says "per 20 people of the population").

## Tests to add (`tests/test_engine`, `tests/test_server`)

1. Winter applies a flu productivity loss within `(0, 0.20]`; non-Winter seasons
   apply none.
2. Full vaccination (`ceil(pop/20)` doses on hand) consumes the doses and cuts
   the loss by 80% (effective loss = strain × 0.2); zero doses → full strain
   loss; partial coverage scales between (per the chosen model).
3. Doses are consumed from inventory exactly once and only up to `needed`.
4. Flu stacks multiplicatively with a co-occurring island event's
   `yield_modifier`.
5. Deterministic strain under a fixed seed (same severity sequence across runs).
6. Server: `game_state` exposes the strain + per-player `flu_doses_needed` /
   `flu_doses_administered` / `flu_effective_loss`.

## Definition of done

- Winter flu strain (deterministic, ≤20%) reduces production; vaccine coverage
  (`ceil(pop/20)`, 80% at full) mitigates it by consuming doses; folded into the
  existing event/production path.
- Rule-AI vaccinate heuristic; seeded sim re-run with before/after win-rate
  spread reported (and any retune).
- New tests green; **full suite green**.
- `APP_VERSION` bump + `RELEASE_NOTES.md`; relevant docs (e.g.
  `requirements/` health/event notes) updated.
- PR `Closes #49`; one-line note on UI integration (wired vs stub).
- Hand back: "branch X at commit Y — flu/vaccine model live" with the
  `game_state` flu field names for the UI banner/indicator.
