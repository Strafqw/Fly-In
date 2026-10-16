"""Command line entry point for the Fly-in drone routing simulation."""

import argparse
import os
import sys

from errors import FlyInError
from parser import MapParser
from renderer import (
    GridRenderer,
    PlainRenderer,
    Renderer,
)
from simulator import Metrics, Simulator
from solver import ReservationSolver, ShortestPathSolver, Solver


class FlyInApp:
    """The command line application: parse, solve, verify, display."""

    SOLVERS: dict[str, type[Solver]] = {
        "reservation": ReservationSolver,
        "shortest": ShortestPathSolver,
    }
    """Routing strategies selectable with ``--solver``."""

    def build_arg_parser(self) -> argparse.ArgumentParser:
        """Describe the command line interface.

        Returns:
            The configured argument parser.
        """
        parser = argparse.ArgumentParser(
            prog="fly-in",
            description="Route a fleet of drones through a zone network.",
        )
        parser.add_argument("map", help="path to the map file")
        parser.add_argument(
            "--solver",
            choices=sorted(self.SOLVERS),
            default="reservation",
            help="routing strategy to use (default: reservation)",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="suppress the turn by turn output",
        )
        parser.add_argument(
            "--visual",
            action="store_true",
            help="show the coloured grid view instead of raw output",
        )
        parser.add_argument(
            "--turns-only",
            action="store_true",
            help="print only the total turn count, for benchmarking",
        )
        parser.add_argument(
            "--stats",
            action="store_true",
            help="print the secondary evaluation metrics",
        )
        return parser

    def run(self, args: argparse.Namespace) -> int:
        """Parse a map, solve it, verify the plan and display it.

        The plan is validated before anything is printed, so an illegal
        plan reports an error rather than showing output that looks
        right.

        Args:
            args: Parsed command line arguments.

        Returns:
            A process exit status.
        """
        network = MapParser().parse_file(args.map)
        solver = self.SOLVERS[args.solver](network)
        plan = solver.solve()
        metrics = Simulator(network).validate(plan)

        if args.turns_only:
            print(metrics.turns)
        elif not args.quiet:
            renderer: Renderer = (
                GridRenderer(network) if args.visual
                else PlainRenderer(network)
            )
            renderer.render(plan)

        if args.stats:
            sys.stdout.flush()      # keep the plan above the summary
            self._print_stats(solver.name, metrics)
        return 0

    def _print_stats(self, solver_name: str, metrics: Metrics) -> None:
        """Print the secondary evaluation metrics on stderr.

        Args:
            solver_name: Label of the strategy that produced the plan.
            metrics: The validated plan's metrics.
        """
        rows = [
            ("solver", solver_name),
            ("turns", str(metrics.turns)),
            ("drones", str(metrics.drones)),
            ("moves", str(metrics.total_moves)),
            ("moves per turn", f"{metrics.moves_per_turn:.2f}"),
            ("turns per drone", f"{metrics.turns_per_drone:.2f}"),
            ("total path cost", str(metrics.total_cost)),
        ]
        print(file=sys.stderr)
        for label, value in rows:
            print(f"{label:<16}{value}", file=sys.stderr)

    def main(self, argv: list[str] | None = None) -> int:
        """Run the program, turning known failures into clean messages.

        Args:
            argv: Command line arguments, or None to read ``sys.argv``.

        Returns:
            0 on success, 1 on a handled failure.
        """
        args = self.build_arg_parser().parse_args(argv)
        try:
            return self.run(args)
        except FlyInError as error:
            print(f"error: {error}", file=sys.stderr)
        except BrokenPipeError:
            # The reader went away (e.g. piped into head): stop quietly.
            # stdout is pointed at devnull so the interpreter's final
            # flush does not raise a second time.
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except OSError as error:
            print(f"error: cannot read map: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(FlyInApp().main())
