"""Visual representation of the simulation.

The subject makes visual feedback mandatory. Renderers sit behind a
common interface so the machine readable output required by §VII.5 and
a colourful grid view can be swapped without touching the solvers.
"""

import os
import shutil
import sys
from abc import ABC, abstractmethod

from network import Network
from plan import Plan
from zone import UNLIMITED, Zone, ZoneType

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

ANSI_COLORS: dict[str, str] = {
    "black": "\033[38;5;240m",
    "blue": "\033[38;5;33m",
    "brown": "\033[38;5;130m",
    "crimson": "\033[38;5;161m",
    "cyan": "\033[38;5;51m",
    "darkred": "\033[38;5;88m",
    "gold": "\033[38;5;220m",
    "gray": "\033[38;5;245m",
    "grey": "\033[38;5;245m",
    "green": "\033[38;5;40m",
    "lime": "\033[38;5;154m",
    "magenta": "\033[38;5;201m",
    "maroon": "\033[38;5;52m",
    "orange": "\033[38;5;208m",
    "purple": "\033[38;5;99m",
    "rainbow": "\033[38;5;207m",
    "red": "\033[38;5;196m",
    "violet": "\033[38;5;135m",
    "white": "\033[38;5;255m",
    "yellow": "\033[38;5;226m",
}
"""Maps the subject's free-form colour words onto 256-colour codes."""

TYPE_MARK: dict[ZoneType, str] = {
    ZoneType.NORMAL: " ",
    ZoneType.PRIORITY: "+",
    ZoneType.RESTRICTED: "!",
    ZoneType.BLOCKED: "#",
}
"""Single character hint of a zone's type, shown beside its name."""


class Renderer(ABC):
    """Common interface shared by every visual representation."""

    def __init__(self, network: Network) -> None:
        """Bind the renderer to a network.

        Args:
            network: The map being simulated.
        """
        self.network = network

    @abstractmethod
    def render(self, plan: Plan) -> None:
        """Display a whole plan.

        Args:
            plan: The validated plan to display.
        """


class PlainRenderer(Renderer):
    """The machine readable output required by the subject.

    One line per turn, moves space separated, drones that do not move
    omitted. This is what gets piped or diffed.
    """

    def render(self, plan: Plan) -> None:
        """Print one line per turn.

        Args:
            plan: The validated plan to display.
        """
        print(plan)


class GridRenderer(Renderer):
    """Colour coded, turn by turn view of the network.

    Zones are laid out on their declared x and y coordinates, tinted
    with their ``color=`` tag, and annotated with how many drones they
    hold against their capacity. Drones crossing a connection towards
    a restricted zone are listed separately, since they occupy no zone
    at all during that turn.
    """

    MIN_CELL = 5
    MAX_CELL = 14

    def __init__(self, network: Network) -> None:
        """Bind the renderer and pre-compute the grid geometry.

        Args:
            network: The map being simulated.
        """
        super().__init__(network)
        zones = list(network.zones.values())
        self.min_x = min(zone.x for zone in zones)
        self.max_x = max(zone.x for zone in zones)
        self.min_y = min(zone.y for zone in zones)
        self.max_y = max(zone.y for zone in zones)
        self.columns = self.max_x - self.min_x + 1
        self.cell = self._cell_width()
        self.color = self._supports_color()

    # -- geometry -------------------------------------------------------

    def _cell_width(self) -> int:
        """Pick a cell width that fits the terminal.

        Returns:
            The number of characters each zone cell occupies.
        """
        available = shutil.get_terminal_size((100, 24)).columns
        fitted = available // max(self.columns, 1)
        return max(self.MIN_CELL, min(self.MAX_CELL, fitted))

    def _supports_color(self) -> bool:
        """Whether escape codes should be emitted at all.

        Returns:
            False when output is redirected or NO_COLOR is set, so the
            view stays readable in a log file.
        """
        if os.environ.get("NO_COLOR"):
            return False
        return sys.stdout.isatty()

    # -- painting -------------------------------------------------------

    def _tint(self, text: str, zone: Zone, occupied: bool) -> str:
        """Apply a zone's colour to a piece of text.

        Args:
            text: The text to colour.
            zone: The zone whose colour tag to use.
            occupied: Whether the zone currently holds drones.

        Returns:
            The text wrapped in escape codes, or unchanged when colour
            is disabled.
        """
        if not self.color:
            return text
        code = ANSI_COLORS.get(zone.color or "", "")
        weight = BOLD if occupied else DIM
        return f"{weight}{code}{text}{RESET}"

    def _cell_for(self, zone: Zone | None, count: int) -> str:
        """Render one grid cell.

        Args:
            zone: The zone at this position, or None if empty space.
            count: How many drones occupy it.

        Returns:
            A fixed width string for this cell.
        """
        if zone is None:
            return " " * self.cell
        label = zone.name[: self.cell - 2]
        if count:
            suffix = f"{count}"
            keep = max(1, self.cell - 3 - len(suffix))
            label = label[:keep] + ":" + suffix
        body = f"{TYPE_MARK[zone.zone_type]}{label}".ljust(self.cell)
        return self._tint(body, zone, bool(count))

    def _legend(self) -> str:
        """Describe the symbols used in the grid.

        Returns:
            A one line legend.
        """
        return (
            f"{DIM}legend: +priority  !restricted  #blocked"
            f"   name:N = N drones inside{RESET}"
            if self.color
            else "legend: +priority  !restricted  #blocked"
            "   name:N = N drones inside"
        )

    # -- the frame ------------------------------------------------------

    def _draw_turn(
        self,
        index: int,
        occupancy: dict[str, int],
        flying: list[str],
        line: str,
    ) -> None:
        """Print one frame of the animation.

        Args:
            index: 1-based turn number.
            occupancy: How many drones each zone holds.
            flying: Labels of drones crossing a connection.
            line: The raw output line for this turn.
        """
        at = {(zone.x, zone.y): zone for zone in self.network.zones.values()}
        print(f"\n{BOLD if self.color else ''}turn {index}"
              f"{RESET if self.color else ''}")
        for y in range(self.max_y, self.min_y - 1, -1):
            row = "".join(
                self._cell_for(
                    at.get((x, y)), occupancy.get(
                        at[(x, y)].name, 0) if (x, y) in at else 0
                )
                for x in range(self.min_x, self.max_x + 1)
            )
            print(f"  {row.rstrip()}")
        if flying:
            print(f"  in flight: {', '.join(flying)}")
        if line:
            print(f"  moves: {line}")

    def render(self, plan: Plan) -> None:
        """Animate the whole plan, one frame per turn.

        Args:
            plan: The validated plan to display.
        """
        start = self.network.start.name
        end = self.network.end.name
        position = {
            drone: start
            for drone in range(1, self.network.nb_drones + 1)
        }
        crossing: dict[int, str] = {}

        print(self._legend())
        for turn in plan.turns:
            for move in turn.moves:
                if move.in_flight:
                    crossing[move.drone_id] = move.connection or ""
                    position.pop(move.drone_id, None)
                else:
                    crossing.pop(move.drone_id, None)
                    position[move.drone_id] = move.zone

            occupancy: dict[str, int] = {}
            for name in position.values():
                occupancy[name] = occupancy.get(name, 0) + 1

            flying = [
                f"D{drone}->{link}"
                for drone, link in sorted(crossing.items())
            ]
            self._draw_turn(turn.index, occupancy, flying, str(turn))

        arrived = sum(1 for name in position.values() if name == end)
        print(f"\n{arrived}/{self.network.nb_drones} drones delivered"
              f" in {plan.turn_count} turns")

    def describe_capacities(self) -> str:
        """Summarise which zones are capacity limited.

        Returns:
            A one line summary, useful above the animation.
        """
        limited = [
            f"{zone.name}({zone.capacity})"
            for zone in self.network.zones.values()
            if zone.capacity != UNLIMITED and zone.capacity > 1
        ]
        return "wide zones: " + (", ".join(limited) or "none")
