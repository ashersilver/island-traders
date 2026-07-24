# Wave 10 — Professional salaries and training travel time (2026-07-22)

Source: Ash, 2026-07-22 —
1. "In regard to the Banking island having an advantage, Bankers and Actuaries
   receive very high salaries of the order of 5 Dp per season once they are
   qualified and on the island."
2. "If training takes place using regular PassengerSeats instead of airfare the
   trainee returns back halfway through the season instead of being available
   at the start of a season."

## Task 10.1 — Banker/Actuary salaries as a Banking-island cost (balance)

**Why:** the Banker consistently finishes near the top of the sim
(≈16.6% mean wealth share across seeds 42/1/7, second only to the Miner at
20.1%, versus the Farmer at 9.1%) while carrying almost no input costs — its
recipe needs only Expertise, and its income is loan spread plus premiums.
Paying its qualified professionals a premium salary gives the advantage a
running cost instead of nerfing the mechanics.

**Current model:** `PAYROLL_WAGE_BY_BAND` (`constants.py:28-32`) pays by *band*
only — Worker 0.25 / Technician 0.5 / Manager 1.0 Dp per active worker per
season, applied in the seasonal payroll pass. Profession is not consulted.

**Change:** add a per-profession salary override, applied on top of (replacing,
not adding to) the band wage for qualified holders of that profession who are
active on the island:

```python
# Qualified professionals command a premium far above the band wage; this is
# the running cost of the Banking island's income advantage.
PROFESSION_SALARY_PER_SEASON: dict[str, float] = {
    "Banker": 5.0,
    "Actuary": 5.0,
}
```

Rules:
- Applies only to **qualified** holders of the profession (i.e. those who
  completed training / hold the profession), and only while **active on the
  island** — trainees away and contracted-out staff are excluded, exactly as
  the existing payroll pass already excludes them.
- The override replaces the band wage for that worker; do not pay both.
- Surface it: the payroll line in the season report and the wellbeing/финance
  panel should show the premium-salary component separately from ordinary
  payroll so the Banker can see what its desk actually costs.

**Gate:** 3 same-seed sims. Expect the Banker's mean wealth share to fall; the
change is working if it lands nearer the field (target roughly 12–14% rather
than 16.6%) **without** pushing the Banker to routine insolvency. Record the
new baseline — this deliberately moves the economy, so the ±10% regression rule
does not apply to the Banker row for this wave.

## Task 10.2 — Sea travel costs the trainee half a season

**Requirement:** a trainee who travels on ordinary **PassengerSeats** (sea)
returns **halfway through the season** and is unavailable for the first half;
one who travels by **air** is available from the start of the season.

**Current model:** training travel consumes PassengerSeats
(`engine/turn.py:2149-2158`, split educator/requester), and returning trainees
become active immediately at the season boundary. There is no notion of a
partial-season return, and no air-vs-sea distinction on the training path —
though the capital catalogue already distinguishes `passenger_liner` (sea) from
`passenger_plane` (air), and capital delivery already has an
`expedited_eligible` air concept to mirror.

**Change:**
- Record the travel mode on the training request (sea by default; air when the
  requester pays the air premium / the route is served by a passenger plane).
- A sea-returning trainee is **half-available** for the season of return:
  they count as 0.5 of a worker for capacity and payroll that season, becoming
  whole from the following season. Air-returning trainees are whole immediately.
- Prefer the existing fractional-workforce arithmetic
  (`models/capacity.py` `workforce_capacity` already works in fractional
  per-unit terms) over inventing a separate "half worker" entity.
- Surface the return timing in the training pipeline panel so the requester can
  see "returns mid-Summer (sea)" versus "available Summer (air)", and price the
  air option so the choice is a real trade-off.

**Gate:** full suite plus 3 same-seed sims; assert a sea-returning trainee
contributes half capacity in the return season and full capacity thereafter,
and that air travel is unchanged from today's behaviour.

---

Sequencing: 10.1 first (small, self-contained, and it re-baselines the economy
that 10.2 will be measured against). Both are balance-affecting, so land them
separately with a sim run each rather than as one PR.
