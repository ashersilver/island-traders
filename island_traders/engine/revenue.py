from __future__ import annotations

from math import ceil
from typing import Any

from ..constants import (
    BASE_PRODUCTION,
    FARMER_SEASONAL_CONVERSION,
    LABOUR_REQUIREMENTS,
    MANUFACTURER_PRODUCT_LINES,
    OUTPUT_PRODUCTION_INPUTS,
    PRODUCTION_INPUTS,
    PRODUCER_PRODUCTIVITY_MULTIPLIER,
    CONSUMER_STRUCTURAL_ADVISORY_WEIGHT,
    SKILLED_PROFESSIONS,
)
from ..models.market import Market
from ..models.player import Player
from ..models.resource import ResourceType
from .consumer import structural_consumer_demand_units


def _resource(value: str | ResourceType) -> ResourceType:
    return value if isinstance(value, ResourceType) else ResourceType(value)


def _add_inputs(
    totals: dict[ResourceType, float],
    inputs: dict[str | ResourceType, int | float],
    multiplier: float = 1.0,
) -> None:
    for resource, qty in inputs.items():
        rtype = _resource(resource)
        totals[rtype] = totals.get(rtype, 0.0) + float(qty) * multiplier


def _structural_demand_units(
    output: ResourceType,
    all_players: list[Player],
    season_name: str,
) -> float:
    total = 0.0
    for consumer in all_players:
        for role in consumer.roles:
            if role.name == "Farmer":
                inputs = FARMER_SEASONAL_CONVERSION.get(season_name, {}).get("inputs", {})
            elif role.name == "Manufacturer":
                inputs = {}
                for line in MANUFACTURER_PRODUCT_LINES.values():
                    _add_inputs(inputs, line.get("inputs", {}))
            else:
                inputs = {
                    _resource(resource): qty
                    for resource, qty in PRODUCTION_INPUTS.get(role.name, {}).items()
                }
                for recipe_inputs in OUTPUT_PRODUCTION_INPUTS.get(role.name, {}).values():
                    _add_inputs(inputs, recipe_inputs)
            total += inputs.get(output, 0)
    total += (
        structural_consumer_demand_units(output, all_players, season_name)
        * CONSUMER_STRUCTURAL_ADVISORY_WEIGHT
    )
    return total


def _live_bid_units(market: Market, output: ResourceType) -> int:
    return (
        sum(bid.remaining for bid in market.available_bids(output))
        + market.demand.get(output, 0)
    )


def _unit_price(market: Market, output: ResourceType) -> float:
    bid = market.best_bid(output)
    if bid is not None:
        return round(bid.price_per_unit, 2)
    if hasattr(market, "market_maker_bid"):
        return round(market.market_maker_bid(output), 2)
    return round(market.current_price(output), 2)


def _opportunity_specs(player: Player, season_name: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for role in player.roles:
        role_name = role.name
        if role_name == "Farmer":
            conversion = FARMER_SEASONAL_CONVERSION.get(season_name, {})
            inputs = conversion.get("inputs", {})
            for output, qty in conversion.get("outputs", {}).items():
                specs.append({
                    "role": role_name,
                    "line": None,
                    "output": _resource(output),
                    "qty": float(qty),
                    "inputs": inputs,
                    "required_professions": SKILLED_PROFESSIONS.get(role_name, []),
                })
        elif role_name == "Manufacturer":
            for line_key, line in MANUFACTURER_PRODUCT_LINES.items():
                inputs = dict(line.get("inputs", {}))
                freight = int(line.get("freight_per_unit", 0))
                if freight > 0:
                    board_scale_qty = max(
                        1, round(float(line["qty"]) / PRODUCER_PRODUCTIVITY_MULTIPLIER)
                    )
                    inputs["Freight"] = inputs.get("Freight", 0) + freight * board_scale_qty
                specs.append({
                    "role": role_name,
                    "line": line_key,
                    "output": _resource(line["output"]),
                    "qty": float(line["qty"]),
                    "inputs": inputs,
                    "required_professions": SKILLED_PROFESSIONS.get(role_name, []),
                })
        else:
            role_inputs = PRODUCTION_INPUTS.get(role_name, {})
            for output, qty in BASE_PRODUCTION.get(role_name, {}).items():
                output_inputs = dict(role_inputs)
                output_inputs.update(
                    OUTPUT_PRODUCTION_INPUTS.get(role_name, {}).get(output, {})
                )
                specs.append({
                    "role": role_name,
                    "line": None,
                    "output": _resource(output),
                    "qty": float(qty),
                    "inputs": output_inputs,
                    "required_professions": SKILLED_PROFESSIONS.get(role_name, []),
                })
    return specs


def revenue_opportunities(
    player: Player,
    market: Market,
    all_players: list[Player],
    season_name: str,
) -> list[dict[str, Any]]:
    """Rank producible outputs by expected profit from live + structural demand."""
    opportunities: list[dict[str, Any]] = []
    for spec in _opportunity_specs(player, season_name):
        output: ResourceType = spec["output"]
        qty = max(1.0, float(spec["qty"]))
        unit_price = _unit_price(market, output)
        input_cost = sum(
            market.current_price(_resource(resource)) * float(amount)
            for resource, amount in spec["inputs"].items()
        )
        unit_input_cost = round(input_cost / qty, 2)
        unit_margin = round(unit_price - unit_input_cost, 2)
        structural = _structural_demand_units(output, all_players, season_name)
        live_bid = _live_bid_units(market, output)
        demand = max(structural, live_bid)
        recommended_qty = min(int(qty), int(ceil(demand))) if demand > 0 else 0
        if recommended_qty > 0:
            runs = max(1, ceil(recommended_qty / qty))
        else:
            runs = 1
        inputs_to_stockpile = {
            _resource(resource).value: int(ceil(float(amount) * runs))
            for resource, amount in spec["inputs"].items()
            if amount > 0
        }
        score = round(unit_margin * demand, 2)
        opportunities.append({
            "role": spec["role"],
            "product_line": spec["line"],
            "output": output.value,
            "unit_price": unit_price,
            "unit_input_cost": unit_input_cost,
            "unit_margin": unit_margin,
            "structural_demand_units": int(structural)
                if float(structural).is_integer() else round(structural, 2),
            "live_bid_units": live_bid,
            "recommended_qty": recommended_qty,
            "required_professions": list(spec["required_professions"]),
            "labour_requirements": LABOUR_REQUIREMENTS.get(spec["role"], {}),
            "inputs_to_stockpile": inputs_to_stockpile,
            "score": score,
        })
    return sorted(
        opportunities,
        key=lambda item: (item["score"], item["unit_margin"], item["recommended_qty"]),
        reverse=True,
    )
