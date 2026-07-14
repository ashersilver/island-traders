# Brief — Harden agent WebSocket keepalive for slow LLM agents + cap transcript growth (2026-06-23)

**Suggested owner:** Codex (server WS config + tests; agent-side items flagged separately).
**Relates to:** AI agent reconnect loop observed in 2026-06-23 playtest.
**Base off:** `origin/pre-release` at **`b5d4d88`** or later. `git fetch origin` and confirm
`git rev-parse origin/pre-release`.

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees — do NOT use the primary checkout.** The primary checkout
  (`/Users/ashleysilver/Documents/projects/island-traders`) holds unrelated Claude work.
  Create your **own dedicated worktree** off the base and work there:
  `git fetch origin && git worktree add -b codex/agent-ws-keepalive-2026-06-23 ../it-codex-keepalive origin/pre-release`
- **PRs only.** Reach `pre-release` via a PR Claude merges. Update `RELEASE_NOTES.md` and
  bump `APP_VERSION` `.N` in `constants.py`.
- **Git discipline.** No `--no-verify`/`--amend`/force-push. Run the **full** `pytest` suite
  before handoff.
- **Handoff.** "branch X at commit Y — ready to integrate."

## Why (observed)

Playtest 2026-06-23: the local ollama AI (`island-trader-qwen`, qwen3 8B Q4) is **very slow**
— a measured **81.8 s for a trivial "reply ok"** generation (it emits a long "thinking"
chain even for trivial prompts; ~5 tok/s). A real in-game decision blocks the agent's
event loop for **tens of seconds to minutes** on a single synchronous LLM call.

The game server (`island_traders/server/app.py` `main()`) runs
`uvicorn.run(app, ..., ws="wsproto")` with **no ping settings**, i.e. uvicorn's default
~20 s WebSocket keepalive. While the agent is blocked in its LLM call it cannot answer the
keepalive ping, so the connection is closed with **`1011` "keepalive ping timeout"**, the
agent reconnects, and the cycle repeats — a reconnect storm. Two failure modes were seen:
the transcript ballooned to **2.86 GB** (reconnect storm logging everything), and in a later
run the agent simply blocked forever on its first decision (auction bid) so the game was
stuck in "investing".

## Scope

This brief fixes the **server-side keepalive** so a slow but healthy agent is not
disconnected mid-decision. It does **not** fix the underlying ollama slowness (separate:
consider a faster model or disabling qwen3 "thinking"); that's out of scope.

## Spec — server (this repo)

1. **Tolerant keepalive for agent WS.** Configure the server so a long synchronous gap on an
   agent WebSocket does not trigger a server-initiated `1011` close. In `main()` (and
   anywhere the app is served), pass generous WebSocket ping settings to uvicorn — e.g.
   `ws_ping_interval=30`, `ws_ping_timeout=300` (or disable with `None`). Verify the chosen
   `ws` implementation actually honours these: uvicorn's `ws_ping_*` apply to
   `ws="websockets"`; with `ws="wsproto"` they may be ignored. If so, **switch to
   `ws="websockets"`** (already a dependency) so the timeouts take effect, or implement an
   equivalent application-level keepalive tolerance.
2. **Make the values named/overridable** (constants or CLI flags) so they can be tuned, and
   document them.
3. **Don't regress disconnect handling.** Genuine dead connections must still be cleaned up
   eventually (the `_ws_lock` / `unregister_ws` path). Only the *timeout window* changes.

## Spec — agent side (DIFFERENT repo: `island-traders-agents`) — flag, don't do here

These belong in `island-traders-agents`, not this PR — note them in the handoff so Claude
routes them:
- Run the blocking LLM call in an executor / thread so the agent's asyncio loop keeps
  answering server pings (the robust fix, complementary to the server change).
- **Cap / rotate the transcript** (`/tmp/island-traders-transcript.json`) so a reconnect
  storm can never write multi-GB files (observed 2.86 GB). E.g. size cap + rotation, and/or
  de-dupe repeated reconnect records.

## Tests

- A test that an agent WebSocket which goes silent for longer than the old ~20 s window is
  **not** closed by the server before the new timeout (simulate a processing gap; assert the
  connection stays registered / no `1011`).
- Keepalive settings are read from the named constants/flags.
- Full `pytest` suite green (baseline: **811 passing** on `b5d4d88`).

## Out of scope (note for the user)

- ollama/model latency itself (faster model, disable qwen3 thinking, GPU offload).
- Agent-repo transcript cap + executor (separate `island-traders-agents` change).
