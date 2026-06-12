# UI v2 — Modular Tile UI, Order/Training Desks, Trade Finder, Chat Rooms

**Date:** 2026-06-12
**Status:** Design — for review before issues are opened
**Mockup:** `requirements/mockups/ui-v2-modular.html` (open in a browser)
**Predecessor:** PR #99 (hide/collapse panels + 4 presets + log filter + disaster
modal). This design extends that work; it does not replace it.

---

## 1. Problem statement

The current UI is a single 240 KB `index.html` with a fixed CSS grid
(`side / main / info / log`). Pain points this design addresses:

1. **One-at-a-time actions.** Every market buy/sell and every training request
   goes through the sequential prompt wizard (`choose_action → choose_resource →
   choose_quantity → confirm`, one WS round-trip each). Placing five orders
   means five full wizard passes inside a timed season window.
2. **No visibility into other players' inventories.** The All Players table
   shows net worth/treasury/workers only, so finding a trading partner ("who
   has Oil?") is guesswork — even though `game_state.players[*].inventory` is
   already broadcast for human players.
3. **Chat is a stub.** The WS `chat` message is a bare room-wide broadcast that
   lands in the event log. Meanwhile a complete chat module
   (`island_traders/chat/`: rooms, invites, messages, structured agreements,
   SQLite store, 100% tested) sits unwired.
4. **One-size-fits-all layout.** A Banker stares at the same panels as a
   Farmer. #99 added hide/collapse + presets, but defaults aren't
   role-aware and tiles can't be reordered.
5. **Performance.** Every `game_state` re-renders most of the side/info panels;
   the log grows unboundedly in the DOM.

## 2. Goals / non-goals

**Goals**
- Modular tile architecture; per-**role** default layouts + user customization
  (show/hide/collapse/reorder + named presets), persisted in localStorage.
- **Order Desk**: stage multiple buy/sell orders in a basket, submit as one
  batch.
- **Training Desk**: stage multiple training requests, submit as one batch.
- **Trade Finder**: search every player's inventory by resource, see
  quantities and surpluses, jump straight into a negotiation (chat + deal).
- **Chat rooms**: 1:1 and group rooms backed by the existing chat module, with
  structured deal proposals in-line, and the ability to **push a conversation
  to an AI participant** so an LLM agent can read it and reply.
- Performant: tile-scoped re-render, bounded DOM, zero-build static files
  (engine restarts must stay unnecessary for frontend iteration).

**Non-goals**
- Full freeform drag/resize tiling (explicitly scoped out 2026-06-11; we keep
  hide/collapse/reorder + presets).
- A frontend framework/build step. Static files are served fresh without a
  server restart today; we keep that property with native ES modules.
- Changing game rules. Batched orders execute with exactly the same engine
  semantics as N sequential orders.

## 3. Architecture

### 3.1 File layout (zero-build ES modules)

```
island_traders/server/static/
├── index.html          # shell only: grid container, dialogs, <script type=module>
└── ui/
    ├── core/
    │   ├── store.js    # normalized state + slice-level change detection
    │   ├── ws.js       # socket, reconnect, message routing (extracted as-is)
    │   ├── layout.js   # tile registry, presets, persistence
    │   └── fmt.js      # esc(), Dp formatting, resource icons (extracted)
    └── tiles/
        ├── island.js  inventory.js  production.js  market.js
        ├── order_desk.js  training_desk.js  trade_finder.js
        ├── players.js  conditions.js  funding.js  insurance.js  loans.js
        ├── chat.js  log.js
        └── ...one module per tile
```

Migration is mechanical: the existing renderers (`renderInventory`,
`renderMarket`, …) already write into dedicated element IDs, so each becomes a
tile module's `render()`. No behavioural rewrite in phase 1.

### 3.2 Tile contract

```js
export default {
  id: 'order_desk',
  title: 'Order Desk',
  slices: ['market', 'me.inventory', 'me.treasury'],   // what it re-renders on
  roles: null,            // null = all; ['banker'] = only offered to that role
  defaultRegion: 'main',  // side | main | info | dock
  render(el, state) {...},     // called only when a subscribed slice changed
  onMessage(msg) {...},        // optional: targeted WS events (acks, chat)
}
```

### 3.3 Store + rendering performance

- `store.apply(gameState)` keeps the previous payload and computes a changed
  set at slice granularity (`market`, `players.<id>.inventory`, …) via
  cheap reference/JSON-segment comparison. Only tiles subscribed to changed
  slices get `render()` calls, batched in one `requestAnimationFrame`.
- Log + chat lists are **windowed**: keep ≤ 300 rows in the DOM, older rows in
  a JS ring buffer, restored on scroll-up.
- Targets: apply+render < 16 ms for a 7-player payload; idle CPU ~0 between
  messages; no listener leaks on tile hide (tiles get `destroy()`).

### 3.4 Layout, customization, presets

- Each region is a CSS grid of tile cards. Per tile: collapse, hide, and
  **reorder** via ▲▼ on the tile header (keyboard-friendly; cheap; no drag lib).
- `layout.js` persists `{preset, perTile: {hidden, collapsed, order, region}}`
  in localStorage (extends the #99 schema, migrating it).
- **Role-aware defaults**: on first join, the preset is seeded from the
  player's role(s):

| Role | Promoted tiles (main/info) | Demoted/hidden by default |
|---|---|---|
| Farmer | Production, Order Desk, Market | Funding Rates |
| Miner / Manufacturer | Production, Order Desk, Trade Finder | Insurance |
| Transporter | Order Desk, Trade Finder, Players | Funding Rates |
| Educator | **Training Desk**, Campus load, Trade Finder | Insurance |
| Banker | **Funding Rates**, Loans, Players, Chat | Production detail |
| Doctor | Production, Insurance, Training Desk | Funding Rates |
| Multi-role | union of promoted tiles | — |

- The ▦ Layout menu from #99 stays; presets become: role default, Full,
  Trader, Focus, + user-saved.

## 3.5 Input conventions (apply everywhere, including legacy dialogs)

User-mandated 2026-06-12:

- **Number capture boxes are never pre-populated.** They open empty with the
  valid range / suggestion as a `placeholder` (e.g. `1–40`, `best: 9.20`), so
  the player lands in the box and types immediately. This includes the
  existing `choose_quantity` / dollop-amount dialogs, which currently prefill
  `min` / best-price values.
- **Focus lands in the first capture box** when a dialog/panel opens — no
  click needed.
- **Tab / Shift-Tab moves between capture boxes** within a panel in visual
  order (explicit `tabindex` where DOM order doesn't match), wrapping to the
  submit button last.
- **Enter submits** the panel's primary action from any capture box (where a
  multi-row desk is open, Enter on the add-row inputs adds the row instead).
- Number inputs carry `inputmode="numeric"` (or `decimal` for Dp amounts).

## 3.6 Unread indicators (chat)

- Each room button in the chat dock shows an **unread badge** (count) when
  messages arrived while the room wasn't focused.
- The chat tile header shows a **dot indicator** (and the ▦ Layout menu entry
  likewise) when *any* room has unread messages and the tile is collapsed or
  hidden, so a hidden chat can't swallow a negotiation silently.
- Unread state clears per-room when the room gains focus; persisted last-read
  message ids in localStorage so a refresh doesn't mark everything unread.

## 4. Order Desk (multi-order basket)

**UI.** A tile with the live bid/ask per resource and a basket. Rows are added
with side (Buy/Sell), resource, qty, and optional limit price; the tile shows a
running cash/inventory check against treasury and stock (client-side preview
only — server revalidates). Submit sends the whole basket; per-row results come
back (filled / partial / rejected+reason) and rejected rows stay in the basket
for editing.

**Protocol (new).**

```jsonc
// client → server (only valid during the player's action window)
{"type": "order_batch", "batch_ref": "ob-17",
 "orders": [
   {"side": "buy",  "resource": "Oil",  "quantity": 12, "limit_price": 9.5},
   {"side": "sell", "resource": "Food", "quantity": 30}
 ]}
// server → client
{"type": "order_batch_result", "batch_ref": "ob-17",
 "results": [
   {"index": 0, "status": "filled", "quantity": 12, "unit_price": 9.2, "total": 110.4},
   {"index": 1, "status": "rejected", "reason": "insufficient stock: have 22"}
 ]}
```

**Engine seam (Codex).** A `TradingEngine.execute_order_list(player, orders)`
that iterates the existing single-order path **in order**, with the same price
movement per fill as today (a batch is semantically identical to N sequential
orders — no new market mechanics). Each row validates independently; a
rejection doesn't abort the rest. Server-side it runs inside the player's
turn thread using the existing park/Done machinery in `ws_adapter.py` (the
"Open Order Desk" action parks the wizard exactly like the current training
picker does, accepts one or more `order_batch` messages, resumes on Done).

## 5. Training Desk (multi-request queue)

**UI.** A tile listing workforce by profession, university capacity
(`training_capacity` is already in the payload), and a queue builder: rows of
(profession, count, campus, transport). Capacity warnings render live (e.g.
"Professors cap 1/season"). Submit-as-batch; each row acks individually.

**Protocol (new).** Mirrors orders:

```jsonc
{"type": "training_batch", "batch_ref": "tb-4",
 "requests": [
   {"profession": "Nurse", "count": 2, "campus_player_id": 3, "transport_mode": "air_ticket"},
   {"profession": "Engineer", "count": 1}
 ]}
{"type": "training_batch_result", "batch_ref": "tb-4", "results": [...]}
```

**Engine seam (Codex).** The engine already models multi-worker requests as a
`TrainingRequest` with a `batch_id` and a full counter-offer negotiation flow
(`training_counter_*` messages). The batch endpoint creates one
`TrainingRequest` per row through the existing pipeline; counter-offers keep
working unchanged because they're keyed by `batch_id`.

## 6. Trade Finder (cross-player inventory search)

**UI.** A tile with a resource picker / free-text search. Results: every
player holding that resource, their quantity, their role's structural surplus
(produces it) or need (consumes it), and the current market mid as a pricing
anchor. Each row has two actions: **💬 Negotiate** (opens/creates a 1:1 chat
room with that player, pre-filled with a deal stub) and **Propose deal**
(jumps straight to a structured agreement form, §7). A reverse view ("who
needs what I have") reuses the existing `barter_market.needs` payload.

**Server change (small).** `game_state` already includes `inventory` for
human players but **skips AI seats** (`app.py:2806-2812`). Include AI/LLM
players' inventories too (flagged `"is_ai": true`) so AI islands are
discoverable trading partners. No other backend work — this feature is
otherwise frontend-only.

**Privacy note.** Inventories are already broadcast to all clients today, so
the Trade Finder reveals nothing new — it surfaces what the payload already
carries. If hidden-information play is ever wanted, that's a separate economy
design decision (filter the payload server-side, not the UI).

## 7. Chat rooms + structured deals

### 7.1 Wiring the existing module

`ChatService`/`ChatAPI` (rooms, invites, leave, messages, propose/accept/
reject agreement, pending-agreement expiry, SQLite store) are implemented and
tested but unreachable. Wire them through the game WebSocket — new message
types handled in `app.py` next to the current bare `chat` case, delegating to
`ChatAPI`:

```
client → server: chat_create_room {name, invitee_ids[]}
                 chat_invite {room_id, player_id}
                 chat_leave {room_id}
                 chat_send {room_id, text, push_to: [player_id...]?}
                 chat_history {room_id, since_id?}
                 chat_propose_deal {room_id, give: {res: qty}, get: {res: qty},
                                    gold_delta, counterparty_id, expires_seasons}
                 chat_deal_respond {agreement_id, accept: bool}
server → client: chat_room_update {rooms: [...]}        // on join/invite/leave
                 chat_message {room_id, from, from_id, text, ts, is_ai}
                 chat_deal {room_id, agreement}          // structured card
                 chat_deal_update {agreement_id, status}
```

Messages fan out **only to room members'** sockets (not room-wide broadcast).
The legacy `chat` broadcast becomes the pre-seeded "Table" room everyone is in.

### 7.2 Chat dock UI

A persistent dock tile (bottom of the `info` column, expandable to an
overlay): room list with unread badges, member roster with AI badges (🤖),
message pane (windowed), composer. Deal proposals render as **cards** with
give/get/Dp and Accept / Reject / Counter buttons — accepted agreements land
in the existing deal ledger and the log. Negotiate-from-Trade-Finder (§6)
creates/focuses a 1:1 room.

### 7.3 Pushing chat to an AI participant

LLM agents (island-traders-agents repo) hold a normal player WebSocket, so
room-scoped `chat_message` events reach them with zero transport work once
they're room members. The design adds explicit **push semantics** on top:

1. **Membership**: AI players appear in the invite picker like anyone else.
   Inviting one makes its socket receive that room's events.
2. **Passive mode (default)**: the server accumulates a per-agent, per-room
   digest of unseen messages and appends it to the agent's next turn-state
   render — same pattern as the planned revenue-opportunity feed into
   `protocol.py` (agents-repo seam). The agent reads chat when its turn
   starts; replying is a normal `chat_send`.
3. **Active push**: the composer's 📤 **Push to AI** toggle (or an
   `@AgentName` mention) sets `push_to: [agent_id]` on `chat_send`. The server
   then delivers `{"type": "chat_push", "room_id", "history": [last N msgs],
   "pushed_by"}` to the agent socket immediately, signalling "a reply is
   wanted now, out of turn". Rate limit: max 1 in-flight push per agent, and
   N pushes per player per season (constant in `constants.py`) so humans
   can't use a free LLM oracle as a chat toy.
4. **Agents-repo work**: handle `chat_push` (render history → one reply →
   `chat_send`), add chat digest to the state render, and let the agent
   propose/accept structured deals (`chat_propose_deal` / `chat_deal_respond`)
   — its negotiation already has the deal ledger semantics to lean on.

## 8. Work split & phasing

| Phase | Owner | Scope | Protocol changes |
|---|---|---|---|
| **1. Tile shell** | Claude | ES-module refactor, store + slice rendering, reorder + role-aware presets, log windowing, **Trade Finder** (incl. the small AI-inventory payload fix) | `is_ai` flag + AI inventory in `game_state` |
| **2. Desks** | Codex (engine) + Claude (UI) | `execute_order_list`, training batch endpoint; Order Desk + Training Desk tiles | `order_batch(_result)`, `training_batch(_result)` |
| **3. Chat** | Claude (server wiring + UI) | ChatService over WS, chat dock, deal cards, push plumbing | `chat_*` family |
| **4. AI chat** | Claude (agents repo) | `chat_push` handling, digest in state render, agent deal responses | agents repo only |

Phases 2 and 3 are independent and can run in parallel (second to merge wires
any shared seam, per the standing rule). Each phase = one GitHub issue with a
checklist; PRs reference `Closes #N`. Version bumps + release notes per merge
as usual. Existing `tests/test_server` patterns cover the new message types;
phase 1 needs a frontend smoke pass in preview (per the #99 playbook: serve
the branch via `python -m` from the worktree root).

## 9. Risks / open questions

- **Timer pressure vs. batch UX**: the Order Desk parks the wizard like the
  training picker; the season timeout still applies. An unsubmitted basket is
  lost on timeout — show the timer inside the desk.
- **Order interleaving**: while a basket executes, prices move per fill;
  client preview totals are estimates. The result message is authoritative —
  the UI must reconcile, never assume.
- **Chat persistence across restarts**: ChatStore is SQLite; decide whether
  rooms are per-game (wipe on game end) or per-server-lifetime. Recommend
  per-game, keyed by room_id, wiped on `game_over`.
- **Push abuse / cost**: each push is a real LLM call in the agents repo —
  hence the per-season cap; the cap constant should be visible in the UI.
- **localStorage schema migration** from the #99 preset format — versioned key.
