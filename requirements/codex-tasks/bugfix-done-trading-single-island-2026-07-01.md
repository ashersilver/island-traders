# Brief — Bug: "Done Trading" button only shown on one island (2026-07-01)

**Suggested owner:** Codex (engine: diagnose + fix `season_active_humans`
computation / broadcast timing).
**Base off:** `origin/pre-release` at `3399e9f` (APP_VERSION `0.1.5-dev.2026-06-22.16`
— confirm current tip before starting).
**Tracking issue:** none filed yet — file a new issue titled "Done Trading
button missing on some islands mid-season" if the root cause is confirmed,
and close it in the PR.
**Pairs with:** none — this is engine-only; no frontend changes expected
unless the root cause turns out to require a client-side fix, in which case
say so in the handoff and Claude will pick it up.

> **Process:** See `requirements/codex-tasks/_README.md` — that file is the
> standing working agreement and overrides anything here on process.

---

## Symptom (reported during a 6-human + 1-AI playtest, 2026-07-01)

During the action phase, the "Done Trading ✓" button (`#ready-btn` in the
frontend) was visible on only **one** of the six human players' island tabs.
The other five saw no Done Trading control at all — they could still act, but
had no way to signal readiness to advance the season.

This was observed live; no server logs were captured (backgrounded process,
no `--terminal` output redirected to a file this run). **First step: get a
repro with logging captured** — run a similar 6-7 human config with server
stdout piped to a file (`... 2>&1 | tee /tmp/it-server.log`) so the
`[season-timer]` log line (see below) and any auction/role-assignment
logging is available for the actual repro, not just static reading of the code.

---

## Where to look

### 1 — `active_humans` computation (`app.py`, `_start_season` / season loop)

```python
humans = {
    lp.player_id for lp in room.players
    if lp.is_human and lp.role_names
}
```

This set is broadcast once at `season_start` (and again at `pre_season_start`)
via `active_humans`. Each client independently computes
`showForMe = seasonActiveHumans.has(myPlayerId)` and toggles `#ready-btn`
visibility on that.

**Hypothesis A — role_names race.** If a human player's `role_names` list is
empty at the exact moment `_start_season` runs (e.g. mid-transfer via the
role-transfer path at `app.py:1157-1162`, which does
`seller.role_names.remove(role)` then `buyer.role_names.append(role)` as two
separate statements — not atomic), that player would be excluded from
`humans` for that season's `active_humans` broadcast, even though they hold a
role a moment later. Check:
- Does any in-game mechanic in this config (training-into-new-role,
  role-transfer, insurance, etc.) remove and re-add a role for one of these
  six human seats around the time the bug was observed?
- Is `_start_season` ever invoked concurrently with a role-mutating handler
  (i.e., is there a lock/mutex around `room.players` mutations, or could the
  season-loop thread read `role_names` while a WS handler thread is
  mid-mutation)? Search for `threading.Lock` / `room_lock` usage around
  `room.players` mutations vs. the season loop in `app.py`.

**Hypothesis B — stale `myPlayerId` after reconnect.** If one of the six
human tabs reconnected (browser refresh, network blip) between
`pre_season_start` and `season_start`, and the reconnect path
(`rejoin_room_by_name`, `app.py:597`) assigns a *new* `LobbyPlayer` entry
instead of reusing the existing `player_id`, that tab's `myPlayerId` would no
longer be in the `humans` set computed from the *original* seat. Check:
- Does `rejoin_room_by_name` ever create a new `LobbyPlayer` rather than
  returning the existing one for a name match? (Should always return the
  existing entry — verify.)
- Is there a window where `active_humans` was broadcast *before* a
  reconnecting player's rejoin completed, so that player's tab received a
  `season_start` with a stale/incomplete `humans` set from a race between the
  reconnect handler and the season-loop broadcast?

**Hypothesis C — broadcast delivery.** `_thread_safe_broadcast` sends to all
connected sockets for the room. If one island had multiple WS connections
open (e.g. a duplicate tab from the quick-seat auto-launch, per
`island-traders-testing`'s Chrome-tab-per-player launcher), and the *old*
socket for that player was still registered but the *new* socket (the one
actually visible to the user) wasn't the one the broadcast reached, the
visible tab would silently miss `season_start` entirely (not just the
`active_humans` field) — but the report says other messages that season *were*
received (players could still act), so this is the least likely explanation
but worth a quick check of `app.py:6081` ("reconnect has already replaced it")
to confirm socket replacement is airtight (no dual-registration window).

### 2 — Confirm humans isn't dropping ALL but one incorrectly

Check whether the affected islands still saw their action menu / could still
submit turns during that season (per the report, "Done Trading" was missing
but other functionality worked) — if so, the bug is isolated to the
`active_humans` set / `showForMe` gate specifically, not a broader per-player
broadcast failure. This narrows to Hypothesis A or B above, not C.

---

## What to do

1. Reproduce with a fresh 6-7 human config and full server log capture
   (`python launch.py ... 2>&1 | tee /tmp/it-repro.log`). Look for the
   `[season-timer] season_start ... active_humans=%s` log line
   (`app.py` around the season-start broadcast) each season — confirm whether
   the set legitimately excludes 5 of 6 players at the engine level (config
   bug / real omission) vs. the client-side `showForMe` check failing despite
   a correct server-side `active_humans` (frontend gate bug — flag this back
   to Claude if so, don't fix client code in this branch).
2. If Hypothesis A (role_names race) confirms: make the role-transfer
   remove+append sequence atomic, or defer `_start_season`'s `humans`
   computation until any in-flight role mutation completes (e.g. guard with
   the same lock used elsewhere for `room.players` mutations).
3. If Hypothesis B (reconnect race) confirms: ensure `rejoin_room_by_name`
   always resolves to the same `player_id`, and that `active_humans` is
   computed fresh (not cached) at the moment of broadcast so a completed
   reconnect is picked up.
4. Add a regression test in `tests/test_server/` that exercises the specific
   race found (e.g. role transfer immediately before season-start, or
   reconnect immediately before season-start) and asserts `active_humans`
   contains all connected human players with an assigned role.
5. If, after investigation, the root cause turns out to be **client-side**
   (e.g. `showForMe` computed from a stale `seasonActiveHumans` snapshot that
   a later message should have corrected but didn't), stop — do not patch
   `index.html` in this branch. Say so explicitly in the handoff with the
   exact mechanism found, and Claude will make the frontend fix.

---

## Tests to write

At minimum, `tests/test_server/test_active_humans_regression.py`:

1. A season-start broadcast's `active_humans` set contains every connected
   human player who holds at least one role, immediately after a role
   transfer between two human players that occurred in the same tick.
2. (If reconnect race is the cause) `rejoin_room_by_name` returns the same
   `player_id` for a repeat name-based rejoin, and `active_humans` computed
   after a rejoin includes that player.

Full suite must pass: `pytest`.

---

## Handoff format addendum

In addition to the standard handoff (branch, commit, base SHA, pytest count),
state explicitly: **which hypothesis (A/B/C/other) was confirmed**, and
**whether any frontend follow-up is needed** (name the exact client-side gap
if so, don't just say "maybe check the frontend too").
