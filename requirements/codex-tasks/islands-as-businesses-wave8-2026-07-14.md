# Wave 8 — Islands as businesses: per-island books, acting island, equity sales (2026-07-14)

Source: Ash, 2026-07-14 — "each island should have its own balance sheet…
the players' cash is indivisible, but each island has its own consumables,
debts, assets and income and its own treasury… a 'consolidated' tab in which
everything is pooled… trading and rebuilding and training all done from the
perspective of a single island. Each island is a business." Plus net-new:
"sell portions of an island to another player to raise (personal player) cash."

## Verdict from the code review (2026-07-14)

The pooling is real and architectural, not a merge bug:

- There is **no Island object**. An island is a `Role` descriptor
  (`models/role.py:6-14`, 1:1 role↔island name). Owning two islands = one
  `Player` with two entries in `roles` (`models/player.py:252`) and a single
  `dollops`, `inventory`, `workforce`, `capital_units`, `insurance_policies`,
  `population`, `shareholder_loans` (`player.py:253-350`). Bank loans key on
  `player_id` (`models/loan.py:115-116`).
- Pooling is cemented at setup: a multi-role lobby player becomes ONE
  `PlayerSpec` with `ISLAND_STARTING_CASH` seeded **once** (`app.py:1500-1509`);
  the island-guarantee purchase just moves a role name between lists
  (`app.py:1166-1167`).
- **But** the investor layer already splits player-vs-island:
  `personal_cash` (indivisible wallet, `player.py:342`), `cap_table` (100
  shares/island; owner 60, unissued 40, `models/equity.py`), `holdings`,
  shareholder loans (personal_cash ↔ treasury, `turn.py:4844-4919`), and live
  per-island valuation `fair_value`/`share_price` (`app.py:4575-4581`).
- **And** the client is nearly ready: `game_state.players[]` is already one
  complete balance-sheet dict per engine Player (`app.py:4595-4850`); the
  role-tab bar already renders one tab per role **plus a Consolidated tab**
  with whole-dashboard re-render (`buildIslandTabs`/`switchTab`,
  `index.html:6884-6913`, `isConsolidated` branch `5246-5262`).
- The 1:1 human↔engine-Player binding is the chokepoint:
  `Room.lobby_to_engine_id: dict[str,int]` (`app.py:434`, built
  `app.py:1538-1540`); every WS action carries NO identity — the actor is
  implied by the connection (~18 handler sites re-derive it); ws_adapter's
  turn/Ready coordination assumes one turn per human
  (`ws_adapter.py:201-250, 362-395`).

**Target architecture (smallest-change path): keep Player-as-island.** Each
island permanently gets its own engine `Player` (one role each) — all
per-island systems (loans, insurance, capital, production, scoring payload)
then work unchanged. Add an OWNER layer above: a lobby human owns a set of
engine Players. Hoist the investor fields (`personal_cash`, `holdings`) to
the owner; `cap_table` stays on the island it describes.

---

## Task 8.1 — Per-island books (the defect) — LARGE, engine

1. **Setup:** in `_start_investing` (`app.py:1500-1509`), emit one
   `PlayerSpec`/`Player` **per role won**, each seeded `ISLAND_STARTING_CASH`
   and its own starting inventory/capital/workforce for that role. A human
   winning 2 auctions starts 2 businesses.
2. **Ownership map:** `Room.lobby_to_engine_id` → `dict[str, list[int]]`
   (owned set) + per-connection `acting_engine_id` (defaults to first).
   Update the ~18 resolution sites (`app.py:5341, 5907, 6422, 6465, 3142,
   3474, 3498, 3576`, …).
3. **Acquisition keeps books separate:** the island-guarantee purchase
   (`app.py:1166-1167`) and any future takeover transfer the engine Player's
   *ownership*, not its state — the island keeps its treasury, inventory,
   debts, insurance, workforce. Purchase price paid from buyer's
   **personal_cash** (it buys the equity, not the till).
4. **Investor layer hoist:** `personal_cash`, `holdings`, investor
   `net_worth` (`player.py:342-369`) move to an `Owner` record (keyed by
   lobby id; serialised on the room/game). Shareholder-loan actions
   (`turn.py:4844-4919`) name an explicit island (owner may lend personal
   cash to ANY island they own). `cap_table` stays per-island.
5. **Turn coordination (DECIDED 2026-07-14 — free tab-switching, no
   ordering):** one human, N islands = N concurrently-open action loops.
   There is NO imposed sequence: the frontmost island tab determines which
   island the player's next action binds to, and the server processes
   actions strictly in arrival order (the existing single event loop already
   serialises them). Each owned island keeps its own independent prompt
   state and its own end-turn/"done trading" flag, reusing the existing
   per-player prompt routing (`ws_adapter.py` stamps `player_id` on every
   prompt already). Season-Ready for the human = ALL owned islands flagged
   done; park/interrupt logic keys on the owned set, not the single id.
   Mid-wizard state is per-island: switching tabs must NOT cancel another
   island's in-flight wizard — the tab badge (8.2.4) shows which islands
   await input.
6. **AI multi-island:** an AI owning 2+ islands simply runs its normal
   per-player loop for each — this REPLACES today's merged-AI behaviour and
   should simplify it (each AI island is a plain single-role player).
7. **Scoreboard:** keep one row per island (it already is per engine Player);
   add owner grouping — indent islands under their owner with the owner's
   consolidated position (see 8.2) as the group header. Win condition
   (`app.py:1757-1779`) ranks **owners** by consolidated net position:
   personal_cash + Σ (stake fraction × island fair_value) + shareholder-loan
   receivables.

Migration note: saves/state-files predating this change hold merged players —
version-gate the loader; no in-place migration of old saves required (games
are short-lived).

## Task 8.2 — Acting-island selector + Consolidated tab — MEDIUM, mostly client

1. **Actor rides on the message:** add `island_id` (engine player id) to
   every action sender (`order_batch`, `training_batch`, `capital_order`,
   `deal_propose`, `worker_transfer_offer`, `market_order_update`,
   `cancel_training`, `capital_repair`, the `response` envelope, …). Every
   handler validates `island_id ∈ owned set of this connection` then resolves
   that Player. Reject with a clear error otherwise. (Single largest new
   surface — handlers currently trust the socket.)
2. **Selector UI:** re-target the existing role-tab machinery
   (`buildIslandTabs`/`switchTab`/`activeTabRole`, `index.html:6884-6913`) to
   partition by owned island: one tab per island + **Consolidated**.
   Selecting a tab sets the acting island (generalise
   `myPlayerIdx`/`_myEnginePlayerId`, `index.html:5225, 6079-6082`) and
   re-renders — mechanically identical to today's `switchTab`.
3. **Consolidated tab = read-only:** pooled net position summed client-side
   over the viewer's owned `players[]` entries (net_worth, treasuries,
   inventories, loans, workforce) + the owner wallet (personal_cash,
   holdings, receivables). NO action controls render on this tab — trading,
   rebuilding, training, repairs are only available with a specific island
   selected (Ash's explicit requirement). Prefer a server-side
   `consolidated` block to reuse `wealth_breakdown` math (`app.py:4613-4644`)
   rather than duplicating it in JS.
4. **Prompt routing:** wizard prompts already carry `player_id`
   (`ws_adapter.py:270`); the client shows a prompt badge on the tab of the
   island awaiting input and auto-switches (or prompts to switch) when the
   acting island differs from the prompt's island.

## Task 8.3 — Sell portions of an island (net-new) — MEDIUM

Builds on: `CapTable.transfer(frm,to,n)` (generic, invariant-preserving),
live `share_price`/`fair_value`, the `personal_cash` wallet, and the
offer/accept patterns (`WorkerTransferOffer`, `game.py:361-446`;
capital-negotiation ledger).

1. **Secondary sale flow:** owner offers X shares of island A at price P
   (default suggestion: `X × share_price(A)`, editable) to a named player OR
   openly. Buyer accepts/counters/declines (single counter round, same shape
   as deals). Settlement: buyer `personal_cash` −P → seller `personal_cash`
   +P (NEVER the island treasury — this is the point of the feature);
   `cap_table.transfer(seller, buyer, X)`; both owners' `holdings` mirrors
   updated. This is the first cross-player cap-table mutation — add the
   mirror-consistency helper (cap_table ↔ both holdings) with tests.
2. **Control rule (default, flag for Ash):** operational control (acting the
   island's turns, taking its actions) stays with the **largest holder**;
   ties → incumbent. Selling below 50% therefore risks losing the business
   to whoever accumulates more. UI warns before a sale that would drop the
   seller to ≤50%.
3. **Minority economics (default, flag for Ash):** without dividends a
   minority stake only pays off via valuation/scoreboard. Minimal viable:
   minority holders' stakes are marked to `share_price` in their consolidated
   net position (already how holdings are scored, `player.py:367-368`).
   Dividends (share of seasonal profit) are OPTIONAL scope — spec as a
   follow-on task 8.4 unless Ash wants them now.
4. **Buy-out-the-float unchanged** (`app.py:3482-3556`) — primary issuance
   still routes cash into the island treasury; only secondary sales settle
   personally. AI: sell-side only when treasury-desperate AND holding >60;
   buy-side opportunistic when `share_price < fair_value × 0.8` and
   personal_cash allows (conservative first pass).

---

## Sequencing & gates

8.1 → 8.2 → 8.3 (8.2 depends on the owned-set map; 8.3 depends on the owner
wallet hoist). Each task: full pytest suite + 3 same-seed all-AI sims — no
season-end crash; for 8.1 specifically, a 2-island-AI sim must show two
independent treasuries (assert no cross-island inventory/dollops bleed) and
net-worth dispersion vs post-#212 baseline within ±10% for single-island
players. 8.1 is the largest engine change since capital tracking — budget a
dedicated review pass on ws_adapter turn coordination before merge.

## Decision points — RESOLVED by Ash 2026-07-14

- D1 ✅ control = largest holder, ties → incumbent (8.3.2).
- D2 ✅ dividends deferred to a follow-on task (8.3.3).
- D3 ✅ NO turn ordering — free tab-switching; the frontmost tab is the
  acting island and actions apply in the order they are captured (8.1.5).
