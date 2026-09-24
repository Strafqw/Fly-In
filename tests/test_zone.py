"""Unit tests for the zone model."""


import pytest
from zone import ZoneType, Zone, UNLIMITED


def test_restricted_costs_two_turns() -> None:
    """A restricted zone takes two turns to enter."""
    assert ZoneType.RESTRICTED.entry_cost == 2


def test_blocked_zone_refuses_to_give_a_cost() -> None:
    """Asking a blocked zone for its cost is a caller bug."""
    with pytest.raises(ValueError):
        ZoneType.BLOCKED.entry_cost


def test_normal_and_priority_cost_one_turn() -> None:
    """Priority zones are preferred, not cheaper."""
    assert ZoneType.NORMAL.entry_cost == 1
    assert ZoneType.PRIORITY.entry_cost == 1


def test_blocked_zone_is_not_passable() -> None:
    assert not ZoneType.BLOCKED.is_passable


def test_start_hub_ignores_declared_capacity() -> None:
    """max_drones is ignored on the start hub, per the subject."""
    zone = Zone("start", 0, 0, max_drones=3, is_start=True)
    assert zone.capacity == UNLIMITED


def test_ordinary_zone_reports_declared_capacity() -> None:
    zone = Zone("hub1", 1, 0, max_drones=2)
    assert zone.capacity == 2
