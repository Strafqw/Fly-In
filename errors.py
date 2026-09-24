"""Exception hierarchy for the Fly-in drone routing simulation.

These are the failures a *user* can cause: a malformed map, an
impossible network. They are caught in ``main`` and turned into a clean
message. Programming mistakes keep raising the built-in exceptions, so
they surface as tracebacks instead of being swallowed.
"""


class FlyInError(Exception):
    """Base class for every user facing error of this project."""


class ValidationError(FlyInError):
    """Raised when a map parses but is semantically invalid."""


class ParseError(FlyInError):
    """A map file that does not respect the expected syntax.

    The subject requires every parsing error to report the line and the
    cause. Building that message in the exception itself means no call
    site can forget to do it.

    Attributes:
        cause: Explanation of what went wrong.
        line_num: 1-based index of the offending line, if known.
        content: Raw text of the offending line, if available.
    """

    def __init__(
        self,
        cause: str,
        line_num: int | None = None,
        content: str | None = None,
    ) -> None:
        """Build a parse error and format its message.

        Args:
            cause: Explanation of what went wrong.
            line_num: 1-based index of the offending line.
            content: Raw text of the offending line.
        """
        self.cause = cause
        self.line_num = line_num
        self.content = content
        super().__init__(self._format())

    def _format(self) -> str:
        """Assemble the user facing message.

        Returns:
            A message such as ``line 6: nb_drones must be positive``,
            followed by the offending line when it is known.
        """
        if self.line_num is None:
            where = "map file"
        else:
            where = f"line {self.line_num}"
        message = f"{where}: {self.cause}"
        if self.content is not None:
            message = f"{message} | {self.content.strip()!r}"
        return message


class UnsolvableMapError(FlyInError):
    """Raised when no drone can ever reach the end hub."""


class SimulationError(FlyInError):
    """Raised when a plan violates a movement or occupancy rule."""
