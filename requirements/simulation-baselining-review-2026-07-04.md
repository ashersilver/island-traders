# Review — Simulation Baselining vs Manual Play (P3) — 2026-07-04

**Status: REVIEW + RECOMMENDATIONS for Ash.** Recommendations R1–R3 are cheap
and immediately actionable; R4–R6 are the structural fix for "sim doesn't
follow manual play".

## How baselining works today

`island_traders/simulation/runner.py` runs N all-AI games (default seed 42),
aggregating wins/wealth into `RoleStats` → CSV. Turns are driven by
`engine/ai.py` `AIStrategy.take_turn` (heuristics); any prompt the strategy
doesn't handle falls through to `_SilentIO`, which answers **degenerately**:
`choose_quantity → min_qty`, `choose_option/resource/player → first option`,
`confirm → True`, `ask_dollop_amount → 0.0`.

## Why it diverges from manual play

1. **Degenerate fallbacks bias flows.** Any new prompt chain silently plays
   "minimum/first/yes/zero" — e.g. a quantity default of min 1 sells 1 unit
   where a human sells the surplus. These divergences are invisible: nothing
   logs when `_SilentIO` (rather than `AIStrategy`) answered.
2. **Heuristics encode policies humans don't play.** Documented example: the
   invest rule "buy the cheapest unclaimed catalogue item" made the
   Manufacturer's share swing 8%↔44% purely on an integer maintenance term —
   a sensitivity no human table would produce (2026-06-21 Capital Orders II
   analysis). The heuristic AI also never proposes/counters P2P deals, never
   finances capital, accepts every posted rate: exactly the systems the P1
   briefs are about to deepen.
3. **Single-seed baselining.** Decisions are gated on seed-42 point estimates
   with no variance bar; a ±2pt "regression" can be noise. The runner already
   supports `--seeds` — it's just not the protocol.
4. **No ground truth.** Until now there was nothing to calibrate *against*.
   That changed: live games now persist full turn transcripts to Mongo
   (`island_traders.turns_v31/32/33`) plus per-agent JSONL — actual human and
   LLM action streams.

## Recommendations

**R1 — Variance protocol (small).** Baselines = 5 seeds × 200 games
(`--seeds 42,1,7,99,123`); report per-role mean ± stddev; a change is a
regression only if outside 2σ. Add stddev columns to `RoleStats`/CSV.

**R2 — Fallback telemetry (small).** Count `_SilentIO` answers per prompt type
per game; print the top 10 in the sim summary. Any nonzero count on a prompt
the current test targets = the sim isn't exercising the mechanic, it's
defaulting through it. (Would have flagged the produce-quantity and deal flows
immediately.)

**R3 — Same-base A/B discipline (process, already learned).** Every balance
PR quotes before/after on the same base commit, same protocol as R1 — codify
in `_README.md` (the spares regression lesson).

**R4 — Transcript-derived behaviour profiles (the structural fix).** From the
Mongo turn logs, extract per-role empirical distributions: action mix per
season phase, sell-quantity as fraction of surplus, ask-price vs market bid,
loan uptake, deal frequency. Two uses:
  a) **Parity report**: same distributions from sim games, side by side —
     "sim Miner sells 1.0× min qty; live Miners sell 0.8× surplus at ≥1.4×
     bid" — a concrete divergence list to burn down.
  b) **Calibrated policies**: replace the worst heuristics with samplers from
     the live distributions (quantity fractions, price multipliers, invest
     preferences) behind a `--policy transcript` flag, keeping the legacy
     heuristics as the stable baseline.

**R5 — Replay harness (medium).** Re-run a recorded live game's action stream
through the engine headlessly; assert identical outcomes. Catches engine
regressions against *real* play and doubles as validation that transcripts
capture everything (they're already Mongo-normalised).

**R6 — LLM-agent sim tier (medium, infra exists).** A `--agents ollama` mode
that seats island-trader-gemma/qwen agents in N=10–20 headless games as a
mid-fidelity check between heuristic sims and live tables. Slow, so it's a
release gate (pre-merge to master), not a per-PR gate. All the plumbing
(play.sh, launcher, transcripts) already exists.

**R7 — Degeneracy metrics (small).** Add wealth Gini / share-HHI per game to
the stats; a balance change that keeps means flat but doubles concentration is
currently invisible.

## Suggested order

R1+R2+R7 in one small PR (pure runner/stats, no engine risk) → R3 doc change →
R4a parity report → R4b/R5 as the P1 briefs land (they need trustworthy
baselining most) → R6 before the next release cut.
