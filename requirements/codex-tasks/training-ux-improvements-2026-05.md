# Codex Task — Training UX Improvements (2026-05-25)

**Owner:** Codex
**Origin:** Bug 1 (training stuck) follow-up + the in-game "approval box doesn't show what you're approving" observation. Three small-but-impactful improvements that together close the cross-island-training loop.

## Goal

Three changes, ranked by how often they bite players:

1. **Add 10 PassengerSeats to Educator's `STARTING_INVENTORY`** — eliminates the Bug 1 #5 failure mode ("needs N PassengerSeats air ticket(s)") for the first 2–3 cross-island training requests in a fresh game.
2. **Let the training requester supply their own PassengerSeats** — bypasses the air-ticket gate entirely when the requester has the seats and is willing to spend them. The requester can then offer a **lower** Educator fee since the Educator isn't sourcing tickets.
3. **Approval prompt shows the full training request** — when the Educator (human or AI) reviews a pending request, the prompt must list every relevant detail (trainee count, target profession, transport mode, fee, who supplies tickets, requester name, current status). Today the prompt is sparse and the reviewer can't tell what they're agreeing to.

Combined, these unblock cross-island training in the common case without rewriting the staffing model.

## Branching

- **Base:** `pre-release` at `409c810` ("Merge codex/training-staffing-2026-05 e0c4411") or later.
- **Branch name:** `codex/training-ux-improvements-2026-05`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Sequencing

This brief is independent of the lease subsystem (`capital-equipment-lease-2026-05.md`); pick up whichever's convenient first. Both must land **before** the next calibration re-run (`balance-calibration-2026-05.md`), so calibration sees the final training cadence.

## Spec

### Item 1 — Educator starts with 10 PassengerSeats

In `island_traders/constants.py`, update `STARTING_INVENTORY["Educator"]`:

```python
"Educator":      {"Expertise": 6,
                  "Courses": 5,
                  "LaboratoryEquipment": 2,
                  "PassengerSeats": 10},   # NEW — bootstraps cross-island training
```

That's enough to dispatch ~10 trainees worth of cross-island courses before the Educator must acquire more tickets from the market.

### Item 2 — Requester-supplied PassengerSeats

**TrainingRequest field.** Add to `island_traders/models/training.py`:

```python
@dataclass
class TrainingRequest:
    ...
    tickets_supplied_by_requester: int = 0   # NEW
```

Semantics:

- `0` (default) — Educator supplies all `len(worker_ids)` PassengerSeats from their own inventory at dispatch (existing behaviour).
- `N > 0` — the requester pledges to supply `N` of the required `len(worker_ids)` tickets from their own inventory at dispatch. Educator supplies the remainder (`len(worker_ids) - N`). If the requester is supplying all of them, the Educator's ticket gate is satisfied trivially.

**Request-flow prompt.** In `_action_request_training` (`island_traders/engine/turn.py`), after the worker count is chosen and BEFORE the dollop fee is asked:

- If `transport_mode == "air_ticket"` AND `requester.inventory.get(PASSENGER_SEATS) > 0`:
  - Prompt `choose_quantity("How many PassengerSeats will you supply yourself (saves on Educator fee)?", min=0, max=min(worker_count, requester.inventory.PASSENGER_SEATS))`.
  - Store the answer on `req.tickets_supplied_by_requester`.
- If requester has zero PassengerSeats, skip the prompt; default to 0 (Educator supplies all).

**Fee adjustment.** The current AI Educator fair-rate ask in `_ai_educator_respond` is:

```python
fair_rate   = 20.0 * len(req.worker_ids)
ticket_cost = market.current_price(PASSENGER_SEATS) * len(req.worker_ids)
required_offer = fair_rate + ticket_cost
```

Change `ticket_cost` to only cover the tickets the Educator must source:

```python
educator_tickets = len(req.worker_ids) - req.tickets_supplied_by_requester
ticket_cost      = market.current_price(PASSENGER_SEATS) * educator_tickets
required_offer   = fair_rate + ticket_cost
```

So a requester supplying all their own tickets only needs `20 Dp × worker_count` for the AI Educator's fair-rate gate. The human-Educator review path uses the same `ticket_cost` arithmetic to display the suggested fee.

**Suggested fee in `_action_request_training`** (the value the requester sees as the default `dollops_to_educator` prompt prefill) — recompute to reflect `tickets_supplied_by_requester`. The requester gets visible feedback that self-supplying reduces the suggested fee.

**Dispatch flow.** In `_ensure_training_air_tickets` (`turn.py` ~line 961):

```python
def _ensure_training_air_tickets(self, educator, req, requester=None):
    """Consume PassengerSeats for this batch.
    
    Requester supplies tickets_supplied_by_requester from their own
    inventory; Educator supplies the rest. Returns False if either side
    can't cover their share.
    """
    requester_share = req.tickets_supplied_by_requester
    educator_share  = len(req.worker_ids) - requester_share
    if requester is not None and requester_share > 0:
        if requester.inventory.get(ResourceType.PASSENGER_SEATS) < requester_share:
            return False
    if educator.inventory.get(ResourceType.PASSENGER_SEATS) < educator_share:
        return False
    if requester is not None and requester_share > 0:
        requester.give_resources(ResourceType.PASSENGER_SEATS, requester_share)
    if educator_share > 0:
        educator.give_resources(ResourceType.PASSENGER_SEATS, educator_share)
    return True
```

Update callers (`_ai_educator_respond` and the human-Educator review path) to pass the requester player.

### Item 3 — Approval prompt shows full request details

The Educator's review/approve flow currently presents a thin prompt. Replace it with a structured detail-rich prompt. Concretely:

- In `_action_review_training` (`turn.py`), before the existing approve/reject/counter prompt, emit a multi-line description via `io.print` (or pass it as part of the prompt text — Codex's call):

```
Training request #4 from "Farmer Island":
  - Trainees:           3 worker(s)
  - Target profession:  Nurse (Manager-tier, university-trained, 1 season away)
  - Educator fee:       80 Dp (offered)
  - Transport:          Air ticket — requester self-supplies 0 of 3, Educator supplies 3
  - Suggested floor:    20 × 3 + price(PassengerSeats) × 3 = 80 Dp (current)
  - Workforce impact:   3 of 6 Farmer Unskilled workers depart for 1 season
```

The exact field set is flexible — Codex's call which fields are useful. The principle: the reviewer should never have to ask "wait, what am I agreeing to?"

This applies to both:
- The human-Educator's `choose_option` prompt for approve/counter/reject.
- The requester's `choose_option` prompt for accept/reject-counter (existing counter-offer flow). Same detail block, same field set.

**Server payload.** Add a `request_summary` (or similar) field to the prompt payload that the dashboard can render in the existing approval popup. UI rendering is **out of scope for Codex** — flag in the brief that a Claude branch will follow up to render the structured summary in the dashboard's approval modal.

## Out of scope

- Client-side UI rendering of the new request_summary payload — Claude UI follow-up branch.
- AI Educator proactive PassengerSeats market-buying — separate (smaller) follow-up if needed.
- Changing the staffing model — that's `codex/training-staffing-2026-05` (already shipped). This brief layers on top.
- Anything in `island_traders/server/static/` — Claude domain.
- Game balance constants outside the items above.

## Tests required

Add to `tests/test_engine/test_training_ux.py` (or extend existing training test files where natural):

1. `test_educator_starts_with_10_passenger_seats` — `STARTING_INVENTORY["Educator"]["PassengerSeats"] == 10`.
2. `test_request_with_zero_self_supplied_tickets_uses_educator_inventory` — `tickets_supplied_by_requester=0` (default) consumes tickets only from the Educator at dispatch.
3. `test_request_with_partial_self_supplied_tickets_splits_consumption` — `tickets_supplied_by_requester=2` of a 5-worker batch consumes 2 from requester, 3 from Educator.
4. `test_request_with_full_self_supplied_tickets_skips_educator_ticket_gate` — `tickets_supplied_by_requester=N` (= worker_count) means Educator with 0 tickets can still approve.
5. `test_ai_educator_fee_drops_when_requester_self_supplies_tickets` — AI's `fair_rate + ticket_cost` ask drops by `price(PassengerSeats) × tickets_supplied_by_requester` per request.
6. `test_ai_educator_approves_lower_offer_when_requester_self_supplies` — a previously-too-low offer is now accepted because the AI's threshold dropped.
7. `test_dispatch_fails_when_requester_promises_tickets_but_lacks_inventory` — requester pledged 3 tickets but has only 1 in inventory at dispatch time → batch stays pending, no tickets consumed from either side.
8. `test_approve_prompt_payload_includes_request_summary` — the prompt payload (server-side, what the IO adapter sends) for an Educator approval includes a `request_summary` field with trainee count, target profession, transport-mode-with-tickets-breakdown, and offered fee.
9. `test_counter_prompt_payload_includes_request_summary` — same `request_summary` field appears on the requester's counter-acceptance prompt.

Run the full suite. **Bar is the full suite green plus the new tests.**

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

Expected: ≥ `404 + 9 = 413 passing` (or more if you add extra coverage).

## When to stop and hand off

Push the branch when:

- All three items implemented per spec.
- 9+ new tests + suite green.
- `RELEASE_NOTES.md` has a new `### codex/training-ux-improvements-2026-05` section listing the three items + UI follow-up flag.
- Signed-off commits.

**Do not:**

- Modify any client-side file (Claude UI follow-up handles the request-summary rendering).
- Tag a release.
- Merge into `pre-release` yourself.

## What to push

```bash
git push -u origin codex/training-ux-improvements-2026-05
```

Open a PR with summary, new test count, and a note about the Claude UI follow-up.

## When to wait for merge

After pushing:

1. **Wait** for Claude to review (the approval-prompt change interacts with both human and AI flows; wants a careful pass).
2. **Wait** for Claude to merge.
3. Claude will follow up with a UI branch surfacing the `request_summary` in the dashboard's approval modal.

## Reference

- **Existing AI Educator response:** `island_traders/engine/turn.py::_ai_educator_respond` (~line 880).
- **Existing human-Educator review:** `_action_review_training` (~line 1167).
- **Air-ticket consumption helper:** `_ensure_training_air_tickets` (~line 961).
- **TrainingRequest dataclass:** `island_traders/models/training.py` (~line 60).
- **Existing prompt mechanism:** `_send_and_wait` in `island_traders/server/ws_adapter.py` — server payload to client. The new `request_summary` field gets added to the payload of `choose_option` prompts where appropriate.
- **STARTING_INVENTORY:** `island_traders/constants.py` (~line 21).
- **Related TODO:** none new — this brief picks up the Bug 1 #5 follow-up I flagged in the conversation thread that produced the staffing redesign.
