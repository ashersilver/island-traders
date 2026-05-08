# Island Traders — Enhancement Tracker

## In Progress

### Production Capacity Model & Investing Phase
See [`requirements/production-capacity-model.md`](requirements/production-capacity-model.md) for full spec.
- [ ] Worker bands (Manager / Technician / Worker) with per-island titles
- [ ] Investing Phase between auction and Year 1 Spring
- [ ] Per-output capital catalogue + per-unit input requirements
- [ ] Production Capacity sidebar panel
- [ ] Production Constraint Popup (inputs / workforce / capital)
- [ ] Patents (Educator output, permanent boost, capped at 3 active per output)
- [ ] Apprenticeship pipeline (separate slot pool from Education)
- [ ] Education pipeline (Doctor 2 seasons, Nurse 1 season, other Managers 2)
- [ ] Mechanic profession (–20% per Mechanic, capped at –60%)
- [ ] Equipment Insurance (Banker product, market-rate replacement payout)
- [ ] AI auction bidding (per-role heuristic + 2nd round)
- [ ] Simultaneous-play architecture (timer + Ready button replaces End Turn)
- [ ] Season timer with 60-second flash warning

### Lobby & Game Start Redesign
- [ ] Redesigned start screen (visual polish, intuitive flow)
- [ ] Create game: public or private option
- [ ] Join game: browse public games, enter code, or receive invite
- [ ] Players join with proportional starting wealth & population (based on player count)
- [ ] Role auction phase: players bid Dollops for island roles
- [ ] Unclaimed roles become AI-controlled
- [ ] Game option: require all roles claimed by humans before start

### Financial Model
- [ ] Rename "Dollops" heading → "Working Capital" (suffix remains Dp)
- [ ] Introduce Loans as a balance sheet item
- [ ] Wealth = total assets at market value − loans outstanding
- [ ] All monetary values show Dp suffix consistently

### Dashboard
- [ ] Tabbed view: one tab per island/role the player controls
- [ ] Consolidated view when controlling multiple islands

## Backlog

### From CLAUDE.md
- [ ] README.md (proper GitHub project readme)
- [ ] RULES.md — fix Doctor workforce numbers (6 total: 2 Doctors + 4 Nurses)
- [ ] Simulation recalibration after ForgeHaven + insurance changes
- [ ] PDF export via reportlab (stretch goal)

### Feature Roadmap (from design review)
- [ ] Auction margin lending: borrow up to 50% of starting capital at 10% (Banker, back-to-back 5% IMF loan with island as collateral). See requirements/production-capacity-model.md §16.
- [ ] Roleless players — role aftermarket (secondary sales between players) + on-call bank deposits (depositors expand Banker's lending capacity). See requirements/production-capacity-model.md §17.
- [ ] Brokerage services: Banker negotiates deals between islands for a commission
- [x] Loans system (Banker offers bullet bonds — 1 year term, repaid at maturity with interest)
- [ ] Contracts & Futures (forward agreements between players)
- [ ] Infrastructure Investment (upgrade production capacity)
- [ ] Chat integration (in-game messaging)
- [ ] Market orders (limit orders, standing offers)
- [ ] Tournament mode (bracket play across multiple games)
- [ ] Population migration: islands lose population to others with higher standard of living
  - Standard of Living Index based on food per capita, insurance coverage, health services, etc.
  - Net migration proportional to differential between islands

## Completed
- [x] ForgeHaven product line differentiation (4 specialized product lines)
- [x] Banker insurance products (life + medical)
- [x] Workplace risk system (injuries, fatalities, experience scaling)
- [x] WebSocket game server + responsive dashboard
- [x] Fix WebSocket 403 (future annotations + local imports)
