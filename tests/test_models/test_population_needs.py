from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def test_population_food_need_scales_with_population():
    small = Player(1, "Small", [ROLES["Farmer"]], 100.0, population=20)
    large = Player(2, "Large", [ROLES["Farmer"]], 100.0, population=120)

    assert small.population_food_fish_needs()[ResourceType.FOOD] == 1
    assert large.population_food_fish_needs()[ResourceType.FOOD] == 3


def test_educated_workforce_increases_fish_need():
    basic = Player(1, "Basic", [ROLES["Educator"]], 100.0, population=80)
    educated = Player(2, "Educated", [ROLES["Educator"]], 100.0, population=80)
    educated.workforce.add_workers(4, training_level=1, profession=Profession.PROFESSOR.value)

    assert (
        educated.population_food_fish_needs()[ResourceType.FISH]
        > basic.population_food_fish_needs()[ResourceType.FISH]
    )
