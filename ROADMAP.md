# Island Traders — Development Roadmap

This document is the living prioritised plan for Island Traders development.
It is updated each release cycle and is the single source of truth for what
comes next. Detailed requirements live in the GitHub issue tracker
(`ashersilver/island-traders`) and in `requirements/`; this roadmap organises
them into phases and adds platform-level suggestions not yet captured as
issues.

**Reading this doc:** phases are roughly sequential but not strictly gated —
an item from Phase 3 can land before Phase 2 is complete if the work is
ready. Suggestions marked ✦ are Claude additions not yet tracked as issues;
open one before starting the work.

---

## Phase 0 — Housekeeping *(do first)*

**Goal:** close the gap between the codebase and its documentation; clear the
known-bad state before adding new features.

| Item | Issue / ref | Notes |
|------|-------------|-------|
| Write `README.md` | *(CLAUDE.md §Pending 1)* | Install, quickstart, play, simulate, print, test, tune — see CLAUDE.md for full outline |
| Fix `RULES.md` Doctor numbers | *(CLAUDE.md §Pending 2)* | 6 total workers (2 Doctors + 4 Nurses), not 12/10 |
| Simulation calibration | [#155](https://github.com/ashersilver/island-traders/issues/155) | Target ≈1/7 win rate per role; tune `config/event_charts.yaml` |
| Role complexity index | [#27](https://github.com/ashersilver/island-traders/issues/27) | Add High/Medium/Low activity index to "How to Play" so players bid knowingly |
| Training bookings — batch UI | [#158](https://github.com/ashersilver/island-traders/issues/158) | Request training for multiple workers + job types in one dialog; include air tickets option |

---

## Phase 1 — Economy Fundamentals

**Goal:** complete the core economic mechanics that are missing or known-broken
before layering on new gameplay content.

| Item | Issue | Notes |
|------|-------|-------|
| Capital purchases at game start | [#157](https://github.com/ashersilver/island-traders/issues/157) | Purchases deducted from island capital; shortfall covered by 3-year bank loans at preferred rate |
| Payroll (per-season wages) | [#83](https://github.com/ashersilver/island-traders/issues/83) | Every active worker costs Dollops each season; changes the money-supply dynamic |
| Market-maker spread + finite depth | [#82](https://github.com/ashersilver/island-traders/issues/82) | Bid/ask spread; orders consume available depth; verify closed PR landed correctly |
| Consumer demand for end products | [#84](https://github.com/ashersilver/island-traders/issues/84) | External buyers create a demand floor; re-check Doctor win-rate regression from [#112](https://github.com/ashersilver/island-traders/issues/112) |
| Freight friction on trades | [#85](https://github.com/ashersilver/island-traders/issues/85) | Market and inter-island trades consume Freight units or pay a fee routed to the Transporter |
| Loan rollover | [#6](https://github.com/ashersilver/island-traders/issues/6) | Roll over or renegotiate loans before/when due |
| Net-worth scoring-driver panel | [#86](https://github.com/ashersilver/island-traders/issues/86) | UI panel breaking down what's driving each player's score |
| Training costs (accommodation, duration) | [#18](https://github.com/ashersilver/island-traders/issues/18) | Food, accommodation, and duration fees; apprenticeship reduces vocational length by 1 season |

---

## Phase 2 — UI Polish (v3 completion)

**Goal:** finish the approved dark-prestige visual redesign (Phase 1 already
shipped) and add the key missing UI utilities.

| Item | Issue | Notes |
|------|-------|-------|
| UI v3 Phase 2 — cinematic island hero | [#149](https://github.com/ashersilver/island-traders/issues/149) | Promote `island-art` from 34%-opacity wallpaper to framed hero with scrim + meta overlay |
| UI v3 Phase 3 — live overlay | [#149](https://github.com/ashersilver/island-traders/issues/149) | Equipment pins driven by `capital_inventory`; disaster/weather FX from `season_events`; season tint |
| UI v3 Phase 4 — Build & Develop panel | [#149](https://github.com/ashersilver/island-traders/issues/149) | Front-end for the existing Purchase Equipment action + season/weather display controls |
| All-player summary on island layout | [#7](https://github.com/ashersilver/island-traders/issues/7) | Net-worth and key stats superimposed on the board map |
| What-if production tables | [#4](https://github.com/ashersilver/island-traders/issues/4) | Spreadsheet-like panel: enter desired output → see required inputs + gaps; one-click enact |
| Logo bolder + island popups | [#23](https://github.com/ashersilver/island-traders/issues/23) | Bolder top-left logo; click any island → formatted popup with description + graphic |
| Action alerts | [#3](https://github.com/ashersilver/island-traders/issues/3) | User subscribes to event types; popup fires when that event appears in the log |
| In-game role guide panel ✦ | *(new issue)* | Collapsible quick-reference built from `requirements/role-player-guides.md`; visible from the player's tile |

---

## Phase 3 — Health, Environment & Insurance

**Goal:** add the interlinked health/environment systems that make the Doctor
and Transporter islands more strategic.

| Item | Issue | Notes |
|------|-------|-------|
| Vaccines & flu season | [#49](https://github.com/ashersilver/island-traders/issues/49) | Winter flu reduces productivity up to 20%; 1 vaccine per 20 people → 80% infection reduction |
| Quality of Life (QoL) metric | [#48](https://github.com/ashersilver/island-traders/issues/48) | Composite score (food, pollution, healthcare, forests); gap drives emigration; surplus drives pop growth |
| Pollution | [#45](https://github.com/ashersilver/island-traders/issues/45) | Oil use generates pollution → missed workdays; forests offset; medical coverage reduces impact |
| Doctors certify insurance | [#19](https://github.com/ashersilver/island-traders/issues/19) | Annual physical halves insurance premiums; insured workers have no productivity loss from harm; death pays out training replacement cost |
| Hiring Doctors and Nurses | [#50](https://github.com/ashersilver/island-traders/issues/50) | 2–4 season contracts; Nurses reduce injury impact, improve nutrition efficiency by 20% |
| Medical island labs | [#26](https://github.com/ashersilver/island-traders/issues/26) | Doctor island adds Lab Tests resource (soil assay, metal assay, environmental assessment); required by Farmer and Miner |

---

## Phase 4 — New Resources & Industries

**Goal:** expand the production graph with new capital investments and
resources that create interdependencies between islands.

| Item | Issue | Notes |
|------|-------|-------|
| Lumber Mill | [#159](https://github.com/ashersilver/island-traders/issues/159) | Any island can plant a forest (5 Produce; 2-year grow time); Lumber Mill + Forestry Technicians + Foreman; raw timber shippable to island with mill; lumber used in construction and products |
| Fertiliser plant | [#42](https://github.com/ashersilver/island-traders/issues/42) | Convert Oil → Fertiliser (requires Engineer + Patent); improves Farmer grain/produce yield |
| Air Freight | [#51](https://github.com/ashersilver/island-traders/issues/51) | Transporter purchases freight aircraft + trains 2 Pilots; allows same-turn capital delivery; requires Oil + Freight Insurance from Banker |
| Manufacturing MPS | [#43](https://github.com/ashersilver/island-traders/issues/43) | Production schedule for large capital items: bill of materials, resource queue, season-count lead time |
| Order book for capital equipment | [#63](https://github.com/ashersilver/island-traders/issues/63) | Manufacturer reviews and prioritises their order queue; bill of materials shown per order |
| Seed presets / scenario packs ✦ | *(new issue)* | Named YAML presets layered on `config/event_charts.yaml` (e.g. "oil shock", "doctor shortage") for repeatable playtesting |

---

## Phase 5 — Workforce Depth

**Goal:** make the workforce model richer — specialist professions, realistic
training costs, and degraded-mode operation without full staffing.

| Item | Issue | Notes |
|------|-------|-------|
| Ecologist profession | [#25](https://github.com/ashersilver/island-traders/issues/25) | 2-season training; qualifies for environmental assessment before capital comes online; commissions Lab Tests |
| Banking requires Lawyers / Actuaries | [#44](https://github.com/ashersilver/island-traders/issues/44) / [#24](https://github.com/ashersilver/island-traders/issues/24) | New managerial tier; Lawyers needed for large capital leases; Actuaries for insurance products |
| Missing workforce option | [#47](https://github.com/ashersilver/island-traders/issues/47) | Islands produce at reduced rate (configurable floor) if a required profession is absent |
| Engineer training speciality | [#78](https://github.com/ashersilver/island-traders/issues/78) | 3-season base + optional 4th-season speciality track |
| Science-track reagent gating | [#76](https://github.com/ashersilver/island-traders/issues/76) | Reagents gate science/medical training progression |
| New professions | [#75](https://github.com/ashersilver/island-traders/issues/75) | Actuary, Tradesman, Medical Researcher, Medical Technician |

---

## Phase 6 — Platform & Infrastructure

**Goal:** make the game easier to run, share, and extend — especially for
multi-session and agent-driven play.

| Item | Issue | Notes |
|------|-------|-------|
| Save / load game state ✦ | *(new issue)* | JSON snapshot of the full `Game` object; resume across days; essential for long games |
| Post-game export ✦ | *(new issue)* | Download CSV/JSON of the finished game: per-turn actions, trade ledger, final net worth; useful for AI tuning |
| Spectator / observer mode ✦ | *(new issue)* | Read-only dashboard for a facilitator or audience; pairs with the agent-interactions endpoint ([#132](https://github.com/ashersilver/island-traders/issues/132)) |
| OpenAPI spec ✦ | *(new issue)* | Document the REST/WebSocket surface so the agent adapter and future UIs are self-describing |
| Automated calibration CI ✦ | *(new issue)* | GitHub Actions workflow: run `island-traders-sim --games 1000 --seed 42` on every `pre-release` merge; post win-rate CSV as artifact |
| Mobile-responsive UI ✦ | *(new issue)* | Single-column stacked layout for tablet/phone; opens up face-to-face play without a laptop |

---

## Phase 7 — Stretch / Future Parking Lot

These items are parked for the future — interesting but large, or dependent on
earlier phases landing first.

| Item | Issue | Notes |
|------|-------|-------|
| Warehousing capability | [#64](https://github.com/ashersilver/island-traders/issues/64) | Logistics island: refrigerated + bulk storage for a fee; food spoilage without refrigeration |
| Intro screen | [#8](https://github.com/ashersilver/island-traders/issues/8) | Board overview with hotspot popups + per-island graphics before the game begins |
| Tournament / season mode ✦ | *(new issue)* | Play N games in sequence with a persistent leaderboard; standings carry over between games |
| Game replay viewer ✦ | *(new issue)* | Play back a finished game turn-by-turn in the UI from the event log; valuable for post-mortems and AI agent tuning |
| Banker AI lending model | [#72](https://github.com/ashersilver/island-traders/issues/72) | AI Banker evaluates creditworthiness and sets terms dynamically |
| Equity: authorized-but-unissued capital | [#107](https://github.com/ashersilver/island-traders/issues/107) | 40% non-auctioned capital as authorized-but-unissued; owner buy = primary issuance |
| Open source license | [#28](https://github.com/ashersilver/island-traders/issues/28) | Choose and add a LICENSE file |

---

## Maintenance

Update this file as part of the release notes PR for each batch of work.
When an issue ships, replace its link with ~~strikethrough~~ and note the
version in which it landed. When a ✦ suggestion is formalised, open a GitHub
issue and replace *(new issue)* with the link.

Version scheme: `APP_VERSION = 0.1.0-dev.YYYY-MM-DD.N` in
`island_traders/constants.py`. See `requirements/release-process.md` for the
full process.
