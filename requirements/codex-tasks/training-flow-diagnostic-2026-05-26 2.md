# Codex Task — Training flow diagnostic + unblock (2026-05-26)

**Owner:** Codex
**Origin:** Recurring playtest defect (2026-05-26, `0.1.0-dev.2026-05-26`). The user reports: *"There's still something wrong in training — it seems that there are a lot of constraints in place to provide training and return the trainees to their islands."* This is the **third** consecutive playtest cycle where training has been called out as broken or over-constrained. The previous two cycles fixed concrete bugs (workers not returning from training, AI Educator not approving requests, ticket-supply mechanics) but the symptom keeps coming back.

The user is not asking for new functionality — they're asking us to find the remaining choke points and remove them.

## Goal

**Diagnose-and-fix pass** on the entire training pipeline, end to end. Find every place where a training request can quietly stall, every place where a trained worker can fail to return to their home island, and every place where the Educator's approval / dispatch loop can drop a request without telling the requester why. Fix what you find. Add or strengthen regression tests so the next cycle doesn't surface a new variant of the same complaint.

## Branching

- **Base:** `pre-release` at `6d3888e` (current head — restore-action-menu fix) or later.
- **Branch name:** `codex/training-flow-diagnostic-2026-05-26`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## What we already know from previous cycles

- **Phase 1** (training-staffing-2026-05): redesigned the per-course staffing rule (0.5 Prof + 1 Lect + 2 Expertise for Manager / 0.5 TD + 1 Instructor + 1 Expertise for Technical). Bootstrap fix added 4 Lecturers to the Educator starting workforce.
- **Phase 2** (training-ux-improvements-2026-05): added 10 PassengerSeats to Educator starting inventory + `tickets_supplied_by_requester` so requesters can supply their own seats. Added `request_summary` payload for the approval modal.
- **Recurring symptom across all three cycles:** trainees sometimes never return to their home island even after the training period nominally elapses. User reported this explicitly in 2026-05-22 and again on 2026-05-26.

## Suggested investigation order

These are *hypotheses*, not a prescribed work plan — run with whichever ones the code tells you are real and ignore the ones that aren't.

1. **Return logistics.** Trace the path from "training complete" → "worker re-added to home roster". Look in `engine/turn.py` (post-season hook), `models/training.py` (TrainingRequest lifecycle), and `models/workforce.py` (`WorkforceRoster.add`). Specifically: is the return gated by anything that can silently fail? (PassengerSeats availability on the *return leg*, capacity check on the home roster, an off-by-one in the "seasons remaining" counter, a `TrainingStatus` transition that lands in an end-state without firing the return?)

2. **Educator dispatch under load.** When the Educator has more incoming approved requests than they have classroom slots for the current season, what happens to the overflow? Are they re-queued or silently dropped? If re-queued, do they survive across years? Worth checking that the AI Educator doesn't `END_TURN` with pending approved requests still in the queue.

3. **Ticket math under partial supply.** With `tickets_supplied_by_requester`, the dispatch is supposed to consume seats from the requester first, then from the Educator. Confirm the rollback path on a *failed* dispatch (e.g. Educator runs out of seats after the requester paid) doesn't leave the requester's seats burned without trainees moving.

4. **Sustenance interaction.** Workers in training are physically on the Educator island — are they consuming sustenance there, on their home island, in both, or in neither? If neither, the basket allocator might be under-reporting demand and skewing yields. If both, they're double-fed and the home island has phantom population. Either skew distorts the win-rate band.

5. **Cancel / decline paths.** When a request is declined, counter-offered, or the requester runs out of cash before approval, are the workers correctly returned to the requester's "Unskilled" pool? Same for an explicit "withdraw request" if one exists.

6. **AI Educator behaviour.** Confirm the AI Educator strategy in `engine/ai.py` actually walks the pending-requests queue every season and approves anything it can staff. Confirm it doesn't pass on requests just because the next-season ROI is uncertain — the user explicitly flagged "AI Educator not approving training" as a recurring complaint.

7. **Display-title vs trainable-profession mismatch.** (Added 2026-05-26 from a fresh playtest complaint: *"Manufacture doesn't see a Factory Foreman in the training list."*)  `BAND_TITLES` in `island_traders/models/profession.py` lists per-island display labels that don't all correspond to entries in `ROLE_PROFESSIONS`. Concretely, the Manufacturer Technician band shows "Factory Foreman" / "Assembly Tech" / "Mechanic" as roster titles, but `ROLE_PROFESSIONS["Manufacturer"]` only registers `ASSEMBLY_WORKER` and `MECHANIC` as trainable — there's no `Profession.FACTORY_FOREMAN` enum at all. Same gap probably exists for Miner ("Mining Foreman", "Refiner"), Transporter ("Stevedore"), Doctor ("Aide"). Decide per role whether to (a) add the missing profession enums + training pipelines so the UI labels are real career paths, or (b) collapse the display-title list to match the actual trainable set so players don't see phantom job titles. Either is fine — pick one per role and document the choice in the PR description. Make sure the AI Educator and the requesting AI both see the same set of profession options the human UI shows.

## Acceptance criteria

- **Pre-fix diagnostic report** in the PR description: list every choke point you investigated, what you found, and what you changed (or didn't, and why). This is as valuable as the code — Claude will use it to brief the next playtest cycle.
- **Test coverage** specifically for the return-leg failure modes: at least one regression test per real bug found, plus a "happy path: 3 trainees go to Educator, train for N seasons, all 3 land back on home roster with the new profession" end-to-end test.
- **Engine log lines** at every state transition (approve / decline / counter / dispatch / arrive / train-complete / return / fail-return). Use the existing `print` / log channel; the user has called out that they only see "messages 4 and 5" in the in-game log when training fails — that's a sign the earlier transitions aren't logging.
- **No regression** on the post-balance band: 1000g seed 42 + 4-seed sweep show all 7 roles in [12 – 18 %] win rate, with Educator no more than +2 pp warmer than the post-calibration baseline (17 – 18 %).
- Full test suite green at the new baseline count (429 + new tests).
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/training-flow-diagnostic-2026-05-26` block listing what shipped.

## Out of scope for this brief

- New training mechanics (no new professions, no new course types, no new ticket types).
- UI changes (Claude will pick those up if your engine changes need a new surface).
- AI Educator's broader island-management behaviour (separate issue; will get its own brief if it comes back).
