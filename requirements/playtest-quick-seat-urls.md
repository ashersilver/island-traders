# Playtest Quick-Seat URLs

**Status:** Approved design (2026-05-29) — not yet implemented.
**Audience:** Developers building the feature; playtesters using it.
**Scope:** A developer/playtest convenience only. Not a player-facing feature
and not exposed in the normal lobby UI.

---

## 1. Goal

Let one person drive a full 7-player game from seven browser tabs by pasting in
seven pre-composed URLs — one per island role. Each URL:

1. Lands the tab in the right game (creating it on the first tab, joining on the
   rest).
2. Names the player.
3. Auto-bids the player's chosen role at a chosen amount during the auction.
4. Auto-submits a chosen investment selection during the investing phase.

After the auction and investment selection complete, the automation **stops** and
hands control back to the human, who then plays Year 1 onward manually in each
tab.

---

## 2. Room coordination — name hash, not server code

The room ID is normally server-generated (`_short_id()`), so tabs 2–7 cannot
know it ahead of time. To allow all seven URLs to be composed *before* the game
exists, the room is keyed off a **shared room name** that every tab hashes
locally to the same deterministic room ID.

- Tab 1 (`create=1`) creates a room whose ID is `hash(roomName)`.
- Tabs 2–7 (`join=...`) compute the same `hash(roomName)` and join it.

Example name: `Trading Hell`.

### Hash rule

```
roomId = "pt-" + cyrb53(normalize(roomName))   // 16 hex chars
normalize(s) = s.trim().toLowerCase().replace(/\s+/g, " ")
```

The hash is **cyrb53** — a small, fast, dependency-free synchronous string hash
(implemented as `quickSeatHash()` in `index.html`). It is computed entirely on
the client so the create tab and all join tabs agree without any server
round-trip, and it avoids the async / secure-context constraints of
`crypto.subtle`.

- `pt-` prefix marks the room as a playtest/quick-seat room (easy to spot in
  logs and to filter out of any public room list).
- Normalization makes `"Trading Hell"`, `"trading hell"`, and
  `" Trading  Hell "` resolve to the same room, so casual re-typing still works.
- 16 hex chars (64 bits) is collision-safe for the handful of concurrent
  playtest rooms this is ever used for.

The server simply accepts a caller-specified room ID on create (see §6).

---

## 3. URL parameters

### Tab 1 — create + seat host

```
http://localhost:8001/?create=1&room=Trading%20Hell&player=Agricola&role=Farmer&bid=200&invest=110101&startcapital=1000&season=600
```

| Param          | Required | Meaning                                  | Maps to                          |
|----------------|----------|------------------------------------------|----------------------------------|
| `create=1`     | yes      | This tab creates the room                | `POST /api/rooms`                |
| `room=`        | yes      | Shared room name (hashed to room ID)     | room ID = `hash(room)`           |
| `player=`      | yes      | Host display name                        | `creator_name` / join `name`     |
| `role=`        | yes      | Role to auto-bid                         | `auction/bid role_name`          |
| `bid=`         | yes      | Bid amount (Dp)                          | `auction/bid amount`             |
| `invest=`      | no       | Investment bitmap (see §4)               | `investment_submit item_ids`     |
| `startcapital=`| no       | Per-player budget (Dp)                   | `starting_capital`               |
| `season=`      | no       | Season timer (seconds, 0 = no timer)     | `season_timer_seconds`           |

Room-wide params (`startcapital`, `season`) only take effect on the **create**
tab; they are ignored on join tabs.

### Tabs 2–7 — join + seat

```
http://localhost:8001/?join=Trading%20Hell&player=Minerva&role=Miner&bid=180&invest=101100
```

| Param      | Required | Meaning                                | Maps to                       |
|------------|----------|----------------------------------------|-------------------------------|
| `join=`    | yes      | Shared room name (hashed to room ID)   | room ID = `hash(join)`        |
| `player=`  | yes      | Display name                           | join `name`                   |
| `role=`    | yes      | Role to auto-bid                       | `auction/bid role_name`       |
| `bid=`     | yes      | Bid amount (Dp)                        | `auction/bid amount`          |
| `invest=`  | no       | Investment bitmap (see §4)             | `investment_submit item_ids`  |

> `room` and `join` carry the same value; the two names just make the host vs.
> joiner intent obvious. (`create=1` also disambiguates if both were ever
> present.)

---

## 4. Investment bitmap

The investment catalogue is built **per role, after the auction**, so the bitmap
is positional against *the won role's* ordered catalogue:

- Bit `1` = select that catalogue item; `0` = skip it.
- `110101` → select items 1, 2, 4, 6; skip 3, 5.
- **Mandatory** items are always included regardless of the bitmap.
- The bitmap is clamped to the catalogue length: extra bits are ignored, missing
  bits are treated as `0`.

Because catalogue length differs per role, a fixed-width bitmap is forgiving by
design — over/under-runs never error, they just clamp.

---

## 5. Client bootstrap flow (per tab)

On page load, if quick-seat params are present:

1. **Parse** params; compute `roomId = hash(room || join)`.
2. **Create or join:**
   - `create=1` → `POST /api/rooms` with the hashed room ID, `creator_name`,
     `starting_capital`, `season_timer_seconds`; then open the WebSocket.
   - else → `POST /api/rooms/{roomId}/join` with `name`; then open the
     WebSocket. (If the room doesn't exist yet, retry with backoff for a few
     seconds so join tabs can be opened before/around tab 1.)
3. **Auction:** the **host clicks "Start Auction"** once all seven tabs are
   seated (this is the natural sync point — no auto-start, so a tab opened late
   never gets left out). When the `auction_start` broadcast arrives, every tab
   auto-submits its bid over the WebSocket (`{type:"bid", role_name, amount}`).
4. **Investing:** when the investing phase opens, auto-submit
   `investment_submit` with `item_ids` derived from the bitmap against the
   delivered catalogue.
5. **Stop.** Clear the quick-seat state and surface a small banner
   (e.g. "Auto-seated as Minerva (Miner). You're driving from here.") so the
   human knows automation has handed off. From here the tab behaves like a
   normal manual session.

Automation must be idempotent against re-renders (only bid once, only submit
investments once) and must no-op cleanly if the phase is already past (e.g. the
tab was opened late).

---

## 6. Server change required

`POST /api/rooms` must honor a **caller-specified room ID** (the hashed value)
instead of always generating one via `_short_id()`. Guard rails:

- Only accept caller-specified IDs with the `pt-` prefix (keeps the override
  scoped to playtest rooms; normal lobby rooms keep server-generated IDs).
- If a room with that ID already exists, return it (idempotent create) rather
  than erroring, so re-pasting tab 1 doesn't fail.

No other server endpoints change — join/bid/investment all already key off the
room ID.

---

## 7. Example 7-tab table

| Tab | Player    | Role         | Bid | Invest  |
|-----|-----------|--------------|-----|---------|
| 1   | Agricola  | Farmer       | 200 | 110101  |
| 2   | Minerva   | Miner        | 180 | 101100  |
| 3   | Cargo     | Transporter  | 160 | 110000  |
| 4   | Professa  | Educator     | 150 | 100110  |
| 5   | Goldman   | Banker       | 220 | 111000  |
| 6   | Forge     | Manufacturer | 190 | 101010  |
| 7   | Medina    | Doctor       | 170 | 100011  |

Tab 1 URL:

```
http://localhost:8001/?create=1&room=Trading%20Hell&player=Agricola&role=Farmer&bid=200&invest=110101&startcapital=1000&season=600
```

Tabs 2–7 URL pattern:

```
http://localhost:8001/?join=Trading%20Hell&player=<NAME>&role=<ROLE>&bid=<DP>&invest=<BITMAP>
```

---

## 8. Out of scope / non-goals

- Not wired into the lobby UI or any public room listing.
- No auto-play beyond auction + investment selection — Year 1 onward is manual.
- No security hardening beyond the `pt-` prefix guard; this is a local
  playtest tool, not a production join mechanism.
