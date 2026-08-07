"""Role display naming (#26).

The Medical island is presented as "Medical & Laboratory" now that it runs
the archipelago's assay lab alongside the clinic.  The rename is display-only:
the engine key stays `"Doctor"` so saved games and the JSON wire format are
unchanged.
"""
from __future__ import annotations

from island_traders.models.role import ROLES, ROLE_DISPLAY_NAMES


def test_medical_island_is_renamed_at_the_display_layer():
    role = ROLES["Doctor"]

    assert role.display_name == "Medical & Laboratory"
    assert role.short_name == "Medical & Laboratory"
    assert role.island == "Medical & Laboratory Island"
    assert ROLE_DISPLAY_NAMES["Doctor"] == "Medical & Laboratory"


def test_medical_island_keeps_its_engine_key():
    """Saved games and the wire format key on `name`, which must not move."""
    assert ROLES["Doctor"].name == "Doctor"
    assert "Doctor" in ROLES


def test_no_role_still_advertises_the_old_healthcare_label():
    for key, role in ROLES.items():
        for field in (role.display_name, role.short_name, role.island):
            assert "Healthcare" not in field, f"{key} still says Healthcare: {field}"
