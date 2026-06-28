# Brief — #195 Worker Skills Management: Cancel Training + Transfers (2026-06-28)

**Suggested owner:** Codex (engine: cancel-training action, cross-island
worker-transfer negotiation).
**Base off:** `origin/pre-release` at `1e75609` (APP_VERSION `0.1.5-dev.2026-06-22.16`).
**Tracking issue:** [#195](https://github.com/ashersilver/island-traders/issues/195).
File as `Closes #195`.
**Pairs with:** Claude wires the frontend (cancel button on training queue,
transfer offer/accept UI in the staffing panel).

> **Process:** See `requirements/codex-tasks/_README.md` — that file is the
> standing working agreement and overrides anything here on process.

---

## Context

Training was implemented in the `codex/training-loans-repair-actions-2026-06-25`
branch (merged 2026-06-28). The training queue already has skip/cancel
no-op stubs but the user wants:

1. **Cancel a specific training request** — remove a pending (not-yet-started)
   training batch from the queue, and optionally refund fees.
2. **Offer/accept a worker transfer** — one island can offer skilled or
   unskilled workers to another for a negotiated per-head fee. The receiving
   island accepts or declines. Workers move immediately on acceptance.

---

## Part 1 — Cancel Training

### Engine changes

**New WS message:** `cancel_training`

```json
{ "type": "cancel_training", "training_id": "<uuid>" }
```

**Handler in `app.py`:** Find the `training_batch` handler. Add a sibling
handler for `cancel_training`:

```python
case "cancel_training":
    training_id = msg.get("training_id")
    result = turn_manager.cancel_training_request(player, training_id)
    await ws.send_json({"type": "cancel_training_result", **result})
    await _broadcast_game_state()
```

**Engine method** `TurnManager.cancel_training_request(player, training_id)`:

```python
def cancel_training_request(self, player: Player, training_id: str) -> dict:
    req = next(
        (r for r in player.training_queue if r.id == training_id and not r.started),
        None
    )
    if not req:
        return {"ok": False, "error": "Training request not found or already started"}
    player.training_queue.remove(req)
    # Refund: if student_loan_requested=False and fee was already charged, refund it.
    refunded = 0.0
    if not req.student_loan_requested and req.fee_paid:
        player.treasury += req.fee_paid
        refunded = req.fee_paid
    return {"ok": True, "training_id": training_id, "refunded": refunded}
```

If `fee_paid` isn't tracked on the training request, check how fees are
deducted when the batch is submitted and store the amount on the request at
that point.

**Check `req.started`:** Only allow cancellation of requests that haven't been
picked up by the Educator yet (i.e., not `started` and not `complete`). Once
the Educator has started reviewing it, it's too late to cancel (they should
decline it instead via the existing review flow).

**`pending_actions` update:** If a player's training queue becomes empty after
a cancel, remove `"review_training"` from their pending_actions if no other
training requests exist.

---

## Part 2 — Worker Transfer

### Concept

Either side can initiate: island A offers to send N workers of a given skill to
island B for a fee; OR island B requests to hire N workers from island A. Both
directions go through the same negotiation: one party creates an offer, the
other accepts or declines.

### Data model — `WorkerTransferOffer`

```python
@dataclass
class WorkerTransferOffer:
    offer_id:    str        # uuid4
    from_player: int        # player_id offering to send workers
    to_player:   int        # player_id requested to receive workers
    profession:  str        # "Unskilled" | any trained profession name
    count:       int        # number of workers
    fee_per_head: float     # Dp per worker, paid by receiving island
    expires_season: int     # offer expires if not accepted by this season
    status:      str = "pending"  # "pending" | "accepted" | "declined" | "expired"
    direction:   str = "offer"    # "offer" (sender initiates) | "request" (receiver initiates)
```

Store `game.transfer_offers: list[WorkerTransferOffer] = []` on `Game`.

### New WS messages

**Create offer:** `worker_transfer_offer`
```json
{
  "type": "worker_transfer_offer",
  "to_player_id": 3,
  "profession": "Teacher",
  "count": 5,
  "fee_per_head": 20.0,
  "direction": "offer"
}
```
Sender is `player_id` of the current WS connection. `direction="offer"` means
sender sends workers; `direction="request"` means sender wants to receive.

**Respond to offer:** `worker_transfer_respond`
```json
{
  "type": "worker_transfer_respond",
  "offer_id": "<uuid>",
  "accept": true
}
```

### Handler — create offer (`app.py`)

```python
case "worker_transfer_offer":
    offer = game.create_transfer_offer(
        from_player=player if msg["direction"] == "offer" else target_player,
        to_player=target_player if msg["direction"] == "offer" else player,
        profession=msg["profession"],
        count=msg["count"],
        fee_per_head=msg["fee_per_head"],
        direction=msg["direction"],
        expires_season=game.current_season_index + 2,
    )
    # Notify the target player
    await _send_to_player(target_player_id, {
        "type": "transfer_offer_received",
        "offer": offer.to_dict(),
    })
    await ws.send_json({"type": "transfer_offer_sent", "offer_id": offer.offer_id})
```

### Handler — respond (`app.py`)

```python
case "worker_transfer_respond":
    offer_id = msg["offer_id"]
    accept = msg.get("accept", False)
    result = game.resolve_transfer_offer(player, offer_id, accept)
    await ws.send_json({"type": "worker_transfer_result", **result})
    if result["ok"]:
        await _broadcast_game_state()
```

### Engine method — `Game.resolve_transfer_offer`

```python
def resolve_transfer_offer(self, responding_player: Player, offer_id: str, accept: bool) -> dict:
    offer = next((o for o in self.transfer_offers if o.offer_id == offer_id), None)
    if not offer or offer.status != "pending":
        return {"ok": False, "error": "Offer not found or already resolved"}

    # Confirm the responding player is the correct counterparty
    expected_responder = offer.to_player if offer.direction == "offer" else offer.from_player
    if responding_player.player_id != expected_responder:
        return {"ok": False, "error": "Not your offer to respond to"}

    if not accept:
        offer.status = "declined"
        return {"ok": True, "accepted": False, "offer_id": offer_id}

    # Validate: sender has enough workers of the profession
    sender = self._get_player(offer.from_player)
    receiver = self._get_player(offer.to_player)
    available = sender.count_workers(offer.profession)   # see below
    if available < offer.count:
        return {"ok": False, "error": f"Sender only has {available} available {offer.profession} workers"}

    total_fee = offer.fee_per_head * offer.count
    if receiver.treasury < total_fee:
        return {"ok": False, "error": "Receiver cannot afford the transfer fee"}

    # Execute transfer
    sender.remove_workers(offer.profession, offer.count)
    receiver.add_workers(offer.profession, offer.count)
    receiver.treasury -= total_fee
    sender.treasury   += total_fee
    offer.status = "accepted"

    return {
        "ok": True,
        "accepted": True,
        "offer_id": offer_id,
        "workers_moved": offer.count,
        "profession": offer.profession,
        "fee_paid": total_fee,
    }
```

**`Player.count_workers(profession)`** — count available (not-currently-working?
or all?) workers of a given profession. "Unskilled" maps to `player.population -
employed_count`. For trained professions, count from `player.staffing` or
the workforce ledger. Define "available" as workers not currently assigned to a
production slot (idle).

**`Player.remove_workers(profession, count)`** — remove `count` workers from the
player's workforce. For trained workers this means removing them from the staffing
list; for unskilled it reduces `player.population`.

**`Player.add_workers(profession, count)`** — inverse: add to staffing or
increase population.

If those methods don't exist, add them. Prefer modifying the minimal surface
(don't redesign the workforce model — just add/remove from the right list).

### Expiry

In `TurnManager._start_season()` (or wherever season-end processing runs),
expire stale offers:

```python
for offer in game.transfer_offers:
    if offer.status == "pending" and game.current_season_index > offer.expires_season:
        offer.status = "expired"
```

### `pending_actions`

Add `"review_transfer_offers"` to `_pending_actions_for_viewer(player)` when
the player has at least one `pending` transfer offer addressed to them.

### Expose in `game_state`

In `_build_player_state(player)`, add:

```python
"transfer_offers": [
    o.to_dict() for o in game.transfer_offers
    if o.status == "pending"
    and (o.from_player == player.player_id or o.to_player == player.player_id)
],
```

So each player sees only their own pending offers (sent and received).

---

## Serialisation

`game.transfer_offers` must be serialised to save/load (it's active game state).
Add `WorkerTransferOffer.to_dict()` / `from_dict()` and include
`transfer_offers` in `Game.__getstate__` / `__setstate__`.

---

## Tests to write

Create `tests/test_engine/test_worker_transfer.py`:

1. `cancel_training_request` removes a pending request and refunds fee.
2. Cancelling an already-started training returns `ok=False`.
3. Creating a transfer offer adds it to `game.transfer_offers`.
4. Accepting a transfer: workers move from sender to receiver; fee paid correctly.
5. Declining: offer status becomes "declined"; no workers moved; no money moved.
6. Accepting when sender has fewer workers than offered → `ok=False`.
7. Accepting when receiver can't afford the fee → `ok=False`.
8. Offer expires after `expires_season`.
9. `count_workers("Unskilled")` returns `population - employed`.

---

## What Claude does next (do not implement)

- **Cancel button** on each pending training row in the Training Desk. Sends
  `cancel_training` WS message; removes the row from the UI on success.
- **Transfer panel** in the staffing/workforce section: list of pending offers
  with Accept/Decline buttons; a "Make offer" form with profession, count, fee.
- Gold-glow highlight on the staffing action button when `review_transfer_offers`
  is in `pending_actions`.
