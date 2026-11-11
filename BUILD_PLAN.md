# Build Plan: Unified System Resource & Memory Optimization Suite

This plan takes the project from an empty folder to a finished, tested, documented submission. It follows `project_proposal.md`. Each step lists exactly what to build and a **"Done when"** check to confirm before moving on.

**Total budget:** about 14 hours of work plus a 1-hour buffer, in 6 phases (Phase 0 is 15 minutes of setup).

---

## 0. Ground Rules

* **Python version:** this machine has **Python 3.9.6**. To stay compatible:
  * Put `from __future__ import annotations` at the top of every module (this allows `list[int]` and `X | None` in type hints).
  * Don't use `match` statements (3.10+).
* **Dependencies:** only `psutil` and `matplotlib` (`numpy` comes with `matplotlib`). Everything else comes from the standard library.
* **No built-ins inside custom structures:** `MaxHeap` must not use `heapq`. `ChainedHashTable` must not store entries in a `dict`. Python lists are allowed as the underlying array and as buckets.
* **Deterministic tests:** tests never read live system data. They use JSON fixtures through `SnapshotSource`.
* **Commit after every "Done when"** if you use git.

---

## 1. Final Folder Layout

```
DS Project/
├── project_proposal.md
├── BUILD_PLAN.md
├── README.md
├── requirements.txt
├── sysopt/                      # main package
│   ├── __init__.py
│   ├── __main__.py              # enables `python3 -m sysopt ...`
│   ├── cli.py
│   ├── structures/              # all custom data structures
│   │   ├── __init__.py
│   │   ├── heap.py              # MaxHeap, MinHeap, top_k
│   │   ├── hash_table.py        # ChainedHashTable
│   │   ├── graph.py             # DirectedGraph (BFS, DFS, reachable)
│   │   └── linked_list.py       # DoublyLinkedList
│   ├── sources/                 # where process data comes from
│   │   ├── __init__.py
│   │   ├── base.py              # ProcessSnapshot, ProcessSource
│   │   ├── live.py              # LiveSource (psutil)
│   │   └── snapshot.py          # SnapshotSource (JSON) + recorder
│   ├── engine/                  # Subsystem 1
│   │   ├── __init__.py
│   │   ├── registry.py          # ProcessRegistry
│   │   ├── idle.py              # IdleTracker
│   │   └── monitor.py           # Monitor (poll loop, ranking, savings)
│   ├── profiler/                # Subsystem 2
│   │   ├── __init__.py
│   │   └── subtree.py           # build_process_graph, subtree_totals
│   ├── leaksim/                 # Subsystem 3
│   │   ├── __init__.py
│   │   ├── heap_sim.py          # SimulatedHeap, Block, errors
│   │   └── scenarios.py         # scripted demo programs
│   └── viz/
│       ├── __init__.py
│       └── charts.py            # matplotlib charts
├── fixtures/                    # JSON process snapshots for tests and demos
│   ├── small_tree.json
│   ├── idle_sequence.json
│   ├── edge_cases.json
│   └── recorded_session.json    # recorded from your machine in Phase 2
├── tests/
│   ├── test_heap.py
│   ├── test_hash_table.py
│   ├── test_graph.py
│   ├── test_linked_list.py
│   ├── test_sources.py
│   ├── test_registry_idle.py
│   ├── test_monitor.py
│   ├── test_subtree.py
│   └── test_leaksim.py
├── benchmarks/
│   ├── bench_heap.py
│   ├── bench_hash_table.py
│   ├── plot_benchmarks.py
│   └── results/                 # CSV output
└── report/
    ├── REPORT.md
    └── figures/                 # PNG charts
```

---

## Phase 0: Setup (≈ 15 min)

1. Create the virtual environment and install the dependencies:
   ```bash
   cd "/Users/odon/Desktop/DS Project"
   python3 -m venv .venv
   source .venv/bin/activate
   pip install psutil matplotlib
   pip freeze | grep -iE "psutil|matplotlib" > requirements.txt
   ```
2. Create the folder layout above, with an empty `__init__.py` in each package folder.
3. Optional: run `git init`, and add a `.gitignore` containing `.venv/`, `__pycache__/`, and `benchmarks/results/`.

**Done when:** `python3 -c "import psutil, matplotlib; print('ok')"` prints `ok` inside the venv, and `python3 -m unittest discover -s tests` runs (0 tests is fine).

---

## Phase 1: Bootstrap Data Structures (≈ 3.0 h)

### 1.1 `structures/heap.py`: MaxHeap, MinHeap, top_k (≈ 1.0 h)

```python
class MaxHeap:
    def __init__(self, key=None):          # key(item) -> comparable; default identity
    def __len__(self) -> int
    def is_empty(self) -> bool
    def peek(self)                          # raises IndexError if empty
    def insert(self, item) -> None          # append, then _heapify_up
    def extract_max(self)                   # swap root with last, pop, _heapify_down
    def build_heap(self, items) -> None     # bottom-up, O(N): from (n//2 - 1) down to 0
    def _parent(i): return (i - 1) // 2
    def _left(i):   return 2 * i + 1
    def _right(i):  return 2 * i + 2
    def _higher(self, a, b) -> bool         # True if a should sit above b
    def _heapify_up(self, i) -> None
    def _heapify_down(self, i) -> None
    def is_valid(self) -> bool              # checks the heap property at every index (used by tests)

class MinHeap(MaxHeap):
    def _higher(self, a, b) -> bool         # reversed comparison; extract_max acts as extract_min
    # add an alias: extract_min = MaxHeap.extract_max

def top_k(items, k, key=None) -> list:
    """K largest items, sorted largest first. O(N log K) time, O(K) space.
    Keep a MinHeap of size k. For each item: if size < k, insert it;
    else if item > heap root, replace the root and heapify down.
    At the end, extract everything and reverse the order."""
```

Edge cases to handle: `k <= 0` returns `[]`; `k > N` returns all items sorted; duplicate values; extracting from an empty heap raises `IndexError`.

**Done when:** `tests/test_heap.py` passes:
* random insert sequences: `extract_max` output equals `sorted(data, reverse=True)`
* `is_valid()` is true after every insert and every extract
* `build_heap` on random data gives a valid heap
* `top_k` matches `sorted(...)[:k]` for k = 0, 1, 5, N, N + 3, and for data with duplicates
* `key=` works (for example, ranking dicts by `"cpu"`)

### 1.2 `structures/hash_table.py`: ChainedHashTable (≈ 1.0 h)

```python
class ChainedHashTable:
    def __init__(self, capacity: int = 8, max_load: float = 0.75)
    def _hash(self, key) -> int             # custom hash function, see below
    def _index(self, key) -> int            # _hash(key) % capacity
    def __setitem__(self, key, value)       # insert or update; resize if load > max_load
    def __getitem__(self, key)              # raises KeyError if missing
    def __delitem__(self, key)              # raises KeyError if missing
    def __contains__(self, key) -> bool
    def __len__(self) -> int
    def get(self, key, default=None)
    def keys(self) / values(self) / items(self)   # generators
    def load_factor(self) -> float
    def _resize(self, new_capacity) -> None       # double the capacity and rehash every entry
    # Attributes: self._buckets = [[] for _ in range(capacity)], each bucket a list of [key, value]
```

**Custom hash function:** write your own instead of calling Python's `hash()`:
* `int`: multiplicative hashing, `(key * 2654435761) & 0xFFFFFFFF`
* `str`: polynomial rolling hash, `h = h * 31 + ord(c)`, masked to 32 bits
* `float`: hash `int(key * 1000)` (for example, a process `create_time`)
* `tuple`: combine the element hashes, `h = h * 31 + hash_elem(e)`, masked. Process keys are `(pid, create_time)` tuples.
* anything else: raise `TypeError`

**Done when:** `tests/test_hash_table.py` passes:
* insert / get / update / delete for 1,000 random keys match a reference `dict`
* forced collisions (capacity 1, or keys chosen to land in one bucket) still work
* resizing happens right after the load factor passes 0.75, and no entries are lost
* deleting or getting a missing key raises `KeyError`
* tuple keys `(pid, create_time)` work

### 1.3 Benchmarks (≈ 1.0 h)

`benchmarks/bench_heap.py` and `benchmarks/bench_hash_table.py`:
* Sizes: N = 100; 1,000; 10,000; 100,000. Use `random.seed(42)`.
* Time with `time.perf_counter()`. Repeat each measurement 5 times and keep the **median**.
* Heap experiments:
  * push N, then pop all: `MaxHeap` vs. `heapq` (push negated values)
  * build heap: `build_heap` vs. `heapq.heapify`
  * top-10: `top_k` vs. `heapq.nlargest`
* Hash table experiments: insert N, look up N, delete N: `ChainedHashTable` vs. `dict`.
* Write results to `benchmarks/results/heap.csv` and `hash_table.csv` with columns `experiment, impl, n, seconds`.

`benchmarks/plot_benchmarks.py`:
* For each experiment, draw a log–log plot of time vs. N with one line per implementation. Save to `report/figures/bench_*.png`.
* Print the fitted slope for each line (`numpy.polyfit(log n, log t, 1)`). A slope of about 1 means linear growth. N log N growth shows a slope slightly above 1.

**Done when:** `python3 benchmarks/bench_heap.py && python3 benchmarks/bench_hash_table.py && python3 benchmarks/plot_benchmarks.py` produces the CSVs and PNGs, and the slopes for custom and built-in versions are close to each other (the built-ins will just be faster by a constant factor).

---

## Phase 2: Data Sources, Ingestion & Ranking (≈ 3.0 h)

### 2.1 `sources/base.py` (≈ 15 min)

```python
@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    ppid: int
    name: str
    create_time: float
    cpu_percent: float        # 0.0 if unknown
    rss_mb: float             # 0.0 if unknown
    restricted: bool = False  # True if AccessDenied blocked a metric

    @property
    def key(self) -> tuple:   # (pid, create_time), unique even when PIDs get reused
        return (self.pid, self.create_time)

class ProcessSource(ABC):
    @abstractmethod
    def poll(self) -> tuple[float, list[ProcessSnapshot]] | None:
        """Returns (timestamp, snapshots), or None when no data is left."""
```

### 2.2 `sources/snapshot.py`: SnapshotSource + recorder (≈ 30 min)

JSON fixture format:
```json
{
  "polls": [
    {"t": 0.0, "processes": [
      {"pid": 1, "ppid": 0, "name": "launchd", "create_time": 100.0, "cpu_percent": 0.5, "rss_mb": 12.0}
    ]},
    {"t": 2.0, "processes": [ ... ]}
  ]
}
```

* `SnapshotSource(path)`: each `poll()` returns the next entry; returns `None` at the end.
* `record_session(source, n_polls, interval, out_path)`: polls any source and writes the results in the same JSON format. You'll use this to turn real data from your machine into a fixture.

Hand-write these fixtures:
* `small_tree.json`: one poll, about 10 processes in a known tree: `1 → {10, 20}`, `10 → {11, 12}`, `20 → {21}`, `21 → {22, 23}`, plus a "Browser" family. Pick round numbers so the sums are easy to check by hand.
* `idle_sequence.json`: about 8 polls, 60 s apart:
  * process A stays below 1% CPU the whole time (becomes idle)
  * process B spikes once in the middle (its idle timer resets)
  * process C is always busy
* `edge_cases.json`:
  * a process disappears between polls
  * a PID is reused with a new `create_time`
  * a child whose parent exits gets re-parented to PID 1
  * a `restricted: true` process

### 2.3 `sources/live.py`: LiveSource (≈ 45 min)

```python
class LiveSource(ProcessSource):
    def __init__(self, prime: bool = True)
    def poll(self) -> tuple[float, list[ProcessSnapshot]]
```

Implementation notes:
* Keep a cache `ChainedHashTable[(pid, create_time)] -> psutil.Process`. `cpu_percent(interval=None)` measures since the *previous call on the same object*, so the same object has to be reused across polls.
* **Priming:** in `__init__`, call `cpu_percent(None)` on every process, then `time.sleep(1.0)`. A process that shows up later reports 0.0 on its first poll, which is acceptable.
* Use `psutil.process_iter(['pid', 'ppid', 'name', 'create_time'])`.
* Read each metric inside `try/except`:
  * `psutil.NoSuchProcess`: skip the process (it has exited)
  * `psutil.AccessDenied`: set that metric to 0.0 and `restricted=True`
  * `psutil.ZombieProcess`: skip
* `rss_mb = memory_info().rss / (1024 * 1024)`
* Remove cache entries whose process no longer appears.

**Checkpoint:** record a real fixture:
```bash
python3 -c "from sysopt.sources.live import LiveSource; from sysopt.sources.snapshot import record_session; record_session(LiveSource(), 10, 2.0, 'fixtures/recorded_session.json')"
```

### 2.4 `engine/registry.py` + `engine/idle.py` (≈ 45 min)

```python
@dataclass
class ProcessRecord:
    snap: ProcessSnapshot
    first_seen: float
    last_seen: float
    below_since: float | None = None   # when CPU last dropped below the threshold
    is_idle: bool = False

class ProcessRegistry:
    """A ChainedHashTable keyed by (pid, create_time)."""
    def update(self, t: float, snaps: list[ProcessSnapshot]) -> tuple[list, list]:
        """Insert new processes, update existing ones, delete processes missing from this poll.
        Returns (added_keys, removed_keys)."""
    def get(self, key) -> ProcessRecord | None
    def by_pid(self, pid: int) -> ProcessRecord | None   # newest record for this PID
    def records(self) -> list[ProcessRecord]
    def __len__(self)

class IdleTracker:
    def __init__(self, cpu_threshold: float = 1.0, idle_seconds: float = 300.0)
    def update(self, rec: ProcessRecord, t: float) -> None:
        # if cpu < threshold: set below_since = t if it is None, and is_idle = (t - below_since >= idle_seconds)
        # else: below_since = None, is_idle = False
```

`by_pid` needs a lookup by PID alone. Keep a second `ChainedHashTable[pid] -> key` that is updated together with the main one.

**Done when:** `tests/test_registry_idle.py` passes, using `idle_sequence.json` and `edge_cases.json`:
* a process that exits is removed from the registry
* a reused PID with a new `create_time` is a different record
* idle exactly at `T`, not at `T − ε`
* one CPU spike resets the idle timer
* restricted processes don't crash anything

### 2.5 `engine/monitor.py`: Monitor (≈ 30 min)

```python
@dataclass
class PollResult:
    t: float
    top: list[ProcessRecord]        # top-K by the chosen metric
    idle: list[ProcessRecord]       # idle candidates, sorted by rss_mb descending
    savings_rss_mb: float           # total RSS of idle candidates
    process_count: int

class Monitor:
    def __init__(self, source, k=10, metric="cpu", cpu_threshold=1.0, idle_seconds=300.0)
    def poll_once(self) -> PollResult | None
    def run(self, n_polls: int | None, interval: float, on_result=print) -> list[PollResult]
```

Ranking: `top_k(registry.records(), k, key=lambda r: r.snap.cpu_percent)`, or `rss_mb` when `metric="ram"`. Skip PID 0 and restricted processes when ranking by CPU.

**Done when:** `tests/test_monitor.py` passes on fixtures (correct top-K order, correct idle list and savings), and a live run prints sensible output:
```bash
python3 -c "from sysopt.engine.monitor import Monitor; from sysopt.sources.live import LiveSource; Monitor(LiveSource(), k=5).run(3, 2.0)"
```

---

## Phase 3: Subtree Profiler (≈ 2.5 h)

### 3.1 `structures/graph.py`: DirectedGraph (≈ 1.0 h)

```python
class DirectedGraph:
    """Adjacency list built on ChainedHashTable: vertex -> list of out-neighbors."""
    def add_vertex(self, v) -> None
    def add_edge(self, u, v) -> None          # adds missing vertices automatically
    def remove_vertex(self, v) -> None        # also removes incoming edges
    def has_vertex(self, v) -> bool
    def neighbors(self, v) -> list
    def vertices(self) -> list
    def in_degree_zero(self) -> list          # roots
    def bfs(self, start) -> list              # visit order; uses collections.deque; keeps a visited set
    def dfs(self, start) -> list              # iterative with an explicit stack (avoids recursion limits)
    def reachable(self, starts) -> set        # multi-source BFS, used by the leak detector
```

Keep a visited set even though process trees have no cycles. The leak simulator's reference graph *can* have cycles.

**Done when:** `tests/test_graph.py` passes:
* BFS order on a known graph
* DFS visits the same set of nodes
* `reachable` from multiple sources
* a cycle doesn't cause an infinite loop
* `remove_vertex` cleans up incoming edges

### 3.2 `profiler/subtree.py` (≈ 1.0 h)

```python
def build_process_graph(records) -> DirectedGraph:
    # edge ppid -> pid for every process whose parent is present;
    # a process whose parent is missing becomes a root

@dataclass
class SubtreeTotals:
    root_pid: int
    process_count: int
    cpu_percent: float
    rss_mb: float
    members: list[int]

def subtree_totals(graph, registry, pid, method="bfs") -> SubtreeTotals
def top_families(graph, registry, k=5, metric="rss") -> list[SubtreeTotals]
    # find each top-level app process (a direct child of PID 1/launchd), total its subtree,
    # and rank the families with top_k
def find_by_name(registry, name) -> list[int]   # case-insensitive substring match
```

**Done when:** `tests/test_subtree.py` passes:
* totals for every node in `small_tree.json` match hand-calculated values
* BFS and DFS give the same totals
* after re-parenting (`edge_cases.json`), the orphan counts toward PID 1's subtree
* a leaf process's subtree is just itself

A live run should show something like "Google Chrome family: 23 processes, 1.8 GB".

### 3.3 Wire Subsystems 1 & 2 into the CLI (≈ 30 min)

`sysopt/cli.py` (argparse), run as `python3 -m sysopt <command>`:

| Command | What it does |
| :--- | :--- |
| `top --k 10 --metric cpu\|ram [--source live\|PATH]` | One ranked table |
| `watch --interval 2 --polls 30 --idle-cpu 1.0 --idle-secs 300 [--record PATH]` | Repeated polling; prints top-K, idle candidates, and potential savings each poll |
| `tree --pid N` or `tree --name chrome [--method bfs\|dfs]` | Subtree totals plus an indented tree view |
| `families --k 5 --metric rss` | Biggest app families |

Print aligned tables with plain f-strings (no extra libraries). Every command accepts `--source PATH`, so demos work offline from fixtures.

**Done when:** each command runs both on `--source live` and on `--source fixtures/recorded_session.json`.

---

## Phase 4: Memory Leak Simulator (≈ 2.5 h)

### 4.1 `structures/linked_list.py`: DoublyLinkedList (≈ 30 min)

```python
class DLLNode:  __slots__ = ("value", "prev", "next")

class DoublyLinkedList:
    # uses sentinel head and tail nodes so there are no edge cases at the ends
    def append(self, value) -> DLLNode        # O(1)
    def unlink(self, node) -> None            # O(1)
    def __iter__(self) / __len__(self)
```

**Done when:** `tests/test_linked_list.py` passes:
* append / unlink at the head, middle, and tail
* iteration order
* length stays correct

### 4.2 `leaksim/heap_sim.py`: SimulatedHeap (≈ 1.25 h)

```python
class InvalidFreeError(Exception): ...    # free of an address that was never allocated
class DoubleFreeError(Exception): ...     # free of an address that was already freed

@dataclass
class Block:
    address: int
    size: int
    label: str
    allocated_at: int                     # tick number
    pointers: dict                        # field name -> target address (outgoing references)

class SimulatedHeap:
    def __init__(self, base_address=0x1000, alignment=16)
    # --- C-style API ---
    def malloc(self, size, label="") -> int       # O(1): DLL append + hash insert; returns an address
    def free(self, address) -> None               # O(1): hash lookup + DLL unlink
    # --- pointer model ---
    def set_root(self, name, address | None)      # a stack variable pointing at a block (or NULL)
    def set_pointer(self, src, field, dst | None) # block-to-block reference (e.g. node.next)
    # --- time & analysis ---
    def tick(self) -> None                        # advance time; record leaked bytes in the history
    def reference_graph(self) -> DirectedGraph    # roots + blocks as vertices, pointers as edges
    def detect_leaks(self) -> list[Block]         # allocated blocks NOT in graph.reachable(roots)
    def dangling_pointers(self) -> list           # roots/fields that point at freed memory (bonus warning)
    def leaked_bytes(self) -> int
    def velocity_history(self) -> list[float]     # leaked_bytes[t] - leaked_bytes[t-1]
    def average_velocity(self) -> float           # leaked_bytes / ticks
    def stats(self) -> dict                       # allocated count/bytes, leaked count/bytes, frees, ticks
```

Internals:
* `self._live = ChainedHashTable[address -> DLLNode]`; each node's value is a `Block`
* `self._order = DoublyLinkedList()`, allocation order, used for listing
* `self._freed`: a set of freed addresses, so a double free can be told apart from an invalid free
* `self._roots = ChainedHashTable[name -> address]`
* Addresses come from a bump counter: `next = align_up(next + size, alignment)`. Addresses are never reused, which keeps double-free detection simple.

Graph vertices are labeled like `"root:head"` and `0x1040` so roots and blocks can't collide.

### 4.3 `leaksim/scenarios.py` (≈ 30 min)

Scripted "programs", each a function `scenario(heap) -> None` that calls `malloc`, `set_root`, `set_pointer`, `free`, and `tick`:

| Scenario | Behavior | Expected leaks |
| :--- | :--- | :--- |
| `clean_program` | allocates a linked list and frees every node | 0 |
| `lost_head` | builds a 5-node list, then `set_root("head", None)` without freeing | all 5 nodes |
| `cycle_leak` | A ↔ B point at each other, and the root is dropped | A and B (reference counting would miss this) |
| `slow_leak` | a loop that leaks one 64 B buffer every tick for 50 ticks | constant velocity of 64 B/tick |
| `partial_free` | frees the head but not the rest of the list | the remaining nodes, plus a dangling-pointer warning |

Add `python3 -m sysopt leaks --scenario NAME [--plot]` to the CLI. It prints `stats()`, the leaked blocks (address, size, label, tick allocated), and the average velocity. `--plot` saves the leak velocity chart.

**Done when:** `tests/test_leaksim.py` passes:
* each scenario's leak count and bytes match the table above
* `free` twice raises `DoubleFreeError`; `free` of a random address raises `InvalidFreeError`
* the `slow_leak` velocity history is all 64s
* allocating N and freeing M with all roots still held leaves N − M live blocks and 0 leaks

---

## Phase 5: Visualization, Testing Pass & Report (≈ 3.0 h)

### 5.1 `viz/charts.py` (≈ 45 min)

| Function | Chart | Output |
| :--- | :--- | :--- |
| `plot_benchmarks(csv_paths)` | log–log time vs. N, custom vs. built-in | `report/figures/bench_heap.png`, `bench_hash.png` |
| `plot_resource_timeline(poll_results, top_n=5)` | RSS (or CPU) over time for the top processes | `report/figures/timeline.png` |
| `plot_savings(poll_results)` | potential savings (MB) from idle candidates over time | `report/figures/savings.png` |
| `plot_leak_velocity(heap)` | leaked bytes over ticks, plus a per-tick velocity bar | `report/figures/leak_velocity.png` |
| `plot_family_breakdown(families)` | horizontal bar chart of top app families by RSS | `report/figures/families.png` |

Add `--plot` flags to the `watch`, `families`, and `leaks` commands. Use `matplotlib.use("Agg")` so charts save without opening a window.

### 5.2 Full test pass (≈ 45 min)

```bash
python3 -m unittest discover -s tests -v
```

* Every test file from the earlier phases passes.
* Add an integration test: `SnapshotSource(recorded_session.json)` → `Monitor` → `build_process_graph` → `subtree_totals`, end to end, with no exceptions.
* Optional coverage check: `pip install coverage && coverage run -m unittest discover -s tests && coverage report`. Aim for 85% or more on `sysopt/structures`.

### 5.3 `report/REPORT.md` (≈ 1.0 h)

Sections:
1. **Overview**: what the suite does (a short version of the proposal).
2. **Design**: one paragraph per data structure. Explain why it was chosen (chaining vs. probing, rebuilding the heap vs. an indexed heap, DLL + hash map, reachability vs. reference counting).
3. **Bootstrap results**: the benchmark plots, a table of median times, and the fitted log–log slopes. Explain why the built-ins are faster by a constant factor but grow at the same rate.
4. **Complexity analysis**: the Big-O table from the proposal, each row checked against your actual code.
5. **Results on my machine**: screenshots or text output of `top`, `families`, and `tree --name <browser>`, plus the timeline and savings charts from a recorded session.
6. **Leak simulator results**: output and charts for each scenario, with emphasis on the cycle case.
7. **Testing**: what each test file covers, and the coverage numbers.
8. **Limitations & future work**: idle is inferred from CPU only; `AccessDenied` processes; the indexed heap; cross-platform differences.

### 5.4 `README.md` (≈ 30 min)

Include setup, every CLI command with an example, how to run the tests and benchmarks, and the folder layout.

**Done when:** a fresh clone can follow the README from setup to the tests passing to every CLI command working.

---

## Buffer (≈ 1.0 h)

Reserved for debugging `psutil` behavior on macOS, matplotlib layout tweaks, and polishing the report.

---

## Build Order at a Glance

| # | Step | Depends on | Hours | Running total |
| :-: | :--- | :--- | :-: | :-: |
| 0 | Setup | – | 0.25 | 0.25 |
| 1.1 | Heap + top_k | 0 | 1.0 | 1.25 |
| 1.2 | Hash table | 0 | 1.0 | 2.25 |
| 1.3 | Benchmarks | 1.1, 1.2 | 1.0 | 3.25 |
| 2.1–2.2 | Snapshot model + fixtures | 1.2 | 0.75 | 4.0 |
| 2.3 | LiveSource | 2.1 | 0.75 | 4.75 |
| 2.4 | Registry + idle | 1.2, 2.2 | 0.75 | 5.5 |
| 2.5 | Monitor | 1.1, 2.4 | 0.5 | 6.0 |
| 3.1 | Graph | 1.2 | 1.0 | 7.0 |
| 3.2 | Subtree profiler | 3.1, 2.4 | 1.0 | 8.0 |
| 3.3 | CLI (top/watch/tree/families) | 2.5, 3.2 | 0.5 | 8.5 |
| 4.1 | Doubly linked list | 0 | 0.5 | 9.0 |
| 4.2 | SimulatedHeap | 1.2, 3.1, 4.1 | 1.25 | 10.25 |
| 4.3 | Scenarios + `leaks` CLI | 4.2 | 0.5 | 10.75 |
| 5.1 | Charts | all | 0.75 | 11.5 |
| 5.2 | Test pass | all | 0.75 | 12.25 |
| 5.3–5.4 | Report + README | all | 1.5 | 13.75 |
| – | Buffer | – | 1.0 | 14.75 |

**If time runs short:** finish through step 3.3 first, since that alone is a complete must-have project. Then do 5.2 and 5.3. Phase 4 is the "should have." The stretch goals (indexed heap, live dashboard) come after everything else.

---

## Risks & Mitigations

| Risk | Mitigation |
| :--- | :--- |
| `psutil` returns 0% CPU or `AccessDenied` for many macOS processes | Priming plus the `restricted` flag. Rank by RAM when CPU data is sparse. Demos can use the recorded fixture |
| Custom structures are much slower than the built-ins | Expected; the report compares growth rates, not raw speed |
| Bugs in the hash table spread into every subsystem | Hash table tests in Phase 1 compare against `dict` on 1,000 random operations before anything else depends on it |
| Live data makes results vary between runs | All tests use fixtures; live runs are for demos only |
| Running out of time | Follow the priority order above; the Phase 1–3 work is a complete project on its own |

---

## Final Submission Checklist

- [ ] `python3 -m unittest discover -s tests -v`: all tests pass
- [ ] Benchmarks re-run; plots in `report/figures/`
- [ ] All 5 CLI commands work on live data and on fixtures
- [ ] `report/REPORT.md` complete, with charts and the Big-O table
- [ ] `README.md` setup steps tested from scratch
- [ ] zyBook chapter numbers in the proposal checked against the syllabus
- [ ] No `heapq` or `dict` storage inside `sysopt/structures/` (`grep -rn "heapq\|= {}" sysopt/structures` returns only allowed uses)
