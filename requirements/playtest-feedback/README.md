# Playtest Feedback

Raw playtest reports and the triage docs that turn them into action.

## Why a separate folder

Keeps unstructured player observations distinct from:
- **Spec docs** in `requirements/` root (`island-ledger.md`, `production-capacity-model.md`, etc.) — these describe how the system *should* work.
- **Codex briefs** in `requirements/codex-tasks/` — these are scoped engineering tasks ready for an agent to pick up.

Feedback lives here until it's been triaged into one of the four destinations below; the raw report and the triage doc stay paired so we have a record of how each playtest item was handled.

## Naming convention

**One report file per build version:**

```
playtest-{APP_VERSION}.md
```

Examples:
- `playtest-0.1.0-dev.2026-05-26.5.md`
- `playtest-0.1.0-dev.2026-05-27.md`

If a single version is playtested in multiple sessions, append the session date:

```
playtest-{APP_VERSION}-{YYYY-MM-DD}.md
```

The version comes from `APP_VERSION` in `island_traders/constants.py` (surfaced via `GET /version` and the in-game "About" dialog). Playtesters are asked to quote it when reporting defects, so the filename matches the build under test 1:1.

**One triage doc per report:**

```
triage-{APP_VERSION}.md
```

The triage doc cross-references items across the reports inside the matching `playtest-*.md` and assigns each to one of the four destinations.

## Triage destinations

Each item from a report lands in exactly one bucket:

| Symbol | Bucket | Lands as |
|---|---|---|
| ✅ | **Already fixed** | A short note pointing at the merge commit. No further action. |
| 🐛 | **New Codex brief** | A new `requirements/codex-tasks/{name}-{date}.md`. |
| 🎨 | **Claude UI follow-up** | A direct commit on `claude/...` branch (small) or a follow-up batch (larger). |
| ⚖️ | **Calibration / design** | Discussion item; either becomes a brief later or feeds an existing design doc. |
| ⏭ | **Deferred / out of scope** | Logged with the reason. Common: known issue, lower priority than current cycle, or duplicate of an existing GitHub issue. |

## Workflow

1. Playtester submits report (markdown file or GitHub issue text).
2. Save raw report to `playtest-{APP_VERSION}.md` here.
3. Produce `triage-{APP_VERSION}.md` that:
   - De-duplicates items across reports inside the file (multiple players often see the same bug)
   - Cross-references each item to in-flight work (open Codex briefs, existing GitHub issues, recent merges)
   - Sorts what's left into the four buckets
   - Notes which items need a clarification question back to the playtester before they can become a brief
4. Reference the triage doc when drafting new Codex briefs or scheduling UI work — it's the single source of truth for "what came out of this playtest cycle."

## Index

| Version | Raw report | Triage |
|---|---|---|
| `0.1.0-dev.2026-05-26.5` | [playtest-0.1.0-dev.2026-05-26.5.md](./playtest-0.1.0-dev.2026-05-26.5.md) | [triage-0.1.0-dev.2026-05-26.5.md](./triage-0.1.0-dev.2026-05-26.5.md) |
