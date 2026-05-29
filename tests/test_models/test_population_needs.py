"""Sustenance basket model tests (2026-05-25 redesign).

Replaces the legacy ``population_food_fish_needs`` tests. The new model:

- Every resident counts toward demand (no ``BASE_POPULATION_SELF_FED``).
- Each ``PEOPLE_PER_MEAL`` residents need 1 meal/season.
- A meal = 1 Food OR (1 Grain + 1 Produce + 1 (Fish or Meat)).
- Cross-substitution between raw ingredients at 2:1 (2 surplus units →
  1 missing slot fill).
- Food is consumed FIRST when both Food and raw are available.
"""
from island_traders.constants import PEOPLE_PER_MEAL
from island_traders.models.player import Player, _allocate_raw_meals
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


# ---------------------------------------------------------------------------
# meals_needed
# ---------------------------------------------------------------------------

def test_meals_needed_one_per_ten_residents():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=100)
    assert p.meals_needed() == 100 // PEOPLE_PER_MEAL  # 10

def test_meals_needed_rounds_up_partial_groups():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=23)
    assert p.meals_needed() == 3   # ceil(23/10)

def test_meals_needed_zero_population_is_zero():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=0)
    assert p.meals_needed() == 0

def test_extra_residents_add_meal_demand():
    """Visiting trainees on a campus add transient mouths without
    mutating resident population."""
    p = Player(1, "X", [ROLES["Educator"]], 0.0, population=80)
    base = p.meals_needed()
    with_visitors = p.meals_needed(extra_residents=20)
    assert with_visitors == base + 2   # +20 residents → +2 meals
    assert p.population == 80


# ---------------------------------------------------------------------------
# _allocate_raw_meals — pure helper, edge cases
# ---------------------------------------------------------------------------

def test_allocate_zero_meals_returns_nothing():
    meals, used = _allocate_raw_meals(0, 5, 5, 5, 5)
    assert meals == 0
    assert all(v == 0 for v in used.values())

def test_allocate_native_only_fills_one_meal():
    meals, used = _allocate_raw_meals(1, 1, 1, 1, 0)
    assert meals == 1
    assert used[ResourceType.GRAIN] == 1
    assert used[ResourceType.PRODUCE] == 1
    assert used[ResourceType.FISH] == 1
    assert used[ResourceType.MEAT] == 0

def test_allocate_users_example_3_grain_0_produce_1_fish_makes_1_meal():
    """The example from the spec: 3 grain + 0 produce + 1 fish satisfies
    1 meal — 1 grain native + 1 fish native + 2 grain substituting for
    1 produce slot at 2:1."""
    meals, used = _allocate_raw_meals(1, 3, 0, 1, 0)
    assert meals == 1
    # All 3 grain are consumed (1 native + 2 sub for produce).
    assert used[ResourceType.GRAIN] == 3
    assert used[ResourceType.PRODUCE] == 0
    assert used[ResourceType.FISH] == 1
    assert used[ResourceType.MEAT] == 0

def test_allocate_4_grain_alone_cannot_make_even_1_meal():
    """1 meal would need 1 grain native + 2 sub for produce + 2 sub for
    protein = 5 grain. Only 4 grain available → 0 meals."""
    meals, used = _allocate_raw_meals(1, 4, 0, 0, 0)
    assert meals == 0
    assert all(v == 0 for v in used.values())

def test_allocate_5_grain_alone_makes_exactly_1_meal():
    meals, used = _allocate_raw_meals(1, 5, 0, 0, 0)
    assert meals == 1
    assert used[ResourceType.GRAIN] == 5

def test_allocate_fish_meat_fungible_for_protein():
    """Protein slot accepts either fish or meat 1:1 (not 2:1)."""
    meals, used = _allocate_raw_meals(2, 2, 2, 1, 1)
    assert meals == 2
    assert used[ResourceType.FISH] + used[ResourceType.MEAT] == 2

def test_allocate_partial_when_inventory_short():
    """1 grain + 1 produce + 1 fish = 1 meal; remaining 2 meals worth
    needs 2g+2p+2protein = 6 native units but we have 0 → 1 meal only."""
    meals, _ = _allocate_raw_meals(3, 1, 1, 1, 0)
    assert meals == 1

def test_allocate_meal_target_caps_native_use():
    """Surplus inventory beyond what's needed for `meals_needed` meals
    doesn't get over-consumed."""
    meals, used = _allocate_raw_meals(1, 10, 10, 10, 0)
    assert meals == 1
    # Only 1 unit of each slot type used (native, capped at meals_needed).
    assert used[ResourceType.GRAIN] == 1
    assert used[ResourceType.PRODUCE] == 1
    assert used[ResourceType.FISH] == 1


# ---------------------------------------------------------------------------
# consume_sustenance — Food-first + raw + substitution end-to-end
# ---------------------------------------------------------------------------

def test_consume_eats_food_first():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=20)  # 2 meals
    p.inventory = p.inventory.add(ResourceType.FOOD, 5)
    p.inventory = p.inventory.add(ResourceType.GRAIN, 5)
    p.inventory = p.inventory.add(ResourceType.PRODUCE, 5)
    p.inventory = p.inventory.add(ResourceType.FISH, 5)

    satisfied, used, shortfall = p.consume_sustenance(2)

    assert satisfied == 2
    assert shortfall == 0
    assert used[ResourceType.FOOD] == 2
    # Raw untouched because Food covered both meals.
    assert used[ResourceType.GRAIN] == 0
    assert used[ResourceType.PRODUCE] == 0
    assert used[ResourceType.FISH] == 0
    # Inventory reflects deduction.
    assert p.inventory.get(ResourceType.FOOD) == 3
    assert p.inventory.get(ResourceType.GRAIN) == 5

def test_consume_falls_back_to_raw_when_food_runs_out():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=30)  # 3 meals
    p.inventory = p.inventory.add(ResourceType.FOOD, 1)
    p.inventory = p.inventory.add(ResourceType.GRAIN, 5)
    p.inventory = p.inventory.add(ResourceType.PRODUCE, 5)
    p.inventory = p.inventory.add(ResourceType.MEAT, 5)

    satisfied, used, shortfall = p.consume_sustenance(3)

    assert satisfied == 3
    assert shortfall == 0
    assert used[ResourceType.FOOD] == 1
    # 2 raw meals consumed natively.
    assert used[ResourceType.GRAIN] == 2
    assert used[ResourceType.PRODUCE] == 2
    assert used[ResourceType.FISH] + used[ResourceType.MEAT] == 2

def test_consume_reports_shortfall_when_inventory_insufficient():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=30)  # 3 meals
    # Only 1 meal of food, 1 meal of native raw.
    p.inventory = p.inventory.add(ResourceType.FOOD, 1)
    p.inventory = p.inventory.add(ResourceType.GRAIN, 1)
    p.inventory = p.inventory.add(ResourceType.PRODUCE, 1)
    p.inventory = p.inventory.add(ResourceType.FISH, 1)

    satisfied, _used, shortfall = p.consume_sustenance(3)

    assert satisfied == 2
    assert shortfall == 1

def test_consume_zero_meals_is_noop():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=0)
    satisfied, used, shortfall = p.consume_sustenance(0)
    assert satisfied == 0
    assert shortfall == 0
    assert all(v == 0 for v in used.values())


# ---------------------------------------------------------------------------
# meals_available — sustenance runway peek
# ---------------------------------------------------------------------------

def test_meals_available_counts_food_plus_raw_basket():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=0)
    p.inventory = p.inventory.add(ResourceType.FOOD, 3)
    p.inventory = p.inventory.add(ResourceType.GRAIN, 2)
    p.inventory = p.inventory.add(ResourceType.PRODUCE, 2)
    p.inventory = p.inventory.add(ResourceType.FISH, 2)
    # 3 food + 2 raw meals = 5 meal capacity.
    assert p.meals_available() == 5

def test_meals_available_does_not_mutate_inventory():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=0)
    p.inventory = p.inventory.add(ResourceType.FOOD, 2)
    p.inventory = p.inventory.add(ResourceType.GRAIN, 2)
    before = (
        p.inventory.get(ResourceType.FOOD), p.inventory.get(ResourceType.GRAIN),
    )
    p.meals_available()
    after = (
        p.inventory.get(ResourceType.FOOD), p.inventory.get(ResourceType.GRAIN),
    )
    assert before == after


# ---------------------------------------------------------------------------
# sustenance_shortfall_demand — market basket signal
# ---------------------------------------------------------------------------

def test_shortfall_demand_empty_when_inventory_covers_meals():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=20)  # 2 meals
    p.inventory = p.inventory.add(ResourceType.FOOD, 5)
    assert p.sustenance_shortfall_demand() == {}

def test_shortfall_demand_posts_basket_at_shortfall_level():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=30)  # 3 meals
    # No inventory at all — every meal short.
    basket = p.sustenance_shortfall_demand()
    # All 5 components advertised at the shortfall level (3 meals).
    assert basket == {
        ResourceType.FOOD: 3,
        ResourceType.GRAIN: 3,
        ResourceType.PRODUCE: 3,
        ResourceType.FISH: 3,
        ResourceType.MEAT: 3,
    }

def test_shortfall_demand_reflects_partial_inventory():
    p = Player(1, "X", [ROLES["Farmer"]], 0.0, population=30)  # 3 meals
    # 1 food + 1 raw meal native = 2 satisfied, 1 short.
    p.inventory = p.inventory.add(ResourceType.FOOD, 1)
    p.inventory = p.inventory.add(ResourceType.GRAIN, 1)
    p.inventory = p.inventory.add(ResourceType.PRODUCE, 1)
    p.inventory = p.inventory.add(ResourceType.FISH, 1)
    basket = p.sustenance_shortfall_demand()
    # 1 meal short → 1 of each posted.
    assert basket[ResourceType.FOOD] == 1
    assert basket[ResourceType.GRAIN] == 1
