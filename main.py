"""Command line entry point for the Fly-in drone routing simulation."""

import argparse
import sys

from errors import FlyInError
from parser import MapParser
from renderer import (
    GridRenderer,
    PlainRenderer,
    Renderer,
)
from simulator import Simulator
from solver import ShortestPathSolver, Solver

SOLVERS: dict[str, type[Solver]] = {
    "shortest": ShortestPathSolver,
}


def build_arg_parser() -> argparse.ArgumentParser:
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
        choices=sorted(SOLVERS),
        default="shortest",
        help="routing strategy to use (default: shortest)",
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


def run(args: argparse.Namespace) -> int:
    """Parse a map, solve it, verify the plan and display it.

    The plan is validated before anything is printed, so an illegal
    plan reports an error rather than showing output that looks right.

    Args:
        args: Parsed command line arguments.

    Returns:
        A process exit status.
    """
    network = MapParser().parse_file(args.map)
    plan = SOLVERS[args.solver](network).solve()
    metrics = Simulator(network).validate(plan)

    if args.turns_only:
        print(metrics.turns)
    elif not args.quiet:
        renderer: Renderer = (
            GridRenderer(network) if args.visual else PlainRenderer(network)
        )
        renderer.render(plan)

    if args.stats:
        sys.stdout.flush()      # keep the plan above the summary
        print(f"\nturns           {metrics.turns}", file=sys.stderr)
        print(f"drones          {metrics.drones}", file=sys.stderr)
        print(f"moves           {metrics.total_moves}", file=sys.stderr)
        print(
            f"moves per turn  {metrics.moves_per_turn:.2f}",
            file=sys.stderr,
        )
        print(
            f"turns per drone {metrics.turns_per_drone:.2f}",
            file=sys.stderr,
        )
        print(f"total path cost {metrics.total_cost}", file=sys.stderr)
    return 0


def main() -> int:
    """Run the program, turning known failures into clean messages.

    Returns:
        0 on success, 1 on a handled failure.
    """
    args = build_arg_parser().parse_args()
    try:
        return run(args)
    except FlyInError as error:
        print(f"error: {error}", file=sys.stderr)
    except OSError as error:
        print(f"error: cannot read map: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
