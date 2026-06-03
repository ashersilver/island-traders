from __future__ import annotations

from island_traders.constants import APP_VERSION
from island_traders.server.app import create_app


def test_openapi_schema_documents_room_and_agent_join_routes():
    schema = create_app().openapi()

    assert schema["info"]["title"] == "Island Traders API"
    assert schema["info"]["version"] == APP_VERSION
    assert "/ws/{room_id}/{player_id}" in schema["info"]["description"]

    paths = schema["paths"]
    assert "/api/rooms" in paths
    assert "/api/rooms/join-by-code" in paths
    assert "/api/rooms/{room_id}/state" in paths

    join = paths["/api/rooms/join-by-code"]["post"]
    assert join["summary"] == "Join or rejoin by room code"
    body_schema = join["requestBody"]["content"]["application/json"]["schema"]
    assert body_schema["$ref"].endswith("/JoinByCodeRequest")


def test_openapi_schema_has_typed_request_models_for_client_actions():
    schema = create_app().openapi()
    components = schema["components"]["schemas"]

    assert "CreateRoomRequest" in components
    assert components["CreateRoomRequest"]["properties"]["starting_capital"]["default"] == 1500.0
    assert "JoinByCodeRequest" in components
    assert set(components["JoinByCodeRequest"]["required"]) == {"code"}
    assert "AuctionBidRequest" in components
    assert set(components["AuctionBidRequest"]["required"]) == {
        "player_id",
        "role_name",
        "amount",
    }


def test_openapi_schema_groups_routes_with_swagger_tags():
    schema = create_app().openapi()
    tags = {tag["name"] for tag in schema["tags"]}
    assert {"Lobby", "Game Flow", "Reference"}.issubset(tags)

    assert schema["paths"]["/api/rooms"]["post"]["tags"] == ["Lobby"]
    assert schema["paths"]["/api/rooms/{room_id}/auction/bid"]["post"]["tags"] == [
        "Game Flow"
    ]
    assert schema["paths"]["/api/roles"]["get"]["tags"] == ["Reference"]
