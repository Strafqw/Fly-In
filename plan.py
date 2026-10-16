"""Data produced by a solver and consumed by the simulator."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Move:
    """A single drone action taken during one turn.

    Attributes:
        drone_id: 1-based identifier of the drone.
        zone: The zone the drone occupies, or is heading towards when
            in flight.
        connection: Name of the link the drone is crossing, set only
            while in transit towards a restricted zone.
    """

    drone_id: int
    zone: str
    connection: str | None = None

    @property
    def in_flight(self) -> bool:
        """Whether the drone is mid-transit on a connection."""
        return self.connection is not None

    @property
    def label(self) -> str:
        """What the output prints: the connection in flight, else the zone.

        Returns:
            The connection name while in flight, otherwise the zone name.
        """
        if self.connection is not None:
            return self.connection
        return self.zone

    def __str__(self) -> str:
        """Render the move in the subject's output format.

        Returns:
            A token such as ``"D1-roof1"``.
        """
        return f"D{self.drone_id}-{self.label}"


@dataclass(frozen=True)
class Turn:
    """Every move performed during one simulation turn.

    Attributes:
        index: 1-based turn number.
        moves: The moves executed this turn. Drones that stay put are
            omitted, as the subject requires. A tuple rather than a
            list, so the frozen dataclass is immutable all the way
            down.
    """

    index: int
    moves: tuple[Move, ...] = ()

    def __str__(self) -> str:
        """Render the turn as one line of the simulation output.

        Returns:
            The moves of this turn, space separated.
        """
        return " ".join(str(x) for x in self.moves)


@dataclass(frozen=True)
class Plan:
    """A complete routing solution: every turn, in order.

    Attributes:
        turns: The ordered simulation turns.
    """

    turns: tuple[Turn, ...] = ()

    @property
    def turn_count(self) -> int:
        """Total number of simulation turns, the project's score."""
        return len(self.turns)

    @property
    def total_moves(self) -> int:
        """Total number of individual drone moves performed."""
        return sum(len(turn.moves) for turn in self.turns)

    def __str__(self) -> str:
        """Render the whole plan in the subject's output format.

        Returns:
            One line per turn.
        """
        return "\n".join(str(turn) for turn in self.turns)
