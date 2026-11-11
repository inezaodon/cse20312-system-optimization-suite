# Unified System Resource & Memory Optimization Suite

CSE 20312 final project. A system diagnostic tool built on custom data structures:

1. **Core Engine**: ranks resource-heavy processes and flags idle ones.
2. **Subtree Profiler**: totals CPU/RAM across process families using graph traversal.
3. **Memory Leak Simulator**: simulates `malloc`/`free` and finds leaked blocks by reachability.

See [`project_proposal.md`](project_proposal.md) for the design and [`BUILD_PLAN.md`](BUILD_PLAN.md) for the build plan.

## Status

| Phase | Status |
| :--- | :--- |
| 0. Setup | ✅ Done |
| 1. Bootstrap data structures + benchmarks | ✅ Done |
| 2. Data sources, ingestion & ranking | ✅ Done |
| 3. Subtree profiler + command-line tool | ✅ Done |
| 4. Memory leak simulator | ⏳ Not started |
| 5. Charts, testing pass & report | ⏳ Not started |

## Setup

Requires Python 3.9+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the Tests

Run from the project root:

```bash
python3 -m unittest discover -v
```

| Module (sample functions) | Test file | What the tests check |
| :--- | :--- | :--- |
| [`sysopt/structures/heap.py`](sysopt/structures/heap.py): `MaxHeap`, `MinHeap`, `top_k` | [`tests/test_heap.py`](tests/test_heap.py) | Extract order matches `sorted()`, heap property after every operation, `build_heap`, top-K edge cases (k = 0, k > n, duplicates) |
| [`sysopt/structures/hash_table.py`](sysopt/structures/hash_table.py): `ChainedHashTable`, `hash_key` | [`tests/test_hash_table.py`](tests/test_hash_table.py) | Insert/get/update/delete, forced collisions, resizing at load factor 0.75, `(pid, create_time)` keys, 1,000 random operations checked against `dict` |
| [`sysopt/sources/`](sysopt/sources/): `ProcessSnapshot`, `SnapshotSource`, `record_session`, `LiveSource` | [`tests/test_sources.py`](tests/test_sources.py) | Fixture loading and validation, record/replay round trip, `psutil` `AccessDenied` / `NoSuchProcess` / first-sample handling (with fake processes), one live smoke test |
| [`sysopt/engine/registry.py`](sysopt/engine/registry.py), [`idle.py`](sysopt/engine/idle.py): `ProcessRegistry`, `IdleTracker` | [`tests/test_registry_idle.py`](tests/test_registry_idle.py) | Process exit, PID reuse, re-parenting, idle exactly at T (not before), CPU spikes reset the timer, unknown CPU is never idle |
| [`sysopt/engine/monitor.py`](sysopt/engine/monitor.py): `Monitor` | [`tests/test_monitor.py`](tests/test_monitor.py) | Top-K by CPU and RAM, idle candidates and RAM savings, user-only filter, minimum-size filter, output formatting |
| [`sysopt/structures/graph.py`](sysopt/structures/graph.py): `DirectedGraph` | [`tests/test_graph.py`](tests/test_graph.py) | BFS and DFS order, same nodes from both, cycles terminate, multi-source `reachable`, vertex/edge removal, 5,000-deep chain without recursion errors |
| [`sysopt/profiler/subtree.py`](sysopt/profiler/subtree.py): `ProcessTree` | [`tests/test_subtree.py`](tests/test_subtree.py) | Subtree totals match hand-calculated values (BFS and DFS), re-parented orphans, app families, name search, tree rendering |
| [`sysopt/cli.py`](sysopt/cli.py): `main` | [`tests/test_cli.py`](tests/test_cli.py) | Every command on fixtures, recording with `--record`, error messages and exit codes |

All tests except one live smoke test run on hand-written JSON fixtures in [`fixtures/`](fixtures/), so results are the same on every machine.

## Command-Line Tool

Run from the project root with the virtual environment active. Every command reads this computer by default; add `--source PATH` to replay a JSON fixture instead.

```bash
# Top 10 processes by CPU (or --metric ram)
python3 -m sysopt top

# Poll every 2 seconds; show top processes, idle apps, and the RAM they hold. Ctrl-C to stop.
python3 -m sysopt watch --idle-secs 300 --min-rss 50

# Same, and save every poll so it can be replayed later
python3 -m sysopt watch --polls 10 --record fixtures/recorded_session.json

# One app's whole process family (BFS or DFS), with totals
python3 -m sysopt tree --name chrome --depth 2
python3 -m sysopt tree --pid 1 --method dfs --depth 1

# Biggest app families: each app plus every process it spawned
python3 -m sysopt families --k 10 --mine

# Any command on recorded or hand-written data
python3 -m sysopt families --source fixtures/small_tree.json
```

Example on the hand-written test data (`tree --source fixtures/small_tree.json --name browser`):

```
Browser (20) family: 4 processes, 40.0% CPU, 900.0 MB RAM
Browser (20)  cpu 10.0%  ram 200.0 MB
└── Browser Helper (GPU) (21)  cpu 20.0%  ram 300.0 MB
    ├── Browser Helper (Renderer) (23)  cpu 6.0%  ram 250.0 MB
    └── Browser Helper (Renderer) (22)  cpu 4.0%  ram 150.0 MB
```

On a real Mac, `families` rolls a browser's dozens of helper processes into one line with their combined CPU and RAM.

**Notes on macOS:**
- About a third of processes belong to the system and deny access to CPU and memory readings when run without `sudo`. These are marked `restricted` and left out of the rankings.
- Idle means "CPU below a threshold for T seconds." The OS doesn't report when you last used an app.
- Safari tabs and other WebKit pages (`com.apple.WebKit.WebContent`) are started by launchd rather than by the app, so each one shows up as its own family.
- Recorded sessions list every process on your machine, so `fixtures/recorded_*.json` is in `.gitignore`.

## Bootstrap Benchmarks

The custom heap and hash table are compared against Python's built-in `heapq` and `dict` at n = 100 to 100,000:

```bash
python3 benchmarks/bench_heap.py
python3 benchmarks/bench_hash_table.py
python3 benchmarks/plot_benchmarks.py
```

Results go to `benchmarks/results/*.csv`, and charts to `report/figures/`. The built-ins are written in C, so they run about 15–50× faster. Both versions grow at the same rate: the fitted log–log slopes match. For example, push/pop is 1.12 for the custom heap and 1.11 for `heapq`, and build-heap is 1.00 vs. 0.99.

![Heap benchmarks](report/figures/bench_heap.png)
![Hash table benchmarks](report/figures/bench_hash_table.png)

## Project Layout

```
sysopt/
  structures/   custom data structures: heap, hash table, directed graph (linked list in Phase 4)
  sources/      process data: live psutil, JSON replay, recording
  engine/       process registry, idle detection, monitor
  profiler/     process trees, subtree totals, app families
  cli.py        command-line tool (python3 -m sysopt ...)
  leaksim/      simulated heap and leak detection                        [Phase 4]
  viz/          matplotlib charts                                        [Phase 5]
tests/          unittest files
benchmarks/     benchmark scripts and results
fixtures/       JSON process snapshots for tests
report/         final report and figures
```
