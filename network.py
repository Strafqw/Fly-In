"""The zone network: the graph the drones fly through.

All graph logic is written from scratch here and in the solvers, since
the subject forbids any graph library.
"""

from connection import Connection
from errors import ValidationError
from zone import Zone


class Network:
    """An undirected graph of zones linked by connections.

    Zones are stored by name and connections by their order independent
    key, so lookups and duplicate detection are both constant time.
    Adjacency maps a zone name to the connections incident to it; use
    :meth:`Connection.other` to find where each one leads.

    Attributes:
        nb_drones: Number of drones that must reach the end hub.
    """

    def __init__(self, nb_drones: int) -> None:
        """Initialise an empty network.

        Args:
            nb_drones: Size of the fleet to route.
        """
        self.nb_drones = nb_drones
        self._zones: dict[str, Zone] = {}
        self._connections: dict[tuple[str, str], Connection] = {}
        self._adjacency: dict[str, list[Connection]] = {}
        self._start: Zone | None = None
        self._end: Zone | None = None

    def __repr__(self) -> str:
        """Developer facing summary of the network's size."""
        return (
            f"Network(zones={len(self._zones)}, "
            f"connections={len(self._connections)}, "
            f"drones={self.nb_drones})"
        )

    @property
    def start(self) -> Zone:
        """The unique start hub.

        Returns:
            The start zone.

        Raises:
            ValidationError: If the map declared no start hub.
        """
        if self._start is None:
            raise ValidationError("map declares no start_hub")
        return self._start

    @property
    def end(self) -> Zone:
        """The unique end hub.

        Returns:
            The end zone.

        Raises:
            ValidationError: If the map declared no end hub.
        """
        if self._end is None:
            raise ValidationError("map declares no end_hub")
        return self._end

    @property
    def zones(self) -> dict[str, Zone]:
        """Every zone, keyed by name."""
        return self._zones

    @property
    def connections(self) -> list[Connection]:
        """Every connection, in declaration order."""
        return list(self._connections.values())

    def zone(self, name: str) -> Zone:
        """Look up a zone by name.

        Args:
            name: Name of the zone.

        Returns:
            The matching zone.

        Raises:
            KeyError: If no such zone exists, which means the caller
                believes in a zone the map never declared.
        """
        return self._zones[name]

    def neighbours(self, name: str) -> list[Connection]:
        """List the connections incident to a zone.

        Unlike :meth:`zone`, an unknown name is not an error here: a
        zone with no links simply has no neighbours, and traversals
        should not have to guard every lookup.

        Args:
            name: Name of the zone.

        Returns:
            The incident connections, empty if there are none.
        """
        return self._adjacency.get(name, [])

    def link_between(self, a: str, b: str) -> Connection | None:
        """Return the connection joining two zones, if any.

        Args:
            a: Name of the first zone.
            b: Name of the second zone.

        Returns:
            The connection, or ``None`` if the zones are not linked.
        """
        return self._connections.get(Connection(a, b).key)

    def add_zone(self, zone: Zone) -> None:
        """Register a zone.

        Also records it as the start or end hub when flagged, and gives
        it an empty adjacency entry so later lookups never miss.

        Args:
            zone: The zone to add.

        Raises:
            ValidationError: If the name is already taken, or if a
                second start or end hub is declared.
        """
        if zone.name in self._zones:
            raise ValidationError(f"duplicate zone name {zone.name!r}")
        if zone.is_start:
            if self._start is not None:
                raise ValidationError("two start hubs")
            self._start = zone
        if zone.is_end:
            if self._end is not None:
                raise ValidationError("two end hubs")
            self._end = zone
        self._zones[zone.name] = zone
        self._adjacency[zone.name] = []

    def add_connection(self, conn: Connection) -> None:
        """Register a connection between two known zones.

        Args:
            conn: The link to add.

        Raises:
            ValidationError: If an endpoint is unknown, if the link is
                a self loop, or if it duplicates an existing one.
        """
        if conn.zone_a not in self._zones:
            raise ValidationError(f"unknown zone {conn.zone_a!r}")
        if conn.zone_b not in self._zones:
            raise ValidationError(f"unknown zone {conn.zone_b!r}")
        if conn.zone_a == conn.zone_b:
            raise ValidationError(f"self loop on {conn.zone_a!r}")
        if conn.key in self._connections:
            raise ValidationError(f"duplicate connection {conn.name!r}")
        self._connections[conn.key] = conn
        self._adjacency[conn.zone_a].append(conn)
        self._adjacency[conn.zone_b].append(conn)

    def validate(self) -> None:
        """Check the consistency of the whole parsed map.

        Called once after parsing, for the rules that can only be
        checked once every line has been read.

        Raises:
            ValidationError: If the map is structurally invalid.
        """
        start = self.start
        end = self.end
        if start is end:
            raise ValidationError("start and end hubs must differ")
        if self.nb_drones <= 0:
            raise ValidationError(
                f"nb_drones must be positive, got {self.nb_drones}"
            )
