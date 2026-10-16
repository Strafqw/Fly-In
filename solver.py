"""Routing strategies: turn a network into a plan for the whole fleet."""

import heapq
import itertools
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from connection import Connection
from errors import UnsolvableMapError
from network import Network
from plan import Move, Plan, Turn
from zone import UNLIMITED, Zone


class Solver(ABC):
    """Common interface shared by every routing strategy."""

    def __init__(self, network: Network) -> None:
        """Bind the solver to the network it will route through.

        Args:
            network: The parsed and validated map.
        """
        self.network = network

    @property
    @abstractmethod
    def name(self) -> str:
        """Short human readable label, shown by ``--stats``."""

    @abstractmethod
    def solve(self) -> Plan:
        """Compute a routing plan for the whole fleet.

        Returns:
            A plan moving every drone from the start to the end hub.

        Raises:
            UnsolvableMapError: If the end hub is unreachable.
        """

    @staticmethod
    def _build_plan(by_turn: dict[int, list[Move]]) -> Plan:
        """Assemble per turn moves into a plan with no gaps.

        Args:
            by_turn: Moves keyed by their 1-based turn number.

        Returns:
            The plan, with an empty turn wherever nobody moves.
        """
        last = max(by_turn, default=0)
        return Plan(tuple(
            Turn(index, tuple(sorted(
                by_turn.get(index, []), key=lambda move: move.drone_id
            )))
            for index in range(1, last + 1)
        ))


class ShortestPathSolver(Solver):
    """Baseline: one cost-minimal route, drones queued behind
    each other. Ignores every other path on the map.

    Kept as a reference point for ``--solver shortest``; the default
    strategy is :class:`ReservationSolver`.
    """

    @property
    def name(self) -> str:
        """Label of this strategy."""
        return "shortest-path"

    def solve(self) -> Plan:
        """Route the fleet along one cost-minimal path.

        Returns:
            The resulting plan.

        Raises:
            UnsolvableMapError: If the end hub is unreachable.
        """
        return self._schedule(self._find_path())

    def _find_path(self) -> list[str]:
        """Find one cost-minimal route from the start hub to the end.

        Runs Dijkstra's algorithm weighted by each zone's entry cost,
        so a restricted zone counts as two turns rather than one.
        Blocked zones are never expanded.

        The search key is ``(cost, -priority_zones_seen)``. Tuples
        compare left to right, so cost still decides the route; the
        second term only breaks ties. That is how the subject's
        "priority zones should be prioritized" is honoured without
        making them cheaper, which would break the integer turn model.

        Returns:
            The zone names from start to end, inclusive.

        Raises:
            UnsolvableMapError: If the end hub cannot be reached.
        """
        start = self.network.start.name
        end = self.network.end.name

        distance: dict[str, tuple[int, int]] = {start: (0, 0)}
        came: dict[str, str] = {}
        done: set[str] = set()
        queue: list[tuple[int, int, str]] = [(0, 0, start)]

        while queue:
            cost, seen_priority, here = heapq.heappop(queue)
            if here in done:
                continue
            done.add(here)
            if here == end:
                break

            for link in self.network.neighbours(here):
                there = self.network.zone(link.other(here))
                if not there.is_passable or there.name in done:
                    continue
                bonus = -1 if there.zone_type.is_preferred else 0
                key = (cost + there.entry_cost, seen_priority + bonus)
                if there.name not in distance or key < distance[there.name]:
                    distance[there.name] = key
                    came[there.name] = here
                    heapq.heappush(queue, (key[0], key[1], there.name))

        if end not in done:
            raise UnsolvableMapError(f"no route from {start!r} to {end!r}")

        path = [end]
        while path[-1] != start:
            path.append(came[path[-1]])
        path.reverse()
        return path

    def _schedule(self, path: list[str]) -> Plan:
        """Put the whole fleet onto one route, one drone per turn.

        Drones are released at a fixed interval and each walks the
        whole path. A restricted zone costs two turns: the drone spends
        the first on the connection and lands on the second.

        Args:
            path: The zone names from start to end, inclusive.

        Returns:
            The resulting plan.

        Raises:
            UnsolvableMapError: If two consecutive zones on the path
                are not actually linked.
        """
        gap = 2 if self._has_restricted(path) else 1
        by_turn: dict[int, list[Move]] = {}

        for drone_id in range(1, self.network.nb_drones + 1):
            turn = (drone_id - 1) * gap + 1

            for step in range(1, len(path)):
                here = path[step - 1]
                dest = self.network.zone(path[step])

                if dest.entry_cost == 2:
                    link = self.network.link_between(here, dest.name)
                    if link is None:
                        raise UnsolvableMapError(
                            f"no link between {here!r} and {dest.name!r}"
                        )
                    move = Move(drone_id, dest.name, link.name)
                    by_turn.setdefault(turn, []).append(move)
                    turn += 1

                by_turn.setdefault(turn, []).append(
                    Move(drone_id, dest.name)
                )
                turn += 1

        return self._build_plan(by_turn)

    def _has_restricted(self, path: list[str]) -> bool:
        """Whether any zone on the path costs more than one turn.

        Args:
            path: The zone names from start to end, inclusive.

        Returns:
            True if a restricted zone lies on the route.
        """
        return any(
            self.network.zone(name).entry_cost > 1 for name in path[1:]
        )


State = tuple[str, int]
"""A drone's situation at the end of a turn: (zone name, turn)."""


@dataclass(frozen=True)
class Step:
    """One hop of a planned route.

    Attributes:
        depart: Turn at whose end the drone still stands in the origin
            zone; it moves during turn ``depart + 1``.
        link: The connection crossed.
        dest: The zone entered.
    """

    depart: int
    link: Connection
    dest: Zone

    @property
    def arrive(self) -> int:
        """Turn at whose end the drone stands in ``dest``."""
        return self.depart + self.dest.entry_cost


class ReservationSolver(Solver):
    """Plan drones one at a time through space *and* time.

    Every drone gets the earliest arriving route that fits around the
    drones planned before it. Their positions are kept in reservation
    tables - how many drones sit in each zone, and cross each link, on
    each turn - and a drone may only use what is left.

    The search runs over ``(zone, turn)`` states, so waiting is just
    another move. That gives the subject's requirements for free:

    * **several paths** - once the short route is booked, the next
      drone's earliest arrival goes another way;
    * **capacities** - ``max_drones`` and ``max_link_capacity`` are the
      reservation limits, so wide zones take several drones at once;
    * **strategic waiting** - a drone may hold in a zone, or at the
      start, until a slot frees up;
    * **no conflicts or deadlocks** - a drone never plans into a slot
      someone else holds, and the start hub has unlimited room, so a
      drone can always wait there until the network clears.

    The search is A* with the static cost-to-end as heuristic. That
    cost never overestimates, so the first time the end hub is popped
    is the earliest possible arrival for this drone. Ties are broken in
    favour of routes through more priority zones.
    """

    @property
    def name(self) -> str:
        """Label of this strategy."""
        return "reservation"

    def solve(self) -> Plan:
        """Plan every drone in turn and merge their moves.

        Returns:
            The resulting plan.

        Raises:
            UnsolvableMapError: If the end hub is unreachable.
        """
        self._cost_to_end = self._static_costs()
        start = self.network.start.name
        if start not in self._cost_to_end:
            raise UnsolvableMapError(
                f"no route from {start!r} to {self.network.end.name!r}"
            )

        self._zone_use: Counter[State] = Counter()
        self._link_use: Counter[tuple[tuple[str, str], int]] = Counter()
        self._floor = 0

        by_turn: dict[int, list[Move]] = {}
        for drone_id in range(1, self.network.nb_drones + 1):
            states, steps = self._route()
            self._reserve(states, steps)
            for step in steps:
                if step.dest.entry_cost == 2:
                    by_turn.setdefault(step.depart + 1, []).append(
                        Move(drone_id, step.dest.name, step.link.name)
                    )
                by_turn.setdefault(step.arrive, []).append(
                    Move(drone_id, step.dest.name)
                )
        return self._build_plan(by_turn)

    # -- static information ---------------------------------------------

    def _static_costs(self) -> dict[str, int]:
        """Cheapest cost from every zone to the end, ignoring traffic.

        A reverse Dijkstra from the end hub. Zones missing from the
        result cannot reach the end at all, so the search never enters
        them - dead ends are pruned before any drone is planned.

        Returns:
            Turns needed to reach the end, keyed by zone name.
        """
        end = self.network.end
        if not end.is_passable:
            return {}
        cost: dict[str, int] = {end.name: 0}
        queue: list[tuple[int, str]] = [(0, end.name)]
        while queue:
            here_cost, here = heapq.heappop(queue)
            if here_cost > cost[here]:
                continue
            entry = self.network.zone(here).entry_cost
            for link in self.network.neighbours(here):
                there = self.network.zone(link.other(here))
                if not there.is_passable:
                    continue
                candidate = here_cost + entry
                if candidate < cost.get(there.name, candidate + 1):
                    cost[there.name] = candidate
                    heapq.heappush(queue, (candidate, there.name))
        return cost

    # -- reservation tables ---------------------------------------------

    def _has_room(self, zone: Zone, turn: int) -> bool:
        """Whether one more drone may stand in a zone at a turn's end.

        Args:
            zone: The zone to check.
            turn: The turn number.

        Returns:
            True if the zone is below its capacity.
        """
        if zone.capacity == UNLIMITED:
            return True
        return self._zone_use[(zone.name, turn)] < zone.capacity

    def _can_cross(self, link: Connection, dest: Zone, depart: int) -> bool:
        """Whether a drone may leave along a link after turn ``depart``.

        The link must have room on every turn of the crossing (two for
        a restricted zone), and the destination must have room on
        arrival, since a drone may never wait on a connection.

        Args:
            link: The connection to cross.
            dest: The zone at its far end.
            depart: The last turn spent in the origin zone.

        Returns:
            True if the crossing fits the reservation tables.
        """
        for turn in range(depart + 1, depart + dest.entry_cost + 1):
            if self._link_use[(link.key, turn)] >= link.max_link_capacity:
                return False
        return self._has_room(dest, depart + dest.entry_cost)

    def _can_leave_start(self, turn: int) -> bool:
        """Whether any drone could leave the start hub after ``turn``.

        Args:
            turn: The last turn spent at the start.

        Returns:
            True if at least one outgoing link is usable.
        """
        start = self.network.start.name
        for link in self.network.neighbours(start):
            dest = self.network.zone(link.other(start))
            if dest.name in self._cost_to_end and self._can_cross(
                link, dest, turn
            ):
                return True
        return False

    def _next_departure(self, turn: int) -> int:
        """Earliest turn from ``turn`` on when leaving the start is possible.

        Reservations only ever grow, so a turn when the start was full
        stays full. ``_floor`` remembers how far that is known, which
        keeps a large fleet from rescanning the same full turns once
        per drone.

        Args:
            turn: The earliest turn to consider.

        Returns:
            The first turn at or after ``turn`` with a free exit.
        """
        while not self._can_leave_start(self._floor):
            self._floor += 1
        turn = max(turn, self._floor)
        while not self._can_leave_start(turn):
            turn += 1
        return turn

    def _reserve(self, states: list[State], steps: list[Step]) -> None:
        """Book a planned route so later drones plan around it.

        Args:
            states: Every ``(zone, turn)`` the drone stands in.
            steps: Every hop it makes.
        """
        for zone_name, turn in states:
            if self.network.zone(zone_name).capacity != UNLIMITED:
                self._zone_use[(zone_name, turn)] += 1
        for step in steps:
            for turn in range(step.depart + 1, step.arrive + 1):
                self._link_use[(step.link.key, turn)] += 1

    # -- the search -------------------------------------------------------

    def _route(self) -> tuple[list[State], list[Step]]:
        """Find the earliest arriving route for the next drone.

        Returns:
            The states the drone passes through and the hops it makes.
        """
        start = self.network.start
        end = self.network.end.name
        tie = itertools.count()

        # entry: (estimate, -priority, turn, tie, zone, previous, step)
        queue: list[
            tuple[int, int, int, int, str, State | None, Step | None]
        ] = [(self._cost_to_end[start.name], 0, 0, next(tie), start.name,
              None, None)]
        parent: dict[State, tuple[State | None, Step | None]] = {}

        while queue:
            _, priority, turn, _, here, previous, step = heapq.heappop(queue)
            state: State = (here, turn)
            if state in parent:
                continue
            parent[state] = (previous, step)
            if here == end:
                return self._unwind(parent, state)

            zone = self.network.zone(here)
            if zone is start:
                wait = self._next_departure(turn + 1)
            else:
                wait = turn + 1 if self._has_room(zone, turn + 1) else -1
            if wait >= 0 and (here, wait) not in parent:
                heapq.heappush(queue, (
                    wait + self._cost_to_end[here], priority, wait,
                    next(tie), here, state, None,
                ))

            for link in self.network.neighbours(here):
                dest = self.network.zone(link.other(here))
                if dest.name not in self._cost_to_end:
                    continue
                if not self._can_cross(link, dest, turn):
                    continue
                hop = Step(turn, link, dest)
                if (dest.name, hop.arrive) in parent:
                    continue
                bonus = -1 if dest.zone_type.is_preferred else 0
                heapq.heappush(queue, (
                    hop.arrive + self._cost_to_end[dest.name],
                    priority + bonus, hop.arrive, next(tie), dest.name,
                    state, hop,
                ))

        raise UnsolvableMapError("no route found for a drone")

    @staticmethod
    def _unwind(
        parent: dict[State, tuple[State | None, Step | None]],
        state: State,
    ) -> tuple[list[State], list[Step]]:
        """Rebuild a route from the search's back pointers.

        Args:
            parent: For each reached state, where it was reached from.
            state: The final state, at the end hub.

        Returns:
            The states from start to end, and the hops between them.
        """
        states: list[State] = []
        steps: list[Step] = []
        current: State | None = state
        while current is not None:
            states.append(current)
            previous, step = parent[current]
            if step is not None:
                steps.append(step)
            current = previous
        states.reverse()
        steps.reverse()
        return states, steps
