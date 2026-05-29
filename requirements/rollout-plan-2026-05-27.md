# Rollout Plan — 2026-05-27

Snapshot of what's shipped, in flight, and queued. Pairs with `TODO.md` (development priority tracker) and `requirements/codex-tasks/*.md` (Codex briefs). Bundles open work into shippable milestones for playtest scheduling.

Authoritative sources:
- **Bugs / feature requests** → GitHub issues
- **Sequencing / priority** → this doc + `TODO.md`
- **Engineering scope per task** → `requirements/codex-tasks/*.md`
- **Playtest reports** → `requirements/playtest-feedback/*.md`

---

## Live build

| Version | Released | Notes |
|---|---|---|
| `0.1.0-dev.2026-05-27.2` | 2026-05-27 | **Critical Done Trading fix.** Park-not-terminate semantics, server-side state-sync on reconnect + season-start. 465 tests passing. Live on port 8001. |

## Recently merged (2026-05-25 → 2026-05-27)

| Merge | Brief / Issue | Status |
|---|---|---|
| PR #41 | `educator-approval-queue-2026-05-26` | ✅ Live (.5) |
| PR #46 | `ai-manufacturer-product-mix-2026-05-26` | ✅ Live (.5) |
| PR #38 | `kitchen-island-2026-05-26` | ✅ Live (.2) |
| PR #37 | `training-flow-diagnostic-2026-05-26` | ✅ Live (.2) |
| PR #39 | `training-profession-alignment-2026-05-26` | ✅ Live (.3) |
| PR #40 | `banker-wholesale-funding-2026-05-26` | ✅ Live (.4) |
| direct | Purchase Equipment named-option picker (closes #21) | ✅ Live (.27) |
| direct | Done Trading park + state-sync (this cycle) | ✅ Live (.27.2) |

---

## In flight — Codex brief queue (7 open)

Priority order recommended by 2026-05-26.5 triage; Codex picks the actual order.

| # | Brief | Priority | Notes |
|---|---|---|---|
| 1 | `training-expertise-deadlock-2026-05-27` | **Critical** | **Claude in progress 2026-05-27.** AyaySir 9-season deadlock + Codex Player. |
| 2 | `loan-and-insurance-consent-bugs-2026-05-27` | High | Covers AyaySir BUG-07, Codex Player loan-on-behalf, loan rollover (#6), early default. |
| 3 | `market-bug-cluster-2026-05-27` | Medium | Bid display mismatch, no-cross, stale hints (parts of #22). |
| 4 | `event-frequency-cap-2026-05-27` | Medium | 5-halts-in-5-seasons + Pandemic+Fire+Damage. |
| 5 | `training-request-withdraw-by-requester-2026-05-27` | Low | Small, symmetric to PR #41. |
| 6 | `banker-lawyers-2026-05-26` | Low | Closes #44. |
| 7 | `done-trading-undo-and-auto-set-fix-2026-05-27` | ✅ **Done** | Claude implemented; shipped in `.27.2`. |

## Claude UI follow-up backlog

Three batched passes from the 2026-05-26.5 triage + carry-over surfaces from prior cycles.

**Pass A — Action panel + hints** (depends on done-trading fix — now landed)
- Banker active-loan chip (payload from PR #40 already shipped)
- Educator drag-reorder queue + inline Reject/Counter (payload from PR #41 already shipped)
- Requester training-decisions badge + "Improve bid" popup (payload from PR #41)
- Capital Catalogue z-index / click-target overlap with Market Buy

**Pass B — Market UX** (some covers GitHub #22)
- Real-time capital affordability indicator in Market Buy
- Place Bid vs Buy Now distinction (colour, headers, tooltips)
- "List at Best Bid" one-click in Market Sell
- Inventory panel "listed on market" badge
- Pre-fill bid at market ask / pre-fill sell at best bid (#22 items 3 & 4)

**Pass C — Dashboard surfaces** (some covers GitHub #20)
- "Meals runway: 0" prominent warning
- Persistent compact leaderboard in sidebar
- "Start Game" button + host indicator in waiting room
- Production Capacity inline blocking reason
- Public Education Island capacity visibility
- Educator resource requirements on training-request form
- **Personnel count** (trained + untrained + workers) in left-hand panel (#20)
- **Lawyer chip** on workforce display once `banker-lawyers` ships

**Standalone (any-time):**
- Game log denoise (collapse prior seasons, sticky current header)
- Final game-over screen with stats (also needs engine `GameOver` payload)

## Scoping items needing decisions

Items from the 2026-05-26 GitHub-issues scoping batch that still need clarification before they can become briefs.

| # | Issue | Status |
|---|---|---|
| #42 | Fertiliser | ✅ Decisions captured; ready to brief |
| #43 | MPS | ✅ Decisions captured; needs to split into 3 sub-briefs (Cargo Aircraft + Electronics + scheduling engine) |
| #45 | Pollution + Forests | ⏳ Still needs scoping (per-island vs shared atmosphere, forest mechanic shape, pollution-effect routing) |
| #47 | Graceful degradation | ✅ Variable-by-category answer captured; defaults need confirmation |
| #48 | QoL + population dynamics | ✅ Score-only first; population later — confirmed |

## New scoping items from today (2026-05-27)

| # | Issue | Brief / parking shape |
|---|---|---|
| #49 | Vaccines + Flu Season | Bounded; new event chart entry, vaccine-consumption-reduces-infection. **Easy brief.** |
| #50 | Hiring Doctors and Nurses for fixed terms | **Two birds:** addresses Real Human #1 (workers run out) + introduces inter-island worker rental. Medium brief. |
| #51 | Air Freight | Naturally lives inside MPS (#43) — Cargo Aircraft + freight insurance. Fold into the MPS Cargo Aircraft sub-brief. |

## Older feature requests (still relevant)

These have been in GitHub for weeks and haven't shipped yet. Sequencing them into the right milestone:

| # | Issue | Where it lands |
|---|---|---|
| #6 | Roll over loans | Covered by `loan-and-insurance-consent-bugs-2026-05-27` brief |
| #19 | Doctors certify insurance + physical reduces premiums | Needs new brief; **depends on `loan-and-insurance-consent-bugs` first** so the auto-issue bug is gone before adding more insurance mechanics |
| #24 | Actuaries for insurance | Same pattern as Lawyers (#44). Can copy the brief structure. **After** #19 ships. |
| #25 | Ecologist profession | Needs new brief; **depends on #26** (lab tests) and #45 (pollution / environmental assessment context) |
| #26 | Medical Island = Lab tests (soil analysis, metal assays) | Needs new brief; medium effort, lots of downstream dependencies |
| #27 | Activity index per role (How to Play docs) | Docs-only; do anytime |
| #29 | AI Trading Behaviour | Partially addressed by `ai-manufacturer-product-mix-2026-05-26`; broader pass still needed for AI proactive trading |

## UX backlog (Claude work)

| # | Issue | Effort |
|---|---|---|
| #3 | Action alert popups | Medium |
| #4 | "What If" production tables | Medium-Large |
| #7 | All Players summary on Island layouts | Medium |
| #8 | Add Intro Screen with island hotspots | Large (needs graphics) |
| #22 | Market UI grid + bid/buy clarity | Partially in Pass B; full grid layout is larger |
| #23 | Logo bolder + island click popups | Small (logo) + Large (popups) |

---

## Closeable GitHub issues

Now or after current cycle ships:

- **#21** "product name must be listed when producing" — addressed by named-options purchase picker shipped in `0.1.0-dev.2026-05-27`. Close with reference to commit `a2c31cb`.
- **#10** "Market Board modal cannot be dismissed" — already marked done in TODO.md ("verified live"). Confirm and close.

After their owning brief lands:
- **#6** roll-over loans → close when `loan-and-insurance-consent-bugs-2026-05-27` ships.
- **#44** Lawyers → close when `banker-lawyers-2026-05-26` ships.

---

## Proposed milestone bundles

### 🎯 `0.1.0-rc1` — Critical bug-fix sweep (in flight)
**Target: this week.** Goal: every Critical / High playtest bug closed.

- [x] Done Trading park-and-undo (shipped)
- [ ] Training Expertise deadlock (in progress)
- [ ] Loan + insurance consent bugs
- [ ] Market bug cluster
- [ ] Event frequency cap
- [ ] Training request withdraw (requester side)
- [ ] Lawyers brief (small)
- [ ] UI Pass A (Action panel + hints surfaces)
- [ ] Close GitHub #6, #10, #21, #44

**Playtest gate before rc1 → rc2:** at least one clean game with no Critical-tier bugs reported.

### 🎯 `0.1.0-rc2` — Scoping-batch features
**Target: next 1-2 weeks.** Engine extensions from the 2026-05-26 GitHub issues with decisions already captured.

- [ ] Fertiliser (#42)
- [ ] Graceful degradation (#47)
- [ ] Pollution + Forests (#45) — needs scoping conversation first
- [ ] QoL score-only metric (#48a)
- [ ] Vaccines + Flu (#49)
- [ ] UI Pass B (Market UX) + Pass C (Dashboard surfaces) for the above + carry-overs

### 🎯 `0.2.0` — Major systems
**Target: when rc2 is stable.** Bigger refactors.

- [ ] MPS subsystem split into 3 sub-briefs (#43 + #51 Cargo Aircraft folded in)
- [ ] QoL population dynamics (#48b)
- [ ] Hire Doctors/Nurses for fixed terms (#50)
- [ ] AI Trading broader pass (#29)

### 📋 `0.2.x / 0.3.0` — Content expansion
**Target: post-0.2.0.** Profession + island expansions.

- [ ] Actuaries (#24)
- [ ] Ecologist (#25)
- [ ] Medical Lab tests (#26)
- [ ] Doctor physical / insurance discount (#19)
- [ ] Activity index per role (#27, docs-only)

### 📦 Backlog (nice-to-haves)
Pulled when a milestone has bandwidth.

- Intro Screen (#8)
- Action alert popups (#3)
- "What If" production tables (#4)
- All Players on island layouts (#7)
- Logo + island click popups (#23)

---

## Cadence

- **APP_VERSION bump** on every merge into `pre-release` that's worth playtesting.
- **Playtest cycle** = one playtest session per `.N` build; reports collected in `requirements/playtest-feedback/playtest-{VERSION}.md` + triage doc.
- **Milestone tag** (`0.1.0-rc1`, etc.) when a bundle's exit criteria are met.

Last refreshed: 2026-05-27 after the Done Trading fix.
