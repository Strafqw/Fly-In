"""Tests for the simulator: illegal plans must be rejected."""

import pytest

from errors import SimulationError
from network import Network
from parser import MapParser
from plan import Move, Plan, Turn
from simulator import Simulator

MAP = """nb_drones: 2
start_hub: s 0 0
end_hub: g 3 0
hub: a 1 0
hub: r 2 0 [zone=restricted]
hub: x 1 1 [zone=blocked]
connection: s-a
connection: a-r
connection: r-g
connection: s-x"""


def network() -> Network:
    """Build the small map shared by these tests.

    Returns:
        The parsed network.
    """
    return MapParser().parse_lines(MAP.splitlines())


def plan_of(*turns: list[Move]) -> Plan:
    """Build a plan from the moves of each turn.

    Args:
        turns: One list of moves per turn, in order.

    Returns:
        The plan.
    """
    return Plan(tuple(
        Turn(index, tuple(moves)) for index, moves in enumerate(turns, 1)
    ))


def test_valid_plan_is_accepted() -> None:
    """Two drones walking the corridor one turn apart is legal."""
    metrics = Simulator(network()).validate(plan_of(
        [Move(1, "a")],
        [Move(1, "r", "a-r"), Move(2, "a")],
        [Move(1, "r")],
        [Move(1, "g"), Move(2, "r", "a-r")],
        [Move(2, "r")],
        [Move(2, "g")],
    ))
    assert metrics.turns == 6
    assert metrics.turns_per_drone == 5.0


@pytest.mark.parametrize(
    ("turns", "cause"),
    [
        ([[Move(1, "a"), Move(2, "a")]], "holds 2 drones"),
        ([[Move(1, "x")]], "blocked"),
        ([[Move(1, "g")]], "not connected"),
        ([[Move(1, "a")], [Move(1, "r")]], "in one turn"),
        ([[Move(1, "a")], [Move(1, "r", "a-r")], []], "lingered"),
        ([[Move(1, "a")], [Move(1, "r", "a-r")], [Move(1, "a")]],
         "landed at"),
        ([[Move(1, "a"), Move(1, "a")]], "moves twice"),
        ([[Move(3, "a")]], "unknown drone"),
        ([[Move(1, "a")]], "never delivered"),
    ],
)
def test_illegal_plans_are_rejected(
    turns: list[list[Move]], cause: str
) -> None:
    """Each rule of the subject is enforced by the simulator."""
    with pytest.raises(SimulationError, match=cause):
        Simulator(network()).validate(plan_of(*turns))


def test_restricted_link_is_held_for_both_turns() -> None:
    """A second drone cannot use a link still carrying a crossing."""
    plan = plan_of(
        [Move(1, "a")],
        [Move(1, "r", "a-r"), Move(2, "a")],
        [Move(1, "r"), Move(2, "r", "a-r")],
    )
    with pytest.raises(SimulationError, match="carries 2 drones"):
        Simulator(network()).validate(plan)
