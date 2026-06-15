# Graphics ideas

Drop-zone for concept art and design explorations (e.g. from Claude Design)
that are **not yet wired into the game**.

- Put files here (PNG / SVG / WebP / JPG preferred; keep individual files under
  ~5 MB — no PSDs or huge exports).
- Group related concepts in a subfolder with a short descriptive name, e.g.
  `design/graphics-ideas/island-icons-2026-06/`.
- A one-line note per batch in this README (what it is, where it came from)
  helps later triage.

When an asset is **adopted** into the game, move it to where it's served:
- in-game art → `island_traders/server/static/island-art/`
- board/printable assets → `island_traders/board/`

UI mockups/wireframes (screens, layouts) belong in `requirements/mockups/`
rather than here.

## Batches

- `claude-design-handoff-2026-06/` — Claude Design export (procedural isometric
  island renderer: `engine/`, `data/`, `lib/alpha-sierra.css`, prototype HTML,
  `screenshots/`). Style approved; its vector island graphics were judged less
  sophisticated than the cinematic concept renders. Superseded by the **hybrid**
  direction: cinematic render as base + a live overlay layer (built-equipment
  pins, weather FX, season tint). Mockup: `requirements/mockups/ui-v4-hybrid-island.html`.
