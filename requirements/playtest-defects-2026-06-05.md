# Playtest defects — 2026-06-05 (game PNU61D)

Triage owner: Claude. #1 (pause countdown) fixed by Claude this branch. #2/#3/#4
below are engine/orchestration issues flagged for **Codex**, with root-cause
pointers from the investigation.

Status: ☐ open (Codex) · ✅ done.

---

## ✅ #1 — Countdown keeps ticking while the game is paused (frontend, done)

The server froze its timers on pause, but the browser countdown kept advancing:
`updateSeasonTimerUI` / `updatePreSeasonTimerUI` / the auction interval all read
`Date.now()` directly, and `onGamePaused`/`onGameResumed` didn't freeze or
re-anchor them. Fixed: countdowns now use `effectiveNowMs()` (frozen at the pause
instant) and the end-epochs are bumped forward by the pause duration on resume.

## ☐ #2 — "Done Trading" (parked) state gets stuck; can't resume trading

**Symptom:** in game PNU61D, Agriculture could not trade with ~200s left on the
season timer; re-opening the action menu ("📋 Menu") did not restore the ability
to trade or act. (User suspects it may also be a Chrome rendering issue.)

**Not the same as the earlier fix.** Codex's #5 fix stopped the *season* ending
early when all humans clicked Done. This is the *per-player* park/resume: a
player in the Done-Trading (parked) state isn't being re-issued an action prompt,
so they're stuck even though the season is still open.

**Pointers:**
- Server park orchestration: `all_ready_task` + `interrupt_all()` + `season_human_done`
  (`server/app.py` ~1468, ~3102-3109), and the park loop that re-prompts after
  "Resume Trading".
- Frontend: `choose_action_parked` → `showParkedBanner` (`static/index.html`
  ~3117, ~4278), the "Resume Trading" path, and the "📋 Menu" recovery
  (`lastActionPromptMsg`). The menu recovery re-renders the *cached* prompt; if no
  fresh `choose_action` is delivered after un-parking, the player can't act.

**Fix direction:** when a parked player un-parks (or the grace period lapses with
time remaining), ensure the server re-issues a live `choose_action` to that
player; verify the frontend re-arms the action menu (not just the cached one) on
`game_resumed` / un-park. Repro from PNU61D around the stuck season.

## ☐ #3 — Farmer "Oil needed" display doesn't match actual production model

**Symptom:** the Farmer still "needs a lot of oil" despite the 06-04 halving.

**Root cause — two models for the Farmer:**
- **Actual production** uses `FARMER_SEASONAL_CONVERSION` (`constants.py:177`):
  `inputs {FarmMachinery: 1, Oil: 1}` per season (see `engine/production.py:305`).
- **The capacity panel + `decision_hints`** that render "X Oil needed to unblock
  Grain/Produce/Fish" use `PRODUCTION_RECIPES` (`constants_capacity.py`), which is
  what the 06-04 change halved.

So the displayed oil requirement is computed from a *different* table than the
one the Farmer actually consumes from. Halving the recipe only moved the
displayed number; it didn't change real consumption, and the two still disagree.

**Fix direction (decision needed):** either drive the Farmer's capacity/decision
panel from `FARMER_SEASONAL_CONVERSION` so the displayed oil matches real
consumption, or migrate the Farmer fully onto the recipe model and retire the
seasonal-conversion path. Pick one source of truth for Farmer oil.

## ☐ #4 — "Farming Technician" drops out of the training options mid-game

**Symptom:** `FarmingTechnician` was offered as a training target earlier in the
game (PNU61D) but later disappeared from the options list.

**Likely cause:** an annual/seasonal university quota for that profession is
exhausted, or the option list is filtered by current workforce state. The
profession itself is valid (`SKILLED_PROFESSIONS["Farmer"]`,
`profession.py` FARMING_TECHNICIAN).

**Pointers:** training-option/eligibility generation (`engine/turn.py` ~883-933,
`get_trainable_ids`), `UNIVERSITY_CAPACITY` / `UNIVERSITY_SEASONAL_CAP`, and
`_training_decisions_for_player` (`server/app.py:2179`). Confirm whether the
profession is dropped because a cap is reached (if so, surface *why* it's
unavailable rather than silently removing it) or due to a state bug.
