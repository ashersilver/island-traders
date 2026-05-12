# LLM Player Adapter

## Goal

Introduce an optional AI player mode that can play Island Traders more like a human governor: planning across seasons, negotiating trades, explaining intentions, and reacting to table context. This should complement, not replace, the current deterministic `AIStrategy`.

## Current State

The existing AI implementation in `island_traders/engine/ai.py` is a greedy heuristic. It is valuable because it is fast, deterministic, cheap to run, and suitable for simulation calibration. That path should remain the default for bulk simulations and tests.

## Proposed Shape

Add a separate LLM-backed player adapter that receives a structured game-state snapshot and returns a structured action proposal. The engine remains authoritative: the LLM may suggest actions, but existing game services validate legality, affordability, inventory availability, and side effects.

Suggested components:

- `PlayerStrategy` protocol or base class with a `take_turn(...) -> list[str]`-style interface.
- `HeuristicStrategy` or the existing `AIStrategy` as the deterministic implementation.
- `LLMPlayerStrategy` as an optional implementation behind configuration.
- `GameStateSnapshot` serializer containing only the public and player-private context the model should know.
- `ActionProposal` schema for market buys, sell offers, production choices, trade proposals, training requests, insurance, loans, and chat/deal messages.
- Validation layer that rejects or repairs illegal proposals before applying them.

## Context To Provide

The LLM player prompt/context should include:

- Player identity, roles, island responsibilities, and victory objective.
- Current year, season, event result, and turn order context.
- Dollops, inventory, workforce, production capacity, insurance, loans, and active patents.
- Required production inputs and expected outputs for controlled roles.
- Current market prices, available offers, and recent price movement if available.
- Public summaries of other players: roles, visible offers, known shortages, and deal history.
- Available legal actions for this turn.
- Optional personality/negotiation style, kept separate from rules and state.

## Structured Output Sketch

```json
{
  "production": {
    "action": "produce",
    "manufacturer_product_line": "capital_equipment"
  },
  "market_orders": [
    {"action": "buy", "resource": "Oil", "quantity": 2, "max_price": 12.0}
  ],
  "sell_offers": [
    {"resource": "Food", "quantity": 3, "price": 5.5}
  ],
  "trade_proposals": [
    {
      "to_player_id": 2,
      "offer": {"Food": 4},
      "request": {"CapitalEquipment": 1},
      "message": "I can cover your food needs this season if you can help me scale production."
    }
  ],
  "table_message": "Food is available, but I need equipment before autumn."
}
```

## Non-Goals

- Do not let the LLM mutate game state directly.
- Do not use the LLM strategy for default calibration simulations.
- Do not require network access or API credentials to run the core game or tests.
- Do not hide invalid model output; report enough detail to debug strategy failures.

## Open Questions

- Should LLM players act synchronously on their turn, or pre-plan while human turns are in progress?
- Should the server expose LLM player configuration per room, globally, or via environment variables only?
- Should table chat be treated as public context for all LLM players?
- Should private strategy memory persist across turns, and if so where should it live?
