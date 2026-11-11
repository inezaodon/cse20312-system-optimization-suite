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
| 3. Subtree profiler | ⏳ Not started |
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

All tests except one live smoke test run on hand-written JSON fixtures in [`fixtures/`](fixtures/), so results are the same on every machine.

## Trying the Monitor

```bash
# Live: 3 polls, 2 seconds apart, top 5 by CPU
python3 -c "from sysopt.engine.monitor import Monitor, format_poll_result; from sysopt.sources.live import LiveSource; print(format_poll_result(Monitor(LiveSource(), k=5).run(3, 2.0)[-1]))"

# Record your own session (10 polls), then replay it offline
python3 -c "from sysopt.sources.live import LiveSource; from sysopt.sources.snapshot import record_session; record_session(LiveSource(), 10, 2.0, 'fixtures/recorded_session.json')"
```

A command-line interface (`python3 -m sysopt top|watch|tree|families|leaks`) comes in Phase 3.

On macOS, about a third of processes belong to the system and deny access to CPU and memory readings when run without `sudo`. These are marked `restricted` and left out of the rankings.

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
  structures/   custom data structures (heap, hash table; graph and linked list coming)
  sources/      process data sources (live psutil / JSON snapshots)      [Phase 2]
  engine/       registry, idle detection, monitor                        [Phase 2]
  profiler/     process subtree aggregation                              [Phase 3]
  leaksim/      simulated heap and leak detection                        [Phase 4]
  viz/          matplotlib charts                                        [Phase 5]
tests/          unittest files
benchmarks/     benchmark scripts and results
fixtures/       JSON process snapshots for tests
report/         final report and figures
```
