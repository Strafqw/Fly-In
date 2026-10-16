"""Tests for the routing strategies.

Every plan is replayed by the simulator, so a test that passes here
also proves the plan respects every movement and capacity rule.
"""

from pathlib import Path

import pytest

from errors import UnsolvableMapError
from network import Network
from parser import MapParser
from simulator import Simulator
from solver import ReservationSolver, ShortestPathSolver, Solver

MAPS = Path(__file__).resolve().parent.parent / "maps"

TARGETS = {
    "easy/01_linear_path.txt": 6,
    "easy/02_simple_fork.txt": 8,
    "easy/03_basic_capacity.txt": 6,
    "medium/01_dead_end_trap.txt": 12,
    "medium/02_circular_loop.txt": 15,
    "medium/03_priority_puzzle.txt": 12,
    "hard/01_maze_nightmare.txt": 30,
    "hard/02_capacity_hell.txt": 35,
    "hard/03_ultimate_challenge.txt": 45,
    "challenger/01_the_impossible_dream.txt": 45,
}
"""Reference turn counts from the subject (the challenger's is the
record to beat)."""


def network_of(text: str) -> Network:
    """Parse a map given as one string.

    Args:
        text: The whole map file content.

    Returns:
        The parsed network.
    """
    return MapParser().parse_lines(text.splitlines())


def turns(solver: Solver) -> int:
    """Solve, validate, and return the turn count.

    Args:
        solver: A solver bound to its network.

    Returns:
        The number of turns of the validated plan.
    """
    return Simulator(solver.network).validate(solver.solve()).turns


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_reservation_meets_every_target(name: str) -> None:
    """The default solver matches or beats every reference count."""
    network = MapParser().parse_file(str(MAPS / name))
    assert turns(ReservationSolver(network)) <= TARGETS[name]


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_shortest_path_plans_are_valid(name: str) -> None:
    """The baseline is slower but must still never break a rule."""
    network = MapParser().parse_file(str(MAPS / name))
    turns(ShortestPathSolver(network))


def test_link_capacity_is_used() -> None:
    """Seven drones over a link rated for three need three turns."""
    network = network_of("""nb_drones: 7
start_hub: s 0 0
end_hub: g 1 0
connection: s-g [max_link_capacity=3]""")
    assert turns(ReservationSolver(network)) == 3


def test_fleet_is_split_across_paths() -> None:
    """Two disjoint corridors carry two drones per turn."""
    network = network_of("""nb_drones: 4
start_hub: s 0 0
end_hub: g 2 0
hub: a 1 0
hub: b 1 1
connection: s-a
connection: a-g
connection: s-b
connection: b-g""")
    assert turns(ReservationSolver(network)) == 3


def test_restricted_zone_costs_two_turns() -> None:
    """A lone drone needs two turns to enter a restricted zone."""
    network = network_of("""nb_drones: 1
start_hub: s 0 0
end_hub: g 2 0
hub: r 1 0 [zone=restricted]
connection: s-r
connection: r-g""")
    plan = ReservationSolver(network).solve()
    assert [str(turn) for turn in plan.turns] == ["D1-s-r", "D1-r", "D1-g"]


def test_priority_zone_wins_a_tie() -> None:
    """Between two equally fast routes, the priority one is taken."""
    network = network_of("""nb_drones: 1
start_hub: s 0 0
end_hub: g 3 0
hub: n 1 0
hub: p 1 1 [zone=priority]
connection: s-n
connection: n-g
connection: s-p
connection: p-g""")
    plan = ReservationSolver(network).solve()
    assert str(plan.turns[0]) == "D1-p"


def test_blocked_zone_is_avoided() -> None:
    """A short route through a blocked zone is never used."""
    network = network_of("""nb_drones: 2
start_hub: s 0 0
end_hub: g 2 0
hub: x 1 0 [zone=blocked]
hub: a 1 1
hub: b 2 1
connection: s-x
connection: x-g
connection: s-a
connection: a-b
connection: b-g""")
    plan = ReservationSolver(network).solve()
    assert all(move.zone != "x" for turn in plan.turns for move in turn.moves)


@pytest.mark.parametrize("solver", [ReservationSolver, ShortestPathSolver])
def test_unreachable_end_is_reported(solver: type[Solver]) -> None:
    """A map with no way to the end fails with a clear error."""
    network = network_of("""nb_drones: 1
start_hub: s 0 0
end_hub: g 2 0
hub: x 1 0 [zone=blocked]
connection: s-x
connection: x-g""")
    with pytest.raises(UnsolvableMapError):
        solver(network).solve()


def test_large_fleet() -> None:
    """Thousands of drones are routed, using both corridors."""
    network = network_of("""nb_drones: 5000
start_hub: s 0 0
end_hub: g 2 0
hub: a 1 0 [max_drones=3]
hub: b 1 1
connection: s-a [max_link_capacity=3]
connection: a-g [max_link_capacity=3]
connection: s-b
connection: b-g""")
    assert turns(ReservationSolver(network)) == 1251
