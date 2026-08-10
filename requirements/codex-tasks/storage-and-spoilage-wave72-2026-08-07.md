# Wave 7.2 (re-spec) — One spoilage engine, two routes to protection (2026-08-07)

**Supersedes** Task 7.2 in `spares-storage-spoilage-wave7-2026-07-13.md` **and**
§2 (#64 Transporter Warehousing) of
`economy-expansions-wave3-2026-07-12.md`. Build this instead of either.

## Why a re-spec

The two earlier specs describe the same mechanic with different economics:

| | Wave 7.2 (defect list) | Wave 3 §2 (#64) |
|---|---|---|
| Who stores | Each island buys its own building | The Transporter sells storage as a service |
| Protection | Food building 80, Grain Silo 100, spares warehouse | Bulk + cold warehouses rented per season |
| Balance effect | A cost for everyone | New revenue for the weakest role |

Building both would leave two parallel storage systems. Ash's decision
(2026-08-07): **one spoilage engine, two routes to protection** — an island is
covered either by storage it owns, or by capacity it rents from the Transporter.
Owned and rented capacity are interchangeable; only the total matters.

## The model

**Protection, not prevention.** Every perishable has a per-resource protected
capacity. Stock *within* protected capacity never spoils. Stock *above* it ages,
and is destroyed once it exceeds the resource's shelf life. This is the single
rule the whole feature rests on — do not add a second decay path.

```
protected(resource) = owned storage capacity + rented capacity
at_risk(resource)   = max(0, held - protected)
```

**Shelf lives (unprotected stock only):**
| Resource | Seasons before loss |
|---|---|
| Grain | 1 |
| Food | 2 |
| Spares | 4 |

Fish / Produce / Meat are **out of scope** for this pass — land Grain, Food and
Spares first and re-baseline before widening. Wave 3 §2's "lose 25–50%" partial
decay is dropped in favour of the shelf-life model above, which is what Ash
specified; a bucket past its shelf life is lost entirely.

### Route 1 — own the building

New capital items (any role may order unless noted):

| item | protects | capacity | suggested cost |
|---|---|---|---|
| `common.food_store` | Food | 80 | 40 |
| `farmer.grain_silo` (Farmer) | Grain | 100 | 35 |
| existing spares warehouses | Spares | 12 / 30 | see below |

**Spares warehouse renumbering** (from the original 7.2, still wanted):
`manufacturer.small_warehouse` `spares_storage` 10 → **12**;
`manufacturer.warehouse` → renamed **Large Warehouse**, 12 → **30**, cost
50 → **90**. Update `spares-warehouse-storage-2026-06-22.md`'s capacity notes.

Retire the dead `farmer.storage_building` `inventory_cap` effect (it has never
been enforced) — either delete it or convert that item into the Grain Silo.

### Route 2 — rent from the Transporter

Two Transporter capital items whose capacity is **let to other islands**:
`transporter.bulk_warehouse` (dry: Grain, Spares) and
`transporter.cold_warehouse` (chilled: Food).

- A **storage contract** reserves N units of a Transporter's capacity for a
  named island for a per-season fee, paid Transporter-ward each season while
  active. Mirror the existing lease / staffing fee-flow patterns rather than
  inventing a new settlement path.
- Rented capacity counts toward the renter's `protected(resource)` exactly as
  owned capacity does.
- A Transporter cannot let the same unit twice: track committed vs free
  capacity, and refuse a contract that would oversubscribe.
- If the renter cannot pay the fee, the contract lapses at season end and the
  protection is gone next season — surface this clearly before it bites.
- This is the Transporter's new revenue line; it sat at 14.2% mean share on the
  2026-08-07 baseline, so modest positive movement is expected and fine.

## Implementation notes

- **FIFO age buckets per resource** on the player (`{acquired_tick, qty}`),
  serialised with the rest of player state. Age only what exceeds protection;
  buckets past shelf life are destroyed with a per-player notice
  ("12 Grain perished — no silo capacity").
- **Failed or unmaintained storage does not protect**, consistent with
  `effective_capital_inventory`.
- Generalise the existing `spares_capacity()` into
  `storage_capacity(resource)` covering owned + rented, and keep
  `manufacture_spares`'s clamp working off it.
- Surface per-resource `protected`, `at_risk` and `perishes_in_seasons` in
  `game_state`; the UI shows an amber pill on at-risk inventory rows and the
  dependency map's "needed now" flag should treat imminent spoilage as urgent.
- **Do not let spoilage cause famine cascades.** Food must stay buyable: if a
  sim shows sustenance failures rising, cut shelf-life pressure rather than
  adding compensating hacks.

## Gates

Full pytest; 3 same-seed sims (seeds 42, 1, 7) against the **2026-08-07
baseline** (Farmer 10.0 ± 1.8, Miner 15.2 ± 4.3, Transporter 14.2 ± 2.7,
Educator 15.4 ± 3.1, Banker 15.0 ± 2.7, Manufacturer 16.0 ± 2.9, Doctor
14.3 ± 3.1) — the older post-#212 numbers are stale after the #243 retune.

Assert: no season-end crash; bankruptcies ~0; sustenance failures do not rise;
protected stock never spoils; unprotected stock spoils exactly on schedule; a
lapsed contract removes protection the following season; and the Transporter's
share moves up, not down. Expect the Farmer to feel grain pressure — log the
delta for calibration (#213) rather than silently re-tuning prices.

Sequence after this: 7.3 (CNC Workshop) — unaffected by this re-spec.
