from abc import ABC, abstractmethod
import heapq
from network import Network
from plan import Plan, Turn, Move
from errors import UnsolvableMapError


class Solver(ABC):
    """Common interface shared by every routing strategy."""

    def __init__(self, network: Network) -> None:
        self.network = network

    @property
    @abstractmethod
    def name(self) -> str:
        """Short human readable label, shown in benchmark output."""

    @abstractmethod
    def solve(self) -> Plan:
        """Compute a routing plan for the whole fleet.

        Returns:
            A plan moving every drone from the start to the end hub.

        Raises:
            UnsolvableMapError: If the end hub is unreachable.
        """


class ShortestPathSolver(Solver):
    """Baseline: one cost-minimal route, drones queued behind
    each other. Ignores every other path on the map."""

    @property
    def name(self) -> str:
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

        dist: dict[str, tuple[int, int]] = {start: (0, 0)}
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
                if there.name not in dist or key < dist[there.name]:
                    dist[there.name] = key
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

        last = max(by_turn)
        return Plan([
            Turn(index, by_turn.get(index, []))
            for index in range(1, last + 1)
        ])

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
