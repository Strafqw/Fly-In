"""Parser for the Fly-in map file format."""

from errors import ParseError, ValidationError
from network import Network
from connection import Connection
from zone import Zone, ZoneType


class MapParser:
    """Turn a map file into a validated :class:`Network`.

    The parser is deliberately strict: every deviation from the format
    raises a :class:`errors.ParseError` carrying the offending line
    number and the cause.
    """

    def parse_file(self, path: str) -> Network:
        """Parse a map file from disk.

        Args:
            path: Path to the map file.

        Returns:
            The parsed and validated network.

        Raises:
            ParseError: If the file does not respect the format.
            ValidationError: If the map is semantically invalid.
            OSError: If the file cannot be read.
        """
        with open(path, "r", encoding="utf-8") as handle:
            return self.parse_lines(handle.read().splitlines())

    def parse_lines(self, lines: list[str]) -> Network:
        """Parse a map from a list of raw lines.

        Args:
            lines: The map file content, one entry per line.

        Returns:
            The parsed and validated network.

        Raises:
            ParseError: If the content does not respect the format.
            ValidationError: If the map is semantically invalid.
        """
        network: Network | None = None

        for number, raw in enumerate(lines, start=1):
            text = raw.split("#")[0].strip()
            if not text:
                continue

            if network is None:
                count = self._parse_nb_drones(text, number, raw)
                network = Network(count)
                continue
            try:
                if text.startswith("start_hub:"):
                    network.add_zone(
                        self._parse_zone(text, number, raw, is_start=True)
                    )
                elif text.startswith("end_hub:"):
                    network.add_zone(
                        self._parse_zone(text, number, raw, is_end=True)
                    )
                elif text.startswith("hub:"):
                    network.add_zone(self._parse_zone(text, number, raw))
                elif text.startswith("connection:"):
                    network.add_connection(
                        self._parse_connection(text, number, raw)
                    )
                else:
                    raise ParseError("unknown directive", number, raw)
            except ValidationError as error:
                raise ParseError(str(error), number, raw) from error
        if network is None:
            raise ParseError("map declares no nb_drones")

        network.validate()
        return network

    # ------------------------------------------------------------------
    # Line handlers
    # ------------------------------------------------------------------

    def _parse_nb_drones(self, text: str, number: int, raw: str) -> int:
        """Parse the mandatory ``nb_drones:`` directive.

        Args:
            text: The cleaned line.
            number: 1-based line index, for error reporting.
            raw: The original line, for error reporting.

        Returns:
            The declared fleet size.

        Raises:
            ParseError: If the directive is missing or malformed.
        """
        prefix = "nb_drones:"
        if not text.startswith(prefix):
            raise ParseError(
                "first directive must be nb_drones", number, raw
            )
        value = text[len(prefix):].strip()
        return self._parse_positive_int(value, "nb_drones", number, raw)

    def _parse_zone(
        self,
        text: str,
        number: int,
        raw: str,
        is_start: bool = False,
        is_end: bool = False,
    ) -> Zone:
        """Parse a ``start_hub:``, ``end_hub:`` or ``hmadeub:`` line.

        Args:
            text: The cleaned line.
            number: 1-based line index, for error reporting.
            raw: The original line, for error reporting.
            is_start: Whether the prefix declared the start hub.
            is_end: Whether the prefix declared the end hub.

        Returns:
            The described zone.

        Raises:
            ParseError: If the declaration is malformed.
        """
        body, blob = self._split_metadata(text.split(":", 1)[1])

        tokens = body.split()
        if len(tokens) != 3:
            raise ParseError("expected '<name> <x> <y>'", number, raw)
        name, x_text, y_text = tokens
        if "-" in name:
            raise ParseError(
                f"zone name {name!r} may not contain a dash", number, raw
            )

        x = self._parse_int(x_text, "x coordinate", number, raw)
        y = self._parse_int(y_text, "y coordinate", number, raw)

        meta = self._parse_metadata(blob, number, raw)
        self._reject_unknown_tags(
            meta, {"zone", "color", "max_drones"}, "zone", number, raw
        )

        type_text = meta.get("zone", ZoneType.NORMAL.value)
        try:
            zone_type = ZoneType(type_text)
        except ValueError:
            raise ParseError(
                f"unknown zone type {type_text!r}", number, raw
            ) from None

        max_drones = 1
        if "max_drones" in meta:
            max_drones = self._parse_positive_int(
                meta["max_drones"], "max_drones", number, raw
            )

        return Zone(
            name,
            x,
            y,
            zone_type,
            meta.get("color"),
            max_drones,
            is_start,
            is_end,
        )

    def _parse_connection(
        self, text: str, number: int, raw: str
    ) -> Connection:
        """Parse a ``connection:`` line.

        Args:
            text: The cleaned line.
            number: 1-based line index, for error reporting.
            raw: The original line, for error reporting.

        Returns:
            The described connection.

        Raises:
            ParseError: If the declaration is malformed.
        """
        body, blob = self._split_metadata(text.split(":", 1)[1])
        body = body.strip()

        if len(body.split()) > 1:
            raise ParseError(
                "zone names may not contain spaces", number, raw
            )
        endpoints = body.split("-")
        if len(endpoints) != 2 or not all(endpoints):
            raise ParseError("expected '<zone1>-<zone2>'", number, raw)

        meta = self._parse_metadata(blob, number, raw)
        self._reject_unknown_tags(
            meta, {"max_link_capacity"}, "connection", number, raw
        )

        capacity = 1
        if "max_link_capacity" in meta:
            capacity = self._parse_positive_int(
                meta["max_link_capacity"], "max_link_capacity", number, raw
            )

        return Connection(endpoints[0], endpoints[1], capacity)

    # ------------------------------------------------------------------
    # Shared pieces
    # ------------------------------------------------------------------

    def _split_metadata(self, body: str) -> tuple[str, str | None]:
        """Separate a declaration from its bracketed metadata block.

        Args:
            body: Everything after the line's prefix.

        Returns:
            The text before the block, and the block itself including
            its brackets, or ``None`` when the line carries no
            metadata.
        """
        index = body.find("[")
        if index == -1:
            return body, None
        return body[:index], body[index:].strip()

    def _parse_metadata(
        self, blob: str | None, number: int, raw: str
    ) -> dict[str, str]:
        """Parse a ``[key=value key=value]`` metadata block.

        Args:
            blob: The bracketed text, or ``None`` when absent.
            number: 1-based line index, for error reporting.
            raw: The original line, for error reporting.

        Returns:
            The tags, in no particular order.

        Raises:
            ParseError: If the block is syntactically invalid.
        """
        if blob is None:
            return {}
        if not blob.startswith("[") or not blob.endswith("]"):
            raise ParseError("malformed metadata block", number, raw)

        tags: dict[str, str] = {}
        for token in blob[1:-1].split():
            if token.count("=") != 1:
                raise ParseError(
                    f"expected key=value, got {token!r}", number, raw
                )
            key, value = token.split("=")
            if not key or not value:
                raise ParseError(
                    f"empty key or value in {token!r}", number, raw
                )
            if key in tags:
                raise ParseError(f"duplicate tag {key!r}", number, raw)
            tags[key] = value
        return tags

    def _reject_unknown_tags(
        self,
        meta: dict[str, str],
        allowed: set[str],
        kind: str,
        number: int,
        raw: str,
    ) -> None:
        """Fail on any metadata tag the format does not define.

        Args:
            meta: The parsed tags.
            allowed: The tag names this kind of line accepts.
            kind: Either ``"zone"`` or ``"connection"``, for the
                message.
            number: 1-based line index, for error reporting.
            raw: The original line, for error reporting.

        Raises:
            ParseError: If any tag is not in ``allowed``.
        """
        unknown = sorted(set(meta) - allowed)
        if unknown:
            raise ParseError(
                f"unknown {kind} tag {unknown[0]!r}", number, raw
            )

    def _parse_int(
        self, value: str, label: str, number: int, raw: str
    ) -> int:
        """Convert a token to an integer, or fail with a clear message.

        Args:
            value: The token to convert.
            label: What the token represents, for the message.
            number: 1-based line index, for error reporting.
            raw: The original line, for error reporting.

        Returns:
            The parsed integer, which may be negative.

        Raises:
            ParseError: If the token is not an integer.
        """
        try:
            return int(value)
        except ValueError:
            raise ParseError(
                f"{label} must be an integer, got {value!r}", number, raw
            ) from None

    def _parse_positive_int(
        self, value: str, label: str, number: int, raw: str
    ) -> int:
        """Convert a token to a strictly positive integer.

        Args:
            value: The token to convert.
            label: What the token represents, for the message.
            number: 1-based line index, for error reporting.
            raw: The original line, for error reporting.

        Returns:
            The parsed integer, guaranteed positive.

        Raises:
            ParseError: If the token is not a positive integer.
        """
        result = self._parse_int(value, label, number, raw)
        if result <= 0:
            raise ParseError(
                f"{label} must be positive, got {result}", number, raw
            )
        return result
