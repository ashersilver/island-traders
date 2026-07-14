"""Per-product Produce buttons: the single PRODUCE action fans out into one
"Produce <product>" button per producible product, and the dashboard adapter
round-trips the chosen product back to _action_produce (skipping the picker)."""
from __future__ import annotations

from island_traders.engine.production import ProductionEngine
from island_traders.engine.turn import TurnAction
from island_traders.models.resource import ResourceType
from island_traders.models.profession import Profession
from island_traders.server.ws_adapter import WebSocketIOAdapter


def _stock_manufacturer(manufacturer):
    """Give the manufacturer capital, skilled workers, and inputs so several
    product lines are actually producible (mirrors the production-options test)."""
    manufacturer.add_capital("manufacturer.assembly_line")
    manufacturer.add_capital("manufacturer.shipyard")
    manufacturer.workforce.add_workers(2, training_level=1, profession=Profession.ENGINEER.value)
    manufacturer.workforce.add_workers(3, training_level=1, profession=Profession.ASSEMBLY_WORKER.value)
    manufacturer.receive_resources(ResourceType.METAL, 40)
    manufacturer.receive_resources(ResourceType.OIL, 40)
    manufacturer.receive_resources(ResourceType.FREIGHT, 40)


def test_produce_menu_options_label_each_product(manufacturer, normal_event):
    _stock_manufacturer(manufacturer)
    engine = ProductionEngine()
    menu = engine.produce_menu_options(manufacturer, normal_event, season_name="Spring")

    assert menu, "expected at least one producible product"
    assert all(entry["label"].startswith("Produce ") for entry in menu)
    labels = {entry["label"] for entry in menu}
    # Product-line desc drives the label, not the raw enum value.
    assert "Produce Equipment Spares Kits" in labels
    assert "Produce Consumer Goods" in labels
    assert all(entry["max_qty"] > 0 for entry in menu)


def test_menu_keys_roundtrip_to_production_options(manufacturer, normal_event):
    _stock_manufacturer(manufacturer)
    engine = ProductionEngine()
    menu = engine.produce_menu_options(manufacturer, normal_event, season_name="Spring")
    options = engine.production_options(manufacturer, normal_event, season_name="Spring")

    option_keys = {engine.produce_option_key(o) for o in options}
    menu_keys = {entry["key"] for entry in menu}
    # Every button maps to exactly one production option and vice-versa.
    assert menu_keys == option_keys
    # Each key resolves to a single option (no collisions).
    assert len(option_keys) == len(options)


def _adapter_returning(response, capture):
    adapter = WebSocketIOAdapter("game", lambda *a, **k: None, {})

    def fake_send_and_wait(msg, timeout=None):
        capture["msg"] = msg
        return response

    adapter._send_and_wait = fake_send_and_wait
    return adapter


def test_produce_button_click_roundtrips_to_produce_action(manufacturer):
    key = "Manufacturer|Spares|Spares"
    capture = {}
    adapter = _adapter_returning(f"produce::{key}", capture)
    adapter.set_produce_options(
        manufacturer.player_id,
        [{"key": key, "label": "Produce Equipment Spares Kits", "max_qty": 4}],
    )

    action = adapter.choose_action(manufacturer, [TurnAction.PRODUCE, TurnAction.END_TURN])

    assert action == TurnAction.PRODUCE
    # The chosen product is stashed for _action_produce, then cleared.
    assert adapter.take_produce_choice(manufacturer.player_id) == key
    assert adapter.take_produce_choice(manufacturer.player_id) is None

    values = [o["value"] for o in capture["msg"]["options"]]
    assert f"produce::{key}" in values
    assert "produce" not in values  # fanned out — no bare Produce button
    labels = [o["label"] for o in capture["msg"]["options"]]
    assert "Produce Equipment Spares Kits" in labels


def test_produce_falls_back_to_bare_button_without_options(manufacturer):
    capture = {}
    adapter = _adapter_returning("end_turn", capture)
    # No set_produce_options → the plain Produce button (server picker) remains.

    action = adapter.choose_action(manufacturer, [TurnAction.PRODUCE, TurnAction.END_TURN])

    assert action == TurnAction.END_TURN
    values = [o["value"] for o in capture["msg"]["options"]]
    assert "produce" in values
    assert not any(v.startswith("produce::") for v in values)


def test_produce_button_context_shows_recipe_runs_and_price(manufacturer, normal_event):
    _stock_manufacturer(manufacturer)  # Metal 40, Oil 40 on hand
    engine = ProductionEngine()
    prices = {ResourceType.SPARES: 12.0}
    menu = engine.produce_menu_options(
        manufacturer, normal_event, season_name="Spring", prices=prices
    )
    spares = next(e for e in menu if e["label"] == "Produce Equipment Spares Kits")
    ctx = spares["context"]
    assert "2 Metal + 1 Oil" in ctx           # recipe inputs
    assert "→ 4 Spares" in ctx           # → per-run output
    assert "20 runs from stock" in ctx        # min(40//2, 40//1)
    assert "12 Dp each" in ctx                # market price

    # camelCase resource values are spaced out in the sub-line.
    machinery = next(e for e in menu if e["label"] == "Produce Tractors & Farm Machinery")
    assert "Farm Machinery" in machinery["context"]
    assert "FarmMachinery" not in machinery["context"]


def test_choose_quantity_prefill_is_clamped_and_sent(manufacturer):
    capture = {}
    adapter = _adapter_returning("5", capture)
    # default above max should be clamped to max in the payload.
    result = adapter.choose_quantity("How many?", 1, 10, default=25)
    assert result == 5                        # client's typed value wins
    assert capture["msg"]["prefill"] == 10    # prefill clamped to max
    # No default → no prefill key at all.
    capture.clear()
    adapter2 = _adapter_returning("3", capture)
    adapter2.choose_quantity("How many?", 1, 10)
    assert "prefill" not in capture["msg"]
