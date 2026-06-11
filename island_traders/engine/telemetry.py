"""Dynamic supply-chain liveness telemetry (B1/B2, #73).

A single ``ResourceFlowTelemetry`` is created per game and attached to the
Market, the ProductionEngine, and the TradingEngine.  Each records into it
when present (the attribute defaults to ``None``, so production play and the
unit tests that build engines directly are unaffected).

It answers questions the *static* reachability tests (B3,
``tests/test_models/test_supply_chain_reachability.py``) cannot:

- Which resources are actually produced/consumed/traded, and how much?
  (A resource that is *producible* but never produced — e.g. the original
  Reagents gap, or an output the AI refuses to make — shows zero here.)
- How often does a producer stall because a required input was unavailable?
  (``starvation`` counts each (player, season) production attempt that failed
  on missing inputs, keyed by the missing resource.)

Volumes are keyed by ``ResourceType.value`` (the resource's string name) so the
runner can aggregate across games without importing the enum.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models.resource import ResourceType


@dataclass
class ResourceFlowTelemetry:
    produced: dict[str, float] = field(default_factory=dict)
    consumed: dict[str, float] = field(default_factory=dict)
    traded: dict[str, float] = field(default_factory=dict)
    starvation: dict[str, int] = field(default_factory=dict)

    def record_produced(self, rtype: ResourceType, qty: float) -> None:
        if qty:
            self.produced[rtype.value] = self.produced.get(rtype.value, 0.0) + qty

    def record_consumed(self, rtype: ResourceType, qty: float) -> None:
        if qty:
            self.consumed[rtype.value] = self.consumed.get(rtype.value, 0.0) + qty

    def record_traded(self, rtype: ResourceType, qty: float) -> None:
        if qty:
            self.traded[rtype.value] = self.traded.get(rtype.value, 0.0) + qty

    def record_starvation(self, rtype: ResourceType, count: int = 1) -> None:
        if count:
            self.starvation[rtype.value] = self.starvation.get(rtype.value, 0) + count
