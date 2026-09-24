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
make run              # run on the default map
make lint             # flake8 + mypy
make test             # unit tests
make bench            # every provided map, with turn counts
make clean            # remove caches
```

Running directly:

```bash
python3 main.py maps/easy/02_simple_fork.txt
python3 main.py maps/hard/01_maze_nightmare.txt --visual
python3 main.py maps/medium/02_circular_loop.txt --stats
python3 main.py maps/easy/01_linear_path.txt --turns-only
```

| flag | effect |
|---|---|
| `--solver NAME` | routing strategy (default `shortest`) |
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
 ├── solver.py      Network -> Plan             (strategy, abstract base)
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

- **`Solver`** (abstract) → `ShortestPathSolver`. Adding a strategy
  means adding a subclass; `main.py` and the simulator are unchanged.
- **`Renderer`** (abstract) → `PlainRenderer`, `GridRenderer`. The same
  plan renders as machine readable text or as an animation.
- **`FlyInError`** → `ParseError`, `ValidationError`,
  `UnsolvableMapError`, `SimulationError`. One `except` in `main`
  catches every user facing failure; programming mistakes still raise
  built-in exceptions so they surface as tracebacks.

`ZoneType` is an enum rather than a class hierarchy, because the four
types differ in *data* (cost, passability) rather than in behaviour.

## Algorithm

### Pathfinding — Dijkstra, not BFS

Entering a `restricted` zone costs two turns, so edges are weighted and
breadth-first search gives the wrong answer. `medium/03_priority_puzzle`
proves it: two routes with an identical **four hops** but costs of four
and five turns. BFS would consider them equivalent and could return the
slower one — no crash, just a worse score.

The search key is `(cost, -priority_zones_seen)`. Python compares tuples
left to right, so cost decides the route and the second term only breaks
ties. This is how the subject's *"priority zones should be prioritized"*
is honoured **without** making them cheaper, which would break the
integer turn model the whole simulation rests on.

`heapq` provides the priority queue. It is a general purpose data
structure, not graph logic; every traversal is written from scratch, as
the subject requires.

Complexity: `O(E log V)` time, `O(V)` memory. The path is computed once
and cached in the plan, never recomputed per drone.

### Scheduling

Drones are released down the chosen route at a fixed interval and walk
it step by step. A restricted step emits two moves — one on the
connection, one on arrival — and advances the clock by two turns.

The release interval is `2` when the route contains a restricted zone
and `1` otherwise, because a restricted crossing occupies its
connection for both turns of the transit. **This is a known
inefficiency**: one restricted zone anywhere slows the whole fleet for
the entire journey, even across sections that are wide open.

### Known limitations

- **Only one route is used.** `easy/02_simple_fork` offers two branches
  and this solver uses one. A max-flow based solver would split the
  fleet across both.
- **Capacities are not exploited.** `max_drones` and
  `max_link_capacity` are never read by the solver. Releasing one drone
  per turn can never exceed a limit of one or more, so plans are
  *correct* — but `easy/03_basic_capacity` has zones rated for two and
  three drones and links rated for four, all under-used.

Both are what a flow based solver exists to fix, and the abstract
`Solver` base is already in place for it.

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
at once.

## Visual representation

`--visual` draws the network on the zones' declared `x`/`y`
coordinates, one frame per turn.

```
turn 3
                 loop_d        loop_c
   start:4       loop_a:1      loop_b       !exit_point    goal
  in flight: D1->loop_b-exit_point
  moves: D1-loop_b-exit_point D2-loop_a
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
| easy/02_simple_fork | 4 | 6 | ≤ 8 | ✅ |
| easy/03_basic_capacity | 4 | 6 | ≤ 6 | ✅ |
| medium/01_dead_end_trap | 5 | 8 | ≤ 12 | ✅ |
| medium/02_circular_loop | 6 | 15 | ≤ 15 | ✅ |
| medium/03_priority_puzzle | 5 | 8 | ≤ 12 | ✅ |
| hard/01_maze_nightmare | 8 | 13 | ≤ 30 | ✅ |
| hard/02_capacity_hell | 12 | 16 | ≤ 35 | ✅ |
| hard/03_ultimate_challenge | 15 | 26 | ≤ 45 | ✅ |
| challenger/the_impossible_dream | 25 | 67 | 45 | ❌ |

Every mandatory target is met. The challenger map is not solved
competitively: its entry gate admits one drone per turn and the
cost-minimal route is 19 turns, giving a theoretical floor of **43
turns**. Reaching that needs the fleet spread across several parallel
routes, which the single-path solver cannot do.

Reproduce with `make bench`.

## Resources

- Dijkstra, E. W. — *A Note on Two Problems in Connexion with Graphs*
  (1959). The shortest path algorithm used for routing.
- Ford, L. R. & Fulkerson, D. R. — *Constructing Maximal Dynamic Flows
  from Static Flows* (1958). Flows over time; the basis for a
  makespan-optimal solver.
- Dinic, Y. — *Algorithm for Solution of a Problem of Maximum Flow*
  (1970). Max-flow, for the planned multi-path solver.
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

The data model, the graph container, the Dijkstra implementation and
the test suite were written by hand, with Claude reviewing.
