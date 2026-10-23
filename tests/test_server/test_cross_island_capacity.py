"""Cross-island capital stays visible on an island tab.

Four catalogue items carry `role="Any"` (Kitchen, Industrial Kitchen, Food
Store, Laboratory Equipment) and the Kitchen's Food line is emitted as a
synthesized output row with `role="Kitchen"`. Neither is one of the seven
island roles, so a `filteredCapacity` that matched the role strictly dropped
them from the Production Capacity panel — and from the repair hints, which
iterate the same filtered `capital_owned` — on every island tab.

Client-only fix, so this follows the repo's existing pattern of static checks
over `index.html` (see `test_event_log_alerts.py`), plus a behavioural check
that runs the real function under node when node is available.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from island_traders.constants_capacity import CAPITAL_CATALOGUE, PRODUCTION_RECIPES

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "island_traders" / "server" / "static" / "index.html"
APP = ROOT / "island_traders" / "server" / "app.py"


@pytest.fixture(scope="module")
def markup() -> str:
    return INDEX.read_text()


def _cross_island_roles(markup: str) -> set[str]:
    """The pseudo-roles the client treats as belonging to every island."""
    match = re.search(r"const CROSS_ISLAND_ROLES = new Set\(\[([^\]]*)\]\)", markup)
    assert match, "CROSS_ISLAND_ROLES declaration not found"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_island_roles_are_the_seven_production_roles():
    """Guards the premise: recipe roles are exactly the island roles."""
    assert len({r.role for r in PRODUCTION_RECIPES}) == 7


def test_client_knows_every_non_island_capital_role(markup):
    """A catalogue role that isn't an island role must be cross-island.

    Add a fifth `role="Any"`-style marker to the catalogue without telling the
    client and that equipment silently vanishes from every island tab.
    """
    island_roles = {r.role for r in PRODUCTION_RECIPES}
    catalogue_roles = {item.role for item in CAPITAL_CATALOGUE}
    assert catalogue_roles - island_roles <= _cross_island_roles(markup)


def test_client_knows_the_synthesized_output_roles(markup):
    """Output rows the server labels with a non-island role, e.g. the Kitchen."""
    emitted = set(re.findall(r'"role": "(\w+)",\n\s*"is_service_output"', APP.read_text()))
    island_roles = {r.role for r in PRODUCTION_RECIPES}
    assert emitted, "expected at least one synthesized output role"
    assert emitted - island_roles <= _cross_island_roles(markup)


def test_filtered_capacity_does_not_match_the_role_strictly(markup):
    """The regression itself: a bare `o.role === role` drops cross-island rows."""
    body = markup[markup.index("function filteredCapacity") :][:600]
    assert "onThisIsland" in body
    assert "o.role === role" not in body


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_filtered_capacity_keeps_cross_island_rows(markup, tmp_path):
    """Run the real function: one island's plant, plus anything cross-island."""
    start = markup.index("function onThisIsland")
    end = markup.index("function playerRoles")
    script = tmp_path / "f.js"
    script.write_text(
        "const CROSS_ISLAND_ROLES = new Set(['Any', 'Kitchen']);\n"
        + markup[start:end]
        + """
const capacity = {
  outputs: [
    {output: 'Ore', role: 'Miner'},
    {output: 'Food', role: 'Kitchen'},
    {output: 'Finance', role: 'Banker'},
  ],
  capital_owned: [
    {item_id: 'miner.excavator', role: 'Miner'},
    {item_id: 'common.kitchen', role: 'Any'},
    {item_id: 'banker.vault', role: 'Banker'},
  ],
  capital_in_transit: [{item_id: 'common.food_store', role: 'Any'}],
  band_counts: {Manager: 1},
};
console.log(JSON.stringify({
  filtered: filteredCapacity(capacity, 'Miner'),
  consolidated: filteredCapacity(capacity, 'ALL') === capacity,
}));
"""
    )
    out = json.loads(subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True
    ).stdout)

    filtered = out["filtered"]
    # This island's own plant and output, kept.
    assert [o["output"] for o in filtered["outputs"]] == ["Ore", "Food"]
    assert [c["item_id"] for c in filtered["capital_owned"]] == [
        "miner.excavator", "common.kitchen",
    ]
    # Another island's plant and output, dropped.
    assert all(o["role"] != "Banker" for o in filtered["outputs"])
    assert all(c["role"] != "Banker" for c in filtered["capital_owned"])
    # Cross-island kit still in transit is kept too.
    assert [c["item_id"] for c in filtered["capital_in_transit"]] == [
        "common.food_store",
    ]
    # Consolidated is untouched — same object, no filtering.
    assert out["consolidated"] is True
