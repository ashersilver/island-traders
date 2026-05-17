# Island Traders

A Python-based resource-trading game for 2–7 players. Each player governs an
island built around a different economic sector — **Farming**, **Mining**,
**Transport**, **Education**, **Banking**, **Manufacturing**, or **Healthcare**
— and competes over several seasons to grow the wealthiest economy. Players
produce resources, trade on the open market, broker peer-to-peer deals,
train workers, take and refinance loans, buy insurance, and weather seasonal
events. The richest economy at the end wins.

The codebase supports three play modes:

| Mode | Use when… |
|---|---|
| **Browser dashboard** (multiplayer) | Several people on different computers/phones; the host serves a room over the network. |
| **CLI** (single computer) | Local multi-player at the keyboard or a quick solo test. |
| **Physical board game** | Around a table. The export tool generates all printable cards, charts, and price boards; rules live in [`RULES.md`](RULES.md). |

A simulation runner is included for balancing the event charts.

---

## Install

```bash
git clone https://github.com/ashersilver/island-traders.git
cd island-traders
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Python **3.9+** required. The dev extra pulls in `pytest`, `fastapi`,
`uvicorn`, and the websocket dependencies.

---

## Play

### Multiplayer (browser dashboard)

```bash
island-traders-server --host 0.0.0.0 --port 8000
```

Open `http://<host>:8000/` from any browser on the network. The dashboard
walks you through:

1. **Create or join a room** — host shares the 6-character join code.
2. **Role auction** — sealed-bid auction across the 7 islands. A player can
   win more than one role.
3. **Post-auction island guarantee** — if any human ends the auction with no
   island and any AI won 2+ roles, the islandless human gets one chance to
   buy an AI extra at a formula price before Year 1 starts.
4. **Investing phase** — each owner buys mandatory minimum capital equipment
   plus optional upgrades from a shared budget.
5. **Game proper** — sequential seasons of production, trading, training,
   lending, insurance, and events; running totals visible on the dashboard.

Each player runs their own turn on its own thread, so play feels concurrent
rather than strictly sequential. A configurable **pre-season review window**
and **season timer** keep the pace.

#### Host controls

- **Pause / Resume** — the host can pause the game at any phase. All timers
  freeze; a full-screen overlay shows on every client; the host clicks Resume
  to continue.
- Public/private rooms with optional join codes.

#### Per-player actions (during the game)

`Produce`, `Market Buy/Sell`, `Propose Deal`, `Request Training`,
`Arrange Transport`, `Recruit Workers`, `Sell/Buy Insurance`,
`Manage Insurance` *(cancel for a pro-rata refund)*, `Purchase Capital`,
`Offer Loan`, `Take Loan`, `Roll Over Loan` *(refinance at a fresh banker
quote)*, `View Loans`, `Apply Patent`, `View Market`, `View Players`,
`Inventory`, `End Turn`.

### CLI (single computer)

```bash
island-traders
```

Walks you through setup (number of players, role assignment) and runs
turn-by-turn play. The same engine code powers both the CLI and the browser
dashboard.

### Physical board game

Full rules are in [`RULES.md`](RULES.md). Run the export tool to generate
the role cards, event tables, and price board:

```bash
island-traders-export --output ./printables
```

(Plain-text output today; PDF export is a planned enhancement.)

---

## Simulation

Run many AI-only games to calibrate balance:

```bash
island-traders-sim --games 1000 --seed 42
```

Outputs a CSV to `simulation_results/`. The target is roughly equal win
rates across all 7 roles. Iterate on `config/event_charts.yaml` weights
and rerun.

---

## Tests

```bash
pytest
```

The test suite covers models, engine, simulation, and server (FastAPI
WebSocket flows). 200+ tests, all expected green on `pre-release`.

---

## Project layout

```
island_traders/
├── constants.py            # All numeric constants — tune balance here
├── constants_capacity.py   # Production-capacity model: capital catalogue, workforce
├── models/                 # Resources, roles, players, market, deals, loans,
│                           #   insurance, workforce, professions, training
├── engine/
│   ├── events.py           # Seasonal event resolution
│   ├── production.py       # Inputs → outputs
│   ├── trading.py          # Market + peer-to-peer deals
│   ├── turn.py             # TurnManager: human IO + AI dispatch
│   ├── ai.py               # Heuristic AIStrategy
│   └── game.py             # Game orchestrator
├── simulation/             # SimulationRunner: N games, CSV stats
├── export/                 # Printable asset generator
├── chat/                   # SQLite-backed in-game chat
├── board/                  # HTML board visualisations
├── cli/                    # Interactive CLI entry point + IOAdapter
└── server/
    ├── app.py              # FastAPI app, GameManager, REST + WS endpoints
    ├── ws_adapter.py       # Sync-to-async IO adapter for per-player threading
    └── static/index.html   # Browser dashboard
config/
└── event_charts.yaml       # Tunable event weights per island
requirements/               # Detailed feature specs (production-capacity, ledger,
                            #   release process, LLM player adapter…)
tests/                      # pytest test suite
```

---

## Key game concepts

**Currency** is called **Dollops** (symbol `Dp`). Default starting auction
budget is 700 Dp per player.

**Resources (11 total):** `Food`, `Fish`, `Ore`, `Oil`, `Metal`, `Freight`,
`Expertise`, `CapitalEquipment`, `Goods`, `HealthServices`, `Vaccine`,
`Finance`.

**The 7 islands and their economies:**

| Role | Island | Produces | Needs |
|---|---|---|---|
| Farmer | Agriculture, Fisheries & Foods | Food, Fish | CapitalEquipment, Oil |
| Miner | Mining & Oil | Ore, Oil, Metal | Oil, Freight, MiningEquipment |
| Transporter | Transportation & Shipping | Freight | Oil, CapitalEquipment |
| Educator | Education & Training | Expertise, Patents | CapitalEquipment, Finance |
| Banker | Banking | Finance, Insurance | Expertise, CapitalEquipment |
| Manufacturer | Manufacturing | Goods, CapitalEquipment | Metal, Oil, Freight |
| Doctor | Healthcare | HealthServices, Vaccine | Expertise, CapitalEquipment |

**Workforce model:** Every island starts with at least **1 Manager** and
**2 Technicians** plus general unskilled labour. Transporter, for example,
starts with a Logistics Manager and Flight Crew / Seaman / Warehouse Manager
technicians. Workers can be trained at the Educator's University into higher
tiers; production scales with workforce size and skill mix.

**Loans and insurance:** The Banker quotes rates from a posted funding-rate
curve plus a borrower risk premium. Loans are bullet bonds — repaid in full
at maturity — but can be **rolled over** for a fresh rate and term. Life and
Medical insurance policies last 4 seasons and can be cancelled mid-term for
a pro-rata refund.

**Events** fire per-season per-island from the configurable event charts
(yields, disasters, outages, workforce risks). Insurance + Mechanics dampen
the worst outcomes.

For the complete game rules see [`RULES.md`](RULES.md).

---

## Tuning the event charts

Edit weights in `config/event_charts.yaml`, then run:

```bash
island-traders-sim --games 1000 --seed 42
```

Inspect the output CSV. Aim for ≈ 1/7 (~14%) win rate per role. Adjust
weights and re-run until balanced. The release process recommends a
calibration pass before each version bump.

---

## Contributing & releases

- See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full guide. **Every commit
  must be signed off** under the [Developer Certificate of Origin](DCO)
  (`git commit -s`).
- Work happens on feature branches off `pre-release` (`claude/…`, `codex/…`,
  or `yourname/…` prefixes).
- Release notes live in [`RELEASE_NOTES.md`](RELEASE_NOTES.md) and must be
  updated before a feature branch merges to `pre-release`.
- The release process is documented in
  [`requirements/release-process.md`](requirements/release-process.md).
- Feature specs and design discussions live in [`requirements/`](requirements/).

---

## License

Released under the **Apache License, Version 2.0** — see [`LICENSE`](LICENSE)
and [`NOTICE`](NOTICE).

The game design and rules are original work; any similarity to existing games
is coincidental.  Parts of the code and design were generated and maintained
with AI assistance (Claude, Codex).  See [`DISCLAIMER.md`](DISCLAIMER.md) for
the full originality, contribution, and AI-disclosure statement.
