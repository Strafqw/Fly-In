*This project has been created as part of the 42 curriculum by joasampa.*

# Fly-in

## Description

Fly-in routes a fleet of autonomous drones from a central base to a
target location across a network of connected zones, in the fewest
possible simulation turns.

The map is an undirected graph. Zones have a capacity and a traversal
cost; connections have a capacity of their own. Drones move
simultaneously, so the problem is not simply "find the shortest path"
but "schedule a whole fleet through a constrained network without
anyone colliding".

The program reads a map file, computes a routing plan, verifies that
plan against every rule in the subject, and prints it turn by turn —
either in the required machine readable format or as a colour coded
grid animation.

## Instructions

Python 3.10 or later. The simulation itself uses only the standard
library; `flake8`, `mypy` and `pytest` are development dependencies.

```bash
make install          # create a virtualenv and install the toolchain
make run              # run on the default map (MAP=<path> to change)
make visual           # same, with the colour grid view and metrics
make lint             # flake8 + mypy (installs the toolchain if needed)
make test             # unit tests
make bench            # every provided map, with turn counts
make clean            # remove caches and the virtualenv
```

`run`, `visual`, `debug` and `bench` only need the standard library, so
they use the system `python3` and work even without `make install`.

Running directly:

```bash
python3 main.py maps/easy/02_simple_fork.txt
python3 main.py maps/hard/01_maze_nightmare.txt --visual
python3 main.py maps/medium/02_circular_loop.txt --stats
python3 main.py maps/easy/01_linear_path.txt --turns-only
```

| flag | effect |
|---|---|
| `--solver NAME` | routing strategy: `reservation` (default) or the `shortest` baseline |
| `--visual` | colour coded grid animation instead of raw output |
| `--stats` | secondary metrics, on stderr |
| `--turns-only` | print just the turn count, for scripting |
| `--quiet` | suppress the turn by turn output |

## Example

Input — `maps/easy/01_linear_path.txt`:

```
# Easy Level 1: Simple linear path
nb_drones: 2

start_hub: start 0 0 [color=green]
hub: waypoint1 1 0 [color=blue]
hub: waypoint2 2 0 [color=blue]
end_hub: goal 3 0 [color=red]

connection: start-waypoint1
connection: waypoint1-waypoint2
connection: waypoint2-goal
```

Output:

```
D1-waypoint1
D1-waypoint2 D2-waypoint1
D1-goal D2-waypoint2
D2-goal
```

Four turns: D1 leaves first, D2 follows one turn behind, and the two
pipeline down the corridor rather than queueing at the start.

On a map with a restricted zone, a drone in transit is reported by the
name of the connection it is crossing:

```
D1-loop_b-exit_point       # in flight, occupying the connection
D1-exit_point              # landed, one turn later
```

## Architecture

```
main.py        CLI: parse -> solve -> validate -> render
 │
 ├── parser.py      map text  -> Network        (the only file that
 │                                               knows the file format)
 ├── network.py     the graph: zones, adjacency, structural validation
 │   ├── zone.py         Zone, ZoneType, capacity and cost rules
 │   └── connection.py   Connection: identity, naming, traversal
 │
 ├── solver.py      Network -> Plan             (strategies, abstract base)
 ├── plan.py        Move / Turn / Plan          (the shared vocabulary)
 ├── simulator.py   Plan    -> Metrics          (the referee)
 ├── renderer.py    Plan    -> screen           (abstract base)
 └── errors.py      one exception hierarchy, caught in main
```

Each layer knows strictly less than the one above it. The parser is the
only place that knows maps are text files; the solver is the only place
that decides anything; the simulator is the only place that judges.

### Object orientation

Three genuine polymorphic hierarchies, not classes used as namespaces:

- **`Solver`** (abstract) → `ReservationSolver`, `ShortestPathSolver`.
  Adding a strategy means adding a subclass; `main.py` and the
  simulator are unchanged.
- **`Renderer`** (abstract) → `PlainRenderer`, `GridRenderer`. The same
  plan renders as machine readable text or as an animation.
- **`FlyInError`** → `ParseError`, `ValidationError`,
  `UnsolvableMapError`, `SimulationError`. One `except` in `main`
  catches every user facing failure; programming mistakes still raise
  built-in exceptions so they surface as tracebacks.

`main.py` is the `FlyInApp` class; the only module-level code is the
`if __name__ == "__main__"` guard that instantiates it.

`ZoneType` is an enum rather than a class hierarchy, because the four
types differ in *data* (cost, passability) rather than in behaviour.

## Algorithm

The default strategy, `ReservationSolver`, plans drones **one at a
time through space and time**, each around the drones already planned.
The `ShortestPathSolver` baseline is kept for comparison
(`--solver shortest`).

### Reservation tables

The solver keeps two counters, filled in as drones are planned:

- `zone_use[(zone, turn)]` — drones standing in a zone at the end of a
  turn, limited by `max_drones` (start and end hubs are unlimited);
- `link_use[(link, turn)]` — drones crossing a connection during a
  turn, limited by `max_link_capacity`. A restricted crossing holds
  its link for **both** turns.

A drone may only use what earlier drones left free, so no plan can
ever exceed a capacity, and capacities above 1 are actually used.

### Space-time search — A\*

Each drone searches over `(zone, turn)` states. From a state it may:

- **wait** — stay where it is for a turn, if the zone has room on the
  next turn (at the start hub, which is unlimited, it jumps straight to
  the next turn at which some exit is free);
- **move** to a neighbouring zone, if the link has room on every turn
  of the crossing and the destination has room on arrival — a drone may
  never wait on a connection.

Because waiting is just another move, *strategic waiting* comes for
free, and once the short route is booked the next drone's earliest
arrival naturally goes another way — the fleet **spreads across
several paths** without any explicit path splitting.

The search is A\* ordered by `turn + cost_to_end(zone)`.
`cost_to_end` comes from one reverse Dijkstra from the end hub,
weighted by entry cost (restricted = 2). It never overestimates, so
the first time the end hub comes off the queue is this drone's
earliest possible arrival. Zones that cannot reach the end at all are
absent from that table and never entered, which prunes dead ends.

Ties are broken in favour of routes through more `priority` zones:
the queue key is `(estimate, -priority_zones_seen, ...)`, and tuples
compare left to right, so arrival time still decides and priority only
breaks ties. That honours *"priority zones should be prioritized"*
without making them cheaper, which would break the integer turn model.

`heapq` provides the priority queue. It is a general purpose data
structure, not graph logic; every traversal is written from scratch,
as the subject requires.

### Why it cannot deadlock

A drone only ever books slots that are free, and it never gives back
a slot it booked. The start hub has unlimited room, so the worst case
for any drone is to wait there until the network has cleared — a
route always exists if the end is reachable at all.

### Complexity

- Static costs: one Dijkstra, `O(E log V)`.
- Per drone: an A\* over the states it actually explores, roughly its
  path length plus the waiting it needs. Reservations only grow, so
  the earliest free exit from the start is remembered between drones
  instead of being rescanned (`_floor`), which keeps a large fleet
  linear.
- Memory: the two reservation counters, one entry per (zone or link,
  turn) actually used — proportional to the total number of moves.

Measured: 50 000 drones on a two-corridor map in about 1.4 s.

### Limitations

Planning one drone at a time is greedy: an early drone takes the best
slot for itself, which is not always best for the fleet as a whole.
On every provided map this reaches or beats the reference — the
challenger map is solved in 43 turns, which is the theoretical floor
(see Performance) — but an adversarial map could exist where a joint
optimisation does better.

### Verification

The simulator is deliberately **independent** of the solver. It imports
nothing from it, reuses none of its logic, and derives every rule from
the subject text. It takes a plan as a set of claims — *"on turn 3,
drone 2 is at loop_b"* — and checks each one:

- a drone only moves to a zone connected to where it stands
- no drone enters a `blocked` zone
- zone occupancy never exceeds `max_drones` (start and end exempt)
- connection use never exceeds `max_link_capacity`
- a drone in flight lands on the very next turn and never lingers
- no drone moves twice in a turn, or after being delivered
- every drone reaches the end hub

If the two shared code, a shared misreading would be invisible — both
would be wrong together and every plan would look valid. Keeping them
separate is what lets a disagreement surface.

Occupancy is checked on the state **after** the whole turn is applied,
never move by move, because the subject says a departing drone frees
its space during the same turn — so a full corridor may shift forward
at once. It is kept as a running count updated by each move, so
validating a turn costs time proportional to the moves in it, not to
the size of the fleet.

## Visual representation

`--visual` draws the network on the zones' declared `x`/`y`
coordinates, one frame per turn.

```
turn 3
                 loop_d        loop_c
   start:1       loop_a:2      loop_b:2     !exit_point    goal
  in flight: D1->loop_b-exit_point
  moves: D1-loop_b-exit_point D3-loop_b D5-loop_a
```

- each zone sits at its own coordinates, so the **shape** of the map is
  visible — forks, loops and dead ends are laid out as the map declares
  them
- zones are tinted with their `color=` tag, using 256-colour codes;
  occupied zones are bold, empty ones dimmed
- `name:N` shows how many drones are inside
- `+` marks a priority zone, `!` restricted, `#` blocked
- drones crossing a connection are listed on their own line, because
  during that turn they occupy **no zone at all**
- zones declared on the same coordinates as another are listed on a
  `stacked:` line, so no zone is ever hidden
- `make visual` adds the secondary metrics (`--stats`): moves per
  turn, average turns per drone, total path cost

What this adds over the raw `D1-roof1` output: bottlenecks become
visible. You can watch drones back up behind a capacity-1 zone, see one
branch of a fork sit unused, and see a restricted crossing take a drone
off the board for a turn. The raw format tells you what happened; the
grid tells you *why* the turn count is what it is.

Cell width adapts to the terminal, and colour is disabled automatically
when output is redirected or `NO_COLOR` is set, so logs stay readable.

## Interpretation decisions

The subject leaves three things unstated. Each was resolved
deliberately:

**A restricted crossing occupies its connection for both turns.** The
spec says a drone "occupies the connection during transit" without
saying how that counts against `max_link_capacity`. Taking it as two
turns yields exactly **15 turns** on `medium/02_circular_loop` — the
subject's stated target for that map. The looser reading would finish
in 10, making the published target strangely generous.

**Connection names follow map file order.** The output format requires
`D<ID>-<connection>` for drones in flight but never defines a
connection's name. We join the endpoints in the order they were
declared, mirroring the `connection: <a>-<b>` syntax. Note this differs
deliberately from `Connection.key`, which sorts the endpoints so that
`a-b` and `b-a` are detected as duplicates.

**`nb_drones` is the first *meaningful* line, not literally line 1.**
The subject says "the first line must define the number of drones", but
every provided map opens with a comment — it is on line 2 of
`easy/01_linear_path` and line 6 of the challenger map. A literal
reading rejects all ten maps, so comments and blank lines are skipped
first.

## Performance

| map | drones | turns | target | |
|---|---|---|---|---|
| easy/01_linear_path | 2 | 4 | ≤ 6 | ✅ |
| easy/02_simple_fork | 4 | 4 | ≤ 8 | ✅ |
| easy/03_basic_capacity | 4 | 4 | ≤ 6 | ✅ |
| medium/01_dead_end_trap | 5 | 8 | ≤ 12 | ✅ |
| medium/02_circular_loop | 6 | 15 | ≤ 15 | ✅ |
| medium/03_priority_puzzle | 5 | 7 | ≤ 12 | ✅ |
| hard/01_maze_nightmare | 8 | 13 | ≤ 30 | ✅ |
| hard/02_capacity_hell | 12 | 16 | ≤ 35 | ✅ |
| hard/03_ultimate_challenge | 15 | 26 | ≤ 45 | ✅ |
| challenger/the_impossible_dream | 25 | 43 | record 45 | ✅ |

Every target is met or beaten, including the bonus: the challenger
map's entry gate admits one drone per turn and its cost-minimal route
is 19 turns, so **43 turns is the theoretical floor** — and that is
what the solver reaches.

For comparison, the single-path baseline (`--solver shortest`) needs
6 turns on both `simple_fork` and `basic_capacity`, and 67 on the
challenger map.

Reproduce with `make bench`; `make test` checks every map against its
target.

## Resources

- Dijkstra, E. W. — *A Note on Two Problems in Connexion with Graphs*
  (1959). The shortest path algorithm used for routing.
- Ford, L. R. & Fulkerson, D. R. — *Constructing Maximal Dynamic Flows
  from Static Flows* (1958). Flows over time; the basis for a
  makespan-optimal solver.
- Silver, D. — *Cooperative Pathfinding* (2005). Space-time A\* with a
  reservation table; the approach `ReservationSolver` follows.
- Hart, P. E., Nilsson, N. J. & Raphael, B. — *A Formal Basis for the
  Heuristic Determination of Minimum Cost Paths* (1968). The A\*
  algorithm and why an admissible heuristic finds an optimal path.
- 42's *lem-in* project — the same core problem without edge weights or
  edge capacities; a useful source of prior art on distributing a fleet
  across several paths.
- Stern et al. — *Multi-Agent Path Finding: Definitions, Variants and
  Benchmarks* (2019). Vocabulary for makespan optimisation.
- Python documentation: `heapq`, `dataclasses`, `abc`, `typing`.
- PEP 8, PEP 257, and the `mypy` and `flake8` manuals.

### Use of AI

Claude (Anthropic) was used throughout as an explanatory and review
tool rather than as a code generator of last resort. Specifically:

- **Subject analysis.** Reading the ten provided maps and surfacing
  three contradictions between the spec text and the actual files:
  `nb_drones` never appearing on line 1, negative coordinates, and the
  fact that none of the provided maps exercises any error path.
- **Design discussion.** Working through the decisions recorded above —
  enum versus subclasses for `ZoneType`, where the start/end capacity
  exemption should live, why `Connection` needs both `name` and `key`,
  whether `other()` is necessary or whether adjacency should
  pre-compute neighbours.
- **Algorithm explanation.** Dijkstra, priority queues, and why
  breadth-first search is insufficient here.
- **Review.** Reading drafts and identifying bugs — a neighbour loop
  outside its `while`, a property that called itself, missing
  `@dataclass` decorators, a test with no assertion.
- **Code written by Claude**, reviewed and understood before being
  kept: the parser's helper methods, the simulator, `renderer.py`,
  `main.py`, and parts of this README.
- **Pre-submission pass by Claude**, reviewed together line by line
  afterwards: a full test of the project against the subject (an
  independent output checker and some forty edge-case maps), then the
  fixes it led to — `ReservationSolver` (space-time A\* with
  reservation tables), the incremental occupancy count in the
  simulator and renderer, the `FlyInApp` class, clean handling of
  non-UTF-8 files and closed pipes, the Makefile rework, and the
  parser, solver and simulator tests.

The data model, the graph container, the Dijkstra implementation and
the original test suite were written by hand, with Claude reviewing.
