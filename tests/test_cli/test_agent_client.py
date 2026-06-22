from __future__ import annotations

from island_traders.cli.agent_client import (
    DEFAULT_SERVER,
    _option_value,
    normalise_http_base,
    render_game_state,
    websocket_url,
)


def test_normalise_http_base_defaults_and_accepts_bare_host():
    assert normalise_http_base("") == DEFAULT_SERVER
    assert normalise_http_base("127.0.0.1:8001") == "http://127.0.0.1:8001"
    assert normalise_http_base("https://example.com/game/") == "https://example.com/game"


def test_websocket_url_uses_matching_scheme_and_path_prefix():
    assert (
        websocket_url("http://127.0.0.1:8001", "room-1", "player-1")
        == "ws://127.0.0.1:8001/ws/room-1/player-1"
    )
    assert (
        websocket_url("https://example.com/islands", "room-1", "player-1")
        == "wss://example.com/islands/ws/room-1/player-1"
    )


def test_option_value_accepts_number_exact_value_or_label():
    options = [
        {"value": "produce", "label": "Produce"},
        {"value": "end_turn", "label": "Done Trading"},
    ]

    assert _option_value(options, "1") == "produce"
    assert _option_value(options, "end_turn") == "end_turn"
    assert _option_value(options, "done trading") == "end_turn"
    assert _option_value(options, "custom") == "custom"


def test_render_game_state_summarises_the_joined_player():
    msg = {
        "year": 1,
        "season": "Spring",
        "players": [
            {
                "lobby_player_id": "abc",
                "name": "GPT",
                "roles": ["Farmer"],
                "treasury": 100,
                "inventory": {"Food": 3, "Oil": 0},
            }
        ],
    }

    rendered = render_game_state(msg, "abc")

    assert "Year: 1  Season: Spring" in rendered
    assert "GPT [Farmer] treasury=100" in rendered
    assert '"Food": 3' in rendered
    assert "Oil" not in rendered
