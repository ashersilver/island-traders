"""GET /api/qol-guide (#227) — the QoL explanation the client renders.

Exercised through the OpenAPI schema and the backing function rather than a
TestClient, because starlette's TestClient needs httpx and the project does
not depend on it.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.engine.qol import qol_guide
from island_traders.server.app import create_app


def test_qol_guide_route_is_registered_under_reference():
    operation = create_app().openapi()["paths"]["/api/qol-guide"]["get"]

    assert "Reference" in operation["tags"]
    assert "Quality of Life" in operation["summary"]


def test_qol_guide_route_is_a_plain_get_with_no_parameters():
    """Static reference data — the client fetches it once, before joining."""
    operation = create_app().openapi()["paths"]["/api/qol-guide"]["get"]

    assert operation.get("parameters", []) == []


def test_served_payload_is_json_serialisable_and_complete():
    import json

    payload = json.loads(json.dumps(qol_guide()))

    assert [c["key"] for c in payload["components"]] == [
        "nutrition", "medical", "consumer_goods", "stability",
    ]
    assert payload["productivity"]["min_multiplier"] == 0.85
    assert payload["productivity"]["max_multiplier"] == 1.15
