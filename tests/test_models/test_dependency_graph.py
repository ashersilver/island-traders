from __future__ import annotations

from island_traders.dependency_graph import build_dependency_graph


def _needs(graph, role):
    return {n["resource"]: n for n in graph["needs"] if n["role"] == role}


def test_producers_are_derived_from_the_recipe_table():
    graph = build_dependency_graph()
    producers = graph["producers"]
    assert producers["Freight"] == ["Transporter"]
    assert producers["Oil"] == ["Miner"]
    assert producers["Spares"] == ["Manufacturer"]
    # Reagents moved from the Manufacturer to the Doctor; the hand-written
    # role table still says otherwise, which is why we derive instead.
    assert producers["Reagents"] == ["Doctor"]


def test_every_island_depends_on_freight_and_the_other_universals():
    """The old hand-written map showed no Freight at all, yet every island
    burns it on trades and on equipment repairs."""
    graph = build_dependency_graph()
    for role in graph["roles"]:
        needs = _needs(graph, role)
        for resource in ("Freight", "Oil", "Food", "Expertise", "Spares"):
            assert resource in needs, f"{role} should depend on {resource}"
            assert needs[resource]["universal"] is True


def test_farmer_shows_the_dependencies_that_were_missing():
    graph = build_dependency_graph()
    needs = _needs(graph, "Farmer")
    # Reported gaps: Agriculture needing Freight / PassengerSeats / Oil.
    for resource in ("Freight", "PassengerSeats", "Oil"):
        assert resource in needs
        assert "Transporter" in needs[resource]["from_roles"] or resource == "Oil"
    assert needs["Oil"]["from_roles"] == ["Miner"]


def test_recipe_and_universal_flags_are_independent():
    """Oil is both a Farmer recipe input and a universal energy need; the
    overview filters on `recipe`, so one flag must not mask the other."""
    graph = build_dependency_graph()
    oil = _needs(graph, "Farmer")["Oil"]
    assert oil["recipe"] is True
    assert oil["universal"] is True
    courses = _needs(graph, "Farmer")["Courses"]
    assert courses["recipe"] is False and courses["universal"] is True


def test_capital_layer_maps_each_role_to_its_manufactured_input():
    graph = build_dependency_graph()
    capital = {
        n["role"]: n["resource"]
        for n in graph["needs"] if n["layer"] == "capital"
    }
    assert capital == {
        "Farmer": "FarmMachinery",
        "Miner": "MiningEquipment",
        "Transporter": "TransportEquipment",
        "Educator": "Reagents",
        "Banker": "Reagents",
        "Manufacturer": "TransportEquipment",
        "Doctor": "MedicalDevices",
    }


def test_spares_are_a_consumable_not_a_capital_dependency():
    graph = build_dependency_graph()
    spares = [n for n in graph["needs"] if n["resource"] == "Spares"]
    assert spares and all(n["layer"] == "consumable" for n in spares)


def test_every_need_names_a_reason_and_a_source():
    graph = build_dependency_graph()
    for n in graph["needs"]:
        assert n["reasons"], f"{n['role']}/{n['resource']} has no reason"
        assert n["layer"] in ("consumable", "capital")
        assert isinstance(n["from_roles"], list)
