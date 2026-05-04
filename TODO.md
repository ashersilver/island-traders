# Island Traders — Enhancement Tracker

## In Progress

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
- [ ] Loans system (Banker offers loans with interest)
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
