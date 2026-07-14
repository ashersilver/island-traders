# Codex task briefs — working agreement (READ FIRST, every time)

This file is the standing agreement for **every** brief in this directory. Each brief
assumes it. If a brief and this file disagree, this file wins on process.

## Where the briefs live (canonical source of truth)

- **Repo:** `island-traders` (the game engine + server). GitHub remote `origin`
  = `git@github.com:ashersilver/island-traders.git`.
- **Branch:** briefs are committed to **`origin/pre-release`**, in this directory
  `requirements/codex-tasks/`. They are **not** delivered as loose local files — always read
  them from `origin/pre-release`.
- **Get them:** `git fetch origin && git show origin/pre-release:requirements/codex-tasks/<brief>.md`
  (or check out pre-release in a worktree, below). If `git fetch origin` fails, **fix the
  remote first** (`git remote -v`; re-add `origin` if missing) — do not proceed from a stale
  local copy and guess. (This bit us on 2026-06-24: a brief was implemented "Indiana-Jones"
  from the filename because fetch failed. Don't.)

## What to base your work off

- **Base branch:** always `origin/pre-release` (never `master`, never a feature branch).
- **Confirm the exact tip + version before starting** and quote them in your handoff:
  - `git fetch origin`
  - `git rev-parse --short origin/pre-release`  → the commit you based on
  - `grep APP_VERSION island_traders/constants.py` (on that commit) → the `.N` dev version
- Each brief's **"Base off"** line names the tip + `APP_VERSION` that were current when it was
  written. If `origin/pre-release` has moved on, that's fine — base off the **current** tip
  and note in the handoff that you did.

## How to work (worktrees, branch, PR)

- **Do NOT touch the primary checkout** `/Users/ashleysilver/Documents/projects/island-traders`
  — it routinely holds unrelated uncommitted Claude work. Create your **own dedicated
  worktree** off the base and work only there:
  `git fetch origin && git worktree add -b codex/<task-name> ../it-codex-<short> origin/pre-release`
- **Commit and PUSH your branch** (`git push -u origin codex/<task-name>`). Do not leave the
  work uncommitted in a shared checkout — Claude (the integrator) needs to fetch your branch.
- **PRs only.** Reach `pre-release` via a PR that Claude merges. Update `RELEASE_NOTES.md` and
  bump `APP_VERSION` `.N` in `island_traders/constants.py`.
- **Git discipline:** no `--no-verify`, `--amend`, or force-push. Run the **full** `pytest`
  suite before handoff.

## Handoff format (so Claude can integrate cleanly)

State all of:
> "branch `codex/<task>` **pushed to origin**, at commit `<sha>`, based off `origin/pre-release`
> `<base-sha>` (APP_VERSION `<base .N>`). Full pytest: `<N> passed`. Frontend bits left for
> Claude: `<list, or none>`."

If you couldn't push (remote/network), say so explicitly and name the **local branch + commit
SHA + the worktree path** so Claude can fetch it directly — don't leave it as an uncommitted
diff in a shared checkout.
