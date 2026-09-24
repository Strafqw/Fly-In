"""Zone (hub) model for the Fly-in drone routing simulation."""

from enum import Enum
import sys

UNLIMITED: int = sys.maxsize


class ZoneType(Enum):
    """Type of a zone, which determines how drones may traverse it.

    The member values match the tokens used by the ``zone=`` tag in map
    files, so ``ZoneType("restricted")`` performs the parsing lookup and
    raises ``ValueError`` on an unknown type.
    """

    NORMAL = "normal"
    BLOCKED = "blocked"
    RESTRICTED = "restricted"
    PRIORITY = "priority"

    @property
    def entry_cost(self) -> int:
        """Number of turns required to enter a zone of this type.

        Returns:
            2 for ``RESTRICTED``, 1 for ``NORMAL`` and ``PRIORITY``.

        Raises:
            ValueError: If asked for the cost of a ``BLOCKED`` zone,
                which can never be entered. Callers must filter on
                :attr:`is_passable` before asking for a cost.
        """
        if self is ZoneType.BLOCKED:
            raise ValueError("a blocked zone can never be entered")
        if self is ZoneType.RESTRICTED:
            return 2
        return 1

    @property
    def is_passable(self) -> bool:
        """Whether a drone is allowed to occupy a zone of this type."""
        return self is not ZoneType.BLOCKED

    @property
    def is_preferred(self) -> bool:
        """Whether pathfinding should favour a zone of this type.

        ``PRIORITY`` zones cost the same as normal ones but the subject
        asks for them to be preferred, so this is used as a tie-breaker
        rather than as a cost.
        """
        return self is ZoneType.PRIORITY


class Zone:
    """A single hub of the network.

    Attributes:
        name: Unique identifier of the zone.
        x: Integer x coordinate, used for the visual representation.
        y: Integer y coordinate, used for the visual representation.
        zone_type: Traversal semantics of the zone.
        color: Optional colour tag used by the renderer.
        max_drones: Occupancy limit as declared in the map file.
        is_start: Whether this zone is the fleet's departure hub.
        is_end: Whether this zone is the delivery target.
    """

    def __init__(
        self,
        name: str,
        x: int,
        y: int,
        zone_type: ZoneType = ZoneType.NORMAL,
        color: str | None = None,
        max_drones: int = 1,
        is_start: bool = False,
        is_end: bool = False
    ) -> None:
        """Build a zone from a parsed map file declaration.

        Args:
            name: Unique identifier of the zone.
            x: Integer x coordinate.
            y: Integer y coordinate.
            zone_type: Traversal semantics, from the ``zone=`` tag.
            color: Colour tag, or ``None`` when the map omits it.
            max_drones: Declared occupancy limit, from ``max_drones=``.
            is_start: Whether the line declared a ``start_hub``.
            is_end: Whether the line declared an ``end_hub``.
        """
        self.name = name
        self.x = x
        self.y = y
        self.zone_type = zone_type
        self.color = color
        self.max_drones = max_drones
        self.is_start = is_start
        self.is_end = is_end

    @property
    def capacity(self) -> int:
        """Effective occupancy limit of the zone.

        The subject states that ``max_drones`` is ignored on the start
        and end hubs: every drone starts in the former and any number
        may be delivered to the latter.

        Returns:
            :data:`UNLIMITED` for the start and end hubs, otherwise the
            declared ``max_drones`` value.
        """
        if self.is_start or self.is_end:
            return UNLIMITED
        else:
            return self.max_drones

    @property
    def entry_cost(self) -> int:
        """Turns needed to move into this zone.

        Returns:
            The turn cost of this zone's type.

        Raises:
            ValueError: If the zone is blocked and can never be
                entered. Check :attr:`is_passable` first.
        """
        return self.zone_type.entry_cost

    @property
    def is_passable(self) -> bool:
        """Whether drones may enter this zone."""
        return self.zone_type.is_passable

    def __repr__(self) -> str:
        """Developer-facing representation, used when debugging."""
        cap = "∞" if self.capacity == UNLIMITED else self.capacity
        return (
            f"Zone({self.name!r}, {self.x}, {self.y}, "
            f"{self.zone_type}, capacity={cap})"
        )
