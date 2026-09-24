"""Connection (edge) model for the Fly-in drone routing simulation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Connection:
    """A bidirectional link between two zones.

    A connection is stored once and traversed from either end, so it is
    the single owner of the link's capacity: ``max_link_capacity`` caps
    the drones in transit over it in both directions combined.

    Being frozen makes the class hashable, which lets connections be
    used in sets and as dictionary keys by the parser and the solvers.

    Attributes:
        zone_a: Name of the first zone, in map file order.
        zone_b: Name of the second zone, in map file order.
        max_link_capacity: Maximum number of drones that may traverse
            this connection simultaneously.
    """

    zone_a: str
    zone_b: str
    max_link_capacity: int = 1

    @property
    def name(self) -> str:
        """Identifier printed for drones in flight over this link.

        The subject requires ``D<ID>-<connection>`` for drones still
        travelling towards a restricted zone, but never defines how a
        connection is named. We join the endpoints in the order they
        appear in the map file, mirroring the ``connection: <a>-<b>``
        syntax the format already uses.

        Returns:
            The connection name, for example ``"corridorA-tunnelB"``.
        """
        return f"{self.zone_a}-{self.zone_b}"

    @property
    def key(self) -> tuple[str, str]:
        """Order independent identity of the link.

        The subject treats ``a-b`` and ``b-a`` as the same connection,
        so both spellings must produce the same key for the parser to
        reject the duplicate. Sorting the endpoints makes declaration
        order irrelevant.

        Returns:
            The two endpoint names, alphabetically ordered.
        """
        return min(self.zone_a, self.zone_b), max(self.zone_a, self.zone_b)

    def other(self, zone_name: str) -> str:
        """Return the endpoint opposite to ``zone_name``.

        Used when walking the graph: given the zone a drone currently
        occupies, this answers where the connection leads.

        Args:
            zone_name: One of the two endpoints of this connection.

        Returns:
            The name of the other endpoint.

        Raises:
            ValueError: If ``zone_name`` is not an endpoint of this
                connection, which means the caller believes in an
                adjacency that does not exist.
        """
        if zone_name == self.zone_a:
            return self.zone_b
        elif zone_name == self.zone_b:
            return self.zone_a
        else:
            raise ValueError(
                f"{zone_name!r} is not an endpoint of {self.name!r}"
            )
