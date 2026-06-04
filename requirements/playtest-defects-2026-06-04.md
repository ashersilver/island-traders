# Playtest defects — 2026-06-04 (GPT-player game)

Source: a full game played with the GPT LLM agent (room `pt-89064a2ee31b1238`).
Triage owner: Claude. Engine bugs below are flagged for **Codex** (engine leaf
work); Claude has taken the balance quick-win (#3) and the agent fix (#7).

Status legend: ☐ open · ✅ done · ⏸ deferred.

**Resolution:** engine bugs #1, #2, #4, #5 fixed by Codex on
`codex/playtest-defects-2026-06-04` (`233f575`), integrated to pre-release as
`0.1.0-dev.2026-06-04.2`. #3 + #7 done earlier (Claude). #6 deferred.

---

## ✅ #3 — Farming oil consumption halved (done, Claude)

`branch claude/farming-oil-balance-2026-06-04`. Oil/unit on Farmer recipes in
`constants_capacity.py PRODUCTION_RECIPES` halved: Grain `10/6→5/6`, Fish
`10/3→5/3`, Produce `5.0→2.5`. Food inherits via its inputs.

## ✅ #7 — Agent token rate-limit crash (done, in island-traders-agents)

GPT agent died on a 429 (TPM 200000/200000) after ~1h: it called the LLM on
every prompt incl. dozens of repeat "ready?" gates. Fixed in the agents repo
(auto-handle advance gates with no LLM call; retry/backoff; bounded history).

---

## ✅ #1 — Training dispatch: "worker(s) not active on island" despite an active pool

**Symptom (log):** every training request stalls with
`[Training] Cannot dispatch request #N: worker(s) not active on <island>'s island: <ids>`
(ids 5, 9, 5, 6 …) — even though the island has ~19 active unskilled workers.

**Root cause:** `TurnManager._training_workers_ready` (`engine/turn.py:1302`)
checks that the request's *specific* `req.worker_ids` are in
`requester.workforce.active_workers`. Those ids are chosen when the request is
created, but by dispatch time those exact workers are absent — the game logs
heavy per-season casualties (`[WORKPLACE] Agricola: 7 fatalities; 8 injured —
absent this season`). So the request is pinned to workers who happen to be
injured/dead, while other eligible unskilled workers sit idle and active.

**Fix direction:** at dispatch, re-bind the request to *any* currently-active,
eligible (unskilled / correct prerequisite) workers of the requested count,
rather than requiring the originally-reserved ids. Only fail if fewer than
`len(req.worker_ids)` eligible active workers exist. Keep the casualty model;
just stop pinning to dead/absent ids.

## ✅ #2 — Repurpose direction + Education approval-queue desync

Two issues:
1. **Repurpose semantics:** `repurpose_worker` is meant to let a player *un-skill*
   a trained worker back to Unskilled when the unskilled pool is the bottleneck
   (the "$25 skip-training" trick works skilled→skilled, but the un-skilling
   direction is the intended relief valve and isn't available). Agriculture had
   no way to free workers into the unskilled pool. See `_action_repurpose_worker`
   (`engine/turn.py:383`) + `REPURPOSE_WORKER_COST`.
2. **Approval-queue desync:** at one point Education had **5 training requests**
   pending (`awaiting_educator`) but the review action reported "no requests
   requiring approval"; the list returned later but with the same block. The
   `REVIEW_TRAINING` queue and the dispatch-eligibility check are out of sync —
   likely the same `_training_workers_ready` gate (see #1) hiding requests whose
   pinned workers are absent. Fixing #1 may resolve the visible-but-unapprovable
   state; verify the review list reflects all `awaiting_educator` requests
   regardless of current worker availability.

## ✅ #4 — Kitchen on a non-Farmer island: not shown, no food capability

**Symptom:** the Transporter bought a Kitchen and held 3 Chefs + Grain/Produce/
Fish, but (a) the Kitchen never appeared in its equipment list and (b) no
food-production capability was offered, even inefficiently.

**Context:** `ProductionEngine.run_kitchens` (`engine/production.py:76`) is
explicitly designed so *any* island can own a kitchen ("Kitchens are deliberately
separate from role production"). So the engine intends cross-role kitchens, but:
- the **equipment/inventory UI** doesn't surface kitchen capital for non-Farmer
  roles, and
- the **production-capacity panel** (`_player_capacity`) doesn't advertise the
  Food output a kitchen enables for that island.

**Fix direction:** surface owned kitchen capital in the equipment list for every
role, and include kitchen-enabled Food in the capacity/decision payload so the
player (human or agent) sees and can run it.

## ✅ #5 — Trading stops before the season ends

**Symptom:** trading became unavailable in Spring of Year 2 with ~180s left on
the season timer (the long-standing "trading finishes before end of season"
report). Players still had time and inputs but could not trade.

**Fix direction:** audit the season/trading phase state machine for an early exit
— likely the action loop marks the trading window closed when all *AI* seats
finish, or when the acting player parks, rather than holding it open for the
remaining timer. Repro from the attached game log around the Year 2 Spring
transition.

## ⏸ #6 — Market offer book + withdraw + "on offer" inventory column (feature)

Requested capability (design clarification, not a bug):
- The market should maintain a **resting-order book** (e.g. Mining offers 3 Oil@20
  then 3 Oil@25 — both rest as separate offers).
- An action to **withdraw** outstanding bids/offers (per player), which returns
  the escrowed inventory to the seller.
- Inventory display gets a column to the right of "on hand" showing **quantity on
  offer** (escrowed, still owned by the seller until matched).

Defer until the bug fixes above land; this is a market-model enhancement.
