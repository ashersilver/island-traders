"""Tiny dependency-free module for IO control-flow signals.

Defined separately to avoid the circular import that would arise if either
`island_traders.cli.prompts` or `island_traders.engine.turn` owned these
symbols (prompts imports TurnAction from turn; turn needs to catch
ActionCancelled when the user cancels mid-prompt-chain).
"""
from __future__ import annotations


# Sentinel string the WS client sends to signal an explicit Cancel click.
# Distinct from a `null` value, which means "no answer" (timeout / interrupt)
# and should still fall back to a sensible default.
CANCEL_SENTINEL = "__CANCELLED__"


class ActionCancelled(Exception):
    """Raised by an IOAdapter prompt method when the user explicitly cancels.

    Action handlers in `engine.turn` let this propagate to the main action
    loop, which catches it and prints "Action cancelled" rather than allowing
    the action to fall through to default values (which previously meant a
    Cancel-click could still execute a partial action — e.g. training 1
    worker by default when the user clearly meant to abandon the action).
    """
    pass
