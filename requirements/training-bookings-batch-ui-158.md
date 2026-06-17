# Implementation note — #158 Training Bookings: batch UI (scoped 2026-06-16)

**Issue:** [#158](https://github.com/ashersilver/island-traders/issues/158) —
*"The training request dialog should be able to request training for multiple
workers and multiple job types at the same time. There should be an option to
supply air tickets."*

**Status:** scoped, not yet built. Phase 0 UI item (Claude). The backend is
largely done — this is mostly a **frontend dialog** + one small **read-only
payload addition**.

---

## What already exists (do not rebuild)

- **Batch submit handler:** `ServerApp._handle_training_batch`
  (`island_traders/server/app.py:2582`) accepts
  `{type: "training_batch", batch_ref, requests: [row, ...]}` and returns
  `{type: "training_batch_result", batch_ref, results: [...]}` (per-row), then a
  fresh `game_state`. Routed in the WS dispatcher at `app.py:4570`.
- **Per-row schema** (`_submit_training_batch_row`, `app.py:2626`):
  - `profession` (str, required — the target job type)
  - `count` (int, required — number of workers)
  - `campus_player_id` (optional — which Educator; resolver picks one if omitted)
  - `transport_mode` ("air_ticket" default | sea/PassengerSeats |
    "self_training" when requester is the Educator) — **air-ticket option already
    modelled** (`app.py:2656`; payload reflects it at `app.py:3285`)
  - `tickets_supplied_by_requester` (int — air tickets the requester provides)
  - `dollops_to_educator` / `fee` (float)
  - `specialty` / `engineer_specialty` (str, optional — Engineer 4th-season)
- **Worker selection** is automatic given `count`
  (`_select_training_workers`, `app.py:2647`) — the dialog supplies counts, not
  individual worker ids.

## The one gap (small, read-only) — expose trainable professions in the payload

The current sequential wizard computes the selectable professions server-side in
`_action_request_training` (`island_traders/engine/turn.py:982`) from
`training.capacity_summary(year, season_index)` (professions with remaining
slots) + `_training_skill_deficits(player)` + the count of eligible trainable
workers (`workforce.get_trainable_ids` minus reserved). A **client-side** dialog
needs that same data in `game_state`. Add a per-player field, e.g.:

```
training_options: {
  professions: [
    {value, label, remaining, seasonal_cap, annual_cap, suggested_count}
  ],
  eligible_worker_count: <int>,        # trainable, not reserved
  exhausted: [{value, label, trained, annual_cap}]  # show greyed, with reason
}
```

Reuse `capacity_summary` + `_training_skill_deficits` verbatim — no new
mechanics. This is read-only server glue (integrator-safe), **or** hand it to
Codex as a thin server-seam task while Claude builds the dialog (matches the
#114 Order/Training Desk split: second-to-merge wires the call).

## Frontend dialog (Claude)

Build a **Training Desk** modal (reuse `showDlg`, `island_traders/server/
static/index.html:5670`; send via `sendWsMessage`, `index.html:2969`), launched
from the `request_training` action (currently routed to the old wizard, see the
hint at `index.html:4472`) and/or a dedicated button on the player tile.

- **Dynamic rows** (add / remove). Each row:
  - job-type `<select>` from `training_options.professions` (show remaining
    slots; disable exhausted ones with the reason as a title),
  - worker count (clamped to `min(remaining, eligible_worker_count)` budget
    shared across rows — track a running remaining-workers tally),
  - transport toggle: **Air ticket** vs **By sea (PassengerSeat)**; when air,
    a `tickets_supplied_by_requester` count,
  - optional fee (`dollops_to_educator`) and Engineer `specialty` when relevant.
- **Submit** one `training_batch` with all rows + a generated `batch_ref`.
- **Handle `training_batch_result`:** show per-row success/error (the result
  array is index-aligned to `requests`); leave successful rows, surface failed
  ones with their `error` string. A fresh `game_state` follows automatically.
- Keep the old single-request path working (AI + `FakeIOAdapter` use the wizard);
  the desk is additive on the web client.

## Verification

Reaching the in-game training UI needs a running game (auction → investing →
turn). Verify with the preview server: start a quick-seat game, advance to a
turn, open the Training Desk, stage 2 rows (two professions, one air / one sea),
submit, and confirm the `training_batch_result` toasts + the training strip
(`index.html:656`) updates. Capture a screenshot.

## Definition of done

- `training_options` payload field (Claude or Codex seam).
- Training Desk multi-row dialog submitting `training_batch`, with air-ticket
  option and per-row result handling.
- `APP_VERSION` bump + `RELEASE_NOTES.md`; PR `Closes #158`.
- In-browser verification screenshot.
