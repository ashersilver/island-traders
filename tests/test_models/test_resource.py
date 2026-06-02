import pytest
from island_traders.models.resource import ResourceType, ResourceBundle, InsufficientResourceError


def test_bundle_get_missing_returns_zero():
    b = ResourceBundle()
    assert b.get(ResourceType.FOOD) == 0


def test_bundle_add_returns_new_bundle():
    b = ResourceBundle()
    b2 = b.add(ResourceType.FOOD, 5)
    assert b.get(ResourceType.FOOD) == 0   # original unchanged
    assert b2.get(ResourceType.FOOD) == 5


def test_bundle_add_accumulates():
    b = ResourceBundle()
    b = b.add(ResourceType.OIL, 3).add(ResourceType.OIL, 2)
    assert b.get(ResourceType.OIL) == 5


def test_bundle_subtract_reduces():
    b = ResourceBundle({ResourceType.ORE: 10})
    b2 = b.subtract(ResourceType.ORE, 4)
    assert b2.get(ResourceType.ORE) == 6


def test_bundle_subtract_raises_when_insufficient():
    b = ResourceBundle({ResourceType.ORE: 2})
    with pytest.raises(InsufficientResourceError):
        b.subtract(ResourceType.ORE, 5)


def test_bundle_can_satisfy_true():
    b = ResourceBundle({ResourceType.REAGENTS: 3, ResourceType.OIL: 2})
    assert b.can_satisfy({ResourceType.REAGENTS: 1, ResourceType.OIL: 2})


def test_bundle_can_satisfy_false():
    b = ResourceBundle({ResourceType.REAGENTS: 1})
    assert not b.can_satisfy({ResourceType.REAGENTS: 2})


def test_bundle_total_value():
    b = ResourceBundle({ResourceType.FOOD: 2, ResourceType.OIL: 1})
    prices = {ResourceType.FOOD: 10.0, ResourceType.OIL: 20.0}
    assert b.total_value(prices) == 40.0


def test_bundle_add_operator():
    b1 = ResourceBundle({ResourceType.FOOD: 3})
    b2 = ResourceBundle({ResourceType.FOOD: 2, ResourceType.FISH: 5})
    result = b1 + b2
    assert result.get(ResourceType.FOOD) == 5
    assert result.get(ResourceType.FISH) == 5
