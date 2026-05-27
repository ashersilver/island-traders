# Codex Task — Lawyer profession required for new leases (2026-05-26)

**Owner:** Codex
**Origin:** GitHub issue #44 *"Banking requires Lawyers"* (2026-05-26 scoping batch). Lawyers as a new Manager-tier profession, trained through the existing Educator pipeline, required for any **new** lease on large capital equipment.

The brief is intentionally narrow. Lawyers will get expanded use later (insurance underwriting, deal-guarantee fees, dispute arbitration) but **this brief only ships the profession + the lease-inception gate**. Future work can build on the same enum without retrofitting.

## Goal

1. Add `Profession.LAWYER` as a Manager-tier trainable profession, available to every island through the existing Educator-driven Manager-course pipeline.
2. Gate **lease inception** on the lessee holding ≥1 active Lawyer on their roster. Existing leases at merge time are grandfathered (no Lawyer requirement applied retroactively).
3. Pre-place 1 Lawyer on the Banker starting workforce so the Bank can lease its own equipment from turn 1; no other island gets a free Lawyer — they must train one before leasing.

## Branching

- **Base:** `pre-release` at `81d443e` (current head — queue controls + AI Manufacturer) or later.
- **Branch name:** `codex/banker-lawyers-2026-05-26`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec — decisions locked in 2026-05-26 scoping conversation

| Decision | Answer |
|---|---|
| Retroactive on existing leases? | **No** — only new leases written after merge need a Lawyer. Existing `LeaseLedger` entries grandfathered. |
| Who must hold the Lawyer? | **Lessee only** for this brief. The Banker (lessor) is assumed to have institutional counsel — no roster Lawyer required on the Bank side. (Open for a follow-up if playtest disagrees.) |
| Training pipeline | **Existing Manager-tier course flow** (0.5 Professor + 1 Lecturer + 2 Expertise per concurrent course). Same shape as Banker / Farmer / Miner Manager training. |
| Training duration | **2 seasons** (`EDUCATION_SEASONS[Profession.LAWYER] = 2`). |
| University capacity | **2 per year** (`UNIVERSITY_CAPACITY["Lawyer"] = 2`). Same as Banker. |
| Where can Lawyers train? | **Every island** can train Lawyers (added to every entry in `ROLE_PROFESSIONS` and `SKILLED_PROFESSIONS`). Same treatment Chef got. |
| Banker starting workforce | **+1 Lawyer**. Banker baseline grows from 4 → 5: 1 Banker + 1 Lawyer + 1 BankingAnalyst + 1 BankingClerk + 1 Unskilled remainder. |
| Other-island starting workforce | **No pre-placed Lawyers.** Need to train before leasing. |
| Lease gate enforcement | Both the **investing-phase lease** (opening) and the **mid-game `LEASE_CAPITAL`** action. |

### Files to touch

- `island_traders/models/profession.py`
  - Add `Profession.LAWYER = "Lawyer"` enum
  - Add `PROFESSION_BAND[Profession.LAWYER] = WorkerBand.MANAGER`
  - Add `EDUCATION_SEASONS[Profession.LAWYER] = 2`
  - Add `PROFESSION_LABEL[Profession.LAWYER] = "Lawyer"`
  - Add `Profession.LAWYER` to every list in `ROLE_PROFESSIONS` (same pattern Chef uses — every island can train one)
  - `BAND_TITLES` doesn't need a new entry; "Lawyer" already reads naturally as a per-island Manager title — but if you want per-island flavour (e.g. "Corporate Counsel" on the Banker island, "General Counsel" elsewhere), feel free, just keep "Lawyer" as the primary label.

- `island_traders/constants.py`
  - Add `"Lawyer"` to every list in `SKILLED_PROFESSIONS` (mirrors the `ROLE_PROFESSIONS` addition).
  - Add `"Lawyer": 2` to `UNIVERSITY_CAPACITY`.
  - Update `STARTING_WORKFORCE["Banker"]` from 4 → 5.
  - Update `STARTING_WORKERS_BY_PROFESSION["Banker"]` to add `("Lawyer", 1)`. Drop the Unskilled remainder note from 4 → still 1 (5 total: 1 Banker + 1 Lawyer + 1 Analyst + 1 Clerk + 1 Unskilled).

- `island_traders/models/lease.py` (or wherever lease inception lives)
  - New helper `_lessee_has_lawyer(lessee: Player) -> bool` that returns `True` if the lessee's `workforce.count_profession(Profession.LAWYER.value) >= 1`. Save/load is unaffected (we're reading roster state, not persisting anything new).

- `island_traders/engine/turn.py`
  - In `_action_lease_capital` (mid-game): before calling `lease_ledger.create_lease`, check `_lessee_has_lawyer(player)`. If false, print a clear message — `"  Cannot lease without a Lawyer on your island's roster. Train one through the Education island first."` — and return. Do not consume the Lawyer (it's a gate, not a fee).
  - In the **investing-phase lease application path** (look in `server/app.py` `_launch_game` block that processes `capital_leases`): same check, but since the Lawyer hasn't been trained yet at investing-phase, **only the Banker can lease** during investing (since only the Banker starts with a Lawyer). Other islands attempting to lease at investing-phase get the same refusal message in their investing summary.

- `island_traders/server/app.py`
  - Optional: expose `lessee_has_lawyer: bool` on each player payload so the dashboard can grey out the Lease button for non-Banker islands at game start. Not required — the engine will refuse cleanly without it — but improves UX clarity.

## Tests

- `tests/test_engine/test_lease_lawyer_gate.py` (new):
  - Banker starts with 1 Lawyer → can lease at investing-phase ✓
  - Educator starts with 0 Lawyers → lease attempt refused with the clear message
  - Educator trains 1 Lawyer (2 seasons) → next lease attempt succeeds
  - Mid-game `LEASE_CAPITAL` action respects the same gate
  - Existing lease created **before** the Lawyer rule kicks in continues running normally (grandfather case — create a `Lease` directly via the ledger, then run a season; payment flow unaffected)
  - Lessee Lawyer count change after lease inception does NOT affect the lease (one-shot certification at inception; Lawyer can be retrained / reassigned afterward without breaking the lease)
- `tests/test_models/test_profession_bands.py` (extend):
  - `Profession.LAWYER` is in `PROFESSION_BAND` as MANAGER
  - `Profession.LAWYER` is in `PROFESSION_LABEL` as `"Lawyer"`
  - `Profession.LAWYER` is in every `ROLE_PROFESSIONS` list
- `tests/test_engine/test_training_menu.py` (extend):
  - `UNIVERSITY_CAPACITY["Lawyer"]` exists and is 2
  - Educator's Manager-tier course list includes Lawyer for every requesting island

## Acceptance criteria

- New `Profession.LAWYER` wired into all the workforce-graph tables.
- Banker starts with 1 Lawyer; no other island does.
- Both investing-phase and mid-game lease inception paths refuse cleanly when the lessee has 0 Lawyers, with a clear training-direction message.
- Existing leases at merge time keep running unmodified.
- Lawyer is trainable from every island via the standard 2-season Manager-tier course (capacity 2/year).
- Calibration sweep (1000g seed 42 + 4-seed sweep) shows no role moves more than ±2 pp out of the [12 – 18%] band. Banker getting +1 starting headcount might pull Banker up a hair — recalibrate `STARTING_WORKFORCE["Banker"]` or `MBA_QUALIFIED_THRESHOLD` if it does.
- Full test suite green at the new baseline count (462 + new tests).
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/banker-lawyers-2026-05-26` block.

## UI follow-up (Claude will handle separately)

- Lawyer chip on each player's workforce display (alongside Engineer / Banker / Doctor / etc.)
- Lease button greyed out with tooltip "Train a Lawyer first" on islands with 0 Lawyers
- Investing-phase lease catalogue shows the Lawyer requirement on each lease-eligible item

## Out of scope

- Lawyer involvement in loan underwriting, insurance, deal-guarantee, dispute arbitration — these come later as separate briefs.
- Per-island Lawyer titles (Corporate Counsel / General Counsel / etc.) — pure flavour.
- Retroactive Lawyer requirement on existing leases.
- Banker-side Lawyer requirement (the lessor side is institutional-counsel-by-assumption for now).
- Anything in GitHub issues #42, #43, #45, #47, #48 — those are separate scoping conversations.
