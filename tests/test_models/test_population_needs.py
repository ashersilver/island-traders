from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def test_population_at_self_fed_baseline_has_no_marginal_food_need():
    baseline = Player(1, "Baseline", [ROLES["Farmer"]], 100.0, population=100)

    assert baseline.population_food_fish_needs()[ResourceType.FOOD] == 0


def test_population_growth_above_baseline_adds_marginal_food_need():
    grown = Player(2, "Grown", [ROLES["Farmer"]], 100.0, population=120)

    assert grown.population_food_fish_needs()[ResourceType.FOOD] == 20


def test_extra_residents_add_transient_food_need_without_mutating_population():
    campus = Player(3, "Campus", [ROLES["Educator"]], 100.0, population=100)

    default_need = campus.population_food_fish_needs()[ResourceType.FOOD]
    with_visitors = campus.population_food_fish_needs(extra_residents=7)[ResourceType.FOOD]

    assert default_need == 0
    assert with_visitors == 7
    assert campus.population == 100


def test_educated_workforce_increases_fish_need():
    basic = Player(1, "Basic", [ROLES["Educator"]], 100.0, population=80)
    educated = Player(2, "Educated", [ROLES["Educator"]], 100.0, population=80)
    educated.workforce.add_workers(4, training_level=1, profession=Profession.PROFESSOR.value)

    assert (
        educated.population_food_fish_needs()[ResourceType.FISH]
        > basic.population_food_fish_needs()[ResourceType.FISH]
    )
