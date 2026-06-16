# Island Traders — Development Roadmap

This document is the living prioritised plan for Island Traders development.
It is updated each release cycle and is the single source of truth for what
comes next. Detailed requirements live in the GitHub issue tracker
(`ashersilver/island-traders`) and in `requirements/`; this roadmap organises
them into phases and adds platform-level suggestions not yet captured as
issues.

**Reading this doc:** phases are roughly sequential but not strictly gated —
an item from Phase 3 can land before Phase 2 is complete if the work is
ready. Items marked ✦ are Claude's suggestions not yet tracked as a GitHub
issue; open one before starting the work. Items marked ~~like this~~ shipped
since the last roadmap update.

**Current version:** `0.1.5-dev.2026-06-15.5` (`island_traders/constants.py`).
Note: `pyproject.toml` still reads `0.1.4` — see Phase 0 (version reconciliation).

---

## Recently Shipped (as of 2026-06-16)

| Item | Issue / PR | Notes |
|------|------------|-------|
| `README.md` | — | Substantial project README already in repo (install, quickstart, play, simulate, print, test, tune) |
| UI v3 Phase 1 — dark prestige shell | [PR #150](https://github.com/ashersilver/island-traders/pull/150) (sub-task of [#149](https://github.com/ashersilver/island-traders/issues/149)) | Glass panels, backdrop, fonts, gold net-worth hero |
| UI v3 Phases 2 & 3 — cinematic islands + live overlay | [PR #153](https://github.com/ashersilver/island-traders/pull/153) (sub-task of [#149](https://github.com/ashersilver/island-traders/issues/149)) | Framed island hero, equipment pins, disaster FX, season tint |
| UI v3 Phase 4 — Build & Develop panel | [PR #156](https://github.com/ashersilver/island-traders/pull/156) (sub-task of [#149](https://github.com/ashersilver/island-traders/issues/149)) | Capital catalogue tile (Built / Available), ＋ Build… button |
| Simulation calibration | [#155](https://github.com/ashersilver/island-traders/issues/155) (PR #160) | Win-rate spread 12.3–16.6% (target ≈1/7) |
| Training `in_training` flag leak fix | [#154](https://github.com/ashersilver/island-traders/issues/154) (PR #160) | Personnel "In training" now reconciles against dispatch batches |
| P1 — Market-maker spread + finite depth | [#82](https://github.com/ashersilver/island-traders/issues/82) | Bid/ask spread; orders consume depth |
| P2 — Payroll (per-season wages) | [#83](https://github.com/ashersilver/island-traders/issues/83) | Workers cost Dollops every season |
| P3 — Consumer demand for end products | [#84](https://github.com/ashersilver/island-traders/issues/84) | External buyers create a demand floor |
| P7 — Net-worth scoring-driver panel | [#86](https://github.com/ashersilver/island-traders/issues/86) | UI panel breaking down each player's score |
| Durable equipment model | [#124](https://github.com/ashersilver/island-traders/issues/124) (PR #129) | FarmMachinery/MiningEquipment are durable capital, not per-season consumables |
| Metal smelting from Ore | [#125](https://github.com/ashersilver/island-traders/issues/125) (PR #129) | Metal smelted from Ore + energy, not a free co-product |
| Equipment warranties + failure model | [#130](https://github.com/ashersilver/island-traders/issues/130) (PR #129) | Manufacturer recurring revenue; failure events |
| Agent-interactions endpoint | [#132](https://github.com/ashersilver/island-traders/issues/132) (PR #133) | Observer UI can ingest agent moves in real time |
| Engineer training speciality | [#78](https://github.com/ashersilver/island-traders/issues/78) | 3-season base + optional 4th-season speciality |
| Science-track Reagent gating | [#76](https://github.com/ashersilver/island-traders/issues/76) | Reagents gate science/medical training |
| New professions (Actuary, Tradesman, Med Researcher, Med Tech) | [#75](https://github.com/ashersilver/island-traders/issues/75) | Four new profession types added |
| Bank Actuaries | [#24](https://github.com/ashersilver/island-traders/issues/24) | Actuary profession available for Banking island |

---

## Phase 0 — Housekeeping *(do first)*

**Goal:** close the gap between the codebase and its documentation; address
known easy wins before adding new features.

| Item | Issue | Notes |
|------|-------|-------|
| Reconcile version metadata | *(no issue yet)* | `pyproject.toml` reads `0.1.4` while `constants.py` reads `0.1.5-dev.2026-06-15.5`. Decide the canonical source and align (or document the dev-vs-release split in `requirements/release-process.md`) |
| Fix stale Doctor-workforce comment in `constants.py` | *(no issue yet)* | The comment at `constants.py` (`STARTING_WORKERS_BY_PROFESSION` Doctor block) still says "encoded simply as 2 Doctors + 4 Nurses". The code and `RULES.md` already use **2 Doctors + 2 Nurses + 2 Medical Orderlies** (6 total). Update the comment to match |
| Role complexity index | [#27](https://github.com/ashersilver/island-traders/issues/27) | Add High/Medium/Low activity index to "How to Play" so players can factor role effort into island bidding |
| Training bookings — batch UI | [#158](https://github.com/ashersilver/island-traders/issues/158) | Request training for multiple workers + job types in one dialog; include air tickets option |

---

## Phase 1 — Economy Fundamentals

**Goal:** complete the remaining core economic mechanics before layering new
gameplay content.

| Item | Issue | Notes |
|------|-------|-------|
| Capital purchases at game start | [#157](https://github.com/ashersilver/island-traders/issues/157) | Purchases deducted from island capital (not player wallet); shortfall covered by 3-year bank loans at preferred rate, secured against the assets |
| Freight friction on trades | [#85](https://github.com/ashersilver/island-traders/issues/85) | Market and inter-island trades consume Freight units or pay a fee routed to the Transporter; turns Transport from ingredient-seller to service economy |
| Loan rollover | [#6](https://github.com/ashersilver/island-traders/issues/6) | Roll over or renegotiate loans before/when due; negotiate a different rate of interest |
| Training costs (food, accommodation, duration) | [#18](https://github.com/ashersilver/island-traders/issues/18) | Full cost model: food + accommodation, course duration (1–4 seasons), expertise-per-semester; apprenticeship reduces vocational track by 1 season |

---

## Phase 2 — UI Utilities

**Goal:** now that the v3 visual shell is complete, ship the key missing
in-game productivity tools.

| Item | Issue | Notes |
|------|-------|-------|
| All-player summary on island layout | [#7](https://github.com/ashersilver/island-traders/issues/7) | Net-worth and key stats superimposed on the island map view |
| What-if production tables | [#4](https://github.com/ashersilver/island-traders/issues/4) | Spreadsheet-like panel: desired output → required inputs + gaps → one-click enact |
| Logo bolder + island popups | [#23](https://github.com/ashersilver/island-traders/issues/23) | Bolder top-left logo; click any island → formatted popup with description + graphic |
| Action alerts | [#3](https://github.com/ashersilver/island-traders/issues/3) | User subscribes to event types; non-blocking toast fires when that event appears in the log |
| In-game role guide panel ✦ | *(new issue)* | Collapsible quick-reference built from `requirements/role-player-guides.md`; visible from the player's tile without leaving the game |

---

## Phase 3 — Health, Environment & Insurance

**Goal:** add the interlinked systems that make the Doctor, Transporter, and
Farmer islands more strategic and interconnected.

| Item | Issue | Notes |
|------|-------|-------|
| Vaccines & flu season | [#49](https://github.com/ashersilver/island-traders/issues/49) | Winter flu reduces productivity up to 20%; 1 vaccine per 20 people → 80% infection reduction for one season |
| Quality of Life (QoL) metric | [#48](https://github.com/ashersilver/island-traders/issues/48) | Composite score (food, pollution, healthcare, forests); inter-island gap drives emigration; surplus drives population growth |
| Pollution | [#45](https://github.com/ashersilver/island-traders/issues/45) | Oil use generates pollution → missed workdays; forests offset (5 Produce to plant, 2-year grow time); medical coverage reduces impact |
| Doctors certify insurance | [#19](https://github.com/ashersilver/island-traders/issues/19) | Annual physical halves insurance premiums; insured workers have no productivity loss from harm; death pays out training-replacement cost (Bank → Island) |
| Hiring Doctors and Nurses | [#50](https://github.com/ashersilver/island-traders/issues/50) | 2–4 season contracts; Nurses reduce injury impact and improve nutrition efficiency by 20%; Doctors required for insurance certification |
| Medical island labs | [#26](https://github.com/ashersilver/island-traders/issues/26) | Doctor island produces Lab Tests resource (soil assay, metal assay, environmental assessment); required by Farmer (#42) and Miner as preconditions |

---

## Phase 4 — New Resources & Industries

**Goal:** expand the production graph with new capital investments and
resources that create strategic interdependencies between islands.

| Item | Issue | Notes |
|------|-------|-------|
| Lumber Mill | [#159](https://github.com/ashersilver/island-traders/issues/159) | Any island plants a forest (5 Produce; 2-year grow); Lumber Mill requires Forestry Technicians + Foreman; raw timber shippable to an island with a mill; lumber used in construction and products; mill byproducts improve Reagent yield |
| Fertiliser plant | [#42](https://github.com/ashersilver/island-traders/issues/42) | Convert Oil → Fertiliser (requires Engineer + Patent); improves Farmer grain/produce yield |
| Air Freight | [#51](https://github.com/ashersilver/island-traders/issues/51) | Transporter purchases freight aircraft + trains ≥2 Pilots; enables same-turn heavy capital delivery; requires Oil + Freight Insurance from Banker |
| Manufacturing MPS | [#43](https://github.com/ashersilver/island-traders/issues/43) | Production schedule for large capital items: bill of materials, resource queue, season-count lead time; some items need patents or engineers; delivery via cargo aircraft or +1 season by sea |
| Order book for capital equipment | [#63](https://github.com/ashersilver/island-traders/issues/63) | Manufacturer reviews and prioritises their order queue for named equipment (FarmMachinery, MiningEquipment, MedicalDevices, …); bill of materials shown per order; reorderable priority list |
| Seed presets / scenario packs ✦ | *(new issue)* | Named YAML presets layered on `config/event_charts.yaml` (e.g. "oil shock", "doctor shortage") for consistent, repeatable playtesting without knowing the internals |

---

## Phase 5 — Workforce Depth

**Goal:** make the workforce model richer — new specialist professions,
realistic training costs, and degraded-mode operation for understaffed islands.

| Item | Issue | Notes |
|------|-------|-------|
| Ecologist profession | [#25](https://github.com/ashersilver/island-traders/issues/25) | 2-season University training; qualifies for environmental assessment before capital comes online; commissions Lab Tests from medical island |
| Banking requires Lawyers | [#44](https://github.com/ashersilver/island-traders/issues/44) | New managerial tier; Lawyers required for large capital leases; trained at Education island |
| Missing workforce option | [#47](https://github.com/ashersilver/island-traders/issues/47) | Islands produce at a reduced rate (configurable floor) when a required profession is absent, rather than zero output |

---

## Phase 6 — Platform & Infrastructure

**Goal:** make the game easier to run, resume, share, and extend — especially
for multi-session and agent-driven play.

| Item | Issue | Notes |
|------|-------|-------|
| Save / load game state ✦ | *(new issue)* | JSON snapshot of the full `Game` object; lets sessions resume across days — essential for long games |
| Post-game export ✦ | *(new issue)* | Download CSV/JSON of the finished game: per-turn actions, trade ledger, final net worth; useful for AI agent calibration and post-mortems |
| Spectator / observer mode ✦ | *(new issue)* | Read-only dashboard for a facilitator or audience; pairs with the agent-interactions endpoint ([#132](https://github.com/ashersilver/island-traders/issues/132)) |
| OpenAPI spec ✦ | *(new issue)* | Document the REST/WebSocket surface so the agent adapter (`island-traders-agents`) and future UIs are self-describing |
| Automated calibration CI ✦ | *(new issue)* | GitHub Actions workflow: run `island-traders-sim --games 1000 --seed 42` on every `pre-release` merge; post win-rate CSV as a workflow artifact to catch regressions automatically |
| Mobile-responsive UI ✦ | *(new issue)* | Single-column stacked layout for tablet/phone; makes face-to-face play practical without a laptop |

---

## Phase 7 — Stretch / Future Parking Lot

These items are parked for the future — interesting but large, or dependent on
earlier phases landing first.

| Item | Issue | Notes |
|------|-------|-------|
| Warehousing | [#64](https://github.com/ashersilver/island-traders/issues/64) | Logistics island: refrigerated + bulk storage for a fee; food spoilage without refrigeration after one season |
| Intro / onboarding screen | [#8](https://github.com/ashersilver/island-traders/issues/8) | Board overview with hotspot popups + per-island graphics before the game begins |
| Tournament / season mode ✦ | *(new issue)* | Play N games in sequence with a persistent leaderboard; standings carry over between games; useful for structured play events |
| Game replay viewer ✦ | *(new issue)* | Play back a finished game turn-by-turn in the UI from the event log; valuable for post-mortems and AI agent tuning |

---

## Maintenance

Update this file as part of the release notes PR for each batch of work.
When an issue ships, move it to the "Recently Shipped" table at the top with
the PR number and version. When a ✦ suggestion is formalised, open a GitHub
issue and replace *(new issue)* with the link.

Terminology note: the engine models **named capital equipment**
(`FarmMachinery`, `MiningEquipment`, `MedicalDevices`, `LaboratoryEquipment`)
and **Reagents** — there is no generic `CapitalEquipment` resource. Use the
named-equipment + Reagents vocabulary in new docs and issues.

Version scheme: `APP_VERSION = 0.1.0-dev.YYYY-MM-DD.N` in
`island_traders/constants.py`. See `requirements/release-process.md` for the
full process.
