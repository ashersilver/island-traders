# Brief — Business Cycle & Severity-Scaled Disasters (2026-07-04)

**Status: APPROVED DIRECTION (Ash 2026-07-04) — implementation-ready.**
**Suggested owner:** Codex (engine/events) ; Claude (cycle/severity UI banners).
**Base off:** `origin/pre-release` @ `9938d48`, APP_VERSION `0.1.5-dev.2026-06-22.18`.
**Follows:** `_README.md`. Feeds `medical-response-quality-of-life-2026-07-04.md`
(QoL Stability, care demand) and `loan-negotiation-capital-premium-2026-07-04.md`
(posted rates). Respects `vaccines-flu-season-49-2026-06-18.md`.

## Problem

Disasters are absolute and shallow: one-season `yield_modifier` hits with no
severity dimension, no lasting damage beyond the (already-present but barely
used) `damage_seasons` field, no cash consequences, no workforce impact.
`_capital_failure_multiplier` is a constant 1.0 with a docstring promising
event wiring (game.py:929). The "economic cycle" is a hidden 4-phase modifier
array inside `posted_funding_rates` (loan.py:7) that nothing else can see.

## Design

### 1. BusinessCycle (game-level state machine)

`engine/cycle.py` — `BusinessCycle` owned by the game, advanced once per
season, seeded from the game RNG:

- Phases and durations (seasons): **Expansion 2 → Boom 1–2 (RNG) → Contraction 2 → Trough 1**
  ⇒ full cycle 5–6 seasons, per Ash.
- Outputs (consumed by other systems; all constants tunable):

| Phase | rate_modifier (pts on base cost of funds) | consumer demand × | QoL Stability drift |
|---|---|---|---|
| Expansion | −0.75 | 1.10 | +2 |
| Boom | +1.50 | 1.25 | +5 |
| Contraction | +0.75 | 0.85 | −3 |
| Trough | −0.50 | 0.75 | −5 |

- `posted_funding_rates(year, season)` gains a `cycle` parameter and drops its
  internal `cycle_modifiers` array (loan.py:12) — single source of truth.
- Event-chart tilt: Boom multiplies weights of positive entries (Bumper
  Harvest, Rich Vein, High Demand, Bull Market, Production Surge, Academic
  Excellence, Medical Breakthrough) ×1.5; Contraction/Trough multiply negative
  financial entries (Credit Crunch, Bank Crisis) ×1.5. Renormalise weights.
- UI: cycle phase chip in the header (e.g. "📈 Boom — credit tight, demand
  high"), phase-change line in the event log.

### 2. Severity dice on disasters

Each event entry may declare `severity: true` (earthquake, flood, mine
collapse, factory fire, storm damage, hospital strike→no, pandemic, disease
outbreak, oil spill). On draw, roll severity:

| Severity | p | yield hit | damage_seasons | workforce sidelined | capital failure ×
|---|---|---|---|---|---|
| Minor | 0.50 | as charted | as charted | 0–10% | ×1.5 |
| Major | 0.35 | charted −25% further | +1 | 20% | ×2.5 |
| Catastrophic | 0.15 | floor 0.0–0.2 | +2 | 35% | ×4 |

- **Wires the existing seam**: `_capital_failure_multiplier` returns the
  active severity multiplier for disaster-struck players that season
  (game.py:929 — the docstring already promises exactly this).
- Sidelined workers use the P1.1 sidelining model (2 seasons untreated /
  1 treated). If P1.1 hasn't landed, land the sidelining primitive here and
  P1.1 adds care on top (coordinate; whichever merges second wires them).

### 3. Pandemic: persistent, deep

Pandemic / Disease Outbreak / Pandemic Closure become **persistent states**
lasting `PANDEMIC_DURATION_SEASONS = 2` (reuses `damage_seasons` persistence):

- Productivity multiplier by severity: **−50% / −60% / −75%** (Ash: "might cut
  productivity by over 50%").
- Workforce sidelined (sick): 20% / 35% / 50%.
- Mitigation: vaccine coverage (#49 brief) reduces the sidelined share;
  medical care (P1.1) shortens individual recovery; QoL Stability −10 while
  active.

### 4. Earthquake (and catastrophic-tier disasters): rebuild levy

- Cash levy = **5% / 10% / 20%** of the player's capital replacement value
  (Σ catalogue cost of owned units), **min 20 Dp**, booked over 2 seasons
  (half each). Shortfall → unpaid remainder holds the damaged units in
  `failed` status (can't repair until the levy is cleared). No auto-loan —
  borrowing to rebuild is the player's call (nice loan-demand driver).

### 5. New scenario suggestions (add 3 now, park the rest)

Add now (one per underserved axis):
- **Energy Crisis** (all-role chart, rare): Oil price shock ×2 for 2 seasons
  (`price_shock_resource` already exists) — bites every island via inputs.
- **Harbour Blockade** (Transporter chart): freight charges ×3 for 1 season;
  Transporter yield −50% but freight *revenue* per unit up — a mixed shock.
- **Baby Boom** (all-role, rare, positive): population growth ×2 for 2
  seasons; QoL +5 while active.

Parked for later balance passes: Research Grant (Educator patents ×2), Gold
Rush (Rich Vein weight ×3 + injury rate ×2), Trade Fair (all consumer demand
×1.5 one season), Insurance Scandal (Banker premium income halved, QoL −5).

## Files

engine/cycle.py (new), engine/events.py (severity roll, persistence, weight
tilt), engine/game.py (cycle advance, levy, failure multiplier), models/loan.py
(rate hook), config/event_charts.yaml (severity flags, new entries),
engine/workforce_events.py (sidelining primitive if landing first), UI (Claude).

## Acceptance criteria

1. Cycle advances Expansion→Boom→Contraction→Trough in 5–6 seasons; posted
   rates match the phase table exactly (unit test per phase).
2. Catastrophic earthquake: yield floored, failure multiplier ×4 applied that
   season, levy = 20% of replacement value split over 2 seasons, unpaid levy
   blocks repairs.
3. Pandemic persists exactly 2 seasons, productivity −50% at Minor, sidelined
   share reduced by vaccine coverage.
4. Full pytest; **1000-game seed-42 sim**: all role shares within ±2pts of
   baseline (cycle is symmetric; severity adds variance not bias — quote the
   per-role stddev change in the PR); bankruptcy rate < 2× baseline.

## Out of scope

QoL index computation and care (P1.1 brief), loan negotiation (P1.3),
insurance-product pricing changes.
