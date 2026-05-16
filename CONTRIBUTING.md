# Contributing to Island Traders

Thanks for your interest in contributing.  This project is open source under
the [Apache License 2.0](LICENSE).  Please read this whole file before
opening a pull request — the Developer Certificate of Origin sign-off
(below) is **required** on every commit.

> Not legal advice.  See [`DISCLAIMER.md`](DISCLAIMER.md) for the project's
> originality, AI-disclosure, and intellectual-property statement.

---

## 1. Developer Certificate of Origin (DCO) — required

To keep the project's provenance clean, every contribution must be
**signed off** under the [Developer Certificate of Origin](DCO)
(version 1.1, verbatim in the [`DCO`](DCO) file).

By signing off you certify, in short, that:

- you wrote the contribution (or have the right to submit it),
- it is submitted under the project's Apache-2.0 license, and
- you understand the contribution and your sign-off are a permanent
  public record.

### How to sign off

Add a `Signed-off-by` trailer to every commit using your real name and a
reachable email:

```bash
git commit -s -m "Your commit message"
```

`git commit -s` appends:

```
Signed-off-by: Your Name <you@example.com>
```

The name/email must match your `git config user.name` / `user.email`.
Pseudonymous or anonymous sign-offs are not accepted.

If you forget the sign-off on the most recent commit:

```bash
git commit --amend -s --no-edit
```

For a branch of several commits:

```bash
git rebase --signoff main   # or the base branch you branched from
```

A pull request with any unsigned commit will be asked to amend before it
can be merged.

### AI-assisted contributions

This project itself was substantially built with AI assistance (see
[`NOTICE`](NOTICE) and [`DISCLAIMER.md`](DISCLAIMER.md)).  You may use AI
tools to help write your contribution, **but the DCO sign-off still
applies**: you are personally certifying that you have the right to submit
the contribution under Apache-2.0 and that, to the best of your knowledge,
it does not knowingly incorporate third-party intellectual property.  Do
not submit AI-generated code that you have reason to believe reproduces
someone else's proprietary or incompatibly-licensed work.

---

## 2. Branch & merge workflow

`pre-release` is the integration branch — it always reflects the latest
working state and must stay green.  `master` advances at release
milestones.

- Branch off `pre-release` for every change.
- **Use a prefix that identifies the author/agent:**
  - `claude/<short-topic>` — work done with the Claude agent
  - `codex/<short-topic>` — work done with the Codex agent
  - `<yourname>/<short-topic>` — human contributors
- Keep one logical change per branch so it stays reviewable and
  revertable.
- Open a pull request against `pre-release` (or, if you have merge rights
  and the change is small/green, a local `--no-ff` merge + push following
  the existing project pattern).
- The only file routinely touched by multiple branches is
  `RELEASE_NOTES.md`; adding a new section header at the top of the
  `## Unreleased` block is conflict-safe.

---

## 3. Release-notes gate

**Before a branch is merged into `pre-release`, add a section to
[`RELEASE_NOTES.md`](RELEASE_NOTES.md)** under `## Unreleased`, headed with
your branch name, describing:

- the player-facing and/or internal change,
- which files were touched,
- the tests you added, and
- a one-line verification (e.g. `Test suite: NNN passed`).

See `requirements/release-process.md` for the full policy.

---

## 4. Tests

- Run the full suite before opening a PR:

  ```bash
  .venv/bin/python -m pytest tests/        # or: pytest
  ```

- New behaviour needs new tests.  Bug fixes need a regression test that
  fails before the fix and passes after.
- Don't merge a branch with failing or skipped-due-to-error tests.
- Keep the suite fast; prefer focused unit tests over slow end-to-end
  ones where possible.

---

## 5. Scope coordination (parallel agents)

Claude and Codex sometimes work in parallel.  To avoid conflicts:

- Check `requirements/codex-tasks/` for tasks already assigned to Codex
  and stay out of their in-scope files.
- High-churn files (`island_traders/server/`, `engine/turn.py`,
  `models/loan.py`, `models/insurance.py`, `models/profession.py`,
  `constants.py`, `RULES.md`, `README.md`) are frequently in active use —
  coordinate before large edits there.
- Net-new modules and isolated subsystems (simulation, export, chat,
  `engine/ai.py`) are the safest places for independent work.

---

## 6. Code style

- Match the surrounding code; this project favours clear, commented
  Python over cleverness.
- Public behaviour changes should be reflected in `RULES.md` (game rules)
  and/or `README.md` (project usage) where relevant.
- Keep player-facing wording consistent (currency is **Dollops** / `Dp`;
  see `CLAUDE.md` for the design vocabulary to preserve).

---

By submitting a contribution you agree it is licensed under the Apache
License 2.0 and that you have signed it off under the DCO.  Thank you for
helping build Island Traders.
