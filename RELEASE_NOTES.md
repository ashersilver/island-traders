# Island Traders Release Notes

Release notes are required before merging a feature/fix branch into
`pre-release`.

## Unreleased

### codex/economy-spread-payroll-82-83-current

Version bump: `0.1.0-dev.2026-06-11.4`

**Formula-market spread/depth and payroll calibration pass (#82, #83).** The
central formula market now quotes a bid/ask spread around the dynamic reference
price and has finite per-resource, per-season buy/sell depth, so player-posted
orders can compete with the infinite market maker instead of being undercut by
frictionless liquidity. Formula-market stock is now separated from player
asks, so a central-market buy cannot consume escrowed player inventory without
paying the seller. Active home workers now draw per-season payroll by band
(Worker, Technician, Manager), excluding trainees and contracted-away staff;
shortfalls are logged without adding layoffs in this pass.

**Verification.** Added focused regressions for market-maker bid/ask pricing,
finite depth reset, player-ask isolation, payroll band charging, payroll
exclusions, and payroll shortfalls. Full suite: 669 passed. Calibration sanity
(`--games 1000 --seed 42`): Farmer 3.8%, Miner 19.4%, Transporter 23.6%,
Educator 15.5%, Banker 15.1%, Manufacturer 5.8%, Doctor 16.8%. Mean money
supply closes at 4,954.8 Dp from a 10,500.0 Dp opening (-52.8%, -462.1
Dp/season), so the economy remains a net sink; the payroll bands were trimmed
to 0.25/0.5/1.0 Dp after an initial smoke landed at -60.4%.

### claude/ui-tiled-log-disasters

Version bump: `0.1.0-dev.2026-06-11.3`

**Modular layout, log filtering, and disaster pop-ups.** The dashboard is now
customisable without a full re-tiling:

- **Hide/collapse panels + presets.** A new **▦ Layout** header menu hides the
  left sidebar, right info column, and/or the game log, with four presets (Full,
  Hide log, Trader, Focus). The chosen layout persists per browser
  (`localStorage`).
- **Game log: hideable + filterable.** The log can be hidden entirely, and a
  filter bar (All / My island / Trades / Events / Training) shows only the lines
  in a category. Categories are derived per line; "My island" reuses the
  existing relevance highlight. Filter choice persists.
- **Disaster pop-ups.** Droughts, floods, outages, and other disruptive events
  now raise a modal describing the **problem** (event name), the **impact**
  (yield %, outage, any price shock), and the **duration** (damage seasons), with
  a "don't pop these up" opt-out. The `season_events` payload now carries
  `damage_seasons`, `price_shock_resource/multiplier`, and a `disruptive` flag.

### claude/p7-net-worth-panel-86

Version bump: `0.1.0-dev.2026-06-11.2`

**Net-worth breakdown panel (P7 / #86).** New `Player.wealth_breakdown()`
decomposes the win-condition score into signed drivers — treasury, inventory,
equipment (capital book value), loans receivable, bank debt, shareholder loans
— that sum to exactly `total_wealth()` (now implemented in terms of it, so the
panel and the score can never disagree). Surfaced three ways: a `wealth_breakdown`
object in the server player payload; a click-to-expand breakdown under "Island
Value" in the dashboard (`static/index.html`); and a decomposed "Net Wealth"
block in the CLI player summary. Reporting only — no scoring changes — so it is
independent of the P1/P2/P3 economy rebalance.

### codex/farmer-manufacturer-ai-29

Version bump: `0.1.0-dev.2026-06-11.1`

**Farmer / Manufacturer AI strategy gaps (#29).** Manufacturer AI now keeps the
demand-scored product-line chooser on the human-demand path, weights live bids
as immediate demand there, and treats Freight as a procurement need rather than
a reason to avoid an otherwise viable Metal/Oil product line. Farmer AI now
uses selected-output production for visible human Food/Meat demand when it has
the matching capital and ingredients. Farmer reserve-listing heuristics were
tested and deliberately left out after the simulation smoke showed they
throttled the food basket.

**Verification.** Added regressions for Farmer selected-output Food packaging
and Manufacturer procurement of a visible human-demand line. Focused AI suite:
23 tests passing. A 100-game seed-42 simulation smoke matches the #72 base
balance profile, so this branch does not pre-empt the #73/#82/#83 measurement
and rebalance sequence.

### claude/b1-b2-liveness-metrics-73

Version bump: `0.1.0-dev.2026-06-10.7`

**Dynamic supply-chain liveness metrics (B1/B2, #73 — completes the issue).**
A new `ResourceFlowTelemetry` (`engine/telemetry.py`) records, per resource:
units **produced**, **consumed** (production + kitchen inputs), and **traded**
(formula market, order-book fills, and peer deals), plus an input-**starvation**
count (production attempts that stalled on a missing input). It is attached to
the Market + ProductionEngine in `Game.setup()` and surfaced on
`GameSummary.resource_flow`; the simulation runner aggregates across games,
prints a liveness table (flagging resources that are consumed/traded but never
produced, and the worst starvations), and writes a `*_flows.csv`. Default
`None` everywhere, so live play and direct-construction unit tests pay nothing.
Note: "consumed" is intermediate/producer demand only — population sustenance is
a separate sink and is *not* counted here.

**Findings (`--games 1000 --seed 42`):**
- **The trading game barely trades.** Primary commodities are produced in bulk
  but almost never change hands: Grain 243k produced / **0 traded**, Produce
  186k / 0, Fish 137k / 0; the highest traded item is Freight at 3.2k vs 169k
  produced. The dominant AI strategy is autarkic self-production with output
  hoarded as inventory wealth.
- **End products are economically inert** (produced, never consumed *or* traded):
  Finance 146k, HealthServices 118k, PassengerSeats 56k, Courses 45k, Vaccine
  27k — all with 0 consumed / 0 traded. Empirical confirmation of review D3
  (no final demand) and motivation for P1 (spread/depth → peer trade) and P3.
- **Zero input starvation across all resources** — supply chains are live; the
  original Reagents-style "producible but never produced" gap is closed.

### claude/money-supply-instrumentation-73

Version bump: `0.1.0-dev.2026-06-10.6`

**Money-supply instrumentation (P5 / #73).** The simulation runner and
`GameSummary` now track total Dollops in circulation (every island treasury +
investor personal cash) snapshotted once per season. The runner prints an
opening/closing/net-mint summary and writes a `*_money.csv`; `GameSummary`
exposes `money_supply` for the eventual game-over panel. This is the
measurement-first step the economics review sequences before any
faucet/sink tuning — "don't tune blind."

**First finding:** over a standard 1000×3-year run the money supply *shrinks*
~45% (≈10500 → ~5700 Dp, ~−400 Dp/season), i.e. the net flow is a **sink**, not
the faucet hypothesised in D1 of `economics-review-2026-06-10.md`. The P1/P2
calibration pass should treat this as the baseline. (B1/B2 per-resource
produced/consumed/traded liveness metrics remain open under #73.)

### codex/banker-ai-lending-72

Version bump: `0.1.0-dev.2026-06-10.5`

**Banker AI originates loans (#72).** Banker AI now offers small working-capital
loans to AI borrowers with healthy debt capacity, instead of waiting until a
borrower is nearly broke. Principal is sized from borrower wealth and operating
needs, rates still come from the existing posted-funding / borrower-risk quote,
and the existing `2 × Banker` active customer-loan cap remains the hard stop.

**Verification.** Added AI tests for normal all-AI loan origination, issue-time
rate/bookkeeping, and cap behavior. A 5-game smoke that previously produced
zero customer loans now produces 6 customer loans per 3-year game, with 2 active
at the end under the one-Banker cap.

### codex-engineer-specialisation-75-76-78

Version bump: `0.1.0-dev.2026-06-10.4`

**Engineer specialization + combined science training bundle (#75, #76, #78,
#24).** Extends the science/Reagents branch with #78: Engineer base training is
now 3 seasons, and players can add a fourth consecutive specialty season or
send an existing Engineer back for a 1-season return course. Engineer
specialties are stored on workers and preserved through save/load; each Engineer
holds at most one specialty, with retraining replacing it.

**Specialty effects.** Active Industrial Engineers add +2 capacity to every
product line; Mechanical Engineers extend capital service life by 25% and count
as one Technician of labour relief; Electrical Engineers add +5 percentage
points of workforce efficiency; Chemical Engineers reduce Oil inputs by 20% and
add +2 Reagents capacity to Reagents producers. Specialty effects only count
while the Engineer is active, and each island stacks each specialty at most
twice.

**Training and balance sanity.** Science-track training now consumes Reagents
per course-season, so a base Engineer costs 3 Reagents per course, a first-time
specialized Engineer costs 4, and a return specialty course costs 1. Full suite:
655 passed. Calibration sanity (`--games 1000 --seed 42`): Farmer 3.7%, Miner
19.8%, Transporter 24.9%, Educator 20.0%, Banker 6.2%, Manufacturer 5.9%,
Doctor 19.5%. Educator did not need another #76-specific output trim; broader
economy balance remains a separate measurement-first pass.

### codex/meat-orphan-74

Version bump: `0.1.0-dev.2026-06-10.3`

**Meat orphan resolved (#74).** Confirms Option A: Farmer already has a real
Livestock Barn Meat line that converts Grain feedstock into Meat, so the stale
B3 supply-chain allowlist entry is removed. Static reachability now treats Meat
as an active Farmer output instead of a known exception, so future regressions
will fail the supply-chain tests instead of hiding behind the old orphan note.

### codex-science-reagents-gating-75-76

Version bump: `0.1.0-dev.2026-06-10.1`

**Science profession set + Reagents gating (#75, #76, #24).** Adds Actuary
(Banking), Tradesman (Manufacturing), Medical Researcher, and Medical Technician
(Healthcare) across profession enum/bands/display labels, role training lists,
skilled-workforce maps, university capacities, and course durations. Banking
insurance now requires at least one Actuary on staff, Banking starts with one
Actuary so insurance is live from game start, and each issued policy charges
the Banker the 5 Dp actuarial evaluation cost. Reagents no longer
blanket-gate Educator production: Expertise and generic Courses can run without
Reagents, Patents still consume Reagents as research output, and only the
confirmed science-track professions consume Reagents during training.

**Calibration sanity.** Removing the blanket Educator input made Educator spike
to 44.5% wins on `--games 1000 --seed 42`; trimming Educator Expertise and
Patent output while keeping Course slots at 4 brought the same sanity check to:
Farmer 3.8%, Miner 20.1%, Transporter 25.0%, Educator 19.6%, Banker 6.0%,
Manufacturer 5.9%, Doctor 19.6%. This fixes the #76-specific Educator spike;
broader role balance remains a separate calibration pass.

### claude/pr-template-closes-2026-06-05

Version bump: `0.1.0-dev.2026-06-05.9`

**Process: every PR links the issue it addresses.** Adds
`.github/pull_request_template.md` (so GitHub auto-prompts for
`Closes #N` / `Refs #N`), and reinforces the rule in `CLAUDE.md` and
`requirements/release-process.md`. Requirements live in GitHub issues; PRs
reference them so the backlog self-reconciles on merge. Docs-only; no behavior
change.

### claude/spectator-by-code-2026-06-05

Version bump: `0.1.0-dev.2026-06-05.8`

**Spectator can be addressed by share code, with clearer status.** Watching a
game 404'd when the watcher pasted the 6-char join code (the state endpoint needs
the internal room id) or watched before the game started. New read-only
`GET /api/rooms/by-code/{code}` resolves a code → room metadata without joining;
`static/spectator.html` now accepts a room id **or** a code (resolved via that
endpoint), reports "waiting for the game to start…" on a pre-start 404, and lists
the players present when a name doesn't match. 641 green; `node --check` clean.

### codex/engine-bugs-2026-06-05

Version bump: `0.1.0-dev.2026-06-05.7`

**Fix 06-05 playtest engine/server regressions.** Parked Done-Trading prompts
can now be replayed live and the browser no longer resurrects stale cached
menus while the player is still parked. Farmer raw output capacity/input hints
now use the seasonal conversion table instead of the separate recipe oil model.
Lecture Halls provide Course capacity again, so Educators with Expertise can
produce Course slots. Workforce profession summaries exclude staff away on
contracts, keeping active counts consistent with production. Game state also
surfaces training-capacity rows with unavailable reasons when a profession cap
is exhausted.

### claude/market-event-push-2026-06-05

Version bump: `0.1.0-dev.2026-06-05.6`

**Push discrete market events over the WebSocket (#4).** Previously clients only
learned of market changes on the next full game-state broadcast, so an AI agent
(or dashboard) couldn't react to, e.g., a needed input becoming buyable. The
`Market` now records a `market_event` for each posted ask/bid and each fill
(`{resource, side, action, price, quantity, actor}`); the server drains and
broadcasts them after every action alongside the full state. The
`island-traders-agents` loop already consumes these (buffers them into the next
decision). Tests: `test_market.py` event emit/drain + fill. 636 green.

### claude/spectator-view-2026-06-05

Version bump: `0.1.0-dev.2026-06-05.5`

**Read-only spectator view** (`static/spectator.html`). A standalone page that
polls `GET /api/rooms/{room_id}/state?player_id=…` and renders one island's
dashboard — net worth, treasury/personal cash, workforce, inventory, what's
blocking production, the market order book, other islands' needs, and recent
activity. It never opens a WebSocket and never sends actions, so it can watch a
seat held by a human or an AI agent without disturbing it (the server keeps only
one control socket per player, so co-occupying the live seat would otherwise
hijack it). Accepts `?room=…&player=…` where `player` is a lobby player id *or*
name (resolved to the id). Served from the existing `/static` mount, so it needs
no server restart. Frontend only; `node --check` clean.

### claude/pause-timer-and-playtest-spec-2026-06-05

Version bump: `0.1.0-dev.2026-06-05.4`

**Fix: countdown kept ticking while the game was paused (#1).** The server froze
its timers on pause, but the browser countdowns (`updateSeasonTimerUI`,
`updatePreSeasonTimerUI`, the auction interval) read `Date.now()` directly and
`onGamePaused`/`onGameResumed` never froze or re-anchored them. They now use
`effectiveNowMs()` — frozen at the pause instant — and the end-epochs are bumped
forward by the pause duration on resume, so the display holds steady while paused
and continues correctly after. Frontend only; `node --check` clean.

Also logs the rest of the 06-05 playtest (game PNU61D) for Codex in
`requirements/playtest-defects-2026-06-05.md`: #2 Done-Trading/parked state gets
stuck (player can't resume trading with time left — distinct from the season-end
fix), #3 Farmer "Oil needed" display uses `PRODUCTION_RECIPES` while actual
production uses `FARMER_SEASONAL_CONVERSION` (the two disagree; the 06-04 halving
only moved the displayed number), #4 FarmingTechnician drops out of training
options mid-game.

### claude/quickseat-join-by-code-2026-06-05

Version bump: `0.1.0-dev.2026-06-05.3`

**Quick-seat URLs can now join by room code.** The `?join=NAME` URL found the
room by hashing NAME into a `pt-` id, which only matched a room created with the
paired `?room=NAME` quick-seat URL — so it could not join a game started with the
normal "Create Game" button (random id + share code). The quick-seat parser now
accepts `&code=ABC123`; when present, it joins via `join-by-code` (the room the
host actually created, and reconnects if the game has already started) instead of
the name hash. `?code=ABC123&player=…&role=…` works without a `join=` name too.
Frontend only (served fresh). Verified with `node --check`.

### claude/leave-waiting-room-2026-06-05

Version bump: `0.1.0-dev.2026-06-05.2`

**Leave a waiting room** (deregister after joining the wrong game). New
`GameManager.leave_room` + `POST /api/rooms/{room_id}/leave` remove a lobby
player before the game starts; host duties pass to the next human, and the room
is closed if no humans remain. The waiting-room screen gets a "← Leave Game"
button (visible to every seated player) that calls the endpoint, drops the
WebSocket without auto-reconnecting, and returns to the landing screen. Only
allowed in `waiting` status. Tests: `test_server/test_leave_room.py` (5).

### claude/quickseat-rejoin-2026-06-05

Version bump: `0.1.0-dev.2026-06-05.1`

**Fix: quick-seat `?join=` URLs stopped working once the game was established.**
`POST /api/rooms/{room_id}/join` (used by the quick-seat join URLs) only ever
called `join_room`, which refuses any room not in `waiting` status — so once the
auction/game started, re-opening a join URL 400'd ("Cannot join room") even
though the player's seat still existed. The endpoint now falls back to
`rejoin_room_by_name` for a running room (mirroring join-by-code), reconnecting
the player to their existing seat by name. Tests:
`test_server/test_join_rejoin.py` (2). 629 green.

### codex/playtest-defects-2026-06-04 (integrated by Claude)

Version bump: `0.1.0-dev.2026-06-04.2`. Codex engine fixes for the 06-04 playtest
defects (`233f575`), integrated onto pre-release:

- **#1 Training dispatch** rebinds a pending request to currently-active eligible
  workers (Unskilled or matching the target profession, untrained), preferring
  the originally-pinned ids and reserving across requests to avoid double-booking;
  only fails when too few eligible active workers exist. Stops requests stalling
  because the originally-chosen workers became absent (seasonal casualties).
- **#2 Repurpose** can now return a trained worker to Unskilled (the relief-valve
  direction). Educator review still surfaces requests whose pinned workers are
  absent.
- **#4 Cross-role kitchens** now appear in the capacity payload as kitchen-enabled
  Food for any island that owns one.
- **#5 Timed trading seasons** no longer end early when all humans click done —
  the season stays open until the timer expires.

#6 (market offer-book) intentionally not touched. Tests added across repurpose,
training dispatch/review, investing, and pause-game. 627 green.

### claude/farming-oil-balance-2026-06-04

Version bump: `0.1.0-dev.2026-06-04.1`

**Farming oil consumption halved** (playtest balance, defect #3). Oil inputs on
the three fuelled Farmer outputs in `PRODUCTION_RECIPES` were too high (a single
Produce line needed 5 Oil/unit — ~25 Oil to unblock a typical batch). Halved:
- Grain `10/6 → 5/6` Oil/unit
- Fish `10/3 → 5/3` Oil/unit
- Produce `5.0 → 2.5` Oil/unit

Food (Grain+Produce+Fish) inherits the reduction via its inputs. 622 tests green.

### claude/integrate-codex-llm-swagger-2026-06-03

Version bump: `0.1.0-dev.2026-06-03.1`

Integrates two Codex branches onto pre-release (.12):

**Terminal room client (`island_traders/cli/agent_client.py`)** — from
`codex/llm-room-client-2026-06-02` (b4510cb). Provider-agnostic WebSocket
client for LLM/GPT-style players. Joins or rejoins a room by code, bridges
server prompts to stdin/stdout. Entrypoint: `island-traders-agent ROOMCODE
--name "GPT Player" --server http://127.0.0.1:8001`. Commands: `/state`,
`/bid`, `/withdraw`, `/respond`, `/invest`, `/ready`, `/quit`.
Tests: `tests/test_cli/test_agent_client.py` (7).

**OpenAPI/Swagger documentation** — from `codex/swagger-api-docs-2026-06-02`
(1cf1340). Adds typed Pydantic request models (`CreateRoomRequest`,
`JoinByCodeRequest`, `JoinRoomRequest`, `AddAIRequest`, `AuctionBidRequest`)
and OpenAPI route tags (`Lobby`, `Game Flow`, `Reference`) with summaries and
descriptions throughout `server/app.py`. Docs now live at `/docs`,
`/openapi.json`, `/redoc`. Tests: `tests/test_server/test_openapi_schema.py` (3).

622 green.

### claude/supply-chain-reachability-2026-06-02

Version bump: `0.1.0-dev.2026-06-02.12`

**B3 — static supply-chain reachability tests**
(`tests/test_models/test_supply_chain_reachability.py`): cheap import-time checks
that catch the "silent bottleneck" bug class — (1) every required production
input has a producer, (2) every capacity-recipe output is actually produced by
the active model. Would have caught both the Courses-never-produced stall and
the Reagents-no-producer gap. Surfaced a pre-existing latent gap (`Meat` is
priced + has a livestock recipe but the Farmer never produces it; protein
demand is met by Fish) — documented in an allowlist for follow-up.

**Student medical insurance (per-headcount policies)**:
- `InsurancePolicy.covered_count` + `Player.medical_coverage_seats()`; medical
  policies are now sized and priced per head (`MEDICAL_PREMIUM_PER_HEAD = 8`),
  asked for in the Banker's sell-insurance action.
- Students travelling to the Education island must be medically covered, paid by
  the Education island. At training dispatch, pre-bought cover is consumed first;
  any shortfall is auto-provisioned (Education pays the per-head premium, routed
  to a Banker if present), and dispatch is held only when the Educator can't
  afford it (so training never silently stalls). Self-training needs no cover.
- Tests: `test_student_medical_insurance.py` (7); training-fee tests updated for
  the new dispatch-time premium. 615 green.

### claude/economy-rebalance-2026-06-02

Branch: `claude/economy-rebalance-2026-06-02`
Version bump: `0.1.0-dev.2026-06-02.9`

**Structural economy rebalance** (4-iteration sim-validated):
- **Transporter** massively uplifted (was 553 Dp/s vs ~1300 avg): Freight
  output 2.5→3.5×M, Seats 0.75→1.2×M; Freight price 16.5→22, Seats 18.7→24.
  Win rate 0.8%→20%.
- **Educator** output cut to match: Expertise 4.5→2.5×M, Patents 0.75→0.35×M;
  Patents price 47.5→32. Win rate 88%→22%.
- **Doctor** value-gap correction: HealthServices 31.5→18 Dp, Vaccine 36.75→22 Dp.
  Win rate 34%→21%.
- **Banker** given modest Finance production (0.5×M) for base viability. 0%→10%.
- **Farmer** staples repriced to reflect real demand: Food 13.5→18, Fish 10.8→15,
  Grain 9.45→12, Produce 12.15→15. Win rate 0.2%→2.5%.
- Residual Farmer/Manufacturer gaps are AI-strategy (supply-chain/seasonal timing),
  not pricing — flagged as Codex `ai.py` follow-up.
- 605 tests green. Full analysis in `requirements/calibration-findings-2026-06-02.md`.

### claude/shareholder-loan-to-company-2026-06-02

Branch: `claude/shareholder-loan-to-company-2026-06-02`
Target: `pre-release`
Version bump: `0.1.0-dev.2026-06-02.8`

**Mid-game shareholder loans (Phase 2b — manual lend/repay)**:
The owner can now move personal cash into their island's treasury (and back) at
any time during play, not just at the opening.
- **Lend to island** (`Finance` action group): ask for an amount, move personal
  cash → treasury, record the shareholder loan. Treasury goes up; personal cash
  goes down; the island's liability goes up (subtracted in `total_wealth` →
  net-worth-neutral).
- **Repay shareholder loan** (`Finance` action group): move treasury → personal
  cash, reduce the loan principal. Only available when a loan is outstanding and
  the treasury has funds; clamped to `min(owed, treasury)`.
- Sidebar: a **"Fund island"** row (Lend… / Repay… buttons) appears when you
  have personal cash or an outstanding loan; buttons are individually greyed when
  the relevant prerequisite is absent.
- 6 new engine tests (`test_shareholder_loan_actions.py`): accounting invariants,
  clamp logic, lend-then-full-repay restores original state. 605 tests green.

### claude/calibration-2026-06-02

Branch: `claude/calibration-2026-06-02`
Target: `pre-release`
Version bump: `0.1.0-dev.2026-06-02.7`

**Calibration sweep — chart rebalance + structural findings**:
- Retuned `config/event_charts.yaml` (moderate, non-distorted): trimmed the
  over-generous roles (Educator avg-yield 1.21→0.88, Transporter→0.95) and
  softened the over-harsh (Miner 0.53→0.92, Manufacturer 0.69→0.95, Doctor
  0.65→0.90, Farmer→1.0). Top-role win share nearly halved in sim (Educator
  88%→53%); Miner/Doctor pulled up.
- **Finding (see `requirements/calibration-findings-2026-06-02.md`):** charts
  can't reach 1/7 — the residual imbalance is structural (output value gap:
  Educator/Doctor make high-value goods, Farmer/Transporter cheap ones; Banker
  has no commodity and the AI underuses lending). Recommends a base-economy
  rebalance (output values / Banker model) **before** finer chart calibration.
  All 599 tests green.

### claude/equity-phase3-buyout-2026-06-02

Branch: `claude/equity-phase3-buyout-2026-06-02`
Target: `pre-release`
Version bump: `0.1.0-dev.2026-06-02.6`

**Equity Phase 3 — buy out the public float**: the controlling owner can now
spend personal cash to buy their island's 40% public-float shares at live fair
value. The cash leaves the game (paid to imaginary public holders, like the
auction bid); shares move `public → owner` via `CapTable.transfer`; `holdings`
mirror it. Net-worth-neutral at purchase (cash → equity at fair value); the
payoff is future growth accruing to a bigger stake.
- WS action `buy_out_float` (owner-only, clamps to the float, affordability
  check); payload gains `public_float_shares`.
- Sidebar "Buy shares…" control appears when you control the island and a float
  remains (shows available / price-per-share / affordable count).
- Tests: `tests/test_server/test_equity_buyout_float.py` (transfer, clamp,
  afford guard, net-worth neutrality). 599 green.

Backlog noted separately: partial food production on missing ingredients
(`requirements/food-partial-production-2026-06-02.md`).

### codex/kitchen-tiers-2026-06-02 (merged)

Version bump: `0.1.0-dev.2026-06-02.5`

**Kitchen tiers (Codex)**: the single 6-Food kitchen is replaced by two tiers
via per-item `KITCHEN_SPECS` + a generalised `run_kitchens`:
- **Industrial Kitchen** (`common.industrial_kitchen`, 150 Dp, opening-investment
  + buyable): **20 Food/season, no Chef**, efficient 1 / 0.5 / 0.5 recipe.
- **Manufacturing Kitchen** (`common.kitchen`): **10 Food/season** (up from 6),
  **requires a Chef**; chefs are a limited pool (one per chef-requiring kitchen).
- Kitchens idle gracefully with clear reasons ("needs a Chef" / "short on
  <ingredient>"). Ships `tests/test_engine/test_kitchen_tiers_2026_06_02.py`.

Merged on top of the lab split; the two universal capital items
(`common.industrial_kitchen`, `common.laboratory_equipment`) now sit alongside
`common.kitchen`. 595 tests green.

### claude/lab-split-2026-06-02

Branch: `claude/lab-split-2026-06-02`
Target: `pre-release`
Version bump: `0.1.0-dev.2026-06-02.4`

**Lab Supplies split** (per the 2026-06-02 brief; numbers tunable in calibration):
- **`LaboratoryEquipment` resource renamed to `Reagents`** (display "Reagents")
  across recipes, prices, inventory, AI, UI — with a save-migration so old saves'
  `LaboratoryEquipment` inventory keys fold forward to `Reagents`.
- **Reagents production moved Manufacturer → Medical Sciences (Doctor)**: the
  Doctor now makes Reagents from **Oil + Ore** (6/season), consumes Oil+Ore+
  Expertise, and sells surplus to the Educator. Removed the Manufacturer's
  Reagents product line + foundry/assembly-line capacity for it.
- **New durable capital `common.laboratory_equipment`** ("Laboratory Equipment",
  40 Dp, cash-only, 1-season delivery): soil/sample-testing kit that adds +2
  output capacity for Agriculture (Grain/Produce/Food), Mining (Ore) and Medical
  (HealthServices/+1 Vaccine). Distinct from the consumable Reagents.
- Player briefings + AI Manufacturer tests updated; the Manufacturer's
  medical/lab tests repurposed to the remaining `MedicalDevices` line. 729 green.
- (Kitchen tiers — the other half of the brief — are with Codex on
  `codex/kitchen-tiers-2026-06-02`.)

### codex/training-shared-classrooms-2026-05-29 (merged)

Version bump: `0.1.0-dev.2026-06-02.3`

**Shared training classrooms (Codex)**: same-profession + same-season training
batches now share a 12-seat classroom instead of each batch burning a fresh
Course slot. Incremental Course slots and Expertise are charged per
`(educator, profession, course-running season)` cohort, and the concurrency
gate counts distinct classrooms rather than requests. So a second 1-trainee
Engineer request in the same season rides the existing classroom at zero extra
Course cost until the 12 seats fill. Per
`requirements/codex-tasks/training-shared-classrooms-2026-05-29.md`; ships with
`tests/test_engine/test_training_shared_classrooms.py`.

### claude/starting-workforce-50-2026-06-02

Branch: `claude/starting-workforce-50-2026-06-02`
Target: `pre-release`
Version bump: `0.1.0-dev.2026-06-02.2`

**Each island starts with 50 workers + a real 50-resident population**
(2026-06-02 playtest ask):
- `STARTING_WORKFORCE` → 50 for every role. The skilled faculty/specialist
  breakdown (`STARTING_WORKERS_BY_PROFESSION`) is seeded first; the remainder
  (~40) fills as **Unskilled**, so labour/training requests for up to ~10
  unskilled workers can always be met.
- **Population bug fixed:** `Game.setup` used `TOTAL_STARTING_POPULATION //
  num_players` (= 20/island), silently overriding the intended 50. It now seeds
  `STARTING_POPULATION` (50) per island. (An earlier "set population to 50"
  change had landed on `STARTING_POPULATION`, which `setup` never read.)
- Workforce no longer scales by `7/num_players` — every island gets exactly 50
  workers regardless of player count (the old scaling, with a fixed 50-resident
  population, would have inflated small-game islands past their populace).
- ⚠ **Balance:** this is a large labour-base increase (was 4–11 workers/island);
  production capacity rises substantially. A calibration pass is warranted.
- Tests updated for the new population (sustenance math; Educator roster total).

### claude/courses-production-2026-06-02

Branch: `claude/courses-production-2026-06-02`
Target: `pre-release`
Version bump: `0.1.0-dev.2026-06-02.1`

**Courses are now produced (training-stall bugfix)**: The Educator's
`BASE_PRODUCTION` had no `Courses` entry, so an Educator spent the 5 starting
Course slots training others and could **never** make more — permanently
stalling all training (the capacity panel listed Courses as "producible" but
production never made them). Courses are now produced each season (base 4,
scaled by workforce skill / capacity so they taper if the faculty is gutted),
alongside Expertise and Patents. This also fixes the panel/reality mismatch.

### claude/playtest-fixes-2026-05-29b

Branch: `claude/playtest-fixes-2026-05-29b`
Target: `pre-release`
Version bump: `0.1.0-dev.2026-05-29.4`

**Staffing request approval — detail + counter (web)**: The Doctor-island
staffing-review modal now shows the full contract (staff × profession, duration,
fee offered, per-staff/season rate, PassengerSeats to supply, staff available)
via `request_summary`, instead of bare Approve/Counter/Reject buttons. The
counter-offer fee prompt already worked; reviewers can now see what they're
pricing.

**Education capital hint clarity**: The "Capital limits <output>" decision hint
now names the specific equipment that unblocks the output (e.g. "Needs 1×
Laboratory Equipment — 28 Dp each …") using the catalogue options the server
already computes, instead of the vague "plan a capital purchase" text.

**(Codex brief) Shared training classrooms**: see
`requirements/codex-tasks/training-shared-classrooms-2026-05-29.md` — same
profession + same season should share a 12-seat classroom rather than each batch
burning a fresh Course slot. Engine change handed to Codex.

### claude/equity-phase2b-flip-2026-05-29

Branch: `claude/equity-phase2b-flip-2026-05-29`
Target: `pre-release` (after the Codex shareholder-loans leaf merges first)
Version bump: `0.1.0-dev.2026-05-29.3`

**Equity model — Phase 2b + economy flip** (web game):
- **Two balance sheets.** A player is now an *investor* with `personal_cash`
  separate from their *island's* operating `treasury` (the engine `dollops`).
- **Auction = buying a 60% stake.** At game start the island treasury is seeded
  independently at `ISLAND_STARTING_CASH` (500 Dp); the winning bid leaves the
  investor's personal cash (paid to imaginary former owners). Cap table seated
  60% owner / 40% public float.
- **Shareholder loans (Phase 2b).** Opening capital is bought from the treasury;
  any shortfall is auto-lent from personal cash as a shareholder loan, recorded
  as a senior liability the island owes back. Net-worth-neutral by construction
  (no 60/40 leakage). 0% interest for now.
- **Win condition = net worth** (`personal_cash + Σ shares×share_price +
  loan receivables`) in the web game. Sidebar now shows Net Worth, Personal
  Cash, Island Treasury, Ownership (you % / public %), and Island Value; live
  scoreboard leads with net worth + treasury.
- Engine/CLI/sim keep their single-pool economy and `total_wealth` scoring
  unchanged (additive cap-table scaffolding only) — a calibration pass for the
  flipped web economy is queued separately.
- Model leaf `shareholder_loans.py` (lend/repay/total_owed/receivable) — Codex
  brief `codex-tasks/shareholder-loans-model-2026-05-29.md`; a Claude-side
  reference stub ships on this branch pending Codex's authoritative module.
- Tests: `test_equity_flip.py` (treasury seed, auto-lend, net-worth neutrality);
  Phase-1 `test_player_equity_fields.py`. Full suite 729 green.

### claude/playtest-fixes-2026-05-29

Branch: `claude/playtest-fixes-2026-05-29`
Target: `pre-release`
Version bump: `0.1.0-dev.2026-05-29.2`

**Training: workers only depart on approval (bugfix)**:
Requesting training from an AI Educator used to approve *and dispatch* the
workers inside the requester's own turn — the workers vanished from the island
the instant "Request Training" was clicked, before any visible approval. The
AI Educator no longer auto-responds during the requester's turn; it approves
and dispatches on its **own** turn (via `_ai_review_training_queue`), so workers
stay home and producing until the training is actually approved. Human-Educator
and self-training (train-in-place) behaviour is unchanged. Regression tests:
`tests/test_engine/test_training_dispatch_on_approval.py`.

**Quick-seat banner now dismissable (bugfix)**:
The quick-seat status banner never went away. It now auto-dismisses 8s after
quick-seat completes and is click-to-dismiss at any time.

**Daytime theme: log + other dark surfaces (bugfix)**:
The activity log (and the dependency-map SVG and "won" role card) had hardcoded
dark backgrounds that ignored the Day/Night theme, so they stayed dark in the
Bright Lagoon daytime palette. Added `[data-theme="day"]` overrides so the whole
screen follows the theme.

### claude/playtest-quick-seat-2026-05-29

Branch: `claude/playtest-quick-seat-2026-05-29`
Target: `pre-release`
Version bump: `0.1.0-dev.2026-05-29.1`

**Quick-seat playtest URLs** — new dev/playtest convenience:
Compose seven URLs (one per role) and paste them into seven browser tabs to
stand up a full game without clicking through lobby/auction/investing in each
tab. Tab 1 creates the room; tabs 2-7 join it. Each URL names the player,
auto-bids its role in the auction, and auto-submits an investment selection
(bitmap), then hands control back for Year 1 onward.

- All tabs derive the same room ID by hashing a shared room name
  (`room=Trading Hell`) client-side (cyrb53 → `pt-<hex>`), so the URLs can be
  composed before the room exists.
- `POST /api/rooms` now honours a caller-specified `room_id` for the `pt-`
  prefix only, idempotently (re-pasting tab 1 returns the existing room rather
  than clobbering seated players).
- Auction start stays manual (host clicks "Start Auction") as the natural sync
  point once all tabs are seated.
- Full design + URL parameter reference: `requirements/playtest-quick-seat-urls.md`.

**Balance — population / workforce cap**:
- `STARTING_POPULATION` 30 → 50.
- `MAX_WORKFORCE_FRACTION_OF_POPULATION` 0.80 → 0.60.
- Net effect: an island can now expand its workforce up to 0.60 × 50 = 30
  workers. `test_workforce_cap.py` updated to the new 60% expectations.

### claude/ux-staffing-2026-05-28

Branch: `claude/ux-staffing-2026-05-28`
Target: `pre-release`
Version bump: `0.1.0-dev.2026-05-28.4`

**Blocker reason visibility in training strip**: The sidebar training strip
and Personnel popup now show `blocker_reason` (why training is stalled — e.g.
"Educator lacks Expertise") with a `⚠` warning. When the requester can supply
Expertise to unblock, a hint line appears below.  "Blocked / waiting" column
added to the popup table. `can_supply_expertise` and `seasons_blocked` fields
were already in the server payload but never rendered until now.

**Medical staffing contracts** — new feature:
Any island can hire Doctors or Nurses from the Healthcare island on a
fixed-term contract (1–4 seasons). Staff travel via PassengerSeats (round-trip
= staff_count × 2 seats), are counted as extra residents at the host island
(sustenance included), and return automatically at contract end.

Backend:
- `island_traders/models/staffing.py` — new `StaffingStatus` enum,
  `StaffingContract` dataclass, `StaffingRegistry` class with full propose /
  approve / counter / reject / dispatch / process_returns lifecycle.
- `Worker.on_contract: bool` field added to `workforce.py`; excluded from
  `active_workers` while away.
- `game.py`: `self.staffing = StaffingRegistry()`, `_process_staffing_returns()`
  in the game loop, full save/load serialisation.
- `turn.py`: `TurnAction.REQUEST_MEDICAL_STAFF` and
  `TurnAction.REVIEW_STAFFING_REQUESTS` with action handlers.
- `app.py`: `_staffing_contracts_for_player()` payload helper; visiting staff
  added to sustenance `extra_residents`.
- `ws_adapter.py`: staffing actions added to `ACTION_GROUPS`;
  `REVIEW_STAFFING_REQUESTS` disabled for non-Doctor islands.
- Constants: `STAFFING_BASE_FEE_PER_STAFF_PER_SEASON = 20.0`,
  `STAFFING_FOOD_PER_STAFF_PER_SEASON = 1.0`,
  `STAFFING_MAX_DURATION_SEASONS = 4`.

Frontend (`index.html`):
- Staffing contract sidebar strip (`#s-staffing-strip`) shows active
  contracts with profession, direction (→/← other island), status, and return
  date.
- `_renderStaffingContractsSection()` adds a Medical Staffing Contracts table
  to the Personnel popup (next to the training pipeline table).

**Dependency map improvements**: `showDependencyMap()` rewritten with
quadratic bezier curved edges, per-edge arrowhead markers, and perpendicular
label offsets. Node boundaries clipped with `boundaryPt()` helper; label text
rendered with `paint-order="stroke"` for legibility on dark background.

**Training counter-offer negotiation (counter-counter)**: When the Educator
returns a counter-offer, the requester now sees an alert card in the sidebar
and can **Accept / Counter / Reject**. A counter-counter sends the request back
to the Educator (`TrainingStatus.COUNTERED → AWAITING_EDUCATOR` with the new
fee), so the two sides can negotiate across turns.
- `training.py`: `TrainingRegistry.requester_counter(batch_id, new_fee, message)`.
- `turn.py`: `_review_training_counteroffers()` upgraded from Accept/Reject to
  Accept/Counter/Reject (CLI path).
- `app.py`: async WS handler `_handle_training_counter_response()` accepts
  `approve / counter / reject / ack`, then rebroadcasts state to requester and
  Educator.
- `index.html`: counter-offer accept button sends `action: "approve"`.

**Educator campus-load display**: The Educator sidebar now shows a **Campus
Load** row (visiting trainees + contracted medical staff) with a
"+N Food/season" hint, surfacing the sustenance burden that was previously only
implicit in the meals-runway figure. `campus_load` and `visiting_staff_count`
added to the per-player game-state payload.

**Docs**: `RULES.md` gains a Medical Staffing Contracts section, a rewritten
Training Step 2 covering the counter-offer/counter-counter flow, the three new
actions (Request Medical Staff, Review Staffing Requests, Repurpose Worker),
and a corrected Leases note. `ISLAND_BRIEFINGS.md` fixes Agriculture resource
names, makes the Educator's campus-food burden prominent, rewrites the Doctor
briefing around staffing contracts, and notes staffing-driven PassengerSeats
demand for the Transporter.

**Tests:** 543 tests passing (+28 staffing model tests, +1 counter-counter
flow test `test_requester_can_counter_counter_offer`).

Version bump: `0.1.0-dev.2026-05-28.5`.

---

### claude/playtest-fixes-2026-05-28

Branch: `claude/playtest-fixes-2026-05-28`
Target: `pre-release`
Version bump: `0.1.0-dev.2026-05-28.3`

Addresses the 2026-05-28 playtest-session batch: three bugs that caused
premature season/turn-end, plus five features.

**Bug A — Hint buttons aborted the trading turn** (`buy_market` → `market_buy`):
`_HINT_OPEN_LABEL` in `index.html` used `'buy_market'` but
`TurnAction.MARKET_BUY = "market_buy"`. The server raised `ValueError` and
silently returned `END_TURN`. Fixed by renaming every occurrence in the
frontend hint path.

**Bug B — "Resume Trading" banner never appeared / seasons ended instantly**:
`submit_ready()` called `interrupt_all()` on the same HTTP thread as
`mark_player_ready()`. The player's turn thread saw `_interrupted = True`
before the park loop could engage. Fixed with a 3-second async grace period
(`_delayed_interrupt` coroutine): the turn thread parks and shows the "Season
ending soon" banner before the interrupt fires. The grace task is cancellable
if a player un-readies during the window.

**Bug C — Hint buttons corrupted sub-dialog responses**:
`_isActionPromptOpen()` returned `true` even during confirm/resource-picker
sub-dialogs, causing hint-button clicks to answer the wrong prompt. Fixed by
adding `_activePromptType` state tracking in the frontend; hint buttons only
fire when `_activePromptType === 'choose_action'`.

**Feature 1 — Training "Next" button**: Training review now offers
Approve / Counter / Skip. Skipped requests stay pending and are filtered by
tick (`TrainingRequest.last_skipped_tick`) so they don't loop in one session.

**Feature 2 — Conditions sidebar panel**: Server broadcasts a `season_events`
WebSocket message at season start with per-player yield/outage/disaster data.
Frontend renders a colour-coded "Conditions" panel in the info sidebar
(green = normal, yellow = partial, red = outage, with a ⛈ disaster banner).

**Feature 3 — Exact profession names in training display**: The training
sidebar and training-review modal now show precise role names (e.g., "Nurse",
"Farming Technician") instead of generic band labels ("Manager", "Worker").
`workforce_professions` per-profession breakdown is included in game-state
payloads.

**Feature 4 — Repurpose workers between roles**: New `TurnAction.REPURPOSE_WORKER`
action. Players pick a worker and a target profession; the worker is moved,
resetting `training_level`, `experience_seasons`, and `settling_seasons` to 0
(fresh start in the new role). Cost: 25 Dp (`REPURPOSE_WORKER_COST`).
`Workforce.repurpose_worker()` added.

**Feature 5 — Bid/Ask tight-spread auto-accept (≤2.5%)**: When a new bid or
offer lands with a spread ≤ 2.5% vs. the best counter-order, the market
auto-executes. Price priority: the order placed *first* (lower sequential ID)
sets the trade price. Self-cross guard prevents a player trading with
themselves. `Market._check_tight_spread()` runs in a loop to chain-clear
multiple matching pairs.

**Population cap raised**: `MAX_WORKFORCE_FRACTION_OF_POPULATION` bumped from
0.60 → 0.80 and `STARTING_POPULATION` from 20 → 30 (pre-existing uncommitted
tuning; included in this commit). All `test_workforce_cap` tests updated to
match.

**Tests:** all 514 tests pass. Updated `test_training_review.py`,
`test_training_ux.py`, and `test_workforce_cap.py` for the above changes.

---

### claude/event-frequency-cap-2026-05-27

Branch: `claude/event-frequency-cap-2026-05-27`
Target: `pre-release`

Implements the 2026-05-27 event-frequency-cap brief.  Caps
production-halting events at `HALT_EVENTS_PER_PLAYER_PER_YEAR = 1`
per player.  Addresses the "5 production-halting events in 5
consecutive seasons" reports (Comet 1 #9: Factory Fire →
Infrastructure Damage → Flood → Flood → Hospital Strike; AyaySir
BUG-08: Pandemic + Factory Fire + Infrastructure Damage in
consecutive seasons).

The disaster-mitigation brief already re-tiered the single Flood
event, but the other halt events (Crop Failure, Mine Collapse, Oil
Spill, Factory Fire, Pandemic, Hospital Strike, etc.) could still
stack arbitrarily.  This adds the general per-year cap.

- New `EventResult.is_halt_event` property: `outage` OR
  `yield_modifier <= 0.1`.  Soft damage (yield ~0.5) is not a halt
  and stays uncapped.
- New `EventChart.draw_avoiding_halt(rng, max_tries=3)`: re-rolls to
  dodge a halt, falling back to Normal Operations if every roll is
  a halt.
- `SeasonEventResolver` now tracks a per-player, per-year halt
  counter.  When a player has used their budget and draws another
  halt, the resolver re-rolls avoiding halts and records a
  suppression message.  The budget resets each game year.
- `resolve_all` gained an optional `year` parameter.  When omitted
  (legacy callers / unit tests) the cap is disabled — prior
  behaviour preserved.
- `Game.run` passes the year and prints any suppression messages to
  the game log (`[EVENT] Suppressed halt: ...`).

**Calibration improved.**  The 4-seed sweep band TIGHTENED from
[11.8 – 18.1 %] (previous build) to [12.8 – 16.4 %]:

| Role | Prev | After |
|---|---:|---:|
| Farmer | 11.8% | 12.8% |
| Miner | 14.4% | 13.6% |
| Transporter | 12.6% | 15.1% |
| Educator | 18.1% | 15.5% |
| Banker | 14.8% | 16.4% |
| Manufacturer | 15.4% | 13.9% |
| Doctor | 13.0% | 12.8% |

Capping halt stacking reduces the catastrophic-failure variance
that was spreading roles apart — Educator in particular came off
the 18% ceiling toward the centre.  All roles comfortably in the
[12 – 18 %] band; the distribution is the healthiest it's been.

**Tests:** new `tests/test_engine/test_event_frequency_cap.py` with
8 tests — is_halt_event classification, first-halt-allowed,
second-halt-suppressed, all-halt-chart fallback to Normal, budget
resets each year, soft damage doesn't consume budget, per-player
independent budgets, and the no-year legacy-disable path.

Suite: **514 passing** (was 506 + 8 new).
APP_VERSION bumped to `0.1.0-dev.2026-05-28.2`.

### claude/market-bug-cluster-2026-05-27

Branch: `claude/market-bug-cluster-2026-05-27`
Target: `pre-release`

Implements the 2026-05-27 market-bug-cluster brief — three reported
market defects.  Investigation found one was a real client bug, one
was already-correct engine behaviour (pinned with regression tests),
and one was a missing-context payload gap.

**Bug #1 — bid price display vs commit (Comet #6).**

*"Food showed 17.18 but the bid was calculated at 40.00/unit."*

Root cause was client-side: the Market Buy "Place Bid" price field
prefilled with the resting **ask** price, not the formula/reference
price.  When a resting ask sat far above fair value (40 vs 17.18),
the bid field showed the confusingly-high ask.  The column header
literally says "Place Bid (qty @ **your** price)" — a limit order
should default to fair value.  Changed `bidPrefill` in
`_renderMarketBuyRow` to use `formula_price` (the reference the
player sees elsewhere); "Buy Now" remains the at-ask path.

**Bug #2 — same-price Bid + Ask not crossing (Comet #8).**

*"FarmMachinery Ask 9 + Bid 9 never crossed."*

Investigation: the engine matching is **correct** — `_auto_match_bid`
uses `>` (not `>=`) so equal prices cross, and `_auto_match_offer`
mirrors it.  Verified by direct reproduction in both post orders
(bid-first and ask-first).  The reported symptom was a stale
market-board display artifact (the board the player was looking at
hadn't refreshed after the cross propagated), not an engine bug.
Added three regression tests pinning same-price crossing so it can't
silently regress, plus a sanity guard that a bid below the ask does
NOT cross.

**Bug #3 — stale "buy food" sustenance hint (Codex Player).**

*"'Meals runway: 0' told me to buy food, but there was no ask, only
bids.  The hint remained prominent even after I posted a food bid."*

The sustenance alert fired on `runway < 2` with no awareness of
market state.  Added two context flags to the alert payload:

- `market_has_supply` — True if any basket resource (Food / Grain /
  Produce / Fish / Meat) has a resting ask.  When False, the
  dashboard now suggests "produce it yourself, train a Farmer, or
  build a Kitchen" instead of "buy food" (and drops the Market-Buy
  hand-off, since there's nothing to buy).
- `player_has_pending_bid` — True if the hungry player already has a
  resting basket bid.  When True, the hint softens to "waiting on
  your bid — raise the price if it's not clearing" instead of nagging
  them to re-buy.

**Tests:** new `tests/test_engine/test_market_bug_cluster.py` with 7
tests — same-price crossing (both orders) + below-ask no-cross +
formula_price distinct from ask + the three sustenance-flag states
(no supply / pending bid / supply exists).

No engine economics changed — the matching logic is untouched (only
tested), the prefill + hint rendering are pure UI, and the alert
flags are additive payload fields.  Calibration is unaffected.

Suite: **506 passing** (was 499 + 7 new).
APP_VERSION bumped to `0.1.0-dev.2026-05-28`.

UI note: bugs #1 and #3 are client-rendering fixes that ship in this
same commit (no separate Claude follow-up needed).  The remaining
market UX items from the triage (affordability indicator, List-at-
Best-Bid, listed-on-market badge) are still in the Pass B backlog.

### claude/loan-and-insurance-consent-bugs-2026-05-27

Branch: `claude/loan-and-insurance-consent-bugs-2026-05-27`
Target: `pre-release`

Implements the 2026-05-27 loan-and-insurance-consent-bugs brief.
Three independent Banker-side defects shipped in one branch.

**Fix 1 — Insurance sale routes consent to BUYER.**

AyaySir's BUG-07 report: *"Life Insurance (50 Dp) and Medical
Insurance (60 Dp) were issued automatically mid-session ('Policy
issued' appeared in the log without a player-initiated action),
spending 110 Dp without explicit consent."*

Root cause: `_action_sell_insurance` called `self.io.confirm(...)`
while the IO adapter's active player was still the **Banker (seller)**.
The seller's UI got the prompt; seller accepted on the buyer's
behalf; policy was created with no buyer input.

Fix: stash the seller's active-player TLS, call
`set_active_player(buyer.player_id)`, await the confirm on the
buyer's channel, restore the seller's active player.  Same pattern
used elsewhere (`_pay_lease_for_lessee`).  If the buyer declines,
no policy and no Dp move.

**Fix 2 — Loan offer routes consent to BORROWER.**

Codex Player report: *"the app let Banking accept a loan on behalf
of the borrower."*

Identical root cause and identical fix pattern in `_action_offer_loan`.
The borrower's IO channel now gets the confirm; their answer
decides whether the loan is created.  AI-borrower path (rate ≤ 0.15
heuristic) is unchanged.

**Fix 3 — Loan repayments run AFTER the action phase.**

Codex Player report: *"an earlier mature loan defaulted before I
could intervene."*

Root cause: `_process_loan_repayments(year, season_index)` was
called at `turn.py:139` — BEFORE the action loop opened at line
142.  A loan maturing this season was repaid/defaulted before the
borrower's action turn started, so they had no chance to rollover.
The rollover-candidate query then said "no active loans" because
the loan was already REPAID/DEFAULTED.

Fix: move `_process_loan_repayments` to AFTER the action phase
(right before market snapshot).  Borrowers now have their full
action turn to rollover or repay; end-of-season processing only
acts on what's still due.

Verified end-to-end by `test_run_season_order_processes_repayments_last`
— an AI borrower with a 1-year loan maturing in Y1 S0 now reaches
its action turn with the loan still ACTIVE and rolls it over (or
repays); before the fix the loan would have been auto-defaulted at
season start.

**Tests:** new `tests/test_engine/test_loan_insurance_consent.py`
with 7 tests:
- Insurance confirm routed to buyer (not seller)
- Insurance refused when buyer declines (no Dp move)
- Loan-offer confirm routed to borrower (not lender)
- Loan-offer refused when borrower declines
- AI borrower path uses heuristic, not the IO confirm (regression)
- Loan due this season is still ACTIVE during action phase
- End-to-end: AI borrower rolls over a maturing loan during their turn

**Calibration:** byte-identical to previous build (4-seed sweep).
Consent fixes don't activate in all-AI sims (no human buyers/
borrowers in calibration runs); repayment-timing change is
absorbed because the AI heuristic already handles rollover.

Suite: **499 passing** (was 492 + 7 new).
APP_VERSION bumped to `0.1.0-dev.2026-05-27.8`.

UI follow-up (Claude separate, not in this commit): the buyer's
confirm prompt may need a richer modal showing the policy terms
(currently a bare yes/no) so the buyer can read what they're
agreeing to.  Same for the loan-offer modal on the borrower side.

### claude/disaster-mitigation-and-workforce-resilience-2026-05-27

Branch: `claude/disaster-mitigation-and-workforce-resilience-2026-05-27`
Target: `pre-release`

Implements the 2026-05-27 disaster-mitigation brief.  Addresses two
playtest reports in one branch:

- **Comet's Flood report** — single Flood event that zeroed all
  workers across multiple roles with no insurance/mitigation path,
  hit Year 5 Winter leaving no recovery time.
- **Manny Fracture's 5-year zero-workforce cascade** — Mining had 0
  active workers for virtually the entire 5-year game from
  workplace-risk attrition with no recovery mechanism.

Three fixes shipped:

**Fix 1 — Flood event re-tiered (`config/event_charts.yaml`).**

Flood was `yield_modifier: 0.0` + `outage: true` + `damage_seasons: 1`
+ `natural_disaster: true` — the originating island lost two
halt-equivalent seasons AND every other island dropped to 50% the
same season.  Re-tiered to `yield_modifier: 0.25` + `outage: false`,
keeping the damage cycle and cascade.  Origin island now retains 25%
output rather than zero; the existential "single roll = game over"
character is gone.

**Fix 2 — Life insurance reduces fatality rate
(`LIFE_INSURANCE_FATALITY_REDUCTION = 0.5`).**

Before this brief, Life insurance was payout-only — the worker still
died, the player just got cash.  Now the per-worker fatality
probability is multiplied by `(1 - LIFE_INSURANCE_FATALITY_REDUCTION)`
when a policy is in force, mirroring how Medical insurance halves
injuries (`MEDICAL_INSURANCE_INJURY_REDUCTION` was already there;
this is the symmetric fix).  Mining at base fatality 0.08 drops to
0.04 with a Life policy.

To prevent the resulting Banker calibration spike from FEWER deaths
costing the Banker less in payouts, doubled the per-fatality
`LIFE_INSURANCE_DEATH_BENEFIT` from 60 Dp to 120 Dp so expected
Banker liability stays flat while making the policy more valuable
to the bereaved island.

**Fix 3 — Per-tick workforce-loss cap
(`MAX_WORKFORCE_LOSS_PER_TICK_FRACTION = 0.30`).**

At most 30% of an island's active workers can die from any single
workplace-event tick (minimum 1 to avoid blocking tiny workforces
entirely).  Without this, a streak of bad rolls could wipe most of a
5-worker starting workforce in one tick — exactly the Manny Fracture
cascade.  Cap keeps the most-experienced workers (sorts deceased by
age descending, drops the oldest from the survival list since
domain-logic is "most-vulnerable die first").

`WorkforceEventReport` extended with `insurance_reduced_fatalities`,
`loss_cap_applied`, and `would_have_lost` flags so the dashboard +
game log can attribute survivors to the insurance / cap.

**Tests:** new `tests/test_engine/test_disaster_mitigation.py` with
7 tests covering all three fixes (Flood re-tiered config, Life
insurance halves rate over 50 ticks with deterministic seed, Life
flag set on report, per-tick cap fires deterministically with
forced-100% RNG, minimum-1 cap for tiny workforces, cap preserves
youngest survivors).

**Calibration check** (4-seed sweep × 200 games):

| Role | Baseline | After | Δ |
|---|---:|---:|---:|
| Farmer | 12.9% | 11.8% | -1.1 |
| Miner | 13.1% | 14.4% | +1.3 |
| Transporter | 14.9% | 12.6% | -2.3 |
| Educator | 18.0% | 18.1% | +0.1 |
| Banker | 14.8% | 14.8% | 0.0 |
| Manufacturer | 12.8% | 15.4% | +2.6 |
| Doctor | 13.6% | 13.0% | -0.6 |

All roles remain in the [12 – 18 %] band.  Banker offset (doubled
death benefit) worked precisely.  Transporter and Manufacturer drift
just over ±2 pp from baseline but both stay inside band.

Suite: **492 passing** (was 485 + 7 new).
APP_VERSION bumped to `0.1.0-dev.2026-05-27.7`.

### claude/graceful-degradation-2026-05-27

Branch: `claude/graceful-degradation-2026-05-27`
Target: `pre-release`

Scaffolding for the graceful-degradation brief (GitHub #47 + Manny
Fracture playtest report).  **Application gated off pending
calibration work** — the scaffolding is ready to flip on, but the
floor mechanism shifts the entire economy.

What landed:

- `EXPERTISE_DEGRADATION_FLOORS` table in `constants.py`
  (unique_specialist / manager / technician / unskilled).
- `UNIQUE_SPECIALIST_PROFESSION` map (Farmer / Miner / Doctor /
  Banker / Educator's Professor / Engineer / LogisticsManager).
- `EXPERTISE_DEGRADATION_ROLE_OVERRIDES` empty-by-default map for
  per-role tuning later.
- `EXPERTISE_DEGRADATION_ENABLED: bool = False` master switch —
  gates both the production-engine application and the
  `[DEGRADED]` log line.
- `ProductionEngine.expertise_degradation_floor(player)` staticmethod
  computes per-role floors (multiplicative within a role, MIN across
  multi-role players) and returns 1.0 if no expertise gaps.
- `_labour_productivity_factor` checks the flag before applying
  `max(natural, floor)`.  Default behaviour unchanged.
- `_action_produce` `[DEGRADED]` log line, also flag-gated.
- Server `_player_capacity` payload field `degradation_floor` per
  output entry so the UI can pre-stage the "Operating at X% floor"
  chip.
- 9 unit tests for the helper covering the floor-composition matrix
  + Doctor's unique-specialist edge case + multi-role MIN + the
  patch-flag-on / patch-flag-off branches.

What did NOT ship (and why):

Initial implementation with the brief-spec 0.10/0.25/0.50 floors
broke calibration severely in the 4-seed sweep:

| Role | Baseline | After floor |
|---|---:|---:|
| Farmer | 12.9% | **22.5%** |
| Miner | 13.1% | **4.4%** |
| Transporter | 14.9% | 16.8% |
| Educator | 18.0% | 12.4% |
| Banker | 14.8% | **2.8%** |
| Manufacturer | 12.8% | **23.1%** |
| Doctor | 13.6% | 18.1% |

Halving to 0.05/0.10/0.25 produced byte-identical results.  Further
reducing to 0.02/0.05/0.10 also produced byte-identical results.

**Root cause**: the existing calibration depends on cascading-collapse
positive-feedback loops — when one role's workforce empties, its
consumers also stop, freezing the whole market.  That freeze is what
gives high-risk roles (Miner especially) their scarcity premium when
they recover.  Any non-zero floor — even a 1% trickle — breaks the
freeze chain because downstream consumers can always find SOME
input.  The displacement of the scarcity premium is what crashes
Miner and Banker.

**Path forward (for the next pass)**: pair the floor with rebalancing
of workplace_risk fatality rates and/or starting workforce sizes
(probably combined with the
`disaster-mitigation-and-workforce-resilience-2026-05-27` brief's
Life-insurance fatality reduction + per-tick cap) so the attrition
that causes the cascade is reduced.  Then the floor becomes a real
safety net for edge cases rather than a regular occurrence that
shifts the entire market.  Brief was updated with this finding.

Calibration restored to the documented baseline with flag off.
Suite: **485 passing** (was 475 + 10 new).
APP_VERSION bumped to `0.1.0-dev.2026-05-27.6`.

### claude/workforce-display-round-up-2026-05-27

Branch: `claude/workforce-display-round-up-2026-05-27`
Target: `pre-release`

Three changes from the 2026-05-27 Comet + Manny Fracture playtest
feedback:

**1. Quick fix: round up fractional worker shortfalls in Decision Hints.**

Playtester observation (Comet): *"Decision Hints show fractional
farmer requirements (0.12, 0.06, 0.04 Farmer) — these appear to be
less than 1 full worker unit. It's unclear whether the game expects
partial worker assignment or if this is a display/rounding bug."*

Root cause: the labour-math in `app.py:1547-1561` computes
`per_unit × workforce_target` where `per_unit` is per-output-unit
(e.g. 0.04 Farmer-seasons per Food unit).  Real math, but you
can't hire 0.12 of a person.  Fixed by replacing `round(short, 2)`
with `math.ceil(short)` so shortfalls always show as whole
workers.  Existing tests still pass because they used whole-number
fixtures (1.0, 2.0).

**2. New brief: `disaster-mitigation-and-workforce-resilience-2026-05-27.md`.**

Addresses Comet's Flood report + Manny Fracture's 5-year zero-
workforce cascade.  Three engine fixes proposed:

- Re-tier `Flood` from `catastrophic` (yield 0.0 + outage) to
  `heavy` (yield 0.25 + damage cycle).  Severity tiers via a new
  YAML `severity` field so future events can opt in.
- Life insurance reduces fatality *rate* by 50 %, not just pays a
  death benefit.  Mirrors how Medical reduces injury rate.
- Per-tick workforce-loss cap: at most 30 % of active workers can
  die from any single workforce-event tick (`floor(N × 0.30)`,
  minimum 1).
- Explicit logging: when workers leave, log says WHY (workplace
  fatality / retirement / disaster) + insurance status.

**3. New brief: `graceful-degradation-2026-05-27.md`** (formalises
GitHub issue #47).

Addresses Manny Fracture's "all production lines locked at max 0"
scenario.  An island missing required expertise produces at a
band-tier-specific floor instead of zero:

- Unique specialist missing (Doctor / Banker / Educator's Professor)
  → 10 % floor.
- Other Manager-tier missing → 25 % floor.
- Technician-tier missing → 50 % floor.
- Worker-tier (Unskilled) missing → no floor change.
- Floors compose multiplicatively.

Includes a `degradation_floor` field on the capacity payload and
an explicit `[PRODUCTION] ... operating at X % floor` log line so
the player can see they're degraded and what to train to recover.

Suite: **475 passing** (display fix didn't break anything; tests
fixture values were already whole numbers).
APP_VERSION bumped to `0.1.0-dev.2026-05-27.5`.

The two new briefs raise the open Codex queue to 8 — both are
classified as **High** priority because the Manny Fracture cascade
(Mining at 0 workers, no Oil, all Manufacturing lines locked) is
exactly the kind of game-ending failure the rollout plan's
`0.1.0-rc1` milestone needs to prevent.

### claude/queue-summary-log-export-rollover-2026-05-27

Branch: `claude/queue-summary-log-export-rollover-2026-05-27`
Target: `pre-release`

Three small playtest-driven improvements bundled in one branch:

**1. Reorder training queue — per-row summary.**

Playtester observation: when reordering the Educator's pending
training queue, the picker showed bare "Move #10 to top" with no way
to tell what Request #10 actually was.  The dashboard doesn't yet
have a rich drag-reorder UI, so the engine falls back to a
`choose_option` picker — fix the label format to carry full context:

`#10 AyaySir -> 2x Mechanic (40 Dp) [pri -1]`

Format includes batch ID, requester name, cohort size, target
profession, fee offered, and priority chip when non-zero.  Also
added `worker_count` to the `_training_queue_payload` (used by the
forthcoming Pass A drag UI).

**2. Game log export.**

New "⬇ Log" button next to "📋 Menu" in the game header.  Triggers
a fetch of `/api/rooms/{room_id}/log` which streams the full
server-side game log as a plain-text attachment, with a small
header carrying room name, version, status, and current
year/season for context.  Solves the playtest-debugging ask "we
should be able to export the game log."  Implemented as:

- `WSAdapter.export_log()` returns the full `self._log` history as
  newline-joined text.
- New FastAPI `GET /api/rooms/{room_id}/log` endpoint returns
  `text/plain` with a `Content-Disposition: attachment` header so
  the browser saves rather than renders.
- Client `downloadGameLog()` fetches the endpoint, wraps the
  response in a Blob, and triggers a browser download via a
  temporary `<a download>` element.

**3. GitHub #6 — loan rollover named-options picker.**

The `_action_rollover_loan` action was the last numeric-index
picker in the engine after the purchase / lease / invest /
product-line fixes.  Converted to `choose_option` so the dashboard
renders loans as a labelled radio picker with all the context the
borrower needs (principal, rate, remaining seasons, maturity
date) — matches the pattern documented in `_choose_product_line_human`
and standardised across the rest of the action surface.

Note: this brief intentionally does NOT implement interactive
rate negotiation (counter-offer flow between borrower and Banker).
The current rollover already reprices at the live
`banker_quote_rate` each time, which satisfies "negotiate a
different rate of interest" in the literal sense (rate floats with
the market).  A full propose-and-counter flow would mirror the
training counter-offer plumbing and is parked for a future brief
if playtest demands it.

**Tests:**

- `test_reorder_fallback_picker_labels_include_per_row_summary` —
  pins the label format so future regressions can't reintroduce
  bare "Move #N to top".
- `test_export_log_returns_full_print_history` — pins the
  `export_log()` contract.
- `test_action_rollover_uses_named_option_picker_not_numeric_index`
  — pins the rollover picker shape so it can't quietly regress.
- Updated two existing rollover tests that were scripting
  `quantities=[1, ...]` (numeric loan pick) to drop the
  now-unused index.

Suite: **475 passing** (was 472 + 3 new).
APP_VERSION bumped to `0.1.0-dev.2026-05-27.4`.

### claude/training-expertise-deadlock-2026-05-27

Branch: `claude/training-expertise-deadlock-2026-05-27`
Target: `pre-release`

Implements the second Critical brief from the 0.1.0-dev.2026-05-26.5
playtest triage — AyaySir's 9-season training deadlock + Codex
Player's identical report.  Three layers shipped.

**Layer 1 — AI Manufacturer demand chooser sees indirect demand.**

Root cause: PR #46's `_has_human_equipment_demand` only detected
*direct* equipment consumption (Miner → MiningEquipment, Doctor →
MedicalDevices, etc.).  A human Miner with a pending training
request indirectly drives LaboratoryEquipment demand (Educator needs
Expertise → Educator needs LabEquipment), but PR #46 didn't see
that chain.  The Manufacturer would dutifully build MiningEquipment
for the visible human Miner while letting LabEquipment supply
collapse — the Educator's Expertise pipeline starved and training
requests stuck on `awaiting_educator` indefinitely.

Fix: `_has_human_equipment_demand` now also returns True when any
human player has pending training requests OR has workers already
in training.  Both signal an active pipeline that needs Expertise
upstream of LabEquipment.  Threaded `training_registry` through
`AIStrategy.take_turn` and `_choose_product_line` so the AI can
introspect pending state.

**Layer 2 — `SUPPLY_TRAINING_EXPERTISE` requester escape hatch.**

New `TurnAction.SUPPLY_TRAINING_EXPERTISE` lets a requester gift
Expertise from their own inventory to an Expertise-starved Educator,
unblocking a pending training request.  Authorization: only the
original requester can supply, only for their own batches, only
when the Educator's `_training_capacity_status` blocker mentions
"Expertise".  Computes the exact shortfall (per-course requirement
minus what's already at the Educator) and refuses cleanly if the
requester is short.  Transfer is at zero Dp — this is a deadlock-
breaker, not a sale.  Does NOT auto-approve; the Educator still has
to approve (human via modal, AI via next-season re-review).

Also added `TrainingRegistry.pending_for_requester(requester_id)`
query (used by both Layer 1's indirect-demand check and Layer 3's
payload).

**Layer 3 — `training_pipeline` payload deadlock-visibility fields.**

Extended the existing per-player `training_pipeline` entries with
three new fields populated only for AWAITING_EDUCATOR requests:

- `blocker_reason` — the human-readable reason string from
  `_training_capacity_status` (e.g. "needs 2 Expertise for this
  course", "Technical Workshop capacity full: 6/6 trainee seats
  already in training").
- `seasons_blocked` — how many seasons the request has been pending
  since `proposed_year/season`.
- `can_supply_expertise` — True if the blocker is Expertise AND the
  requester has enough on hand to cover the shortfall.  Drives the
  UI follow-up's "Supply Expertise" button visibility.

**Tests:**

- New `tests/test_engine/test_training_expertise_deadlock.py` with
  7 tests covering all three layers:
  - Indirect demand via pending training requests
  - Indirect demand via in-training workers
  - Direct-demand fallback when no registry is passed (backward
    compat)
  - SUPPLY action transfers Expertise correctly
  - SUPPLY action no-op when no eligible batches
  - SUPPLY action authorization (non-requester refused)
  - `pending_for_requester` filter correctness
- Updated `test_training_pipeline_shape` in `test_ux_payload.py` to
  pin the new payload fields.

Suite: **472 passing** (was 465 + 7 new).
APP_VERSION bumped to `0.1.0-dev.2026-05-27.3`.

**Calibration unchanged.**  4-seed sweep (200g × seeds 42/1/7/99)
returns byte-identical means to the PR #46 baseline:

| Role | Mean | PR #46 baseline |
|---|---:|---:|
| Farmer | 12.9% | 12.9% |
| Miner | 13.1% | 13.1% |
| Transporter | 14.9% | 14.9% |
| Educator | 18.0% | 18.0% |
| Banker | 14.8% | 14.8% |
| Manufacturer | 12.8% | 12.8% |
| Doctor | 13.6% | 13.6% |

This is by design: the indirect-demand path only fires when there
is a *human* player with pending training.  In all-AI calibration
sims there are no human players, so the legacy profit chooser runs
exactly as it did before.  The change is invisible to the
calibration sweep and only activates in the actual deadlock scenario.

UI follow-up: dashboard badge for `seasons_blocked >= 3` + "Supply
Expertise" button when `can_supply_expertise` (Pass A continuation).

### claude/rollout-plan-2026-05-27

Branch: direct commit on `pre-release`
Target: `pre-release`

Docs-only — adds `requirements/rollout-plan-2026-05-27.md`, the
sequenced milestone view of all open work that pairs with `TODO.md`
(development priority tracker) and the brief queue in
`requirements/codex-tasks/`.

Captures:

- Live build (`0.1.0-dev.2026-05-27.2`) + the eight merges that landed
  this cycle.
- Codex brief queue (7 open, prioritised from the
  2026-05-26.5 playtest triage) with the Done Trading fix marked
  complete and the Training Expertise deadlock marked in progress.
- Claude UI follow-up backlog batched into three passes (Action
  panel + hints, Market UX, Dashboard surfaces) with carry-over
  payloads from PR #40 (Banker chip) and PR #41 (Educator queue +
  requester decisions) flagged.
- Scoping items needing decisions (from the 2026-05-26 GitHub
  issues batch) and new scoping items from today (Vaccines + Flu
  #49, Hiring Doctors/Nurses #50, Air Freight #51).
- Closeable GitHub issues — closed #21 (named-options purchase
  picker shipped) and #10 (Market Board modal — already marked
  done in TODO.md, just needed the issue closed).
- Four proposed milestones: `0.1.0-rc1` (Critical bug-fix sweep),
  `0.1.0-rc2` (scoping-batch features), `0.2.0` (major systems
  incl. MPS), `0.2.x / 0.3.0` (content expansion incl. Actuaries
  / Ecologist / Medical Lab tests).

No engine changes; suite remains green at 465.

### claude/done-trading-undo-and-auto-set-fix-2026-05-27

Branch: `claude/done-trading-undo-and-auto-set-fix-2026-05-27`
Target: `pre-release`

Implements the Critical brief from the 0.1.0-dev.2026-05-26.5 playtest
triage — the cross-cutting bug behind seven references across all
three player reports (Done Trading auto-set + no undo path).  Three
sub-issues addressed in one branch.

**Sub-issue A — server stops auto-setting Done.**

Diagnostic: server-side state was correct (`_on_season_start` resets
`season_ready_set` and `season_human_done`, `begin_season` clears
`_player_ready_flags`), but two paths could leave the *client* with
a stale `imReady = true` from before:

- WebSocket reconnect handler sent `game_state` but never a fresh
  `ready_update`, so a player who clicked Done last season would
  see "Done Trading ✓" on reconnect even after the season had
  rolled over.
- `_on_season_start` never broadcast a `ready_update` for the new
  season, so any client that missed the `season_resolved` broadcast
  carried its `imReady = true` forward.

Both fixed defensively: reconnect now sends `_broadcast_ready_update`,
and `_on_season_start` broadcasts `ready_update` after the
`season_start` message with the cleared sets.

**Sub-issue B — Undo path actually works (the deep fix).**

Root cause: `mark_player_ready` resolved the in-flight prompt with
the string `"end_turn"`, which made `choose_action` return
`TurnAction.END_TURN`, which exited the `while True` action loop.
Once the loop exited, the turn thread completed and `_on_player_done`
fired.  Calling `unmark_player_ready` later just cleared a flag that
nothing was reading any more.

Fix: convert Done from a turn-terminator into a turn-pauser.

- `mark_player_ready` now resolves the in-flight prompt with
  `CANCEL_SENTINEL` (reusing the existing dialog-cancel sentinel), so
  whatever sub-prompt the player was in raises `ActionCancelled` and
  drops cleanly back to the action loop.
- `choose_action` now has a park loop: while the Ready flag is set,
  the thread broadcasts a new `choose_action_parked` message and
  waits on the player's event.  Wakes on either `unmark_player_ready`
  (flag clears → falls through to re-prompt) or `interrupt_all`
  (real season end → returns `END_TURN`).
- `unmark_player_ready` now `.set()`s the player's event so the park
  loop wakes immediately.

The turn thread stays alive throughout the parked state, so an Undo
truly resumes the player's action menu instead of being a no-op.

**Sub-issue C — Decision Hints policy in Done state.**

Chose Option 1 (AyaySir IMP-04's preference): hint click auto-undoes
Done first, then fires the action.

- `_actOnHint` checks `imReady`; if true, sends `{type:'ready',
  ready:false}` to undo and queues the action target in
  `_pendingActionAfterUndo`.
- `showActionPrompt` consumes the queued action when the fresh
  prompt arrives from the server-side re-prompt.
- `_renderHintOpenButton` keeps hint buttons enabled in the parked
  state (so the auto-undo path is reachable) with a tooltip
  explaining "Resumes trading then opens this action".

New parked banner UI: when the server broadcasts
`choose_action_parked`, the action panel area shows "You've marked
yourself done for this season" with a prominent "↩ Resume Trading"
button that calls the same Undo path.

**Tests:**

- Updated `test_mark_player_ready_short_circuits_choose_action` to
  reflect the new contract (now
  `test_mark_player_ready_parks_choose_action_until_interrupted`):
  parked thread waits, broadcasts `choose_action_parked`, and only
  exits via `interrupt_all`.
- New `test_unmark_player_ready_wakes_parked_choose_action`:
  parked thread wakes on Undo and sends a fresh `choose_action`
  prompt.
- New `test_mark_player_ready_cancels_in_flight_prompt`: regression
  for the "action panel disappears after End Turn" symptom — Done
  mid-dialog aborts the sub-prompt cleanly via `CANCEL_SENTINEL`.

Suite: **465 passing** (was 463 + 2 net new tests).

APP_VERSION bumped to `0.1.0-dev.2026-05-27.2` for playtest tracking.

### claude/codex-briefs-from-playtest-26.5-2026-05-27

Branch: direct commit on `pre-release`
Target: `pre-release`

Docs-only — drafts the six Codex briefs identified in the
[`triage-0.1.0-dev.2026-05-26.5.md`](./requirements/playtest-feedback/triage-0.1.0-dev.2026-05-26.5.md)
consolidation pass. Each brief carries the playtester source
references, the proposed engine + payload changes, the test list,
and the explicit out-of-scope boundary.

Two Critical fixes (recommended first):

- `done-trading-undo-and-auto-set-fix-2026-05-27.md` — addresses the
  cross-cutting bug behind seven separate item references across all
  three playtest reports (Done Trading auto-set + no undo path).
  Three-layer fix: audit Ready-flag setters, add explicit
  `UNDO_DONE_TRADING` action, decide Decision-Hint policy in Done
  state (Option 1: auto-undo, preferred; Option 2: hide buttons).
- `training-expertise-deadlock-2026-05-27.md` — addresses the
  total-system deadlock reported by AyaySir (9 seasons stuck) and
  Codex Player. Three layers: fix the Expertise pipeline blocker,
  add a requester-supplied-Expertise escape hatch (AyaySir IMP-03),
  surface `training_pipeline_health` payload on the requester
  dashboard.

Four further briefs:

- `loan-and-insurance-consent-bugs-2026-05-27.md` — three related
  Banker-side defects: insurance auto-issue, loan-acceptance on
  borrower's behalf, loan rollover + early-default state-machine
  fix.
- `event-frequency-cap-2026-05-27.md` — caps production-halting
  events at `HALT_EVENTS_PER_PLAYER_PER_YEAR = 1`. Addresses the
  "5 halts in 5 seasons" scenario from Comet 1 and AyaySir.
- `market-bug-cluster-2026-05-27.md` — three independent market
  defects: bid display/commit mismatch, same-price Bid+Ask not
  crossing, stale "buy food" hint when no Asks exist.
- `training-request-withdraw-by-requester-2026-05-27.md` — small,
  symmetric to the educator-side Reject/Counter shipped in PR #41.
  Adds requester-side `WITHDRAW_TRAINING_REQUEST` with state-aware
  refund semantics.

Each brief is self-contained — Codex can pick them up in any order
the team prefers. The two Critical briefs (Done Trading, Expertise
deadlock) are recommended first because they currently make the
game unplayable for affected roles.

No engine or test changes; suite remains green at 463.

### claude/playtest-feedback-folder-2026-05-27

Branch: direct commit on `pre-release`
Target: `pre-release`

Docs-only — stands up a structured home for playtest feedback under
`requirements/playtest-feedback/` and consolidates the four reports
that came in against `0.1.0-dev.2026-05-26.5`.

Structure:

- `requirements/playtest-feedback/README.md` documents the convention:
  one raw report file per build (`playtest-{APP_VERSION}.md`), one
  triage doc per report (`triage-{APP_VERSION}.md`), and a four-bucket
  triage workflow (✅ already fixed / 🐛 new Codex brief / 🎨 Claude UI
  follow-up / ⚖️ calibration design / ⏭ deferred).
- `requirements/playtest-feedback/playtest-0.1.0-dev.2026-05-26.5.md`
  is the verbatim report from Comet Player 1 (Manufacturer), AyaySir
  (Mining), Codex Player (Banking), and Real Human (general).
- `requirements/playtest-feedback/triage-0.1.0-dev.2026-05-26.5.md`
  cross-references all four reports, identifies the shared
  "Done Trading auto-set + no undo" root cause behind seven of the
  bug reports, proposes six new Codex briefs, batches nine UI items
  into three Claude follow-up passes, surfaces five calibration /
  design questions, and lists three deferred items (server-takedown
  reconnects excluded per operator note).

Why a separate folder: keeps raw player observations distinct from
the spec docs in `requirements/` and the Codex brief queue in
`requirements/codex-tasks/`. The raw + triage docs stay paired so
we keep a record of how each playtest item was handled.

No engine or test changes; suite remains green at 463.

### claude/purchase-named-options-2026-05-27

Branch: `claude/purchase-named-options-2026-05-27`
Target: `pre-release`

Fixes a UX defect playtesters reported against `0.1.0-dev.2026-05-26.5`:
the **Purchase Equipment** action presented capital items as a numeric
index picker (`choose_quantity` → bare number-input field on the
dashboard) rather than a named-option picker (`choose_option` → radio
list with the full description on each row). The Lease, Invest, and
product-line pickers already used the named-option pattern; Purchase
was the only outlier.

- `_action_purchase_capital` in `island_traders/engine/turn.py` now
  builds an `options=[{value: item_id, label: "..."}]` list and calls
  `self.io.choose_option(...)`. Same labels as before (name, role,
  cost, manufactured-resource requirement or cash-only flag, delivery
  ETA) — just rendered as a radio picker instead of a text paragraph
  followed by an index input.
- Cancel returns to the action menu cleanly (consistent with the
  other named-option pickers).
- New regression test `test_purchase_capital_uses_named_option_picker_not_numeric_index`
  pins the contract so the picker can't quietly regress to an index
  prompt again.
- Updated `test_purchase_capital_places_delayed_item_in_transit` and
  `test_purchase_capital_can_buy_cash_only_kitchen_without_manufacturer`
  to override `choose_option` (by item_id) instead of `choose_quantity`
  (by numeric index).

No engine semantics changed; 463 tests passing.

### claude/banker-lawyers-brief-2026-05-26

Branch: direct commit on `pre-release`
Target: `pre-release`

Docs-only — drafts the Lawyers Codex brief from GitHub issue #44
("Banking requires Lawyers"), the smallest of the six 2026-05-26
scoping issues. Scope intentionally narrow:

- New `Profession.LAWYER` (Manager band, 2-season Educator pipeline,
  university capacity 2/year), trainable from every island like Chef.
- Lease inception gated on the lessee holding ≥1 Lawyer on roster.
  Existing leases at merge time are grandfathered — no retroactive
  requirement.
- Banker starting workforce grows from 4 → 5 (adds 1 Lawyer) so the
  Bank can lease its own equipment from turn 1. No other island gets
  a pre-placed Lawyer — they must train one before leasing.
- Both investing-phase lease application and mid-game LEASE_CAPITAL
  action respect the gate. Lawyer presence is one-shot at inception;
  losing the Lawyer later does not affect an existing lease.

Out of scope (explicit): Lawyer involvement in loans, insurance,
deal-guarantee, dispute arbitration — those come later. Banker-side
Lawyer requirement also deferred (assume institutional counsel for
the lessor side).

UI follow-up: Lawyer chip on the workforce display + greyed-out
Lease button with "Train a Lawyer first" tooltip on islands with
0 Lawyers.

No engine or test changes; suite remains green at 462.

### codex/educator-approval-queue-2026-05-26

Branch: `codex/educator-approval-queue-2026-05-26`
Target: `pre-release`

Educator training-queue controls:

- Added `TrainingRequest.priority` and sorted pending Educator queues by
  `(priority, batch_id)` for human review and AI Educator review.
- Added `REORDER_TRAINING_QUEUE`, `REJECT_TRAINING_REQUEST`,
  `COUNTER_TRAINING_REQUEST`, and `ACK_TRAINING_DECISION` actions.
- Added persistent rejection/counter metadata on training requests:
  decline reason, decision season, original offer, and acknowledgement state.
- Added server payloads for `training_queue_order` on Educator dashboards
  and `training_decisions` on requester dashboards.
- AI Educator rejections now include a fair-rate decline reason for the
  requester notification payload.

Tests:

- Added 9 regression tests for priority ordering, queue reordering,
  AI sorted processing, queue reject/counter actions, requester decision
  payloads, acknowledgement, auth refusal, and AI decline reasons.
- `PYTHONPATH=. /Users/ashleysilver/Documents/projects/island-traders/.venv/bin/python -m pytest -q`
  -> **452 passing** after merging the latest `pre-release`.
- Balance check stayed unchanged:
  - `--games 1000 --years 3 --seed 42`: all roles 12.3%-17.2%.
  - `--games 200 --years 3 --seeds 42,1,7,99`: four-seed means
    12.8%-18.0%.

### codex/ai-manufacturer-product-mix-2026-05-26

Branch: `codex/ai-manufacturer-product-mix-2026-05-26`
Target: `pre-release`

AI Manufacturer product-line choice:

- Added a demand-scored product-line chooser for human-visible equipment
  demand so a human Educator/Doctor can pull AI Manufacturing toward
  `LaboratoryEquipment` instead of being stuck behind the default
  `FarmMachinery` line.
- Kept the legacy profit/bid chooser for all-AI simulations so calibration
  remains stable when there is no human demand signal.
- Added a 10% sticky guard, input-feasibility fallback, and an idle message
  when no Manufacturer line can be produced.
- Added light supply memory and one-unit LabEquipment release throttling on
  human-demand Lab runs so the AI seeds the bottleneck without dumping a
  whole game worth of lab gear at once.

Tests:

- Added 5 AI Manufacturer tests for LabEquipment demand selection, sticky
  behavior, feasible fallback, no-input idle logging, and human Educator
  LabEquipment listing.
- `PYTHONPATH=. /Users/ashleysilver/Documents/projects/island-traders/.venv/bin/python -m pytest -q`
  -> **453 passing** after merging the latest `pre-release`.
- Balance check stayed on the post-calibration all-AI baseline:
  - `--games 1000 --years 3 --seed 42`: all roles 12.3%-17.2%.
  - `--games 200 --years 3 --seeds 42,1,7,99`: four-seed means
    12.8%-18.0%.

### codex/training-profession-alignment-2026-05-26

Branch: `codex/training-profession-alignment-2026-05-26`
Target: `pre-release`

Follows up the training-flow diagnostic amendment for display-title vs
trainable-profession mismatches:

- Added real Technician-band, trainable profession enums for `FactoryForeman`
  and `MiningForeman`.
- Kept `AssemblyWorker` and `RefinerySpecialist` as the existing engine
  professions but changed their player-facing labels to `Assembly Tech` and
  `Refiner`, matching the roster titles players see.
- Left `Stevedore` and `Aide` as Worker-band population titles rather than
  formal Education courses.
- Added regression coverage so the playtest-reported phantom titles stay
  aligned with the training menu.

### codex/banker-wholesale-funding-2026-05-26

Branch: `codex/banker-wholesale-funding-2026-05-26`
Target: `pre-release`

Banker wholesale-funding rebalance:

- Lowered base Banker reserve ratio from 50% to 5%; MBA-qualified reserve
  ratio drops from 20% to 2%.
- Added active customer-loan caps: `max(1, 2 x Banker Manager count)` per
  Bank. Repaid/defaulted loans free slots, and synthetic depositor funding
  loans do not count.
- Applied the cap to human loan offers, borrower-initiated Bank loans, and
  AI Banker lending.
- Added Banker loan-book cap/count fields to the server player payload for
  dashboard follow-up.

Tests:

- Added/updated regression tests for the 5% / 2% reserve math, active-loan
  cap, starter slot, freed slots after repayment/default, depositor-loan
  exclusion, and AI cap refusal.
- `PYTHONPATH=. /Users/ashleysilver/Documents/projects/island-traders/.venv/bin/python -m pytest -q`
  -> **447 passing**.
- Balance check stayed on the post-calibration band:
  - `--games 1000 --years 3 --seed 42`: all roles 12.3%-17.2%.
  - `--games 200 --years 3 --seeds 42,1,7,99`: four-seed means
    12.8%-18.0%; Banker mean 14.8%.

### claude/educator-queue-brief-amend-2026-05-26

Branch: `claude/educator-queue-brief-amend-2026-05-26`
Target: `pre-release`

Docs-only amendment to `educator-approval-queue-2026-05-26.md` after
two follow-up requests from the 2026-05-26 playtest cycle:

- **Reject / Counter from the queue view itself.** New
  `REJECT_TRAINING_REQUEST` and `COUNTER_TRAINING_REQUEST` actions
  the Educator can fire inline against any pending row, no per-
  request modal walk required. Stores a `decline_reason` on the
  request when an Educator declines or counters.
- **Visual flag + popup on the requester's dashboard.** New
  `training_decisions` server payload (per requester) carries every
  counter / rejection of their own requests with the decline reason
  attached. New `ACK_TRAINING_DECISION` action lets the requester
  dismiss a notification. UI follow-up will render a badge and an
  "Improve bid" popup so the requester can re-submit with a
  stronger offer.

Also bumps required test count and acceptance criteria in the brief
to reflect the new actions / payloads. No code touched here; same
brief, expanded scope.

### claude/codex-briefs-2026-05-26-batch2

Branch: `claude/codex-briefs-2026-05-26-batch2`
Target: `pre-release`

Docs-only — second batch of Codex briefs from a follow-up 2026-05-26
playtest report against `0.1.0-dev.2026-05-26`. Three new briefs and
one amendment:

- **`banker-wholesale-funding-2026-05-26.md`** — drop the Banker
  reserve ratio from 50% → 5% (and the MBA-qualified ratio from 20%
  → 2%) so the existing wholesale-funding architecture
  (`_fund_bank_external_portion`) actually does the work the user
  expects. Add a per-Banker active-loan cap (`max(1, 2 × N_Banker_
  Managers)`) so we don't drift into infinite-leverage degeneracy
  after the reserve drop. Synthetic depositor loans don't count
  toward the cap.
- **`educator-approval-queue-2026-05-26.md`** — add a `priority`
  field on `TrainingRequest` and a `REORDER_TRAINING_QUEUE` action
  so the Educator can drag-reorder the pending approvals list.
  Engine sorts pending requests by `(priority, batch_id)` everywhere
  it iterates them, including in the AI Educator's response loop.
  Server payload exposes `training_queue_order` for the Educator
  player's dashboard; Claude will render the drag UI in a follow-up.
- **`ai-manufacturer-product-mix-2026-05-26.md`** — make the AI
  Manufacturer's product-line choice demand-driven each season
  instead of statically stuck on FarmMachinery. Fixes the symptom
  "Education never gets to buy Laboratory Equipment because
  Manufacturing is never able to produce it." Includes a 10% sticky
  threshold to prevent season-by-season thrashing and an
  input-feasibility fallback when the preferred line is short on
  Metal / Oil.
- **Amendment to `training-flow-diagnostic-2026-05-26.md`** —
  added hypothesis 7: display-title vs trainable-profession mismatch
  (`BAND_TITLES` lists "Factory Foreman" but `ROLE_PROFESSIONS`
  doesn't register a Profession.FACTORY_FOREMAN enum, so the title
  shows on the roster but can't be trained). Same gap likely exists
  for Miner, Transporter, Doctor band titles. Codex picks per role
  whether to add the missing enums or collapse the display list to
  match the trainable set.

No engine or test changes; suite remains green at 429.

### codex/kitchen-island-2026-05-26

Branch: `codex/kitchen-island-2026-05-26`
Target: `pre-release`

Adds the cross-island Kitchen subsystem from the 2026-05-26 playtest
brief:

- Added a universal, cash-only `Kitchen` capital item (`common.kitchen`)
  available to every island catalogue. Cost is 80 Dp, immediate
  delivery, 12-season service life, no lease terms.
- Added `Chef` as a Technician-band profession trainable by every
  island through the existing technical-course pipeline. No starting
  workforce pre-places Chefs.
- Added a per-season Kitchen production pass: each active Kitchen needs
  one active Chef and converts local ingredients into 6 Food using
  `1 Food = 2 Grain + 1 Produce + 1 Fish-or-Meat`.
- Protein selection prefers whichever of Fish or Meat is more plentiful
  in local inventory; ties use Fish.
- Kitchens idle gracefully when unstaffed or short on ingredients,
  logging the reason and consuming no partial inputs.
- Mid-game `PURCHASE_CAPITAL` can buy cash-only Kitchen equipment
  without a Manufacturer counterparty; existing Manufacturer-built
  equipment remains unchanged.

Tests:

- Added 8 Kitchen tests covering universal catalogue availability,
  Chef training metadata, full production, no-Chef idle, missing-
  ingredient idle, Fish/Meat tie-break, partial staffing with multiple
  Kitchens, and cash-only purchase without a Manufacturer.
- `PYTHONPATH=. .venv/bin/python -m pytest -q` → **437 passing**.
- Balance check stayed on the post-calibration band:
  - `--games 1000 --years 3 --seed 42`: all roles 12.3%–17.2%.
  - `--games 200 --years 3 --seeds 42,1,7,99`: four-seed means
    12.8%–18.0%; individual 200-game variance remains comparable to
    the calibration baseline.

### codex/training-flow-diagnostic-2026-05-26

Branch: `codex/training-flow-diagnostic-2026-05-26`
Target: `pre-release`

Diagnose-and-fix pass for the recurring training-flow defect reported
in the 2026-05-26 playtest cycle.

Diagnostic findings:

- Return logistics: the Game return hook did move dispatched workers
  back correctly on the happy path, but it logged nothing when a due
  batch returned zero or fewer workers than expected. It now logs
  complete / returned / failed-return warnings with batch ids and
  missing worker ids.
- Dispatch under load: pending requests blocked by capacity or tickets
  could remain stuck because AI Educators only responded at request
  creation time. AI Educators now review pending requests every season,
  so a request starts once Course / Expertise / PassengerSeats capacity
  clears.
- Ticket math under partial supply: existing split-ticket code already
  checked requester and Educator inventories before consuming either
  side. Regression coverage remains in place and no rollback bug was
  found.
- Sustenance accounting: dispatched cross-island trainees were counted
  both as visiting campus load at Education Island and as mouths to feed
  at their home island. Home islands now subtract dispatched trainees
  while Education Island adds them.
- Decline / cancel paths: rejected and counter-rejected requests did
  release their logical reservation, but workers were not reserved while
  a request was pending. The registry now rejects duplicate active
  requests for the same worker, and the request UI filters already-
  reserved workers out of the eligible list.
- AI Educator behaviour: AI approval now replays seasonally and logs
  pending reasons, approvals, dispatches, and rejections rather than
  silently leaving blocked requests in the queue.

Changes shipped:

- Added active worker reservations to `TrainingRegistry` so the same
  worker cannot be queued into overlapping training requests.
- Added dispatch readiness checks before consuming training / transport
  side effects.
- Added seasonal AI Educator and legacy AI Transporter queue review.
- Added `absent_residents` support to `Player.meals_needed` and wired
  training campus load so trainees eat in one place, not two.
- Improved training state-transition logging around dispatch and return.

Tests:

- Added 5 regression tests covering duplicate worker reservations, AI
  Educator retry after capacity clears, three-trainee happy-path return,
  failed-return logging, and campus-vs-home sustenance accounting.
- `PYTHONPATH=. .venv/bin/python -m pytest -q` → **434 passing**.
- Balance check stayed on the post-calibration band:
  - `--games 1000 --years 3 --seed 42`: all roles 12.2%–17.0%.
  - `--games 200 --years 3 --seeds 42,1,7,99`: four-seed means
    12.9%–17.9%; individual 200-game seed variance matches the
    calibration PR baseline (Manufacturer seed 7 at 8.5%, Doctor seed
    42 at 9.5%).

### claude/codex-briefs-2026-05-26

Branch: `claude/codex-briefs-2026-05-26`
Target: `pre-release`

Docs-only — drafts two new Codex briefs from the 2026-05-26 playtest
feedback (`0.1.0-dev.2026-05-26`):

- `requirements/codex-tasks/kitchen-island-2026-05-26.md` — new
  Kitchen capital item (1 Food = 2 Grain + 1 Produce + 1 Fish-or-Meat)
  with a new Chef Technician profession. Cash-only purchase, capacity
  and price deferred to Codex calibration. Lets any island convert raw
  ingredients into Food in-house, gated by training a Chef.
- `requirements/codex-tasks/training-flow-diagnostic-2026-05-26.md` —
  diagnose-and-fix pass on the training pipeline end to end after a
  third consecutive cycle of "trainees don't return / training over-
  constrained" reports. Hypothesis list focuses on return logistics,
  dispatch under load, ticket math under partial supply, sustenance
  accounting for in-training workers, decline/cancel paths, and AI
  Educator behaviour.

No engine or test changes; suite remains green at 429.

### claude/restore-action-menu-2026-05-26

Branch: `claude/restore-action-menu-2026-05-26`
Target: `pre-release`

Fixes the "trading stops with 240s left on the season clock" defect
playtesters reported against `0.1.0-dev.2026-05-25.2`. Root cause was
that the 📋 Menu recovery button only re-rendered the cached prompt;
if the engine's pending prompt for this player had moved on (or the
cached prompt never matched the engine state) the recovery did
nothing and the season clock kept counting down with no way to act.

- `WebSocket.get_state` handler now also calls
  `replay_pending_prompt(engine_pid)` while the room is `running`,
  so the server redelivers the live unresolved IO prompt for this
  player on demand. Previously this was only done on the initial
  WebSocket connect.
- Client `restoreActionMenu()` now always calls `requestState()`
  after re-rendering the cached prompt — the cached re-render
  provides instant feedback, and the live server replay overwrites
  with the real engine prompt if it disagrees.

No engine changes; 429 tests passing.

### claude/ui-followups-2026-05-25

Branch: `claude/ui-followups-2026-05-25`
Target: `pre-release`

UI follow-ups for the just-merged Training UX and Capital Lease
subsystems, plus a small "About / version" feature so playtesters can
report defects against a specific build:

- Added `APP_VERSION` constant to `island_traders/constants.py` as the
  single source of truth for the build version and exposed it via:
  - `version=APP_VERSION` on the FastAPI app
  - a new `GET /version` JSON endpoint
  - a version label in the landing-page footer (with About link)
  - a version chip in the in-game header (also opens About)
- Added a 📋 Menu recovery button in the game header that re-opens the
  cached Action Menu prompt — fixes the playtest observation that a
  Decision-Hint button could cause the Action Menu to disappear until
  the next turn.
- Cached the last `action.prompt` payload in `lastActionPromptMsg` so
  the Menu recovery button has something to re-render.
- Rendered the new structured `request_summary` payload (training
  approval / counter-offer modals) as a styled key-value table inside
  the option-picker and confirm dialogs.
- Reworked the Investing-phase capital list:
  - Added a 3-way Skip / Buy / Lease `<select>` for lease-eligible items.
  - Server `_investing_payload` now pre-computes a `lease_quote` for
    each lease-eligible catalogue item so the client can show the
    annual payment, buyout, and total cost without a round-trip.
  - Investing totals now correctly sum upfront costs (first lease
    payment for leased items, full price for purchased items).
- Renamed the Loans popup to "Loans & Leases" and added a dedicated
  Leases section that lists active leases with status, annual payment,
  next payment type, and buyout amount.

No engine changes; suite remains green at 429 passing.

### codex/capital-equipment-lease-2026-05

Branch: `codex/capital-equipment-lease-2026-05`
Target: `pre-release`

Adds the capital-equipment lease subsystem:

- Added `Lease`, `LeaseStatus`, and `LeaseLedger` with active,
  repossessed, awaiting-buyout, completed, and buyout-defaulted states.
- Added `CapitalItem.lease_terms` and made `educator.technical_workshop`
  lease-eligible on a 3-year term with 25% buyout and posted 3-year
  funding rate + 2% margin.
- Added lease inception math with locked rates, annual payments in
  advance, and first payment at inception.
- Added mid-game `LEASE_CAPITAL` and `PAY_LEASE` actions.
- Wired season-start annual lease payments, repossession on missed
  payments, one-season delayed return after catch-up, and buyout/default
  handling.
- Added save/load serialization for leases.
- Extended investing payloads with `lease_terms` and accepted
  `lease:<item_id>` selections for opening-phase lease choices.
- Added `leases_detail` to server game-state payloads for the future
  Loans popup section.
- Added 16 regression tests; full suite is green at 420 passing.

UI follow-up: Claude will render lease choices in investing and show
`leases_detail` under the Loans popup.

### codex/training-ux-improvements-2026-05

Branch: `codex/training-ux-improvements-2026-05`
Target: `pre-release`

Implements the training UX follow-up:

- Added 10 `PassengerSeats` to the Educator starting inventory to
  bootstrap early cross-island training.
- Added `TrainingRequest.tickets_supplied_by_requester` so requesters
  can spend some or all of their own PassengerSeats; Educators only
  supply the remainder.
- Updated suggested and AI fair-rate ticket fees to charge only for
  Educator-supplied seats.
- Updated dispatch to consume requester and Educator PassengerSeats
  from the correct inventories without partial burns on failure.
- Added structured `request_summary` payloads to training approval and
  counter-offer prompts for the future dashboard modal rendering.
- Added 9 regression tests covering starting tickets, split ticket
  consumption, AI fee behavior, failed pledged-ticket dispatch, and
  prompt summaries.

UI follow-up: Claude will render `request_summary` in the dashboard
approval modal.

### claude/codex-briefs-refresh-2026-05-25

Branch: `claude/codex-briefs-refresh-2026-05-25`
Target: `pre-release`

Docs-only refresh of three Codex briefs after the 2026-05-25 design
conversation:

**1. `requirements/codex-tasks/capital-equipment-lease-2026-05.md` —
locked-in decisions applied.**

- **Investing phase AND mid-game** lease initiation (was investing-only
  in v1 of the brief). Mid-game uses a sibling `TurnAction.LEASE_CAPITAL`
  action analogous to `PURCHASE_CAPITAL`; same rate-locking math.
- **End-of-term buyout = 25 % of original cost** (option a). Lease no
  longer auto-completes after the 3 annual payments — flips to a new
  `AWAITING_BUYOUT` status; lessee pays `cost × 0.25` to take ownership
  (`COMPLETED`) or walks away (`BUYOUT_DEFAULTED`, item reclaimed).
- **Lease rate = posted 3-year funding rate + 2 % margin**, locked at
  inception, identical for investing-phase and mid-game leases
  (treated as a secured loan against the asset).
- **Annual payment math updated:**
  `(cost − buyout) / term_years × (1 + lease_rate)`. For the Workshop
  (cost 60, buyout 15, ~4 % posted) → ~15.9 Dp/year + 15 Dp buyout =
  ~62.7 Dp total ≈ 4.5 % premium over outright.
- Two new lease statuses: `AWAITING_BUYOUT`, `BUYOUT_DEFAULTED`.
- Server `leases_detail` payload gains `buyout_payment` and
  `next_payment_type` ("annual" | "buyout").
- Required test count grows from 11 → 16 (mid-game lease creation,
  buyout flow, lease-rate-locking-at-inception, etc).
- UI direction: leases list under the Loans panel (single
  `leases_detail` array keeps it simple).

**2. New brief: `requirements/codex-tasks/training-ux-improvements-2026-05.md`.**

Three related improvements addressing the Bug 1 PassengerSeats failure
mode plus the "approval prompt doesn't show what you're approving"
in-play observation:

- **Add 10 PassengerSeats to `STARTING_INVENTORY["Educator"]`** —
  bootstraps cross-island training; eliminates Bug 1 #5 for the first
  few requests in a fresh game.
- **`TrainingRequest.tickets_supplied_by_requester: int = 0`** — new
  field. Requester can pledge to supply some/all of the air tickets
  themselves; Educator only sources the remainder. AI Educator's fair
  rate drops accordingly so requesters get a lower fee for
  self-supplying.
- **Approval prompt shows full request details** — structured payload
  field `request_summary` on the Educator's approve/counter prompt
  AND the requester's counter-acceptance prompt, listing trainees,
  target profession, transport breakdown, fee, etc. Server-side; UI
  rendering is a Claude follow-up.
- 9 required regression tests.

**3. `requirements/codex-tasks/balance-calibration-2026-05.md` —
prerequisites list expanded.**

Added the new pending Codex tasks (lease + training UX) to the
sequencing-dependencies section. Calibration now waits for **five**
upstream landings instead of two: Economy A–D + AI Trading v1/v2 +
sustenance basket + training-staffing (all shipped) + capital lease
+ training UX improvements (both pending). Tuning before all five
land is wasted work.

No code / tests touched. Suite still **404 passing** on `origin/pre-release`.

### claude/codex-brief-equipment-lease

Branch: `claude/codex-brief-equipment-lease`
Target: `pre-release`

Docs-only — new Codex brief at
`requirements/codex-tasks/capital-equipment-lease-2026-05.md` for the
proper capital-equipment lease subsystem (Bug 1 / training-staffing
follow-up).

Replaces the interim "use the existing 1/2/3-year loans" approach
documented in `codex/training-staffing-2026-05`'s release notes.
Key spec points:

- New `Lease` model + `LeaseLedger` mirroring `LoanLedger`.
- `CapitalItem` gains an optional `lease_terms` field opting it into
  the lease flow; only `educator.technical_workshop` opts in for v1.
- 3-year term, annual payments **in advance**, rate locked at lease
  inception (`posted_funding_rate + 2% margin`).
- Missed payment triggers **repossession**: item removed from
  `capital_inventory`, lease flips to `REPOSSESSED`.
- Catch-up payment in a later season reinstates the lease; item
  returns to `capital_inventory` **one season later** (Bank
  redeploy logistics).
- Investing-phase choice between buy outright and lease; AI default
  buy-then-lease-then-skip; auto-pay when solvent.
- Server `leases_detail` payload mirroring `loans_detail`; UI work
  follows on a Claude branch after merge.
- 11 required regression tests covering creation, in-advance payment,
  repossession, season-delayed return, ownership transfer on
  completion, rate math, payload shape, AI behavior.

Calibration follow-up: lease changes equipment-acquisition cadence
slightly; flag for the next calibration re-run.

No code / tests touched.  Suite still **403 passing** on
`origin/pre-release`.

### codex/training-staffing-2026-05

Branch: `codex/training-staffing-2026-05`
Target: `pre-release`

Implements the staffing-based training admission redesign:

- Added `Profession.TECHNICAL_DIRECTOR` as a Manager-band Educator role
  with a starting baseline of 1 Technical Director.
- Replaced the old Manager Course-only gate and Technician slot-pool
  gate with per-concurrent-course staffing commitments.
- Manager courses now require 0.5 Professor + 1 Lecturer, 2 Expertise,
  and the existing Course resource debit.
- Technical courses now require 0.5 Technical Director + 1 Instructor,
  1 Expertise, the existing Course resource debit, and a Technical
  Workshop prerequisite.
- Renamed the Educator capital item to `educator.technical_workshop`
  with `technical_workshop_slots`, and migrated legacy save keys on load.
- Added in-flight course accounting for Manager and Technician courses,
  with staff slots held from Educator approval through completion.
- Added regression coverage for capacity formulas, workshop prerequisite,
  staff lock duration, Expertise/Course debits, capital rename, save
  migration, and legacy helper cleanup.

Follow-up: because this changes training admission cadence, calibration
should be re-run after the branch is reviewed and merged.

**Bootstrap follow-up commit (2026-05-25, Claude review pass).**
The originally-pushed starting workforce (4 Prof + 1 TD + 4 Inst)
left a permanent chicken-and-egg deadlock in the Manager pipeline:
training a first Lecturer is itself a Manager-tier course, but the
new staffing rule needs an existing Lecturer to run any Manager
course. Two patches on top of Codex's commit address this:

- **Option B starting workforce** — `STARTING_WORKERS_BY_PROFESSION["Educator"]`
  is now `2 Professor + 4 Lecturer + 1 Technical Director + 4 Instructor`
  (total 11). Starting Manager-course capacity = `min(2×2, 4) = 4`,
  Technical-course capacity = `min(1×2, 4, workshop) = 2` (with the
  workshop now in mandatory minimum, see below).
- **Technical Workshop added to `MANDATORY_MINIMUM_INVESTMENT["Educator"]`** —
  every Educator opens the game owning a `educator.technical_workshop`
  (3 workshop slots) unless they explicitly deselect it during the
  Investing Phase. Without this, the Technical pipeline was a hard
  block at game start (workshop is a prerequisite, not just a
  capacity multiplier).
- **Updated `test_educator_starting_workforce_*` test** for the new
  shape; added `test_technical_workshop_is_mandatory_minimum_for_educator`.

**Workshop trainee-cap follow-up commit (2026-05-25 part 2, Claude review
pass).** Per spec revision: the Technical Workshop now caps **at 6
trainees in training at a time**, per workshop — a per-trainee
headcount rather than per-course slot count.

- `effects["technical_workshop_slots"] = 3` → `effects["technical_workshop_trainees"] = 6`.
- Helper renamed: `technical_workshop_slot_capacity` →
  `technical_workshop_trainee_capacity`.
- Engine gate split into TWO independent technical checks:
  1. **Staffing gate** (per-course, unchanged): `min(TD*2, Instructors)`
     concurrent courses.  Workshop is no longer in this min().
  2. **Workshop trainee gate** (per-trainee, new): sum of in-flight
     batch sizes ≤ `n_workshops × 6`. A 7-trainee batch tries to admit
     when 4 trainees are already in flight on one workshop → blocked
     with "Technical Workshop capacity full: 4/6 trainee seat(s)
     already in training (need 7 more for this batch)."
- New `TrainingRegistry.technical_trainees_in_flight(educator_id)`
  sums trainee headcount across active Technician-tier batches.
- `_technical_course_capacity` is now staffing-only; the workshop
  check lives inline in `_training_capacity_status`.
- New test `test_technical_workshop_caps_trainee_headcount` covers
  the 6-seat fit / over-cap fail / second-workshop unblock cycle.
- Existing tests adjusted: `test_technical_capacity_min_of_2x_td_and_instructors_staffing_only`
  reflects the staffing-only semantics; `test_technical_workshop_trainee_capacity_helper`
  replaces the slot-capacity helper test; legacy-cleanup test now also
  asserts `technical_workshop_slot*` names are gone.

**Interim lease-equivalent financing** (until the proper Lease
subsystem ships separately): Educators who don't want to commit
the workshop's full `60 Dp` from their `1500 Dp` starting capital
can finance it via the existing 1/2/3-year Bank loans at
`banker_quote_rate` (posted funding rate + 2% margin + borrower
risk). This is documented in the test docstring; a real Lease
subsystem (3-year term, annual payments in advance, repossession
on missed payment, season-delayed return on catch-up) is queued
as a separate Codex brief (`capital-equipment-lease-2026-05`).

### claude/codex-brief-training-staffing

Branch: `claude/codex-brief-training-staffing`
Target: `pre-release`

Docs-only — new Codex brief at
`requirements/codex-tasks/training-staffing-2026-05.md` for the Bug 1
follow-up Track B (staffing-based training admission redesign).

Spec captured from the 2026-05-25 design conversation:

- **Per-concurrent-course staffing**, locked for course duration:
  - Manager course: 0.5 Professor + 1 Lecturer + 2 Expertise + 1 Course
  - Technical course: 0.5 Technical Director + 1 Instructor + 1 Expertise + 1 Course
- **New `Profession.TECHNICAL_DIRECTOR`** (Manager-band) — tier-1 role
  for the technical/vocational faculty, parallel to Professor for
  academia.
- **`educator.apprenticeship_programme` capital item renamed** to
  `educator.technical_workshop` with the same `cost`/`delivery_seasons`;
  effect key `apprenticeship_slots` → `technical_workshop_slots`. The
  workshop is a **prerequisite** for Technical courses (Educator with
  zero workshops can't run them at all), with workshop slot count
  acting as an additional upper bound on the concurrent-course
  capacity: `technical_capacity = min(TD*2, Instructors, workshops)`.
- **`apprenticeship_slot_capacity` helper renamed** to
  `technical_workshop_slot_capacity`.
- **`TrainingRegistry` adds** `manager_courses_in_flight(educator_id)`
  and `technical_courses_in_flight(educator_id)` for the concurrent-
  course accounting.
- **`_training_capacity_status` rewritten** to the staffing model;
  `_consume_training_capacity` now debits per-course Expertise as well
  as the existing `Courses` resource (per-batch).
- 10 required regression tests covering capacity math, the workshop
  prerequisite, staff-locked-for-duration, expertise debiting, and the
  legacy `apprenticeship_*` rename completion.
- Save-file migration callout: old saves with
  `educator.apprenticeship_programme` in `capital_inventory` need to be
  remapped to the new key on load.

Calls out calibration follow-up: this changes training admission
cadence, so a re-tune is likely needed after the redesign lands.

Auction-stuck-at-zero fix (parked locally on
`claude/bug-auction-stuck-at-zero`, commit `2c96369`, not pushed) and
the sustenance basket model (pending on
`claude/sustenance-basket-model`) are flagged in the brief's
mini-changelog so Codex has accurate base context.

No code / tests touched. Suite still **369 passing** on
`origin/pre-release`.

### claude/sustenance-basket-model

Branch: `claude/sustenance-basket-model`
Target: `pre-release`

Replaces the legacy two-resource Food/Fish sustenance model with a
**five-resource basket** model per the 2026-05-25 spec.

**Old model** (`Player.population_food_fish_needs`):
- `food = max(0, population − 100) + transients`
- `fish = ceil(pop / 100) + ceil(educated / 8)`
- `Grain` / `Produce` / `Meat` generated **zero** sustenance demand.
- Below population 100, **zero** Food demand (the `BASE_POPULATION_SELF_FED`
  baseline assumption).

**New model**:
- Each `PEOPLE_PER_MEAL` residents (default **10**) consume **one
  meal** per season — no baseline, every resident counts.
- A meal is satisfied by **1 Food** OR **(1 Grain + 1 Produce + 1
  (Fish or Meat))**. Fish/Meat are 1:1 fungible for the protein slot.
- **Cross-substitution at 2:1**: a surplus unit of any raw ingredient
  (grain/produce/fish/meat) substitutes for a missing slot at 2 units
  → 1 slot fill. Worked example from the spec: `3 Grain + 0 Produce +
  1 Fish` → **1 meal** (1 grain native + 1 fish native + 2 grain
  substituting for the missing produce slot at 2:1).
- **Consumption order**: Food first, then raw with substitution. This
  is now an actual inventory deduction per season (the old model only
  posted demand without consuming).

**API:**

- `Player.meals_needed(extra_residents=0) -> int` — per-season meal
  count (`ceil((population + extra) / PEOPLE_PER_MEAL)`).
- `Player.consume_sustenance(meals_needed) -> (satisfied, used_dict,
  shortfall)` — mutates inventory, returns per-resource consumption.
- `Player.meals_available() -> int` — peek (no mutation); how many
  meals current inventory could satisfy.
- `Player.sustenance_shortfall_demand(extra_residents=0)` — market
  basket signal (Food / Grain / Produce / Fish / Meat at the unmet
  meals level).
- Module-level `_allocate_raw_meals(meals_needed, grain, produce,
  fish, meat)` — pure allocator with the waterfill+2:1 substitution
  logic (extracted so it's unit-testable; consumed by `consume_sustenance`
  and `meals_available`).

**Engine integration**: `TurnManager._post_population_food_demand` →
renamed `_consume_and_post_sustenance`. Each season-start: consume
sustenance from inventory, then post the shortfall basket to the
market (each of Food/Grain/Produce/Fish/Meat at `shortfall_meals`
level — intentionally overcounts in absolute units; it's a signal,
not an order book).

**Server alerts**: per-island sustenance alerts collapse from the
old per-resource Food/Fish format to a single basket-aware **"Meals"**
alert with runway computed against `Player.meals_available()`. Avoids
the per-resource runway being misleading when components are fungible.

**Removed**: `BASE_POPULATION_SELF_FED` constant. **Added**:
`PEOPLE_PER_MEAL = 10`.

**Tests**: 21 new tests in `tests/test_models/test_population_needs.py`
covering meal-count math, all `_allocate_raw_meals` edge cases (zero,
native-only, the user's spec example, ingredient-shortage,
fish/meat fungibility, partial satisfaction, target-cap), and end-to-end
`consume_sustenance` (food-first, fall-through, partial, no-op).
Two existing tests rewritten: `test_education_phase3.py` campus-load
test (basket-aware), `test_game_state_loans_policies.py` server-alert
test (single "Meals" entry).

**Calibration impact (NOT addressed here)**: this change shifts
balance — Grain/Produce/Meat now have non-zero demand (was zero);
Food demand kicks in at population 1 (was 101). The `4e56ead`
calibration is tuned against the old model. **A re-tune is likely
needed** after this lands. Not a release blocker but worth flagging
when scheduling the next calibration pass.

Suite **386 passing** (was 365 + 21 new tests).

### codex/balance-calibration-2026-05

Branch: `codex/balance-calibration-2026-05`
Target: `pre-release`

2026-05-25 rerun after the sustenance basket model, training-staffing
redesign, capital-equipment leases, and training UX improvements landed.
This supersedes the earlier calibration numbers below for the current
`pre-release` equilibrium.

Current rerun diagnosis:

- Fresh baseline against `pre-release` at `540b751` showed the Farmer
  overcorrected downward after the new sustenance/training/lease changes.
  Farmer averaged only 2.0% on the four-seed sweep while Educator,
  Banker, and Manufacturer were mildly hot.
- The main tuning change reprices the now-universal sustenance basket
  and raises Farmer seasonal raw output. This restores value to the
  island feeding every resident without reintroducing the old
  Banker/Farmer runaway pattern.
- Freight and PassengerSeats were lifted modestly, while Education
  resources were cooled slightly, to keep Transporter above the floor
  and Educator below the ceiling.
- The simulation runner now explicitly seeds AI players with
  `STARTING_DOLLOPS` instead of carrying the stale `100.0` literal.

Historical stale baseline (pre-Economy A-D and pre-AI-v2, 800 games
across seeds 42/1/7/99; included only as context):

| Role | Historical stale mean win% |
|---|---:|
| Farmer | 42.5% |
| Miner | 0.4% |
| Transporter | 0.0% |
| Educator | 1.0% |
| Banker | 54.6% |
| Manufacturer | 1.5% |
| Doctor | 0.0% |

Fresh pre-tune baseline on current `pre-release` at `540b751`, before
this rerun's balance tuning:

| Role | Seed 42, 1000g win% | Avg wealth | 4-seed mean win% |
|---|---:|---:|---:|
| Farmer | 2.3% | 1660.1 Dp | 2.0% |
| Miner | 17.5% | 2511.8 Dp | 15.0% |
| Transporter | 14.8% | 2377.3 Dp | 12.9% |
| Educator | 20.4% | 3094.7 Dp | 21.8% |
| Banker | 15.7% | 2369.1 Dp | 17.9% |
| Manufacturer | 18.0% | 2378.2 Dp | 19.9% |
| Doctor | 11.3% | 2867.8 Dp | 10.6% |

Final post-tune verification on this rerun:

| Role | Seed 42, 1000g win% | Seed 42, 5000g win% | Avg wealth (5000g) | 4-seed mean win% |
|---|---:|---:|---:|---:|
| Farmer | 14.7% | 13.1% | 2419.3 Dp | 13.4% |
| Miner | 14.7% | 13.9% | 2438.3 Dp | 13.0% |
| Transporter | 15.6% | 14.1% | 2476.2 Dp | 14.9% |
| Educator | 17.0% | 18.3% | 2975.0 Dp | 17.9% |
| Banker | 12.9% | 14.6% | 2373.0 Dp | 14.9% |
| Manufacturer | 12.2% | 13.1% | 2375.8 Dp | 12.9% |
| Doctor | 12.9% | 12.9% | 2905.2 Dp | 13.1% |

Verification commands:

- `PYTHONPATH=. .venv/bin/python -m island_traders.simulation.runner --games 1000 --years 3 --seed 42`
  passed acceptance after tuning.
- `PYTHONPATH=. .venv/bin/python -m island_traders.simulation.runner --games 200 --years 3 --seeds 42,1,7,99`
  produced four-seed means within the target band; no role was 0% and
  no per-seed role exceeded ~25%. One 200-game seed sample had
  Manufacturer at 8.5%, so watch Manufacturer variance in future runs,
  but the sweep mean and long seed-42 run are both in band.
- `PYTHONPATH=. .venv/bin/python -m island_traders.simulation.runner --games 5000 --years 3 --seed 42`
  produced the final long-run table above.

Release-blocking balance pass after Economy A-D and AI Trading v1/v2.
The first fresh baseline exposed a new post-AI-v2 failure mode:
Transporter was winning nearly every AI-only game. Diagnosis found
three structural issues before event-chart tuning:

- External depositor loans (`lender_id = -1`) crashed simulation
  repayment; repayment now treats those as cash paid to external
  depositors.
- Direct buys from posted offers debited buyers but did not credit the
  resting seller; sellers now receive the trade cash.
- Manufacturer AI ignored Freight surcharges and live equipment bids;
  it now buys required Freight and prioritises visible demand.

Balance levers adjusted:

- Reduced Transporter and Miner raw output from post-AI-v2 levels.
- Rebalanced Farmer seasonal output, Educator/Doctor production, key
  commodity prices, equipment prices, Freight/PassengerSeat values,
  and insurance premiums.
- AI now keeps no-demand services/IP (`HealthServices`, `Vaccine`,
  `Patents`, `PassengerSeats`) unless a bid exists, avoiding stale
  asks that removed value from final scoring.
- Added focused regression tests for external depositor repayment,
  seller payment on direct offer fills, Manufacturer Freight buying,
  and bid-aware Manufacturer line choice.

Historical stale baseline (pre-Economy A-D and pre-AI-v2, 800 games
across seeds 42/1/7/99; included only as context):

| Role | Historical stale mean win% |
|---|---:|
| Farmer | 42.5% |
| Miner | 0.4% |
| Transporter | 0.0% |
| Educator | 1.0% |
| Banker | 54.6% |
| Manufacturer | 1.5% |
| Doctor | 0.0% |

Fresh pre-tune baseline on this branch after the simulation-blocking
external-depositor repayment fix, before balance tuning:

| Role | Seed 42, 1000g win% | Avg wealth | 4-seed mean win% |
|---|---:|---:|---:|
| Farmer | 0.8% | 2073.6 Dp | 1.0% |
| Miner | 0.2% | 1312.3 Dp | 0.2% |
| Transporter | 98.9% | 8556.5 Dp | 98.5% |
| Educator | 0.0% | 1411.9 Dp | 0.0% |
| Banker | 0.1% | 1717.4 Dp | 0.2% |
| Manufacturer | 0.0% | 1248.1 Dp | 0.0% |
| Doctor | 0.0% | 1271.9 Dp | 0.0% |

Final post-tune verification:

| Role | Seed 42, 5000g win% | Avg wealth | 4-seed mean win% |
|---|---:|---:|---:|
| Farmer | 11.1% | 2440.7 Dp | 11.5% |
| Miner | 15.1% | 2492.8 Dp | 14.5% |
| Transporter | 16.6% | 2626.8 Dp | 17.5% |
| Educator | 18.3% | 2894.5 Dp | 17.2% |
| Banker | 13.6% | 2367.1 Dp | 14.6% |
| Manufacturer | 14.6% | 2409.9 Dp | 13.5% |
| Doctor | 10.6% | 2840.5 Dp | 11.1% |

Verification:

- `PYTHONPATH=. .venv/bin/python -m island_traders.simulation.runner --games 1000 --years 3 --seed 42`
  passed acceptance before the final long run.
- `PYTHONPATH=. .venv/bin/python -m island_traders.simulation.runner --games 200 --years 3 --seeds 42,1,7,99`
  produced 4-seed means within the target band; no role was 0% and no
  per-seed role exceeded ~25%.
- `PYTHONPATH=. .venv/bin/python -m island_traders.simulation.runner --games 5000 --years 3 --seed 42`
  produced the final table above, with every role within ±5pp of 14.3%.
- `PYTHONPATH=. .venv/bin/python -m pytest -q` → **369 passing**.

### claude/refresh-codex-calibration-brief

Branch: `claude/refresh-codex-calibration-brief`
Target: `pre-release`

Docs-only — refresh of
`requirements/codex-tasks/balance-calibration-2026-05.md` to reflect
the work that landed between the brief's original 2026-05-18 draft and
today's `pre-release` tip (`4e56ead`). Headlines:

- **Sequencing dependencies marked satisfied** — both prerequisites
  the brief originally waited on (Economy Lifecycle Phases A–D, AI
  Trading v1+v2) are now merged. Brief is unblocked.
- **Baseline table flagged as historical-stale** — the old win-rate
  numbers (Banker 54.6%, Farmer 42.5%, Transporter / Doctor 0%) were
  measured pre-A-D and pre-AI-v2 and should not be taken as ground
  truth. New "What is expected to shift" subsection lists testable
  hypotheses (Banker should come down from MBA reserve gate, Farmer
  should come down from combine maintenance, all roles should shift
  from 700→1500 cash).
- **Mini-changelog added** — covers Economy A–D, AI Trading v1 + v2,
  UX phases 1–6, training-return defect fix, WS reconnect race fix,
  order override rule, market matcher fix. Saves Codex an
  archaeology pass.
- **Branch tip + suite baseline refreshed** — `pre-release` at
  `4e56ead`, **365 passing**.
- **Three-table RELEASE_NOTES requirement** — historical-stale,
  fresh-pre-tune-baseline, final-post-tune. Forces Codex to record
  what shifted just from the prereq work (without their tuning).
- **Hand-off + after-this-lands sections** — explicit do-not-merge
  rule (Claude wants a final read before tagging `v0.1.0`) plus the
  v0.1.0 ship path (pre-release → master → tag) called out.
- **Out-of-scope list expanded** — adds `server/` (WS reconnect
  hardening), `models/loan.py`, `models/insurance.py`,
  `models/market.py` matching semantics.
- **AI markup constants flagged as tuning levers** — `AI_OFFER_MARKUP`,
  `AI_ARBITRAGE_MIN_MARGIN`, `AI_MIN_LOAN_PRINCIPAL`,
  `AI_DEBT_CEILING_MULTIPLIER`.

No code / tests change. Suite still **365 passing**.

### codex/ai-trading-v2

Branch: `codex/ai-trading-v2`
Target: `pre-release`

AI finance + investment lifecycle pass:

- AI Bankers now offer one-year loans to capital-short AI borrowers,
  using the real `banker_quote_rate` and Phase D1 reserve/MBA gate.
- Capital-short AI borrowers now take AI Banker loans when they do not
  already have an active borrowing position.
- AI borrowers now roll over loans one season before maturity when they
  cannot afford repayment.
- AI players now use `INVEST` mid-game to claim the cheapest unowned
  opening-catalogue item when they have sufficient cash.
- Dynamic offer markup was left deferred; this branch keeps the pricing
  model unchanged and focuses on the required finance/invest behaviours.

Added 5 AI tests; expected suite count is 365 passing.

### claude/codex-brief-ai-trading-v2

Branch: `claude/codex-brief-ai-trading-v2`
Target: `pre-release`

Docs-only — new Codex brief at
`requirements/codex-tasks/ai-trading-v2.md` for the finance + invest
follow-up to the shipped `codex/ai-trading` work.

**Why a v2 brief.** The original `requirements/codex-tasks/ai-trading.md`
brief was fully executed in commit `4a65a9a` ("Add proactive AI market
trading", 2026-05-17). All five behaviours it scoped (lists offers,
places bids, Transporter air tickets, cross-island arbitrage, deal
valuation via last-deal / best-offer / formula) are live, covered by
six green tests in `tests/test_engine/test_ai.py`. The v2 brief picks
up the finance + investment lifecycle actions the original deferred:

1. **AI Banker proactively offers loans** to capital-short AI
   borrowers (mirrors the existing `_ai_offer_insurance` pattern).
   Honours the Phase D1 Banker capital-reserve / MBA gate.
2. **AI borrowers take loans** when capital-short and no active
   borrowing position exists.
3. **AI rolls over loans near maturity** when it can't repay the
   `repayment_amount`.
4. **AI uses INVEST mid-game** for opening-catalogue items it didn't
   claim during the Investing Phase.
5. *(optional)* Dynamic per-(player, resource) offer markup that
   adapts to last-season fill rate.

The brief also includes a mini-changelog of everything that has
shipped since the original AI-trading brief was drafted (Economy
Phases A–D, order override rule, market matcher fix, 60% workforce
cap, UX phases 1–6 server payload, training-return fix, WS
reconnect-race fix) so Codex has accurate context.

**Sequencing note in the brief.** AI Trading v2 lands *before* the
release-blocker sim calibration
(`requirements/codex-tasks/balance-calibration-2026-05.md`) so the
balance pass tunes against the final AI behaviour.

No code / tests touched. Suite still **360 passing**.

### claude/bug-action-menu-race

Branch: `claude/bug-action-menu-race`
Target: `pre-release`

**Fixes TODO bug #2 — "Action menu stops displaying for some players"**
(multiplayer blocker).

**Diagnosis.** Not the TLS / `_send_and_wait` surface the original TODO
note suspected — those paths were already hardened in earlier work.
The real root cause was a reconnect race in
`island_traders/server/app.py` around the WebSocket-to-player table:

1. Browser tab A opens, registers WS_A: `_ws_connections[R][P] = WS_A`.
2. User refreshes / loses network briefly / opens a second tab. The
   new connection arrives and `register_ws` runs on the asyncio loop
   thread: `_ws_connections[R][P] = WS_B`.
3. Some time later WS_A's network handler finally notices the
   disconnect and its `finally` block fires
   `manager.unregister_ws(room_id, player_id)`.
4. The old code blindly `pop`'d the entry — **evicting WS_B from the
   table even though WS_B was still alive and connected.**
5. Subsequent `_thread_safe_send` (including the `choose_action`
   payload) found `None` for the slot and silently dropped every
   message. Player saw an empty action panel.

The fix is two parts:

- **Identity-aware unregister.**
  `unregister_ws(room_id, player_id, ws=None)` now takes an optional
  socket argument and only removes the entry if the stored socket is
  the same object. Returns `True` iff something was actually removed.
  The endpoint's `finally` passes `websocket` so a late unregister
  from an already-superseded socket is a no-op.
- **Lock around the connection table.**
  New `GameManager._ws_lock` (a `threading.Lock`) wraps every read /
  write of `_ws_connections` — `register_ws`, `unregister_ws`,
  `_thread_safe_send`, `_thread_safe_broadcast`. The asyncio loop
  thread (endpoint handlers) and the game thread (server-to-client
  sends) both touch this table, so a plain dict isn't enough.

Bonus side-effect: `lp.connected = False` in the endpoint's `finally`
now also only fires when the unregister succeeded, so the lobby
display no longer falsely flips to "disconnected" right after a
quick reconnect.

**Regression tests** in `tests/test_server/test_ws_reconnect_race.py`
(5 new tests):

1. `test_register_then_unregister_removes_the_entry` — happy path
2. `test_unregister_does_not_remove_newer_replacement` — the bug
3. `test_unregister_without_ws_arg_falls_back_to_force_pop` —
   legacy / forced-cleanup signature preserved
4. `test_unregister_returns_false_when_slot_already_empty` —
   double-disconnect doesn't raise
5. `test_thread_safe_send_uses_current_socket_after_reconnect` —
   table lookup returns the reconnected socket, not the old one

Suite **360 passing** (was 355 + 5 new tests).

### claude/ux-plan-status-update

Branch: `claude/ux-plan-status-update`
Target: `pre-release`

Docs-only — annotate `requirements/implementation-plans/review-ux-plan.md`
with a 2026-05-24 status block now that every in-scope UX phase has
shipped to `pre-release`. Adds:

- Status table per phase with merge commit references.
- Note on the training-return defect (incidental fix surfaced by the
  Phase 3 Personnel popup) — merged as `399165e`.
- "Follow-ups identified during implementation" section listing the
  five seams worth picking up next (state-based action gating, server
  hint adoption, in-modal preselection for non-Market actions, inventory
  valuation rule, capacity/deficit section, inline action affordances
  inside Loans / Insurance popups).
- Replaces the as-planned sequencing diagram with the as-shipped order
  (popup-shell landed in parallel with Codex Phase 1; Phase 6 split
  into 6a starter + 6b followups).
- Marks the "Coordination" section as historical.

No code / tests change. Suite still **355 passing**.

### claude/training-return-bug

Branch: `claude/training-return-bug`
Target: `pre-release`

**Fixes the playtest 2026-05-24 defect** flagged in
`claude/ux-popup-followups`'s RELEASE_NOTES and `TODO.md` Bugs:
self-trained workers never graduated / advanced their `training_level`.

**Diagnosis.** The defect was **only** in the self-training path
(`engine/turn.py::_action_request_training` Educator shortcut at line
~828). The cross-island path was always wired correctly:

| Path | Registry side | Workforce side |
|---|---|---|
| Cross-island (`_dispatch_training`) | `training.dispatch(...)` | `workforce.dispatch_for_training(worker_ids)` |
| Self-training (Educator shortcut) | `training.dispatch(...)` | **missing** ← bug |

At the return tick, `Game._process_training_returns` correctly flips
the registry-side status from `DISPATCHED → COMPLETED` and then calls
`workforce.return_from_training(worker_ids, target_profession)`. But
`return_from_training` is a guarded no-op for workers whose
`in_training` flag is still False — so the self-trained worker stays
at their original profession / training level. The new Personnel popup
(Phase 3) made this visible: dispatched batches accumulated with
`seasons_remaining = 0` and a `return_season` already in the past.

**Fix.** One-line addition in the self-training shortcut, mirroring
what `_dispatch_training` already does for the cross-island path:

```python
self.training.dispatch(req.batch_id, year, season_index)
player.workforce.dispatch_for_training(req.worker_ids)   # ← added
```

On-island training still happens at the Educator's college; the
worker is "in class" for the course duration (`in_training=True`,
out of `active_workers`) rather than at their normal job, then
returns and graduates exactly like a cross-island trainee.

**Regression tests** in `tests/test_engine/test_training_returns.py`
(3 new tests, end-to-end through `Game._process_training_returns`):

1. `test_cross_island_trainee_returns_at_return_season_with_upgraded_profession`
   — Nurse, 1 season away, correct Y/S match required.
2. `test_cross_island_doctor_three_season_round_trip` — Doctor,
   3 seasons; verifies the longer course only releases at S3.
3. `test_self_training_round_trip_advances_worker_training_level` —
   exercises the actual `_action_request_training` path so the new
   workforce dispatch is verified end-to-end.

Suite **355 passing** (was 352 + 3 new tests).

### claude/ux-market-filter

Branch: `claude/ux-market-filter`
Target: `pre-release`
Depends on: `claude/ux-hints-to-actions` (built on Phase 4's hint state;
merge Phase 4 first).

UX review Phase 5 — Market Buy first-viewport filtering + hint focus
(Mockup 3).

**What:** The Market Buy modal no longer renders one flat 11-row
table where dormant commodities crowd the urgent ones. Rows now sit
in three tiers:

1. **Hint-mentioned** — resources currently surfaced by a Decision
   Hint (sustenance runway, input shortfall, or the resource the
   player clicked Open on).
2. **Live market** — resources with at least one standing ask or bid.
3. **Dormant** — everything else, hidden behind a *"Show all other
   commodities (N dormant)"* `<details>` expander so they don't
   dominate the first viewport.

When the modal is opened via a hint's Open button, the hinted resource
floats to the top of Tier 1, picks up a gold left-edge ring + tinted
background (`.mkt-row-focus`), and the row auto-scrolls into view.
A one-line banner above the table names the hinted resource so the
player sees why the modal opened where it did.

**Hint state plumbing (Phase 4 follow-through):**

- `_currentHintResources` (Set, populated by `renderDecisionHints`)
  drives Tier 1 detection independent of which player clicks.
- `_pendingHintTarget` (one-shot global, set in `_actOnHint`, cleared
  on first read in the next modal) carries `{action, resource}` —
  e.g. `{action: 'buy_market', resource: 'Oil'}` — so the modal
  knows which row to focus.
- Sustenance hints now carry `target_resource: alert.resource`;
  input-shortfall hints carry `target_resource` = first key of
  `inputs_short`.
- `_renderHintOpenButton` accepts an optional `payload` arg passed
  through to `_actOnHint`.

**Refactor:** Extracted `_renderMarketBuyRow(res, d, focusResource)`
and `_marketBuyHeaderRow()` so the tier 1+2 and tier 3 tables share a
single row implementation (identical columns, same input names — the
existing `submitMarketBuy()` aggregation still picks up inputs from
both sub-tables via `document.querySelectorAll`).

**CSS additions:** `.mkt-row-focus` (focused-row gold ring + tint),
`.mkt-dormant` (collapsed expander styling with a rotating chevron).

**Edge cases:**

- If every commodity is dormant (no hints + no live depth), the
  primary table is replaced with a one-line empty-state notice and
  every row lives in the collapsed expander.
- If there are no dormant commodities (everything has activity or is
  hinted), the expander is omitted entirely.
- If `_pendingHintTarget` is set for a non-`buy_market` action and
  Market Buy happens to open afterwards anyway, focus is left null —
  the target only applies to its matching modal type.

**Scope discipline:**

- No engine / server changes. Pure client.
- The `<details>` element is uncontrolled — collapsed state doesn't
  persist across modal close/reopen. Matches the brief's
  "*should not dominate the first viewport*" requirement.

Suite **352 passing** (no test changes — pure client refactor).

### claude/ux-hints-to-actions

Branch: `claude/ux-hints-to-actions`
Target: `pre-release`

UX review Phase 4 — Decision Hints become actionable.

**What:** Each rendered hint now carries a `triggers_action` field
naming the `TurnAction` value that addresses it (e.g. an "Unblock
Oil" hint triggers `buy_market`; an "Add workers for X" hint triggers
`request_training`). The hint card grows a gold "Open" button:

- When the action menu is currently open for this player, the button
  calls `sendResponse(action)` — the same effect as clicking the
  corresponding action menu button directly. **No auto-submit**: the
  server then surfaces the action's modal (Market Buy, etc.) and the
  player still confirms the final game action there.
- When the action menu is not open (waiting on other players, between
  prompts, etc.), the button is disabled with a "Wait for your action
  prompt" tooltip.

**Recommendation bridge:** The set of currently-hinted action values
is tracked in `_currentHintActions`. When `showActionPrompt` renders
the grouped action menu (Phase 2 work), the matching action button
picks up the gold `.recommended` outline — same affordance Codex's
Phase 1 payload reserved via the `recommended: true` per-option flag
(server-side `recommended` is still default-false as of Codex's
shipped payload; this layers a client-driven view on top of it).

**Hint → action mapping:**

| Hint kind | Triggers |
|---|---|
| Sustenance shortfall (`*_alerts`) | `buy_market` |
| `Produce X` (output is producible) | `produce` |
| `Unblock X` (input shortfall) | `buy_market` |
| `Add workers for X` | `request_training` |
| `Capital limits X` | `purchase_capital` |
| `Underwrite X` (service output) | _(no direct action; service-side flow)_ |
| Fallback "Check market and deals" | _(no direct action)_ |

The brief's `loan_*` and `insurance_review` targets exist in Codex's
server-side `decision_hints` field but the client's own
`renderDecisionHints` does not emit those kinds today, so no UI
shortcut is added for them in this branch. They can be picked up
when the client switches over to consuming `gameState.decision_hints`
directly (a follow-up).

**Render synchronisation:** `showActionPrompt` and `hideOverlay` now
call `renderGameState()` so hint cards re-render their `Open` buttons
and the action menu picks up `recommended` outlines as the prompt
opens / closes. Cheap re-render — gameState is already cached.

**Scope discipline:**

- No engine / server changes. Pure client.
- In-modal preselection / filtering (Phase 5 of the plan, e.g. Market
  Buy with the hinted resource at the top of the table) is deferred —
  the seam is now in place for Phase 5 to plug into.
- Client-side hint generation is unchanged in scope; only `target`
  and `triggers_action` are added per hint.

Suite **352 passing** (no test changes — pure client refactor).
### claude/ux-popup-followups

Branch: `claude/ux-popup-followups`
Target: `pre-release`
Independent of Phases 4/5 — branched directly off `pre-release` so it can
merge in any order.

UX review Phase 6 follow-up — Loans / Insurance / Inventory detail
popups, closing out the §5 "standardize detail surfaces" punch list.

**What:** Each of the three sidebar sections grows a small `⊕`
"Details" button in its header (matching the existing Production
Capacity `⚠` pattern). Click opens a popup using the shared
`showPopup` shell and the `.popup-table` styling from
`claude/ux-personnel-popup`.

- **Inventory popup** — table of held resources sorted by quantity
  descending, with current ask price and estimated value (qty × ask)
  per row. Footer row shows totals.
- **Insurance popup** — table of active policies with insurer name,
  premium paid, expiration, seasons remaining, and cancel refund.
  Policies expiring next season (`seasons_remaining ≤ 1`) get a
  gold-tinted row.
- **Loans popup** — table of active loans with role
  (Borrowing / Lending), counterparty name, principal, rate, term,
  repayment amount, maturity, seasons to maturity. Loans maturing
  next season get a gold-tinted row. Footer shows totals: borrowing
  repay due, lending repay incoming.

**Plumbing:**

- New `_playerNameLookup()` helper builds an `{id → name}` map from
  `gameState.players` for counterparty / insurer display.
- Empty states: "Inventory is empty.", "No active policies.", "No
  active loans." — same `empty-state` styling as the Personnel
  popup.
- Sidebar summaries are unchanged (still render their compact view);
  the popup is purely additive.

**Notes against the brief (`review-ux.md` §5):**

- Production Constraints, Market Board, Market Buy, Personnel
  already use the shared shell from earlier branches. With this
  branch landing, all six surfaces named in §5 (Production,
  Personnel, Market Board, Loans, Insurance, Inventory) share the
  same modal chrome.
- Action entry points inside the popups (e.g. an inline "Cancel
  policy" button) are deferred — those require Phase-4-style
  send-response-during-prompt plumbing and the existing
  `MANAGE_INSURANCE` / `ROLLOVER_LOAN` actions already cover the
  workflows.

**Defect note (separate to the popup work):** `TODO.md` Bugs section
gains a new entry — *"Trainees never return from training"* —
flagged during playtest 2026-05-24. Workers dispatched for training
stay in the `dispatched` state past their `return_year` /
`return_season` and never re-join the home workforce. Likely a
missing per-season sweep in the season bookkeeping that should
advance dispatched batches whose `return_*` ≤ current tick into
`COMPLETED`. The new Personnel popup makes this visible:
`seasons_remaining = 0` rows accumulate. Not fixed in this branch.

Suite **352 passing** (no test changes — pure client refactor
plus a TODO entry).

### claude/ux-personnel-popup

Branch: `claude/ux-personnel-popup`
Target: `pre-release`
Depends on: `claude/ux-popup-shell` (merge popup-shell first).

UX review Phase 3 — Personnel detail popup (Mockup 2).

**What:** The sidebar Personnel summary is now clickable. Click opens
a popup with two sections, both driven entirely by the existing game
state payload:

- **Training Pipeline** — table of in-flight batches consuming the
  `training_pipeline` field added by `codex/ux-server-payload`. One
  row per batch with: trainee count, target profession, status,
  educator, transport mode, fee (Dp), return season/year, seasons
  remaining. Counter-messages (e.g. "Try 30 Dp instead") render
  beneath the table, one per batch that has one. Empty pipeline
  degrades to *"No workers currently in training."*
- **Staffing** — band table (Managers / Technicians / Workers) with
  active and in-training counts, plus a total row. Footer shows
  workforce active/total, efficiency %, and population — the same
  numbers the sidebar shows individually, gathered in one place.

**UI plumbing:**

- `s-personnel` sidebar element gets `onclick="showPersonnelPopup()"`
  and a tooltip; the existing `personnel-breakdown` CSS class gets
  `cursor:pointer` + a subtle hover brightness.
- New popup uses the `showPopup` shell from
  `claude/ux-popup-shell` — single Close button in the standard
  footer, no per-popup chrome.
- New `.popup-section`, `.popup-table`, `.empty-state`, `.batch-notes`,
  `.staffing-extras` CSS rules — reusable by the remaining Phase 6
  popups (Loans / Insurance / Inventory) when they land.
- `_TRAINING_STATUS_LABEL` table maps the enum values from
  `island_traders/models/training.py::TrainingStatus` to display
  text (`awaiting_educator` → "Awaiting educator", etc.).

**Scope discipline:**

- No engine or server-payload changes. Pure client refactor.
- "Capacity/deficit summary: missing professions for the island
  staffing plan and current university slot availability" from the
  brief is deferred — the data is in `pd["capacity"]` but adding a
  third popup section is out of scope for this branch and depends on
  Phase 4 hint plumbing to be meaningful.
- Inventory popup (also Phase 6 §5) is deferred to a follow-up branch
  to keep this one focused on Personnel.

Suite **352 passing** (no test changes — pure client refactor).
### claude/ux-action-grouping

Branch: `claude/ux-action-grouping`
Target: `pre-release`

UX review Phase 2 — grouped action menu (Mockup 1).

**What:** Rewrites `showActionPrompt` in
`island_traders/server/static/index.html` to render the per-season
action prompt as labelled groups instead of one flat button row.
Consumes the structured option payload that Codex's Phase 1 branch
(`codex/ux-server-payload`) added: each option's `group`, `enabled`,
`disabled_reason`, and `recommended` fields drive the layout directly.

- Canonical group order: Production / Trade / People / Capital /
  Finance / Info (stable, defined client-side in
  `ACTION_GROUP_ORDER`).
- Empty groups are skipped; unknown-group labels (forward-compat) are
  appended at the end.
- `Produce` keeps the existing gold `.highlight` style.
- `recommended: true` adds a `.recommended` outline (Phase 4 will set
  this from Decision Hint targets — currently always false).
- `enabled: false` disables the button and shows the
  `disabled_reason` as a native tooltip (`title` attribute). Disabled
  buttons do not bind a click handler so the user can't accidentally
  send a server message that the engine would reject anyway.

**CSS additions:** `.action-groups`, `.action-group`,
`.action-group-label`, `.action-btns button.recommended`,
`.action-btns button[disabled]`. The existing `.action-btns` flex-wrap
layout is unchanged inside each group, so buttons reflow naturally on
narrow widths and groups stack vertically.

**Back-compat:** options that arrive without `group` fall through to
the `Info` bucket — keeps the dashboard functional even if rolled
back to a pre-Phase-1 server.

**Verification:** Suite **352 passing**. Pure client refactor; no
Python tests exercise the prompt rendering. Browser pass deferred to
the PR review (no automated DOM-level test scaffolding exists in this
repo today).

### claude/economy-lifecycle-spec

Branch: `claude/economy-lifecycle-spec`
Target: `pre-release`

**Docs-only — requirements spec.** No code/test changes (suite
unchanged at 297). Captures product-owner direction (2026-05-18) for a
cross-island economic-dependency feature set:

- New `requirements/economy-lifecycle-2026-05.md`: worker
  lifecycle/retirement (general age system, Agriculture bootstrap),
  universal capital lifespan + per-season maintenance, a Banker
  **capital-reserve / MBA leverage** model, and an economy rebalance
  (per-player cash 700→1500, Mining Oil 4→8, Agriculture Food →15).
  Phased A–E, independently mergeable; A–D engine work, E = RULES.md +
  calibration handoff.
- **Banker model (refined 2026-05-18):** fractional-reserve, not a
  binary gate. Loans are backed by the bank's own capital at a reserve
  ratio (**0.50** with <3 MBA Banker Managers, **0.20** with ≥3); own
  capital earns full interest, externally-sourced capital earns only
  the margin over the posted rate at issuance; reserved own capital is
  locked until the loan resolves. Banking starts with **0** MBA
  managers (intentional early constraint, ~2× leverage) and trains up
  (2 Professors + 3 Courses, 2 seasons) to ~5×. Without a
  `banker.computing_centre` capital item, loan applications take +1
  season to disburse. No MBA bootstrap roster.
- **Loan terms & negotiation (refined 2026-05-19):** Banker may quote
  any rate (formula = suggested default) and the applicant can
  **counter** (reuses the training counter pattern); indicative
  **1/2/3-year** term-rate quotes; 2/3-year loans settle interest
  annually and roll the **original amount at the original rate** until
  the final year (rate locked at origination) — distinct from the
  shipped #6 post-maturity opt-in refinance.
- New `requirements/role-player-guides.md`: on-demand per-role
  instruction beyond the acquisition intro (esp. the Banker lending
  rules), single content source shared with RULES.md; scheduled after
  economy Phase D / paired with Phase E. TODO entry under Dashboard &
  UX.
- `TODO.md`: Economy Lifecycle section with the A–E checklist.
- Annotates `codex-tasks/balance-calibration-2026-05.md` with a
  **sequencing dependency**: calibration must run *after* economy
  Phases A–D land (this feature deliberately re-balances the
  over-dominant Banker/Farmer, so calibrating the current economy would
  be wasted).

Decisions locked via AskUserQuestion: 1500/player; general retirement
(Agriculture first, near-retirement seeding as a tuning lever); MBA as a
credential on existing Banker Managers; universal capital wear.

### codex/ux-server-payload

Branch: `codex/ux-server-payload`
Target: `pre-release`

Server-side payload support for the UX review mockups:

- Action prompts now include grouped option metadata with enabled state,
  disabled reasons, and a default `recommended` flag.
- Game state now exposes each player's active training pipeline, including
  canonical training status, educator, transport, return timing, and counter
  message fields.
- Finance is hidden from market quote/history data while retaining the enum
  for compatibility with the Banker service model.
- Decision hints now include structured targets so clients can open focused
  popups without parsing display text.

### claude/ux-popup-shell

Branch: `claude/ux-popup-shell`
Target: `pre-release`

UX review Phase 6 starter — standardised info-popup shell. Lands the
shared modal chrome that subsequent UI phases (Personnel popup, etc.)
will plug into.

**What:**

- New `showPopup(title, body, opts)` helper in
  `island_traders/server/static/index.html`. Adds a standard
  right-aligned footer with a Close button by default; callers can pass
  `footerActions` for custom buttons (Market Buy uses Total + Buy +
  Cancel).
- New `.popup-footer` CSS rule (flex, right-aligned, gap, top-margin).
- Refactored three existing popups to use the shell:
  - `showConstraintPopup` — was manipulating `dlg-title` / `dlg-body`
    directly and baking its own Close button.
  - `showMarketBoardPopup` — was baking its own Close button into the
    body.
  - `showMarketBuyPopup` — now uses `footerActions` so the Total / Buy /
    Cancel line is in the standard footer rather than the body.

**Scope discipline:** `showDlg` is untouched and remains the helper for
IO-driven prompts (option pickers, quantity input, confirm) — those
have a different lifecycle (`sendResponse` / `CANCEL_SENTINEL`). The
unrelated player-onboarding modal (`hideOverlay` flow at line ~1394)
was not touched. New popups (Personnel, Loans, Insurance, Inventory)
are scheduled for follow-up branches alongside Phase 3, per the plan
in `requirements/implementation-plans/review-ux-plan.md`.

Suite **352 passing** (no test changes — pure client refactor; suite
size matches Codex's Phase 1 baseline).

### claude/order-override-and-invest

Branch: `claude/order-override-and-invest`
Target: `pre-release`

Two requirements from continued live testing.

**1. New bid/ask overrides the player's prior orders on that resource.**
Replaces yesterday's cumulative-merge rule. Any new `post_bid` /
`post_offer` now calls `Market.cancel_player_orders(player_id, rtype)`
first, which:

- Cancels every standing bid AND ask that player has on that resource.
- Refunds resources from any resting ask back to the seller.
- Decrements `market.supply` / `market.demand` by the unsold remainder
  so the price formula doesn't see the cancelled depth.

A player can therefore only hold one standing order per resource at a
time. Switching sides (e.g. ask → bid) cancels the prior ask and
refunds its inventory. Other players' orders and orders on other
resources are untouched.

The 5 cumulative-merge tests added in
`claude/cumulative-orders-workforce-cap` are replaced with 6 override
tests covering all four cancel-cases plus supply/demand counter
decrement.

**2. New `TurnAction.INVEST` — opening catalogue stays open.**
Items from the player's role catalogue that they don't currently own
remain takeable post-Investing-Phase. Adds:

- `_action_invest(player, result, year, season)`: lists role-catalogue
  items the player doesn't own; player picks; cost paid in Dp; item
  delivered immediately (acquired_tick = current_tick — no Manufacturer
  transit, distinct from `PURCHASE_CAPITAL`).
- Wired into the action dispatch alongside the other turn actions, so
  the web UI button renders automatically and the CLI menu surfaces
  "Invest" as an option.
- Tests cover: chosen item added + cost debited + acquired_tick set;
  already-owned items omitted from the choice list; insufficient Dp →
  refuse; fully-taken catalogue → "No remaining opening investments."

> The action is distinct from `PURCHASE_CAPITAL` on purpose: Invest is
> the post-Investing-Phase fast lane for items the player passed on at
> game start; Purchase Capital is the commercial mid-game purchase from
> the Manufacturer with its normal `delivery_seasons` transit and
> Phase C lifecycle implications.

Suite **346 passing** (337 baseline − 5 cumulative tests + 6 override
tests + 4 invest tests + 4 other deltas).

### claude/cumulative-orders-workforce-cap

Branch: `claude/cumulative-orders-workforce-cap`
Target: `pre-release`

Two requirements from live `:8001` testing.

**1. Cumulative bids & asks.** `Market.post_offer` / `post_bid` now
merge a new order into an existing same-season same-(player, resource,
price) standing order rather than spawning a separate book entry —
adding to a position cumulates instead of cluttering the depth list.
The matching rules already shipped with the defect-1 fix (cheapest
asks fill first; within-price FIFO via stable sort; walk to the next
price if still within the bid) remain in force.

**2. Workforce capped at 60% of population.** `Player.available_unskilled`
now returns `max(0, ⌊0.60 × population⌋ − workforce.count)` — a hard
cap on the total workforce. Replaces the legacy
`UNSKILLED_RECRUITMENT_RATIO = 0.5` rule (which scaled with non-worker
residents rather than capping the total). New constant
`MAX_WORKFORCE_FRACTION_OF_POPULATION = 0.60`.

Suite **337 passing** (326 baseline + 5 cumulative-order tests + 6
workforce-cap tests).

### claude/market-matcher-and-turn-label-fix

Branch: `claude/market-matcher-and-turn-label-fix`
Target: `pre-release`

**Defect fixes** found during live `:8001` testing.

**1. Market matcher — bids and asks now actually cross.**
`Market._auto_match_bid` / `_auto_match_offer` previously matched only
on **exact-price equality** AND **only when the order's quantity fit
inside the resting order entirely** (`tests/test_models/test_market.py
::test_bid_does_not_auto_resolve_when_quantity_exceeds_offer` literally
codified the bug as expected behaviour). Net effect on the live game:
players reporting "trades don't settle even within a small range".

Rewritten to standard exchange semantics:

- Match when `bid_price >= ask_price` (cross when the bid covers the
  ask, not just when they're equal).
- **Resting (older) order sets the trade price** — the new order is
  the price-taker, getting the better side of the spread.
- **Partial fills supported**: a new order walks the opposite side in
  best-price-first order (asks ascending / bids descending), consuming
  `min(remaining, remaining)` slice by slice until exhausted or no
  remaining cross.

Tests: the broken-codified test is replaced with
`test_bid_partially_fills_when_quantity_exceeds_offer`; new tests cover
crossed-price matching at both the ask price and the bid price, a
non-crossing "bid below all asks" case, and a multi-slice walk
(`test_bid_walks_multiple_resting_asks_for_partial_fills`).

**2. "Turn" terminology removed from per-player headers.**
Players seeing log lines like `--- Bravo's turn (Education, Research,
Manufacturing) ---` were reading them as sequential play, but the
server runs `parallel_mode=True` (one thread per human, concurrent
within a season). Renamed at all three sites:

- `engine/turn.py`: `--- Bravo (roles) — actions this season ---`
- `cli/prompts.py`: `Bravo (roles) — choose an action:`
- `cli/display.py`: `Bravo — choose an action:`

No engine behaviour change — the headers always referred to a single
player's action menu, not a global turn order.

Suite **330 passing** (326 baseline + 4 net new market tests).

### claude/economy-phase-d

Branch: `claude/economy-phase-d`
Target: `pre-release`

**Economy Lifecycle Phase D1** — Banker capital-reserve / MBA-leverage
model (the headline Banker nerf, the principal balance lever in this
feature set). Supersedes the earlier "no loans without 3 MBAs" binary
gate with a proper fractional-reserve mechanic.

**Behaviour:**

- `Worker.has_mba` field (Manager-band Banker workers only).
- New constants: `MBA_RESERVE_RATIO_BASE=0.50`,
  `MBA_RESERVE_RATIO_QUALIFIED=0.20`, `MBA_QUALIFIED_THRESHOLD=3`.
- Helpers `TurnManager._mba_banker_count(banker)` and
  `_banker_reserve_ratio(banker)` — `0.50` while <3 MBA Banker
  Managers are active, `0.20` once ≥3 are.
- Every loan now funds as **own + external**: bank commits `r·P` of
  its own capital (locked, deducted at issue) and sources `(1−r)·P`
  externally at the posted funding rate via the renamed
  `_fund_bank_external_portion`. The external depositor obligation
  matures alongside the loan and is repaid through the existing
  `_process_loan_repayments` path — economics produce **full interest
  on the own slice + margin (loan_rate − posted) on the external
  slice**.
- If the bank can't afford its own share, the loan is **refused** with
  a clear message naming the reserve ratio, the shortfall and the MBA
  depth (e.g., `"Bank cannot back this loan at 50% reserve: needs
  25.0 Dp of own capital but has only 10.0 Dp (MBA-qualified Banker
  Managers: 0/3)."`).
- `Loan` gains `own_committed`, `external_funded`, `posted_at_issue`,
  `reserve_ratio_at_issue` (defaulted 0.0; backward-compat in save/load).
- Self-lending (Banker borrowing from its own Banking Island) skips
  the reserve check — preserves the existing dollops-burn semantics for
  that special case.

**Tests:** suite **326 passing** (316 baseline + 10 net new across
`tests/test_engine/test_loans.py` (3) and
`tests/test_models/test_banker_reserve.py` (8); one Phase-2 shortfall
test was replaced by `test_loan_split_into_own_and_external_per_reserve_ratio`
since the old "fund whatever shortfall" behaviour is exactly what the
reserve gate now forbids).

**Intentionally deferred — clearly flagged D1.5 / D2 follow-ups:**

- In-game **MBA training UI** (Banker Managers earn `has_mba` via a
  University request consuming 2 Professors + 3 Courses over 2
  seasons). The flag is settable from tests today; players can't yet
  earn MBAs through gameplay, so the bank is **stuck at r=0.50** in
  this MVP. That's the principal nerf the calibration brief needs —
  full upgrade path is the next phase.
- **Multi-year annual interest servicing** with original-amount /
  original-rate rollover (the simple rollover rule for 2/3-yr loans).
  Today's bullet repayment still applies; multi-year loans collect all
  interest at maturity rather than annually.
- **Free pricing + applicant counter-offer** loop (Banker may quote
  any rate; applicant counters).
- **`banker.computing_centre`** capital + indicative 1/2/3-yr term
  quotes UI (D2).
- **Default depositor accounting** is still simple: a defaulted
  customer loan loses the bank's `own_committed`, but the external
  depositor obligation continues as a separate ledger entry maturing
  later — adequate for now; a richer "bank also owes the depositors
  even on default" path is a follow-up.

### claude/economy-phase-c

Branch: `claude/economy-phase-c`
Target: `pre-release`

**Economy Lifecycle Phase C** — universal capital lifecycle: every
capital item now has a service life and a per-season maintenance cost,
with an Agriculture **combine harvester** seeded already part-aged.

- `CapitalItem` gains `service_life_seasons` (default
  `DEFAULT_SERVICE_LIFE_SEASONS=20`, tunable accepted first-cut) and
  `maintenance_per_season` (default 0.0 → falls back to
  `DEFAULT_MAINTENANCE_FRACTION=0.03` × cost). Overrides bleed through
  `_multiply_capital_capacity` (it used to drop new fields silently).
- **`farmer.harvester` is now the "Combine Harvester"** with
  `service_life_seasons=8` (≈2 yr) — repurchase from the Manufacturer
  every two years.
- `Player.unmaintained_capital` (transient, not persisted) plus
  `Player.effective_capital_inventory()` which subtracts unmaintained
  units. Production reads
  `player.effective_capital_inventory()` everywhere it used
  `capital_inventory` so unmaintained units contribute **0 capacity**
  that season.
- New `Game._process_capital_maintenance(year, season)` called each
  season after `_process_retirements`:
  - **Expiry** — units whose age ≥ `service_life_seasons` are removed
    (oldest first / FIFO) with a `[CAPITAL EXPIRED]` log; the island
    must repurchase from the Manufacturer to restore that capacity.
  - **Maintenance** — per-unit Dp debit; on shortfall the unit is
    flagged unmaintained for the season (logged `[CAPITAL
    UNMAINTAINED]`); flag clears at the next season's maintenance step.
- New `STARTING_AGED_CAPITAL` table seeds Agriculture with 1
  combine harvester at age 4 — expires end of Year 1, aligning with the
  seeded Farmer's retirement (Phase B) for a deliberate Y1 double
  squeeze that forces real Manufacturer trade.

**Tests:** suite **316 passing** (305 baseline + 11 new in
`tests/test_engine/test_capital_lifecycle.py`). Two existing
`test_investing` tests updated for the "Combine Harvester" rename and
the seeded-aged-combine count.

> Balance note: maintenance only bites when players actually own
> capital, and starts modest (combine = 2.7 Dp/season at the
> 3 %-of-cost default). With 1500/player starting cash it's
> absorbable. The cost-pressure rises naturally with capital purchases
> — exactly the Agriculture → Manufacture dependency the brief asks
> for, applied game-wide.

### claude/economy-phase-b

Branch: `claude/economy-phase-b`
Target: `pre-release`

**Economy Lifecycle Phase B** — worker lifecycle / retirement (general
age system, Agriculture bootstrap activated).

- `Worker.age_seasons` field; `Workforce.add_workers(age_seasons=…)`.
- New `Workforce.advance_age_and_retire(working_life_by_band, default)`
  — ages **every** worker (active + in-training) one season per call,
  removes and returns those whose age ≥ their band working life.
- New constants: `WORKING_LIFE_SEASONS = {"Manager": 40, "Technician":
  32, "Worker": 24}` (tunable; accepted first-cut),
  `DEFAULT_WORKING_LIFE_SEASONS = 32`, and `STARTING_WORKER_AGES` with
  Agriculture seeded (`Farmer`: 4 seasons from retirement,
  `Horticulturalist`: 8).
- `Game._process_retirements(year, season)` called each season after
  `_process_training_returns`; logs `[RETIREMENT]` per island and drops
  retiring in-training workers from their training batch via the new
  `TrainingRegistry.drop_worker` (request rejects if it empties).
- Game setup seeds starting workers' ages from `STARTING_WORKER_AGES`
  using `band_of(profession)` → `WORKING_LIFE_SEASONS[band]`. Other
  islands default to age 0.
- Save format adds `age_seasons` per worker (backwards-compatible
  default 0 on load).

**Tests:** suite **305 passing** (297 baseline + 8 new in
`tests/test_models/test_worker_lifecycle.py` — age tick, band-keyed
retirement, in-training retirement, drop_worker behaviour, Agriculture
bootstrap schedule check).

> Bootstrap effect on simulations: the Agriculture Farmer retires ~4
> seasons into the game and the Horticulturalist ~8 seasons, putting
> real recruit+retrain pressure on the over-dominant Farmer role. This
> is *intended* and feeds the open balance-calibration workstream — do
> not interpret a Farmer win-rate dip post-merge as a regression.

### claude/economy-phase-a

Branch: `claude/economy-phase-a`
Target: `pre-release`

**Economy Lifecycle Phase A** (`requirements/economy-lifecycle-2026-05.md`)
— constants/starting-stock only, zero new mechanics.

- Per-player starting cash **700 → 1500**: `STARTING_DOLLOPS` 700→1500,
  `TOTAL_STARTING_DOLLOPS` 700→10500 (= 1500 × 7),
  `DEFAULT_STARTING_CAPITAL` (server) 700→1500.
- `STARTING_INVENTORY["Miner"]["Oil"]` **4 → 8** (larger Oil buffer).
- `STARTING_INVENTORY["Farmer"]` gains **`"Food": 15`**.

Tunables accepted as first-cut per product-owner ("Accept 2").
Suite **297 green**. Tests updated for the new economy:
`test_economy_balance` Miner-Oil assertion 4→8;
`test_island_guarantee` two offer-pricing tests rebased onto the 1500
starting capital (AI prices now fall in the "low" band; floor scales
to 0.20 × 1500).

> Follow-up (not in A, flagged): `game.py` derives the CLI/sim
> per-player default as `TOTAL_STARTING_DOLLOPS / num_players`, so a
> non-7-player CLI/sim game won't get exactly 1500/player. Server games
> use `DEFAULT_STARTING_CAPITAL` (1500/player) directly. Making
> per-player the canonical constant is spec open-Q #4 — deferred.

### claude/rules-training-reconcile

Branch: `claude/rules-training-reconcile`
Target: `pre-release`

**Docs-only** (RULES.md). No code/test changes (suite unchanged at
297). Reconciles the player-facing rulebook's training chapter with the
shipped Education Phase 1–3 + personnel-sidebar mechanics — it had been
left describing the pre-Phase-3 model.

- **Two-pipeline model documented:** Manager-tier = Course-gated
  university (1 Course per class ≤12); Technician-tier = Apprenticeship
  Programme slot-pool + Instructor gated, never Course-gated.
- **Profession-dependent durations** added to the capacity table
  (Doctor **3** seasons away, other Managers 2, Nurse 1, all Technicians
  1) and the full annual-quota table now lists every profession
  (previously a stale "caps added in a future balance pass" note).
- **Apprenticeship settling season** (1 season home @ 75% before 100%),
  **itemised fee** (base + food/accom 5 Dp/trainee/season + ticket +
  Manager-tier Expertise), **campus load**, and the **"All visible
  skill deficits"** bundled-request option all documented.
- Steps rewritten (the old duplicated "Educator Approval" Steps 2 & 4
  and the charter-flight-as-default were inaccurate); air ticket is now
  correctly the default transport. Quick Reference transport block
  aligned.
- Stale fixes: Educator starting workforce `4 → 8` (4 Professors + 4
  Instructors); profession table `Tutor → Instructor`; turn-action
  one-liner no longer claims "one season".

Clears the second-order release-gate item flagged in
`claude/release-prep` — the v0.1.0 rulebook training chapter is now
trustworthy. (Balance calibration remains the outstanding release
blocker.)

### claude/release-prep

Branch: `claude/release-prep`
Target: `pre-release`

**Docs-only — release-readiness prep.** No code/test changes (suite
unchanged at 297).

- **Balance measured on `pre-release` @ `36c74a4`** (AI-only, 3y, seeds
  42/1/7/99): Banker 54.6% + Farmer 42.5% ≈ 97% of all wins;
  **Transporter and Doctor win 0%** on every seed; Miner 0.4%, Educator
  1.0%, Manufacturer 1.5%. Target ≈14.3% each. Stable across seeds →
  structural, not RNG.
- Adds `requirements/codex-tasks/balance-calibration-2026-05.md` — a
  self-contained Codex brief to fix this (the release blocker). Notes
  the old `codex/sim-calibration` branch is stale/abandoned (0 ahead,
  ~5.8k behind) — calibration must start fresh.
- **RULES.md fix:** the two "Healthcare full capacity" statements
  disagreed (one "20 Medical Orderlies", one "20 unskilled workers");
  aligned to `4 Doctors + 20 Nurses + 20 Medical Orderlies (44 total)`,
  consistent with `STARTING_WORKERS_BY_PROFESSION` (the CLAUDE.md
  "workforce 12 / 10 Nurses" complaint was already fixed in an earlier
  branch — the starting-workforce table already shows 2+2+2=6).

**Release-readiness (proposed, for product-owner decision):**

- **NO-GO to promote `pre-release` → `master` yet.** Blocker: AI balance
  above (Codex brief filed). Tests green, 49 commits of real work, but a
  game that ships with two roles unable to win and two roles taking 97%
  of wins is not releasable.
- **Tag scheme proposal:** no tags exist; `master` was promoted via PRs
  #16/#17 untagged. Suggest annotated semver tags on `master` at each
  promotion, starting **`v0.1.0`** for this milestone (pre-1.0 = rules
  still in flux). Future: `v0.2.0` per feature-milestone promotion.
- **Roll-up mechanic at promote time:** rename `## Unreleased` →
  `## v0.1.0 — <date>` (the 24 accumulated sections become the v0.1.0
  changelog), open a fresh empty `## Unreleased`, PR `pre-release` →
  `master`, then `git tag -a v0.1.0`.
- **Second-order release-gate item (not blocking, but should ship with
  v0.1.0):** RULES.md training chapter is stale vs shipped Phase 1–3
  (single-season model, no apprenticeship slot-pool/Instructor gate, no
  profession-dependent duration, no 75% settling, "Tutor" vs
  "Instructor"). Needs a doc-reconciliation pass before the rulebook is
  a trustworthy v0.1.0 deliverable.

### claude/education-phase3

Branch: `claude/education-phase3`
Target: `pre-release`

Education Model **Phase 3** — training cost components + the
apprenticeship pipeline (Issue #18). Implements the 2026-05-17 rulings
now canonical in `requirements/education-model.md`.

**Behaviour changes:**

- **Two distinct training pipelines (decision (a)).** Phase 2 shipped a
  Course debit for *all* tiers; Phase 3 scopes Courses to **Manager-tier
  only**. Technician-tier training is now gated by the Educator's
  **apprenticeship slot pool** (`educator.apprenticeship_programme`
  capital, +3 slots each) **and** at least one **Instructor** on the
  Education Island workforce — never by Courses. A slot is held while a
  Technician batch is in flight and frees automatically on return.
- **Profession-dependent course duration is now wired into dispatch.**
  Previously every batch returned the next season regardless of
  profession. Now: Doctor **3** seasons away, other Managers **2**,
  Nurse **1**, all Technicians **1** (`EDUCATION_SEASONS[DOCTOR]` 2→3;
  `APPRENTICESHIP_SEASONS` flat 2→1).
- **Apprenticeship settling ramp.** A returning Technician works exactly
  **one season at 75% productivity** on the home island before reaching
  100% (`Worker.settling_seasons`; new constants
  `APPRENTICESHIP_SETTLING_SEASONS=1`,
  `APPRENTICESHIP_SETTLING_EFFICIENCY=0.75`). University (Manager)
  graduates do **not** settle. Persisted in save games.
- **Fee suggestion now itemised.** The training-fee prompt suggests
  `base + food/accom + tickets + expertise` where food/accom is
  `TRAINEE_FOOD_ACCOM_PER_SEASON` (5 Dp) × trainees × course duration,
  and the Expertise term is 1 Expertise per Course per season
  (Manager-tier only — apprenticeships are not Course/Expertise gated).
  Expertise is **not** debited from inventory on training approval (it
  is burned at Course *production* time, per Phase 2) — verified by
  `test_training_approval_does_not_consume_expertise_per_attendee`.
- **Campus load.** The Educator review screen surfaces visiting trainees
  on campus (`TrainingRegistry.visiting_trainees`) as a forward-looking
  "+N Food demand" note. Phase 3 merged **after** Codex's
  `codex/sustenance-model`, so this branch also wires the seam: the
  server now calls `population_food_fish_needs(extra_residents=…)` with
  the Education Island's visiting-trainee count, so campus load actually
  raises the island's marginal Food demand and runway warnings (the §21
  balance-aware model, not the legacy Food/Fish path).

**No-ops:** `provides_apprenticeship_facility` / cross-island
sellable-apprenticeship-token never existed in code (only in the
now-reconciled requirements docs), so nothing to remove.

**Tests:** suite **293 passing** (283 baseline → 10 net new). New
`tests/test_engine/test_education_phase3.py` covers the apprenticeship
gate, slot-pool overbooking, duration-into-dispatch, and the settling
ramp. Six Phase-2 Course tests were repointed to a Manager profession
(Nurse) since Technicians are no longer Course-gated; the duration test
and the self-training return test were updated to the new durations.

**Calibration follow-up:** AI/sim Educators must now hold an
Apprenticeship Programme + an Instructor to admit Technician trainees.
This is a deliberate gate per spec; flag for the Codex sim-calibration
pass if Technician supply tightens.

### codex/sustenance-model

Branch: `codex/sustenance-model`
Target: `pre-release`

- Replaces the legacy population Food-demand path with the §21
  balance-aware model: the first 100 permanent residents are self-fed,
  while residents above that baseline create 1 unit of marginal Food
  demand each season.
- Adds the `extra_residents` seam to
  `Player.population_food_fish_needs()` so Education Phase 3 can charge
  visiting trainees against campus sustenance without mutating resident
  population.
- Adds focused model coverage for baseline demand, population growth, and
  transient residents.
- Leaves the Healthcare workforce wording unchanged because current
  merged code and rules already agree on the newer 2 Doctors + 2 Nurses +
  2 Medical Orderlies composition; the older handoff's “2 Doctors + 4
  Nurses” note is stale against present `pre-release`.

### codex/personnel-sidebar-breakdown

Branch: `codex/personnel-sidebar-breakdown`
Target: `pre-release`

- Makes the left-side Personnel summary readable as an indented multiline
  breakdown and shows per-band workers currently in training.
- Adds a Request Training deficit report so players can see which formal
  professions their island staffing plan is missing.
- Adds an “All visible skill deficits” training option that submits the
  currently requestable missing professions together while preserving
  per-profession University-capacity batches internally.

### claude/codex-brief-sustenance

Branch: `claude/codex-brief-sustenance`
Target: `pre-release`

**Docs-only.** Adds `requirements/codex-tasks/sustenance-model.md` — a
self-contained Codex hand-off to implement the §21 balance-aware
sustenance model (and the standing RULES.md Doctor-workforce fix) in
parallel with Education Phase 3. Defines the campus-load interface seam
and an explicit file-ownership split so the two tracks merge cleanly.
No code or test changes (suite unchanged at 283).

### claude/docs-phase3-reconcile

Branch: `claude/docs-phase3-reconcile`
Target: `pre-release`

**Docs-only.** No code or test changes (suite unchanged at 283).
Reconciles the requirements so Education Phase 3 is unambiguous, after
Codex's role-structuring merge changed the surrounding model.

Decisions ruled by the product owner 2026-05-17, now canonical:

- **Doctor training = 3 seasons** (was ambiguous 2-vs-4). Fixed in
  `education-model.md` duration table + `production-capacity-model.md §5`
  (and flagged for `EDUCATION_SEASONS[DOCTOR] 2→3` in Phase 3 code).
- **Courses vs apprenticeship are distinct, non-overlapping pipelines
  (decision (a))**: Manager-tier = Course-gated; Technician-tier =
  Educator apprenticeship-slot-pool + Instructor gated, **not**
  Course-gated. Phase 2 (shipped) Course-gates all tiers — Phase 3
  scopes that to Manager-tier.
- **Apprenticeship model**: 1 season away at Education, then **75%
  productivity for exactly one season** on the home island, then 100%.
  Supersedes both the old "home-island Apprenticeship Facility" idea
  and `production-capacity-model.md §8`'s "stays home / no loss" model.
- **Dropped**: `provides_apprenticeship_facility` capital flag; the
  in-house cross-island apprenticeship sellable-token mechanic.
- **1 Expertise per Course per season** (per Course, not per trainee).
- **Campus load** must use the new balance-aware sustenance model
  (`production-capacity-model.md §21`), not the legacy Food/Fish path.

Files touched: `requirements/education-model.md` (Phase 1/2 marked done,
Phase 3 promoted + spec'd, training-pipelines split, duration table,
open-questions closed), `requirements/production-capacity-model.md`
(§5 Doctor=3, §8 now points to education-model.md as canonical),
`requirements/medical-laboratory.md` (Ecologist/Actuary durations align
to the apprenticeship model), `TODO.md` (Phase 2 ✅, Phase 3 rewritten).

### claude/education-phase2

Branch: `claude/education-phase2`
Target: `pre-release`
Implements: `requirements/education-model.md` Phase 2 + GitHub #22 (market UX)

Rebased onto `pre-release` after Codex's `codex/role-structuring` split
landed (`f0c0960`). Both bodies of work came from the same combined
safety snapshot `fd519e0`; this branch is exactly the Claude-owned delta
(`git diff f0c0960 fd519e0`), re-applied cleanly in the separate
`island-traders-claude` worktree.

#### Education Model — Phase 2 (Courses + Instructor)

- **New resource `Courses`** (`ResourceType.COURSES`, base price 25 Dp) —
  classroom slots produced by the Education Island.
- **New Educator recipe**: Courses production consumes `Expertise` as an
  input; Patents production now also consumes a small Expertise input.
- **`Tutor` → `Instructor` consolidation**: `Profession.TUTOR` renamed to
  `Profession.INSTRUCTOR` (canonical Technician on the Education Island);
  "Tutor" kept as a display-title alias in `BAND_TITLES`.
- **Course-gated training**: `_action_request_training` /
  `_approve_training_request` / AI educator / self-training now debit
  `ceil(trainees / MAX_CLASS_SIZE_PER_COURSE)` Courses on approval
  (`MAX_CLASS_SIZE_PER_COURSE = 12`). No Courses → request stays pending.
  Course availability is peeked *before* air tickets are consumed so a
  shortfall can't burn the Educator's PassengerSeats.
- **Starting state**: Educator workforce 4 → 8 (4 Professors + 4
  Instructors); starting inventory gains 6 Expertise + 5 Courses.

#### GitHub #22 — Market UX

- New generic `choose_option(prompt, options)` IO prompt (named choice
  buttons) used for product selection — replaces the numeric-index
  picker.
- `ask_dollop_amount` gained a `prefill` argument; market **sell** prompt
  pre-fills the best bid, market **buy** modal pre-fills the ask, with
  bid-vs-buy made visually explicit.
- Market board popup rendered as a clean grid.
- Immediate-fill on a bid that crosses an existing ask now logs the fill.

#### Tests

- New `tests/test_engine/test_education_courses.py`.
- Updated `test_educator_self_training.py`, `test_training_review.py`,
  `test_training_menu.py`, `test_profession_bands.py`,
  `test_market_prefill.py` for Courses + Instructor + prefill.
- **Full suite: 283 passed** in the Claude worktree on top of
  `pre-release` @ `f0c0960` (Codex's 271 + this delta = 283 — reconciles
  exactly with the original combined `fd519e0`).

---

### codex/ai-trading

Branch: `codex/ai-trading`
Target: `pre-release`
Implements: `requirements/codex-tasks/ai-trading.md`

#### Player-Facing Changes

- AI islands now place standing bids when they are short of required production inputs instead of waiting for humans to rescue the supply chain.
- AI islands review pending peer deals with market-aware valuation and accept profitable deals while rejecting value-destroying ones.
- AI islands can capture visible bid/ask arbitrage when the market already exposes a profitable spread.
- Transporter AI now lists produced `PassengerSeats` for sale; previously those seats were produced but omitted from AI selling because the stale role metadata only advertised `Freight`.

#### Before / After Market Activity

- Before: an input-starved Farmer with 0 `FarmMachinery` placed no standing bid; after: it posts a market bid for the missing machinery on its turn.
- Before: Transporter AI produced `PassengerSeats` but did not list them; after: a post-production regression test confirms a standing `PassengerSeats` offer exists.
- Before: AI deal acceptance used only formula prices in the human-turn path; after: AI-targeted deals use latest accepted cash/unit deal price, then current best offer, then formula price as fallback.

#### Known Follow-Ups

- The task brief asks for trade-row verification in the simulation price-history CSV, but the current simulation exporter records seasonal price snapshots only, not executed-trade rows. I left that exporter untouched to stay inside the agreed file scope.
- `Transporter` role metadata still lists only `Freight` in `models/role.py` even though production constants also emit `PassengerSeats`; this branch works around that by selling actual produced resources, but the metadata should be reconciled separately.
- The 1000-game AI-only run still shows structural balance drift once active trading is enabled (Banker 68.0% wins, Educator and Doctor 0.0%); balancing is intentionally left for the separate calibration workstream.

#### Verification

- Test suite: `265 passed` (baseline 262, +3 AI-trading regressions).
- Simulation: `.venv/bin/python -m island_traders.simulation.runner --games 1000 --seed 42 --output simulation_results/ai_trading`.

---

### claude/education-phase1-rename

Branch: `claude/education-phase1-rename`
Target: `pre-release`
Implements: `requirements/education-model.md` — Phase 1 (mechanical rename)

**Pure rename — zero behavioural change.** Test suite unchanged at
**262 passed** (same count and same tests as before).

`ResourceType.KNOWLEDGE` (`"Knowledge"`) → `ResourceType.EXPERTISE`
(`"Expertise"`) everywhere:

- `models/resource.py` — enum member + value
- `models/role.py` — Educator produces / Banker & Doctor need Expertise
- `constants.py` — `BASE_PRICES`, `BASE_PRODUCTION`, `PRODUCTION_INPUTS`,
  `STARTING_INVENTORY`, comments; dead `TRAINING_KNOWLEDGE_COST` →
  `TRAINING_EXPERTISE_COST`
- `constants_capacity.py` — Educator recipe `output="Expertise"`, capacity
  effects, input-relief, descriptions
- `server/app.py` — `ROLE_INFO` produce/needs display strings
- `config/event_charts.yaml` — price-shock resource keys
- `RULES.md`, `README.md` — all player-facing references
- `board/game_board.html` — visible label text (internal DOM id
  `res-knowledge` and JS `gameState.knowledge` left as-is; that file is a
  standalone demo, not the live dashboard)
- `tests/test_engine/test_production.py` — assertions

Phase 2 (add `Courses` resource, Educator produces Courses by consuming
Expertise, Course-gated training, `Profession.INSTRUCTOR`, rebalanced
Education starting workforce) remains a separate future branch per the
spec.

#### Verification

- Test suite: 262 passed (unchanged — confirms pure rename).
- Smoke-tested: enum has `EXPERTISE` and no `KNOWLEDGE`; server imports;
  `island-traders-export` printables contain no "Knowledge".

---

### claude/issue-22-market-ux

Branch: `claude/issue-22-market-ux`
Target: `pre-release`
Closes: GitHub #22

Four market UI/UX fixes from the 2026-05-15 playtest:

1. **Market Prices popup as a grid** — `renderMarketTable` now uses a new
   `.market-grid` style (gridlined, tabular-numeric, right-aligned,
   zebra-striped, colour-coded bid/ask) in the board popup.  The compact
   side-panel mini-table is unchanged.
2. **Bid vs Buy clarity** — the Market Buy popup now has a legend
   ("⬤ Buy Now" = immediate at the ask; "⬤ Place Bid" = limit order at
   your price), grouped headers, gridline separators, tinted columns
   (gold for buy-now, green for place-bid), and tooltips on each input.
3. **Buying prefill** — the new-bid price field is pre-filled with the
   current ask (when one exists) instead of the formula price, so a
   buyer placing a bid starts from the price that would clear.
4. **Selling prefill** — the asking-price prompt is pre-filled with the
   best bid (when one exists).  New optional `prefill` parameter on
   `ask_dollop_amount` across all three IO adapters; the WS message
   carries `prefill` and the dashboard input uses it as its initial
   value with a hint line.

#### Tests

- 7 new tests in `tests/test_engine/test_market_prefill.py`: base
  adapter honours/overrides prefill, FakeIOAdapter accepts the new
  kwarg, WS message carries `prefill`, and `_action_market_sell`
  prefills the asking price with the best bid.

#### Verification

- Test suite: 262 passed (was 255, +7).  Existing test IO adapters that
  override `ask_dollop_amount` with the old 2-arg signature are
  unaffected (they aren't on the market-sell path).

---

### claude/ux-quickwins-20-21

Branch: `claude/ux-quickwins-20-21`
Target: `pre-release`
Closes: GitHub #20, #21

#### #21 — Product selection by name, not index

Producing used to print a numbered list then ask via `choose_quantity`
(a numeric input box on the dashboard).  Players had to read the list and
type a number.

New generic **`choose_option(prompt, options)`** prompt added to all three
IO adapters (base terminal `IOAdapter`, `FakeIOAdapter`, and
`WebSocketIOAdapter`).  `options` is `[{"value", "label"}, …]`; it returns
the chosen `value`.  The dashboard renders it as labelled buttons (reuses
the existing option picker — new `choose_option` WS message case).

`_action_produce` and `_choose_product_line_human` now use it, so the
player picks **"Farmer: Food — up to N now"** or
**"Heavy Machinery — Inputs: … → …"** as a button, never an index.

#### #20 — Personnel counts on the left panel

New **"Personnel"** stat row in the left info panel showing the
trained/untrained breakdown:
`N trained (X Mgr · Y Tech) · Z untrained`.  The "Workers" row label
clarified to "Workers (active/total)".  Server payload already exposed
`workforce_bands`; this is UI-only.

#### Tests

- 9 new tests in `tests/test_engine/test_choose_option.py`:
  base terminal picker (selection + reprompt), FakeIOAdapter default,
  WS round-trip / timeout-first / cancel-sentinel-raises / unknown-value
  fallback, and an integration test asserting `_action_produce` calls
  `choose_option` with human labels.

#### Verification

- Test suite: 255 passed (was 246, +9 new).  No regressions — existing
  production tests still pass (FakeIOAdapter.choose_option returns the
  first option, same effective behaviour as the old choose_quantity=min).

---

### claude/issues-2026-05-15-synthesis

Branch: `claude/issues-2026-05-15-synthesis`
Target: `pre-release`

Docs-only branch.  Synthesises **9 new GitHub Issues** (#18–#26) posted
during the 2026-05-15 playtest into specs and TODO entries.  No code or
test changes.

#### New spec: `requirements/medical-laboratory.md`

Roots three interconnected issues (#19, #25, #26) under a single coherent
spec:

1. **#26 — Medical & Laboratory Island** — Doctor role keeps its
   internal identifier but display label becomes "Medical & Laboratory";
   adds a new tradeable output `LaboratoryTests` (base price ≈ 35 Dp).
2. **#25 — Ecologist profession** — new Technician profession required
   to certify capital-equipment installations.  Each install needs an
   Ecologist on staff + 1 Environmental Assessment Lab Test.
3. **#19 — Doctor-certified insurance** — Doctors issue Lab Tests
   ("Health Certificates") that halve insurance premiums; insured
   workers don't lose productivity from injury; death benefits pay
   replacement training cost.

Lab Tests are the glue — same enum value, four different narrative
"types":

| Consumer | Test type | Why |
|---|---|---|
| Mining | Metal Assay | Required to smelt Ore + Oil → Metal |
| Farmer | Soil Analysis | Seasonal production gate |
| Any island installing capital | Environmental Assessment | Required for activation |
| Banking | Health Certificate | Halves insurance premium |

Five-phase implementation plan (A through E) keeps each piece
independently mergeable.

#### `requirements/education-model.md` extended with Issue #18

New "Training cost components" section formalises the cost breakdown:

* Profession-dependent **course duration** (Doctor=4, most Managers=2,
  Nurse=1, Technicians=1 with apprenticeship facility or 2 without)
* **Expertise consumption = 1 unit per trainee per season** (so a
  Doctor batch of 2 trainees consumes 4×2 = 8 Expertise)
* **Food & accommodation** cost layered into the suggested fee
* **Apprenticeship Facility** — a new capital item flag
  (`provides_apprenticeship_facility: bool`) reduces Technician training
  to 1 season

Duration table covering all professions including the new Ecologist and
Actuary entries from `medical-laboratory.md`.

#### TODO.md sections added / updated

* **New section:** `Medical & Laboratory Island` with phases A–E
  spanning #19, #25, #26
* **Education Model Refinement** got a new Phase 3 covering #18
* **Dashboard & UX** got 4 new entries: #20 (personnel counts), #21
  (product names not indexes), #22 (market UX polish), #23 (bolder
  logo + island popup)
* Two ticked off as already done in earlier merges:
  - `Purchase Capital` → `Purchase Equipment` (✓)
  - Personnel shortages named by profession (✓)

#### Issue #24 (Actuary)

Captured in `medical-laboratory.md §4` (Banking gets a new Actuary
Technician profession required to underwrite insurance policies).
Cross-references this work to the Banker institutional pool in
`island-ledger.md`.

#### Verification

- No code changes.  Test suite unchanged at 246 passed.

---

### claude/ux-polish-2026-05-15

Branch: `claude/ux-polish-2026-05-15`
Target: `pre-release`

Two small UX wins from the 2026-05-15 playtest inbox.

#### "Purchase Capital" → "Purchase Equipment" label

Pure display-label change.  Internal identifier
(`TurnAction.PURCHASE_CAPITAL`, value `"purchase_capital"`) is unchanged
— saved games, server JSON, and existing tests all keep working.

Implementation: new `action_label()` helper + `ACTION_LABEL_OVERRIDES`
dict in `cli/prompts.py`, used by both the CLI `IOAdapter` and the
WebSocket `WebSocketIOAdapter` so both menus render the same label.

#### Workforce shortage messages use profession titles, not band names

Constraint popup used to say *"+2 Technicians"* — not actionable.  Now
it says *"+2 Flight Crew"* (for the Transporter), *"+2 Farming
Technician"* (for the Farmer), *"+2 Banking Analyst"* (for the Banker),
etc.

Implementation: server-side `_player_capacity` now uses
`primary_title(recipe.role, band)` from `models/profession.py` when
building the `workforce_short` dict, so the dashboard receives
profession names ready to render.  Dashboard rendering didn't need to
change — it just prints the keys it gets.

#### Tests

- 4 new tests in `tests/test_engine/test_action_labels.py`:
  * `Purchase Capital` displays as `Purchase Equipment`
  * Unmapped actions still use default title-casing
  * Internal enum name + value are unchanged
  * Every override key points at a real `TurnAction` value
- 2 new tests in `tests/test_server/test_workforce_shortage_messages.py`:
  * Transporter shortages name Logistics Manager / Flight Crew /
    Seaman / Warehouse Manager / Stevedore — never generic bands
  * Banker shortages name Banker / Banking Analyst / Banking Clerk /
    Receptionist — never generic bands
- Updated `tests/test_server/test_investing.py` (1 assertion) to expect
  the new profession-titled keys instead of `"Technician"` / `"Worker"`.

#### Verification

- Test suite: 246 passed (was 240, +6 new).

---

### claude/educator-self-training

Branch: `claude/educator-self-training`
Target: `pre-release`

Bug fix from the 2026-05-15 playtest: the Education Island couldn't train
its own workforce because `_action_request_training` excluded the player
from the educator picker list, then bailed with "No Educator player in
this game."

#### Fix

In `_action_request_training`, detect when the requester is the Educator
(`is_self_training = any(r.name == "Educator" for r in player.roles)`)
and route through a short-circuit branch that:

* Sets `educator = player` (skips the educator-choice prompt)
* Sets `dollops_educator = 0.0` (no fee — skips the prompt entirely)
* Sets `transport_mode = "self_training"` (new mode; bypasses the
  PassengerSeats / air-ticket consumption)
* After submitting the request, **auto-approves and dispatches**
  immediately — the workers go into the on-island programme this
  season and return next season.

University capacity is still consumed for the chosen profession, so
self-training cannot bypass the annual / seasonal caps.

#### Files touched

- `island_traders/engine/turn.py` — self-training branch in
  `_action_request_training`
- `island_traders/models/training.py` — `describe()` now handles the
  new `"self_training"` transport mode

#### Tests

- 5 new tests in `tests/test_engine/test_educator_self_training.py`:
  * Skips the educator picker and fee prompt
  * Consumes zero PassengerSeats; dispatches immediately
  * Returns after exactly one season
  * Still counts against University capacity (no cap bypass)
  * Works in a solo / single-Educator scenario

#### Verification

- Test suite: 240 passed (was 235, +5 new).

---

### claude/edu-spec-and-codex-brief

Branch: `claude/edu-spec-and-codex-brief`
Target: `pre-release`

Docs-only branch.  Two updates following the 2026-05-15 inbox-processing
session and the product decisions that came out of it.

#### `requirements/education-model.md` updates

* **Patents now consume Expertise as an input** (~0.25 Expertise per
  Patent) on top of Laboratory Equipment + Manager capacity.
* **Class-size rule:** 1 Course covers a class of up to **12 students**.
  When a training batch exceeds 12 trainees the system auto-splits across
  multiple Courses (debiting `ceil(trainees/12)`).
* **Self-training Course consumption** clarified: yes, self-training
  still debits a Course even though it skips fees + transport.  The
  12-student class size applies, so multiple workers on the Education
  Island can be trained on a single Course.
* **Tutor → Instructor consolidation:** Profession.TUTOR is renamed to
  Profession.INSTRUCTOR.  The clean Manager/Technician pairing is
  Professor / Instructor.  "Tutor" can stay as a display title alias.
* New constant flagged: `MAX_CLASS_SIZE_PER_COURSE = 12`.
* Open-questions section updated to mark items 1, 3, and 4 as decided.

#### `requirements/codex-tasks/ai-trading.md` (new)

Self-contained Codex task brief for the next parallel work item: making
heuristic AI islands proactively participate in the market (place bids,
list offers, evaluate cross-island arbitrage).  Mirrors the existing
`codex-tasks/sim-calibration.md` format — goal, scope, in/out-of-scope
files, acceptance criteria, hand-off mechanics.

Specific scoped behaviours:

1. List most fresh output for sale each season
2. Bid on missing inputs
3. **Transporter AI must list Passenger Seats** (currently silently
   blocking training)
4. Cross-island arbitrage / opportunistic deals
5. Switch deal valuation to last-deal / best-offer (TODO item)

#### Verification

- No code changes.  Test suite unchanged.

---

### claude/inbox-2026-05-15

Branch: `claude/inbox-2026-05-15`
Target: `pre-release`

Docs-only branch.  Processed the 8 playtest items captured in
`requirements/inbox.md` on 2026-05-15.  No code or test changes.

#### What landed where

| Item | Destination |
|---|---|
| Educator self-training (no fee / no transport / 1 season) | `TODO.md` Bugs section |
| Rename `Purchase Capital` → `Purchase Equipment` | `TODO.md` Dashboard & UX |
| AI live-play economy / automated trading | `TODO.md` new "AI Trading Behaviour" section (proposed next Codex task) |
| Personnel shortages by specialty | `TODO.md` Dashboard & UX |
| Food: base population self-fed | `requirements/production-capacity-model.md §21` (new) + `TODO.md` |
| Cancel open bids / offers + partial fills | `TODO.md` new "Market & Trading" section |
| Education refinement: Knowledge → Expertise, +Courses, +Instructors | **New spec** `requirements/education-model.md` + `TODO.md` new "Education Model Refinement" section |
| Near-match auto-clearing (±1 Dp / ±3%) | `TODO.md` "Market & Trading" |
| Item valuation: last-deal / lower-of-cost-or-market | `TODO.md` Financial Model |

#### Highlight: Education model refinement is the largest piece

`requirements/education-model.md` (new) lays out a two-phase migration:

* **Phase 1 (mechanical):** rename `ResourceType.KNOWLEDGE` →
  `ResourceType.EXPERTISE` and display label "Expertise" everywhere.  Pure
  cascade — zero behavioural change.  ~40-file touch surface.
* **Phase 2 (gameplay):** add `ResourceType.COURSES` (new tradable);
  Education produces Courses by consuming Expertise; training requests
  debit Courses on approval; add `Profession.INSTRUCTOR` (consolidating
  with Tutor is the recommended open question); rebalance Education
  starting workforce to 4 Professors + 4 Instructors.

The spec flags open questions (Tutor vs Instructor consolidation, Course
trade-ability, self-training Course consumption) for product-side
decisions before implementation starts.

#### Highlight: AI Trading Behaviour is the next Codex candidate

The playtest reported that AI islands behave too passively after
production — humans have to push trades on them.  The new "AI Trading
Behaviour" TODO section enumerates the concrete missing behaviours
(placing bids, listing offers, cross-island arbitrage, deal valuation
based on last-deal price).  This is well-scoped, lives mostly in
`engine/ai.py`, and doesn't overlap with Claude's current workstreams —
exactly the kind of task Codex can pick up on a `codex/ai-trading`
branch.

#### Verification

- No code changes.  Test suite unchanged.

---

### claude/banker-rebalance

Branch: `claude/banker-rebalance`
Target: `pre-release`

Banker is a **service business**, not a commodity producer.  Income comes
from loan interest spread + insurance premiums (and, future, deal
guarantees, brokerage, and project finance).  This branch removes the
`Finance` commodity from the production loop — the root cause Codex
identified for the 75.6% Banker win rate.

#### What changed

- **Banker BASE_PRODUCTION is now empty** (was: 30 Finance/season).  The
  Banker no longer "produces" anything on the market.  Banker income comes
  exclusively from the existing loan ledger (interest at the quoted rate)
  and from insurance premiums sold via the existing `SELL_INSURANCE`
  action.
- **Banker PRODUCTION_INPUTS is now empty** (was: 1 Knowledge).  Banking
  doesn't gate on per-season inputs.  Knowledge still useful for training
  workers, but isn't consumed by an idle Produce action.
- **Educator PRODUCTION_INPUTS dropped Finance** (was: Lab Equipment +
  Finance, now: Lab Equipment).  No more "operating budget paid in a
  tradeable commodity".
- **STARTING_INVENTORY:** Banker no longer starts with 2 Finance to sell;
  Educator no longer starts with 2 Finance to spend.
- **`models/role.py`:** Banker `produces=()`, no longer `(FINANCE,)`.
  Educator `needs=(LABORATORY_EQUIPMENT,)`.  Banker short_name renamed
  from "Finance" to "Banking" to reflect the service-focus.
- **`constants_capacity.py`:**
  * Removed the `Banker → Finance` production recipe.
  * Updated Banker capital items (Vault, Trading Floor) to express
    capacity in `Loans` / `InsurancePolicies` instead of `Finance`.
  * Removed `Finance` from Educator recipe inputs.
- **`server/app.py` ROLE_INFO** updated: Banker produces "Loans,
  Insurance" not "Finance"; Educator needs "Laboratory Equipment" only.
- **`RULES.md`** updated: Seven Islands table, Production Inputs table,
  Base Prices table, physical contents list, and Quick Reference now
  reflect Banker as a service business with no Finance commodity.

#### What didn't change

- The `ResourceType.FINANCE` enum still exists — back-compat for any
  saved games or external references.  No code now produces or consumes
  it during normal play.
- The existing loan engine (`models/loan.py`, banker_quote_rate, etc.)
  is unchanged — that was already the right shape.
- The Insurance products (Life + Medical, with manage/cancel/refund
  flows) are unchanged.

#### Simulation impact (500 games × 4 seeds {42, 1, 7, 99})

| Role         | Before       | After (mean) |
|--------------|-------------:|-------------:|
| Banker       | **75.0%**    | **1.1%**     |
| Transporter  | 23.6%        | 95.2%        |
| Farmer       | 1.4%         | 3.8%         |
| Miner        | 0.0%         | 0.0%         |
| Educator     | 0.0%         | 0.0%         |
| Manufacturer | 0.0%         | 0.0%         |
| Doctor       | 0.0%         | 0.0%         |

Banker dominance is **eliminated** — exactly the goal of this fix.

#### Honest caveats

This is a *targeted* fix for the Banker exploit.  It does **not** balance
the overall game.  The post-fix distribution surfaces a separate
structural problem: **Transporter now dominates at ~95%** (already over-
monetized; with Banker out, Transporter sweeps).  Roles at 0% wins still
need their own structural look.

Two known follow-ups, both out of scope for this branch:

1. **Banker AI strategy** — the heuristic AI doesn't yet proactively
   offer/seek loans, so the Banker has almost no income in AI-only
   simulations.  Real multiplayer should be different (humans will seek
   loans).  Once the Island Ledger refactor lands and the institutional
   cash pool + deposit accounts exist, the Banker's economics will be
   meaningfully different — re-baseline at that point.
2. **Transporter economy** — `damage_seasons` semantics and AI market
   behaviour need separate work (Codex's diagnostics noted this).

#### Future Banker revenue streams (TBD, on the roadmap)

- **Deal guarantees** — Banker charges a fee to guarantee a P2P deal so
  the counterparty is paid even if the proposer defaults
- **Brokerage** — Banker negotiates deals between two other islands for
  a commission
- **Project finance** — when project-based capital expenditures are
  introduced, Banker provides structured loans for specific projects
- **Deal insurance** — premium-priced cover for a single transaction
  (vs. the seasonal Life / Medical policies that exist today)

#### Verification

- Test suite: 235 passed (unchanged count; 3 Banker-production tests
  rewritten to assert no production rather than asserting on Finance flow).
- Baseline simulation (`--games 500 --seed 42`) vs post-fix simulation
  recorded in the table above.

---

### codex/sim-calibration

Branch: `codex/sim-calibration`
Target: `pre-release`

Simulation calibration iteration for the current `pre-release` economy.
This is not a final balance certification; further calibration iterations are
expected before the next major release is promoted from `pre-release` to
`main`.

#### Baseline

Ran:

```bash
.venv/bin/python -m island_traders.simulation.runner --games 1000 --seed 42 --output /tmp/island-traders-baseline
```

Current win rates:

| Role | Wins | Win rate | Avg wealth |
|---|---:|---:|---:|
| Farmer | 12 | 1.2% | 112.1 Dp |
| Miner | 0 | 0.0% | 49.9 Dp |
| Transporter | 232 | 23.2% | 993.3 Dp |
| Educator | 0 | 0.0% | 87.2 Dp |
| Banker | 756 | 75.6% | 3770.6 Dp |
| Manufacturer | 0 | 0.0% | 131.1 Dp |
| Doctor | 0 | 0.0% | 89.1 Dp |

#### Diagnosis

Event-chart tuning alone is not enough to satisfy the calibration target
(roughly 14% wins per role, with no role below 8% or above 22%).
Sensitivity runs with extreme Banker / Transporter outage charts and boosted
underdog yield modifiers still left Banker and Transporter structurally
dominant, while Miner, Educator, and Doctor remained near 0%.

The biggest blockers appear structural rather than event-probability driven:

- Banker and Transporter generate high-value inventory from the current
  AI-only economy loop and can remain competitive even under very harsh event
  charts.
- Several low-win roles are wealth-capped by input availability, turn-order
  market flow, and resource valuation; multiplying their event yields did not
  reliably turn into final wealth.
- `damage_seasons` on outage events converts future turns into
  `Infrastructure Damage` at 50% yield rather than extending the outage, so
  "harsher" disaster tuning can accidentally preserve meaningful production.

#### Runner tooling

Added `--seeds` to the simulation runner so calibration can run comparable
multi-seed batches without shell loops:

```bash
.venv/bin/python -m island_traders.simulation.runner --games 1000 --seeds 42,1,7,99
```

Each seed writes its own CSV pair using the configured output prefix plus
`_seed_<seed>`, and stdout includes a compact cross-seed win-rate summary.

#### Known follow-ups

Coordinate before changing out-of-scope balance surfaces. Likely follow-up
work needs to address the AI-only economy and/or production constants before
event chart weights can be meaningfully calibrated:

- Review Banker personal wealth from Finance production versus the planned
  institutional cash-pool model.
- Review Transporter output valuation and AI market behavior.
- Add richer simulation diagnostics for per-role production, input shortages,
  sales, retained inventory value, and insurance / loan income.

---

### claude/fix-playtest-bugs

Branch: `claude/fix-playtest-bugs`
Target: `pre-release`

Three bugs surfaced during live playtesting on `pre-release`.

#### Bug 1 — Post-auction guarantee UI hung after purchase

After the islandless buyer clicked Buy on an AI extra, the guarantee panel
hid but the user stayed on the auction screen.  The investing screen never
opened automatically.  Eventually the game proceeded (the server had moved
on) but the player was left staring at a blank screen until they refreshed.

**Fix:** `onIslandGuaranteeComplete` now proactively switches the user to
the investing screen.  If `investData` has already arrived it renders
immediately; otherwise the existing `investing_start` handler renders when
the data lands.

#### Bug 2 — Training menu lost Banker (and other) options too eagerly

Two issues:
1. The new technician professions added with the workforce baseline rule
   (Logistics Manager, Flight Crew, Seaman, Warehouse Manager, Lecturer,
   Tutor, Banking Analyst, Banking Clerk, Medical Orderly) had no entries
   in `UNIVERSITY_CAPACITY`, so they didn't appear in the Request Training
   menu at all.
2. When a profession exhausted its annual cap the menu silently dropped it,
   so the user couldn't see WHY their option had disappeared (felt buggy).

**Fix:**
- Extended `UNIVERSITY_CAPACITY` with caps for all 9 new professions
  (reasonable defaults: Manager-tier 2/yr, Technician-tier 4-8/yr).
- `_action_request_training` now prints exhausted professions with a `FULL
  — X/Y already requested this year` line so the user understands the
  capacity state.

#### Bug 3 — Cancel button still executed a partial action

Pressing Cancel on a prompt chain (e.g. Request Training) caused the engine
to fall back to default values (`min_qty`, `available[0]`, etc.).  Result:
"I pressed Cancel and it still trained 1 doctor."

**Fix:** Plumbed an explicit cancel signal end-to-end:
- New `cli/signals.py` with `CANCEL_SENTINEL` constant and
  `ActionCancelled` exception (lives in its own module to avoid the
  circular import between `cli/prompts` and `engine/turn`).
- Client `cancelDlg()` now sends `CANCEL_SENTINEL` instead of `null`.  Two
  other "treat as cancel" spots in the dashboard (market-buy modal cancel,
  empty market-buy submit) updated to match.
- `WebSocketIOAdapter` checks the sentinel at the top of every prompt
  method (`_check_cancel`) and raises `ActionCancelled`.  A plain `None`
  response (timeout / interrupt) still falls back to the default — only an
  explicit Cancel raises.
- `engine/turn.py` main action loop catches `ActionCancelled` and prints
  "Action cancelled" — no partial execution.

#### Tests

- 9 new tests in `tests/test_engine/test_action_cancellation.py`:
  * Each of the 7 WS-adapter prompt methods raises `ActionCancelled` on the
    sentinel.
  * `choose_quantity` returns the min on plain `None` (timeout fallback
    preserved, NOT cancelled).
  * End-to-end-ish: a cancelling IO in the training action handler results
    in no training request being created.
- 5 new tests in `tests/test_engine/test_training_menu.py`:
  * All 9 new professions have `UNIVERSITY_CAPACITY` entries.
  * Every Profession (other than Unskilled) is trainable.
  * `capacity_summary` includes all professions.
  * Banker cap is ≥ 2.
  * Request Training menu shows exhausted professions as `FULL`.

#### Verification

- Test suite: `233 passed` (up from 219).

---

### claude/rules-md-refresh

Branch: `claude/rules-md-refresh`
Target: `pre-release`

Documentation-only refresh of `RULES.md` to match the current online rules
(no code changes; tests unchanged at 219 passing).

#### What was updated

- **Seven Islands table** — produces/needs columns refreshed for Metal,
  Farm Machinery, Mining Equipment, Lab Equipment, Patents, Passenger Seats,
  and Insurance/Loans as Banker outputs.
- **Starting Conditions table** — Dollops corrected to 700 (auction budget);
  starting workforce updated to match `STARTING_WORKERS_BY_PROFESSION`,
  including the new transport professions (Logistics Manager / Flight Crew /
  Seaman / Warehouse Manager) and Educator / Banker / Doctor technician
  backfills (Tutors, Banking Analyst & Clerk, Medical Orderlies).
- **Your Turn actions table** — added Purchase Capital, Apply Patent, Sell /
  Buy / Manage Insurance, Offer / Take / Roll Over Loan, View Loans.  Added
  a callout box on simultaneous play, pre-season window, and host Pause.
- **Production inputs table** — updated to current values (Farm Machinery,
  Mining Equipment, Lab Equipment, Metal flow into Manufacturer, etc.).
- **Base Prices table** — added Metal, Farm Machinery, Mining Equipment,
  Medical Devices, Transport Equipment, Lab Equipment, Passenger Seats,
  Patents.
- **Worker Professions table** — full refresh listing every profession with
  its band (Manager / Technician / Worker), with new entries in bold.
- **Training Capacity table** — bands added.  *(The "future balance pass"
  gap this section originally noted was subsequently closed by
  `claude/fix-playtest-bugs`, which added `UNIVERSITY_CAPACITY` entries
  for all 9 new professions.)*

#### New sections added

- **Setting Up: Auction, Island Guarantee, and Investing** (between
  Starting Conditions and Structure of Play) — covers the sealed-bid role
  auction, the §19.1 post-auction human island guarantee (with pricing
  formula explainer), and the Investing Phase.
- **Loans** (between Vaccines and Event Charts) — bullet-bond mechanics,
  borrowing flow with banker quote rate, repayment / default, and Roll Over.
- **Insurance** — Life and Medical products, Buy/Sell/Manage flows,
  pro-rata cancellation refund formula, high-hazard role flag.
- **Capital Equipment** subsection (under Production) — outright purchase,
  mid-game Purchase Capital action, 2-season delivery delay for complex
  items, 5-year straight-line depreciation, future lease pointer.
- **Patents** subsection — Apply Patent action, –20% input cost per Patent,
  cap 3 per output.

#### Misc

- Physical Contents list updated with the current resource and equipment
  token set, band-aware worker tokens, and loan/insurance contract cards.
- Export command updated to the installed `island-traders-export` entry
  point.
- Quick Reference fully refreshed (turn actions, setup phases, formulae,
  resources, capital-equipment lines, workforce baseline, loan-rate
  formula, insurance refund formula).

---

### claude/post-auction-human-guarantee

Branch: `claude/post-auction-human-guarantee`
Target: `pre-release`
Implements: `requirements/production-capacity-model.md §19.1`

#### Player-Facing Changes

- **Post-auction human island guarantee.** If a human player ends the auction
  with no island AND at least one AI player won two or more roles, a new
  guarantee phase opens before Investing.  Islandless humans are walked
  through sequentially (in join order) and offered every AI-extra island to
  take, at a price set by the §19.1 formula.  Each buyer may accept one or
  decline all.
- The islandless buyer sees a panel listing every eligible AI-extra island
  with its seller, the price they'd pay, and a tooltip explaining how the
  price was calculated.  Spectators see "X is choosing whether to take an
  AI island…" while the buyer decides.
- After the human takes control of an AI island, the island state (inventory,
  workforce, etc.) is preserved; the human can review and override the AI's
  default Investing-Phase orders in the next phase.

#### Pricing (§19.1)

Final price = `max(formula, floor)` where:
  * `floor` = 20% of buyer's current cash
  * `formula` depends on `ratio = ai_paid / starting_budget`:
    - `ratio in [11%, 15%]` (inclusive) → `2 × ai_paid`
    - `ratio > 15%`                     → `1.05 × ai_paid`
    - `ratio < 11%`                     → `ai_paid`

#### Server-Side

- New `IslandGuaranteeState` dataclass + `GameRoom.guarantee` field.
- New `room.status = "guarantee"` between `auction` and `investing`.
- New `room.ai_role_prices` captures per-role winning bid amounts so the
  guarantee phase can quote prices.
- New `compute_guarantee_price()` pure helper (testable in isolation).
- New GameManager methods: `_should_run_island_guarantee`, `_build_offers_for`,
  `_start_island_guarantee`, `_advance_island_guarantee`, `_finalize_island_guarantee`,
  `submit_guarantee_choice`, plus `_guarantee_timer` (90s per buyer, default).
- `_resolve_auction` now routes to the guarantee phase when conditions are met,
  otherwise straight to investing as before.
- WS protocol: `island_guarantee_state` (broadcast on entry / on each buyer's
  turn), `guarantee_choice` (client → server `{accept, role}`),
  `guarantee_ack`, `island_guarantee_resolved` (per buyer outcome),
  `island_guarantee_complete` (phase finished).
- Reconnect catch-up: clients connecting mid-guarantee receive the current
  guarantee state immediately.

#### UI

- New "🏝 Island Guarantee" panel on the auction screen (appears after
  auction-result-overlay is hidden).  Per-offer row with role, seller name,
  price, breakdown line ("seller paid X / floor / band"), and Buy / Decline
  buttons.  Unaffordable offers are dimmed.
- "How is the price calculated?" inline explainer.

#### Tests

- 20 new tests in `tests/test_server/test_island_guarantee.py` covering:
  * All three price bands + boundary inclusivity at 11% and 15%
  * Floor-dominates-formula case
  * Degenerate zero-starting-wealth input
  * Trigger condition true/false
  * Offer list building (all AI extras shown, affordability flags)
  * Phase entry sets state correctly
  * Accept path: role transfer, deductions updated
  * Decline path: queue advances
  * Not-your-turn rejection
  * Unknown-role rejection
  * Sequential buyers with two-AI scenarios
  * Sole-AI-loses-extras-after-one-sale skip path

#### Verification

- Test suite: `219 passed` (up from 199 baseline).

---

### claude/workforce-min-manager-tech

Branch: `claude/workforce-min-manager-tech`
Target: `pre-release`

#### Rules / Balance Changes

- **Workforce baseline rule:** every island now starts with at least 1 Manager
  and 2 Technicians.  Workforce totals adjusted where needed:
  * Transporter: 4 (was 4) — composition replaced
  * Educator: 4 (was 3) — bumped to fit the new technicians
  * Banker: 4 (was 3) — bumped to fit the new technicians
  * Doctor: 6 (unchanged) — mix changed (2 Doctors + 2 Nurses + 2 Medical Orderlies)

#### New Professions

- **Transporter:**
  * `LogisticsManager` (Manager) — strategic transport leadership
  * `FlightCrew` (Technician) — air freight ops
  * `Seaman` (Technician) — sea freight ops
  * `WarehouseManager` (Technician — ground-ops supervisor; named "Manager"
    by industry convention but classified as Technician per the operational
    tier)
- **Educator:**
  * `Lecturer` (Manager) — secondary faculty tier
  * `Tutor` (Technician) — apprenticeship-trained teaching staff
- **Banker:**
  * `BankingAnalyst` (Technician)
  * `BankingClerk` (Technician)
- **Doctor:**
  * `MedicalOrderly` (Technician) — backfills the missing technician tier
    on the Healthcare island

All new professions wired into:
  * `PROFESSION_BAND`
  * `BAND_TITLES` (Transporter / Educator / Banker titles refreshed)
  * `EDUCATION_SEASONS` (Logistics Manager, Lecturer = 2)
  * `APPRENTICESHIP_SEASONS` (all new technicians = 2)
  * `ROLE_PROFESSIONS`
  * `PROFESSION_LABEL`
  * `SKILLED_PROFESSIONS`
  * `STARTING_WORKERS_BY_PROFESSION`

#### Tests

- 5 new tests in `tests/test_models/test_profession_bands.py`:
  * `test_new_transporter_professions_have_correct_bands`
  * `test_new_technician_professions_for_educator_banker_doctor`
  * `test_transporter_band_titles_use_new_profession_names`
  * `test_every_island_starts_with_at_least_one_manager_and_two_technicians`
    — the invariant test
  * `test_every_profession_has_a_label`

#### Verification

- Test suite: `199 passed` (up from 194 baseline).

---

### claude/loans-and-insurance

Branch: `claude/loans-and-insurance`
Target: `pre-release`
Closes: GitHub #5, #6

#### Player-Facing Changes

- **Loan roll-over (Issue #6).** New `Roll Over Loan` action in the player
  action menu. The borrower picks an active loan, chooses a new term (1-3
  years), and the Banker quotes a new rate. The old loan's repayment becomes
  the new loan's principal — no cash moves at rollover, the new advance
  exactly covers the old repayment. Useful at or before maturity to extend
  obligations or to lock in a fresh rate quote.
- **Insurance review & cancellation (Issue #5).** New `Manage Insurance`
  action lists the player's active policies with seasons remaining and the
  pro-rata refund amount. Cancellation deactivates the policy and the Banker
  pays out a pro-rata refund (`premium × seasons_remaining / total_seasons`).
- Loans and Insurance side panels in the dashboard now show structured
  per-loan / per-policy detail: principal, rate, term, repayment amount,
  maturity date, seasons remaining, and cancel refund.
- Loans nearing maturity (≤1 season) and policies nearing expiry (≤1 season)
  are highlighted in gold to flag the renewal decision.

#### Engine

- New `LoanStatus.ROLLED_OVER`.
- New `Loan.rolled_over_from_loan_id` traceability field.
- New `LoanLedger.rollover_loan(loan_id, new_rate, new_term_years, year,
  season) -> Loan`. Refuses non-active loans or out-of-range terms.
- New `InsurancePolicy.seasons_remaining()` and `cancel_refund()` methods.
- New `Player.cancel_insurance_policy(policy_id, year, season) -> float` —
  returns the refund amount; caller is responsible for the cash transfer.
- New `TurnAction.ROLLOVER_LOAN` and `TurnAction.MANAGE_INSURANCE` with
  full prompt-chain implementations in `engine/turn.py`. Funding-side loans
  (lender_id == -1) are filtered out of rollover candidates.

#### Server

- `get_game_state` payload now includes `loans_detail` (structured per-loan
  info: role, principal, rate, term, maturity, seasons-to-maturity) and
  `policies_detail` (structured per-policy info: type, premium, expiry,
  seasons-remaining, cancel-refund). The plain `policies` string list is
  retained for back-compat.

#### Tests

- 15 new engine tests in `tests/test_engine/test_loan_rollover_and_insurance.py`:
  ledger primitives, action-level end-to-end (rollover, cancel, confirm-no
  cancellation), external bank funding-loan filtering, pro-rata math edge
  cases, double-cancel guard.
- 3 new server tests in `tests/test_server/test_game_state_loans_policies.py`
  covering the structured payload shape.

#### Verification

- Test suite: `194 passed` (up from 176 baseline).

---

### claude/pause-game

Branch: `claude/pause-game`
Target: `pre-release`
Closes: GitHub #1

#### Player-Facing Changes

- **Pause / Resume game (host only).** The room creator can pause the game at
  any point during auction, investing, or running phases. While paused:
  * All timers freeze (auction, investing, season-action, pre-season).
  * A full-screen "Game Paused" overlay covers the screen for every client.
  * Only the host sees the Resume button.
  * Players can still click Ready while paused, but the game does not advance
    until the host resumes.
- On resume, every timer end-epoch is bumped forward by the pause duration so
  no one loses time. If everyone clicked Ready while paused, the phase closes
  immediately on resume.

#### Server-Side

- New `paused: bool` and `paused_at: float` fields on `GameRoom`.
- New `request_pause(room_id, lobby_player_id, paused)` GameManager method,
  host-only.
- `_do_pause` cancels asyncio timer tasks (auction / investing / season);
  `_do_resume` reschedules them with the remaining seconds and bumps
  `*_timer_end` epochs forward.
- Pre-season game-thread wait loop now polls in 0.5s slices and respects
  `room.paused` — `pre_season_end` is bumped forward on resume so the wait
  naturally extends.
- `submit_ready` collects Ready presses during pause but does NOT fire
  `interrupt_all` or `_pre_season_done.set` until resume.
- WS protocol: client → `{type: "pause_request", paused: bool}`; server →
  `game_paused` / `game_resumed` broadcasts; `pause_ack` reply.
- Reconnecting clients receive `game_paused` if the game is currently paused.
- `room.to_dict()` now includes `creator_id` (so clients know who's host) and
  `paused`.

#### Tests

- New `tests/test_server/test_pause_game.py` — 12 tests covering host gating,
  pause/resume round-trip, timer-end bumping for auction/investing/season/
  pre-season, ready-during-pause queueing, quorum-on-resume short-circuit,
  and asyncio timer-task cancellation.
- Fixed `test_concurrent_ensure_player_does_not_create_duplicate_events`
  isinstance check (`threading.Lock` is a factory function on Python 3.9, not
  a class).

#### Verification

- Test suite: `176 passed`.

---

### claude/fix-action-menu-bug2

Branch: `claude/fix-action-menu-bug2`
Target: `pre-release`

#### Fixes

- **Fixed Bug #2: action menu stops displaying for some players.** Root cause
  was three race conditions in `WebSocketIOAdapter`:
  1. `_ensure_player` was not thread-safe — concurrent calls for the same
     player could create duplicate `Event`/`Lock` objects, leaving threads
     waiting on different Events.
  2. `_send_and_wait` had a split-lock gap between `event.clear()` and storing
     the pending message, allowing `interrupt_all()` or `receive_response()` to
     fire in the gap and be lost.
  3. No logging on timeouts or `None` responses made the issue hard to diagnose.
- Added structured logging in `ws_adapter.py` (choose_action, _send_and_wait)
  and `app.py` (unmapped lobby player IDs).
- Fixed `test_loans.py` Python 3.9 compatibility (missing `from __future__
  import annotations`).

#### Tests

- Added `test_concurrent_ensure_player_does_not_create_duplicate_events` —
  verifies thread-safe lazy initialisation with a 4-thread barrier.
- Added `test_response_during_send_and_wait_is_not_swallowed` — verifies
  near-instantaneous responses are not lost.

#### Verification

- Test suite: `135 passed, 2 skipped`.

---

### claude/test-fixes-and-spec-cleanup

Branch: `claude/test-fixes-and-spec-cleanup`
Target: `pre-release`

#### Balance Changes

- Every island now starts with sufficient resources for at least 2 seasons of
  production inputs (previously 1 season). Gives players breathing room to
  establish trade relationships before running out of critical inputs.

#### Fixes

- Fixed `test_loans.py` Python 3.9 compatibility (missing `from __future__
  import annotations`).
- Cleaned up spec cross-references between `production-capacity-model.md` and
  `island-ledger.md` to eliminate duplication.

#### Tests

- Added `test_every_island_starts_with_at_least_two_seasons_of_inputs`
  invariant test covering all 7 roles.
- Updated `test_economy_balance.py` assertions to match new starting inventory.

#### Verification

- Test suite: `135 passed, 2 skipped`.

---

## 0.1 (codex/future-fixes)

Branch: `codex/future-fixes`
Merged to: `pre-release`

### Player-Facing Changes

- Expanded browser dashboard with richer production capacity, funding-rate,
  market, training, loan, and deal-response flows.
- Added island artwork backgrounds and a wider right-hand market/info panel.
- Renamed player-facing role labels to island specialties, while preserving
  existing internal role identifiers.
- Added Release Notes and release-process documentation before the
  `pre-release` merge gate.

### Rules / Balance Changes

- Added Metal as an intermediate resource; Manufacturing product lines now use
  Metal instead of raw Ore.
- Reduced Mining Oil production and added Metal smelting with enhanced crusher
  and smelter support.
- Added mid-game capital equipment purchases from Manufacturing output.
- Added population-based Food/Fish demand signals, with educated workforces
  increasing Fish demand.
- Added richer loan terms, posted funding rates, banker quote logic, and
  net-wealth treatment including loans and depreciated equipment.
- Documented future requirements for cross-island machinery, product/equipment
  Help text, post-auction human island guarantees, and Claude worktree usage.

### Fixes

- Fixed deal response flow so counterparties can review pending deals on their
  turn.
- Fixed selected-product production so players choose what and how many to
  produce.
- Fixed training review/counteroffer flows and air-ticket requirements.
- Fixed multi-role Banker loan access.
- Fixed market board modal dismissal verification tracking.
- Fixed production capacity and constraint reporting around ordered/owned
  capital equipment.

### Known Issues / Follow-Up

- ~~Issue #2 remains open~~ — fixed in `claude/fix-action-menu-bug2`.
- Cross-island machinery, leases, release-ready Help catalogue, island-ledger
  ownership model, and post-auction AI island purchase are documented future
  requirements, not complete implementations.

### Verification

- Test suite status: `161 passed`.
- Manual browser testing: server restarted on `127.0.0.1:8001`; live gameplay
  testing still recommended before final merge.
