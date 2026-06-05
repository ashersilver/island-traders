# Agent playtest feedback — 2026-06-05 (engine + API items for Codex)

From a live game (PNU61D) played by the Ollama LLM agent. Triage owner: Claude.
Agent-side items (the model bailing on market buys, reasoning↔action mismatch)
were fixed in the `island-traders-agents` repo. The items below are
engine/server and are flagged for **Codex**.

Status: ☐ open.

---

## ☐ #1 + #2 — Mining: 1/37 workers "active" yet the island is dominating

**Symptom:** Mining showed only **1 active worker out of 37**, while other
islands looked healthy — and yet Mining was "making a killing." The user had
**reassigned workers into more senior positions**.

**Hypothesis:** "active workers" and the production-scaling factor are decoupled —
reassigning to senior bands appears to (a) drop the *active* headcount display to
~1, while (b) production/output stays high (a senior worker may carry an outsized
per-head output, or the active-count and the band summary disagree). Either the
**active-count display is wrong** (workforce shows 1 when the senior workers
should still count as active) or the **production scaling over-credits senior
workers** (a balance exploit: reassign everyone up, output stays high with a
near-empty active roster).

**Pointers:** `WorkforceRoster` active-worker accounting + band summary
(`models/workforce.py`), the production scaling that turns workforce into an
output multiplier (`engine/production.py`), and the workforce payload fields
`workforce_active` / `workforce_bands` / `workforce_professions` in
`server/app.py get_game_state`. Confirm whether senior/active are double-counted
or mis-counted, and whether senior reassignment is an unintended income exploit.

## ☐ #5 — Education never produces new Course slots despite ample Expertise

**Symptom:** the Education island had lots of **Expertise** but was **never able
to create new Course slots** — the Expertise→Courses pipeline stalled. (This was
"fixed" once — see the `BASE_PRODUCTION["Educator"]["Courses"]` comment in
`constants.py` about Courses previously being absent from production — so this is
a regression or a second cause.)

**Pointers:** Course production in `engine/production.py` (does it consume
Expertise and emit Courses each season, scaled by faculty?), `BASE_PRODUCTION`
Educator entry, `MAX_CLASS_SIZE_PER_COURSE`, and whether Course output is gated
by a capacity/quota that is being hit immediately. Verify a healthy Educator with
spare Expertise actually accrues Course slots season over season.

## ☐ #4 — Push market events (bids/asks) over the WebSocket

**Symptom / request:** clients (human dashboards and AI agents) only learn about
market changes on the next full game-state broadcast, which fires on
`action_complete`. There is no discrete "a new ask/bid appeared" event, so an
agent can't *react* to, e.g., **Reagents becoming available to buy** the moment
it happens (feedback #3 — "MFG doesn't react to events").

**Fix direction:** broadcast a lightweight `market_event` (or `market_update`)
message when a bid/ask is posted, filled, or withdrawn — `{type, resource, side,
price, quantity, actor}` — in addition to the periodic full state. Keep it small
so it can fire often. This lets the LLM agent (and the dashboard) respond to
opportunities between full-state snapshots.

**Pointers:** the market mutation points (`models/market.py` buy/sell/bid/ask),
the broadcast plumbing (`_broadcast_state` / `io.on_action_complete` in
`server/app.py`), and the existing WS message types. The agent side
(island-traders-agents) will add a handler to consume these once they exist.

---

### Already handled (for context)
- **Agent #7/#8** (model bailed on market buys / reasoning↔action mismatch):
  fixed in `island-traders-agents` — the agent now pre-computes an affordable
  shortfall shopping list and binds the action menu to unblocking moves.
- **Agent #6** ready-spam: fixed earlier (dedupe).
