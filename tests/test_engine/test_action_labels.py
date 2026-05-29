"""Tests for the player-facing TurnAction label overrides (playtest 2026-05-15).

`Purchase Capital` is renamed to `Purchase Equipment` at the display layer
without changing the internal enum identifier `TurnAction.PURCHASE_CAPITAL`
or its value `"purchase_capital"`.
"""
from __future__ import annotations

from island_traders.cli.prompts import action_label, ACTION_LABEL_OVERRIDES
from island_traders.engine.turn import TurnAction


def test_purchase_capital_displays_as_purchase_equipment():
    assert action_label(TurnAction.PURCHASE_CAPITAL) == "Purchase Equipment"


def test_default_titlecase_for_unmapped_actions():
    # An action without an override should use the title-cased value.
    assert action_label(TurnAction.MARKET_BUY) == "Market Buy"
    assert action_label(TurnAction.PROPOSE_DEAL) == "Propose Deal"
    assert action_label(TurnAction.END_TURN) == "End Turn"


def test_internal_enum_name_and_value_are_unchanged():
    # Internal identifier must stay stable — only the player-facing label
    # changes.  Saved games, tests, server JSON all rely on the value.
    assert TurnAction.PURCHASE_CAPITAL.value == "purchase_capital"
    assert TurnAction.PURCHASE_CAPITAL.name == "PURCHASE_CAPITAL"


def test_override_dict_only_contains_known_action_values():
    """Each entry in ACTION_LABEL_OVERRIDES must correspond to a real
    TurnAction value (otherwise a typo silently does nothing)."""
    known_values = {a.value for a in TurnAction}
    for k in ACTION_LABEL_OVERRIDES:
        assert k in known_values, f"override key {k!r} is not a TurnAction value"
