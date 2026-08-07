"""Island map briefing wiring (#23).

Clicking an island on the in-game map opens that island's briefing with its
artwork. The map, the briefing text and the art paths all live in
`index.html`, so these are static checks over that file — enough to catch the
wiring silently breaking (a renamed role key, a missing art asset, a node that
lost its handler) without standing up a browser.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "island_traders" / "server" / "static"
INDEX = STATIC / "index.html"

ENGINE_ROLES = [
    "Farmer", "Miner", "Transporter", "Educator",
    "Banker", "Manufacturer", "Doctor",
]


@pytest.fixture(scope="module")
def markup() -> str:
    return INDEX.read_text()


def test_every_map_island_carries_an_engine_role_key(markup):
    roles = re.findall(r'\{name:\s*\'[^\']+\',\s*role:\s*\'(\w+)\'', markup)

    assert sorted(roles) == sorted(ENGINE_ROLES), (
        "island map nodes must map 1:1 onto the engine roles"
    )


def test_map_islands_open_the_briefing_on_click_and_keyboard(markup):
    assert "class=\"map-island\"" in markup
    assert "node.addEventListener('click', () => showIslandBriefing(role));" in markup
    # Keyboard parity — the map must not be mouse-only.
    assert "ev.key === 'Enter'" in markup
    assert 'tabindex="0"' in markup


def test_every_role_has_a_briefing_and_the_briefing_shows_art(markup):
    briefings = re.search(
        r"const ISLAND_BRIEFINGS = \{(.*?)\n\};", markup, re.S
    ).group(1)
    for role in ENGINE_ROLES:
        assert re.search(rf"\n  {role}: \{{", briefings), f"{role} has no briefing"

    # showIslandBriefing must render the island artwork, not just prose.
    body = re.search(r"function showIslandBriefing\(role\) \{(.*?)\n\}", markup, re.S).group(1)
    assert "ROLE_ART[role]" in body
    assert "briefing-art" in body


def test_every_role_art_asset_referenced_actually_exists(markup):
    art_block = re.search(r"const ROLE_ART = \{(.*?)\n\};", markup, re.S).group(1)
    paths = re.findall(r"'(/static/island-art/[^']+)'", art_block)

    assert len(paths) >= len(ENGINE_ROLES) * 2, "expected a day and night render per role"
    for path in paths:
        asset = STATIC / path.removeprefix("/static/")
        assert asset.is_file(), f"{path} is referenced but missing from disk"


def test_wordmark_is_bold_enough_to_read(markup):
    """#23: the top-left logo was 1rem/700 and read as thin."""
    rule = re.search(r"\.g-hdr \.title\{([^}]*)\}", markup).group(1)

    weight = int(re.search(r"font-weight:(\d+)", rule).group(1))
    size = float(re.search(r"font-size:([\d.]+)rem", rule).group(1))
    assert weight >= 800
    assert size > 1.0
    assert "text-shadow" in rule
