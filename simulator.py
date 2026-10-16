"""Independent referee: replays a plan and verifies every rule.

The simulator never decides where drones go. It takes a plan as a set
of claims and checks each one against the subject's rules, which is
what lets it disagree with the solver that produced it.
"""

from collections import Counter
from dataclasses import dataclass

from errors import SimulationError
from network import Network
from plan import Move, Plan
from zone import UNLIMITED


@dataclass(frozen=True)
class Metrics:
    """Evaluation metrics for a plan that passed validation.

    Attributes:
        turns: Total simulation turns, the subject's primary score.
        drones: Size of the fleet that was routed.
        total_moves: Number of individual drone moves performed.
        total_cost: Sum of the weighted entry costs paid by the fleet.
        total_delivery: Sum over drones of the turn each was delivered.
    """

    turns: int
    drones: int
    total_moves: int
    total_cost: int
    total_delivery: int

    @property
    def moves_per_turn(self) -> float:
        """Average number of drones moved per turn.

        Returns:
            The average, or 0.0 for an empty plan.
        """
        if self.turns == 0:
            return 0.0
        return self.total_moves / self.turns

    @property
    def turns_per_drone(self) -> float:
        """Average turn on which a drone reached the end hub.

        Every drone starts at turn 0, so this is how many turns each
        one took on average, waiting included.

        Returns:
            The average, or 0.0 when there are no drones.
        """
        if self.drones == 0:
            return 0.0
        return self.total_delivery / self.drones


class Simulator:
    """Replays a plan and verifies every rule of the subject.

    Nothing here is derived from how the solver works. A plan is taken
    as a set of claims - "on turn 3, drone 2 is at loop_b" - and each
    one is checked against the rules in the subject.
    """

    IN_FLIGHT = ""
    """Sentinel position for a drone crossing a connection."""

    def __init__(self, network: Network) -> None:
        """Bind the simulator to a network.

        Args:
            network: The map the plan was computed for.
        """
        self.network = network

    def validate(self, plan: Plan) -> Metrics:
        """Replay a plan, checking every movement and occupancy rule.

        Zone occupancy is kept as a running count updated by each move,
        so a turn costs time proportional to the moves in it rather
        than to the size of the fleet.

        Args:
            plan: The plan to verify.

        Returns:
            The metrics of the validated plan.

        Raises:
            SimulationError: If any rule is violated.
        """
        start = self.network.start.name
        end = self.network.end.name

        position: dict[int, str] = {
            drone_id: start
            for drone_id in range(1, self.network.nb_drones + 1)
        }
        occupancy: Counter[str] = Counter({start: len(position)})
        transit: dict[int, tuple[str, str]] = {}
        delivered: dict[int, int] = {}
        link_use: Counter[tuple[str, int]] = Counter()
        total_cost = 0

        for turn in plan.turns:
            must_land = set(transit)
            seen: set[int] = set()
            entered: set[str] = set()

            for move in turn.moves:
                drone = move.drone_id
                self._check_mover(turn.index, move, position, seen,
                                  delivered)
                seen.add(drone)
                dest = self.network.zone(move.zone)

                # The checks read position[drone] as it stood before
                # this turn; it is only overwritten once they pass.
                if move.in_flight:
                    self._depart(turn.index, move, position, transit,
                                 link_use)
                else:
                    self._arrive(turn.index, move, position, transit,
                                 must_land, link_use)
                    total_cost += dest.entry_cost
                    entered.add(move.zone)
                    if move.zone == end:
                        delivered[drone] = turn.index

                if position[drone] != self.IN_FLIGHT:
                    occupancy[position[drone]] -= 1
                if move.in_flight:
                    position[drone] = self.IN_FLIGHT
                else:
                    position[drone] = move.zone
                    occupancy[move.zone] += 1

            if must_land:
                stuck = ", ".join(f"D{d}" for d in sorted(must_land))
                self._fail(
                    turn.index, f"{stuck} lingered on a connection"
                )

            self._check_occupancy(turn.index, entered, occupancy)

        self._check_links(link_use)

        missing = set(position) - delivered.keys()
        if missing:
            names = ", ".join(f"D{d}" for d in sorted(missing))
            raise SimulationError(f"never delivered: {names}")

        return Metrics(
            turns=plan.turn_count,
            drones=self.network.nb_drones,
            total_moves=plan.total_moves,
            total_cost=total_cost,
            total_delivery=sum(delivered.values()),
        )

    def _check_mover(
        self,
        index: int,
        move: Move,
        position: dict[int, str],
        seen: set[int],
        delivered: dict[int, int],
    ) -> None:
        """Check that a drone is allowed to make a move at all.

        Args:
            index: 1-based turn number, for error messages.
            move: The move being checked.
            position: Where every drone stood before this turn.
            seen: Drones that already moved this turn.
            delivered: Drones already at the end hub.

        Raises:
            SimulationError: If the drone does not exist, has already
                moved this turn, was already delivered, or is heading
                into a blocked zone.
        """
        drone = move.drone_id
        if drone not in position:
            self._fail(index, f"unknown drone D{drone}")
        if drone in seen:
            self._fail(index, f"D{drone} moves twice")
        if drone in delivered:
            self._fail(index, f"D{drone} already delivered")
        if not self.network.zone(move.zone).is_passable:
            self._fail(index, f"D{drone} enters blocked zone {move.zone!r}")

    def _depart(
        self,
        index: int,
        move: Move,
        position: dict[int, str],
        transit: dict[int, tuple[str, str]],
        link_use: Counter[tuple[str, int]],
    ) -> None:
        """Check and record a drone setting off across a connection.

        A restricted crossing occupies the link for both turns of the
        transit, so the usage counter is bumped twice.

        Args:
            index: 1-based turn number, for error messages.
            move: The in-flight move being checked.
            position: Where every drone stood before this turn.
            transit: Drones currently crossing, updated in place.
            link_use: Per link and turn usage, updated in place.

        Raises:
            SimulationError: If the crossing is not legal.
        """
        drone = move.drone_id
        link = self.network.link_between(position[drone], move.zone)
        if link is None:
            self._fail(
                index,
                f"D{drone} {position[drone]!r} -> {move.zone!r}"
                " are not connected",
            )
            return
        if link.name != move.connection:
            self._fail(
                index,
                f"D{drone} claims link {move.connection!r},"
                f" expected {link.name!r}",
            )
        if self.network.zone(move.zone).entry_cost != 2:
            self._fail(
                index,
                f"D{drone} in flight towards {move.zone!r},"
                " which is not restricted",
            )
        transit[drone] = (link.name, move.zone)
        link_use[(link.name, index)] += 1
        link_use[(link.name, index + 1)] += 1

    def _arrive(
        self,
        index: int,
        move: Move,
        position: dict[int, str],
        transit: dict[int, tuple[str, str]],
        must_land: set[int],
        link_use: Counter[tuple[str, int]],
    ) -> None:
        """Check and record a drone entering a zone.

        Covers both an ordinary one turn move and the landing half of
        a two turn restricted crossing.

        Args:
            index: 1-based turn number, for error messages.
            move: The move being checked.
            position: Where every drone stood before this turn.
            transit: Drones currently crossing, updated in place.
            must_land: Drones that owe an arrival this turn.
            link_use: Per link and turn usage, updated in place.

        Raises:
            SimulationError: If the move is not legal.
        """
        drone = move.drone_id
        if drone in transit:
            _, destination = transit.pop(drone)
            must_land.discard(drone)
            if destination != move.zone:
                self._fail(
                    index,
                    f"D{drone} was crossing to {destination!r}"
                    f" but landed at {move.zone!r}",
                )
            return

        link = self.network.link_between(position[drone], move.zone)
        if link is None:
            self._fail(
                index,
                f"D{drone} {position[drone]!r} -> {move.zone!r}"
                " are not connected",
            )
            return
        if self.network.zone(move.zone).entry_cost != 1:
            self._fail(
                index,
                f"D{drone} entered restricted {move.zone!r} in one turn",
            )
        link_use[(link.name, index)] += 1

    def _check_occupancy(
        self, index: int, entered: set[str], occupancy: Counter[str]
    ) -> None:
        """Check zone capacities on the state after a whole turn.

        Occupancy is never checked move by move: the subject says a
        drone leaving frees its space during the same turn, so a whole
        corridor may shift forward at once. Only zones that received a
        drone this turn can have gone over capacity, so only those are
        checked.

        Args:
            index: 1-based turn number, for error messages.
            entered: Zones at least one drone moved into this turn.
            occupancy: How many drones each zone holds after the turn.

        Raises:
            SimulationError: If a zone is over capacity.
        """
        for name in sorted(entered):
            count = occupancy[name]
            capacity = self.network.zone(name).capacity
            if capacity != UNLIMITED and count > capacity:
                self._fail(
                    index,
                    f"{name!r} holds {count} drones,"
                    f" capacity is {capacity}",
                )

    def _check_links(self, link_use: Counter[tuple[str, int]]) -> None:
        """Check every connection against its simultaneous use limit.

        Args:
            link_use: How many drones used each link on each turn.

        Raises:
            SimulationError: If a connection is over capacity.
        """
        for (name, index), count in sorted(link_use.items()):
            first, second = name.split("-", 1)
            link = self.network.link_between(first, second)
            if link is None:
                continue
            if count > link.max_link_capacity:
                self._fail(
                    index,
                    f"link {name!r} carries {count} drones,"
                    f" capacity is {link.max_link_capacity}",
                )

    def _fail(self, index: int, cause: str) -> None:
        """Raise a simulation error naming the turn it happened on.

        Args:
            index: 1-based turn number.
            cause: What rule was broken.

        Raises:
            SimulationError: Always.
        """
        raise SimulationError(f"turn {index}: {cause}")
