# Release Process

Release notes are part of the merge gate for `pre-release`.

## Before Merging Into `pre-release`

1. Complete the testing pass for the branch.
2. Update `RELEASE_NOTES.md` with the player-facing changes, rules/balance
   changes, fixes, known issues, and verification performed.
3. Confirm the test suite result and any manual browser testing notes.
4. **Link the PR to the issue(s) it addresses.** Use `Closes #N` for issues this
   PR resolves; `Refs #N` for partial progress or related context. Requirements
   live in the GitHub issue tracker — if no issue exists yet, open one first so
   the requirement is captured. The PR template
   (`.github/pull_request_template.md`) prompts for this automatically.
5. Only then merge the branch into `pre-release`.

## Multi-Agent Worktrees

This repository should use separate git worktrees when Codex and Claude Code
are working at the same time.

- The primary working copy remains this folder:
  `/Users/ashleysilver/Documents/projects/island-traders`
- Claude Code should use a separate worktree checked out to a different folder
  on the same computer.
- Each agent should work on its own branch and avoid editing the other agent's
  worktree directly.
- Merge coordination should happen through normal git branches / pull requests,
  not by sharing one dirty working directory.

Example setup command:

```bash
git worktree add ../island-traders-claude codex/claude-work
```

Use a branch name that reflects Claude's actual task when creating the worktree.

