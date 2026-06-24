# Brief — On-island (local) training needs no transport / PassengerTickets (2026-06-23)

**Suggested owner:** Codex (training engine + tests).
**Relates to:** education-self-training-deadlock-2026-06-22 (reserved faculty lane), training-staffing.
**Base off:** `origin/pre-release` at **`a8853f0`** or later. `git fetch origin` and confirm.

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees — do NOT use the primary checkout.** Create your own worktree:
  `git fetch origin && git worktree add -b codex/local-training-no-transport-2026-06-23 ../it-codex-localtrain origin/pre-release`
- **PRs only.** Reach `pre-release` via a PR Claude merges. Update `RELEASE_NOTES.md` and bump
  `APP_VERSION` `.N`.
- **Git discipline.** No `--no-verify`/`--amend`/force-push. Run the **full** `pytest` suite.
- **Handoff.** "branch X at commit Y — ready to integrate."

## Why (observed)

Playtest 2026-06-23: training **Professor, Lecturer, Technical Director, or Instructor on the
Education Island itself** (the Educator growing its own faculty) still required arranging
transport / PassengerTickets. That's wrong: the trainees are **already on the island**, so no
transport is needed for local/on-island training. (Two earlier statements of the same
requirement: "When the Education Island accepts a request for training it is assumed the
trainee is already on the island so no PassengerTickets are required.")

## What exists today

- `island_traders/models/training.py`: `TrainingRequest.transport_mode` ∈
  {`air_ticket` (default — 1 PassengerSeats/trainee), `flight`, `cargo`, `self_training`,
  `transporter`}. `describe()` and the dispatch path branch on it; `air_ticket` requires the
  Educator/requester to supply PassengerSeats per trainee.
- The Educator's **own faculty self-training** already has a notion of `self_training`
  transport mode, and the reserved-lane work (`education-self-training-deadlock-2026-06-22`)
  added admission for it — but the **transport/ticket requirement** for on-island training was
  not addressed.

## Spec

1. **On-island training requires no transport.** When the trainees are already on the training
   island — i.e. the requester is the Educator training its own workers (`requester_id ==
   educator_id`), and/or `transport_mode == "self_training"` — **do not require PassengerTickets
   / a Transporter / any travel cost**. The cohort dispatches locally and returns locally.
   Apply this at minimum to the Educator's own faculty (Professor, Lecturer, Technical Director,
   Instructor), but the rule is general: **local trainee ⇒ no transport**.
2. **Don't break cross-island training.** A *different* island sending trainees to the Education
   Island still needs transport for the trainees to travel there (the existing `air_ticket` /
   `flight` / `cargo` paths). Only the **local** case is exempt.
3. **UI/state.** Where the training request flow asks the requester to arrange transport, skip
   that step for local training and make the turn log say it's local (no transport needed).
   Surface enough in `game_state` / the training payloads that Claude's frontend can hide the
   transport step for local requests (you provide the flag, Claude wires the UI).

## Tests

- An Educator self-training its own Professor/Lecturer/Technical Director/Instructor dispatches
  with **zero PassengerSeats consumed** and no Transporter involvement.
- A cross-island training request **still** requires/consumes transport (regression guard).
- The local cohort still returns and settles correctly (no transit-season anomalies).
- Full `pytest` suite green (baseline: **811 passing**).
