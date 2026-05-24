# Role-Player Guides (per-role instructions)

Status: **draft requirements** (2026-05-19)
Source: product-owner direction 2026-05-19
Touches: CLI session, server UI, RULES.md (source of truth), export

---

## Problem

Today a player gets a short **island introduction** when they acquire a
role (auction win). That intro is not enough: several roles now have
non-obvious subtleties a new player must understand to play well — most
acutely the **Banker's lending rules** (capital-reserve ratio, MBA
leverage, own-capital vs external funding, negotiation, term/rollover),
but also the Educator's two training pipelines, the universal capital
lifecycle (maintenance + replacement), and worker retirement.

A player should be able to read a concise, role-targeted guide for the
island(s) they hold, on demand, not just at acquisition.

## Requirement

Provide a **per-role player guide** in addition to the acquisition
intro:

- **On demand**, any time during play (CLI: a "Role guide" menu /
  action; server: a help panel/button on the dashboard for each island
  the player holds).
- **Role-targeted and concise** — the subtleties that change how *that*
  role decides, not the whole rulebook. Examples of must-cover items:
  - **Banker:** own-capital reserve ratio (0.50 → 0.20 with ≥3 MBA
    managers), what own-capital vs external funding earns (full
    interest vs margin), reserved capital is locked until the loan
    resolves, the bank may quote any rate and the applicant may counter,
    1/2/3-year terms and the original-amount/original-rate annual
    rollover, the +1-season processing delay without a computing centre.
  - **Educator:** Manager (Course-gated university) vs Technician
    (apprenticeship slot-pool + Instructor) pipelines, profession-
    dependent durations, the 75% settling season, Course/Expertise
    economics, the MBA request (2 Professors + 3 Courses).
  - **All roles:** capital items wear out and need maintenance +
    eventual replacement from the Manufacturer; workers age and retire
    and must be replaced (recruit + train) — plan ahead.
  - Each producing role: its inputs/outputs and key cross-island
    dependencies (e.g. Agriculture → Manufacturer for machinery).
- **Single source of truth.** `RULES.md` remains canonical. The guides
  are short role-specific distillations *derived from* the same
  mechanics; they must not contradict RULES.md. Prefer generating guide
  text from one shared content module so a rules change updates intro,
  guide, and (where possible) RULES.md together — avoid a third place
  that silently goes stale (the exact failure we just fixed in the
  RULES.md training chapter).

## Acceptance (when built)

- A player holding role X can open a guide for X at any turn (CLI +
  server) and see X's decision-relevant subtleties.
- The Banker guide accurately states the reserve/MBA/negotiation/term/
  rollover/computing-centre rules per `economy-lifecycle-2026-05.md §3`.
- Guides and the acquisition intro draw from one content source; a
  mechanics change has a single edit point.
- Multi-role players can view the guide for each island they hold.

## Phasing / ownership

- This is **UX/onboarding**, independent of the economy-lifecycle
  engine work — it can be built in parallel **after** the mechanics it
  documents are stable (so the text isn't written against a moving
  target). Sensible to schedule **after economy-lifecycle Phase D** (so
  the Banker rules are final) and pair with the `economy-lifecycle`
  **Phase E** RULES.md pass — same content, two surfaces.
- Candidate as a focused **Codex docs/UX task** once the Banker model
  lands, briefed from this file + `economy-lifecycle-2026-05.md §3`.

## Open questions

1. Content source format — a `role_guides.py` content module the CLI,
   server, and `export/printables.py` all render? (Recommended.)
2. Does the acquisition intro get replaced by "guide page 1", or stay
   separate and link to the fuller guide? (Recommend: intro = the
   guide's summary section; one document, progressive depth.)
3. Localisation/length budget — keep each guide to ~1 screen?
