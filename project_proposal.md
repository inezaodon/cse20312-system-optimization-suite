# CSE 20312 Final Project Proposal

## 1. Project Title & Domain Goal

* **Project Title:** Unified System Resource & Memory Optimization Suite
* **Domain:** System Utilities & Memory Diagnostics
* **Overview:** A diagnostic tool that applies core course data structures to live process monitoring, process-hierarchy analysis, and a simulated heap with leak detection. All three subsystems share a common data model: processes and memory blocks are both stored in a custom hash table, and both hierarchies (process trees and pointer references) are analyzed with the same graph traversal code.

### Subsystems

1. **Core Engine (Resource Hog & Idle Monitor)**
   Polls process metrics (PID, parent PID, CPU %, RAM MB, creation time) at a fixed interval. Ranks the top-K resource-heavy processes and flags idle ones. It never terminates processes; it only reports how much CPU and RAM each idle candidate would free.

   **Idle definition:** A process is *idle* when its CPU usage stays below a threshold `X` (default 1.0%) for `T` consecutive seconds of polling (default 300 s). The OS does not report when a user last used an app, so idleness is inferred from CPU activity over time.

2. **Subtree Profiler (Process Dependency Graph)**
   Models parent → child process relationships (e.g., a browser and its renderer/helper processes) as a directed graph stored in an adjacency list. BFS/DFS from any PID computes the aggregate CPU and RAM of that process's whole subtree.

3. **Memory Leak Simulator (Reachability-Based Garbage Profiler)**
   Simulates C-style `malloc` / `free` with a reference graph:
   * **Roots** represent stack variables that hold pointers.
   * **Blocks** are simulated heap allocations, which can point to other blocks (e.g., linked list nodes).
   * A block is **leaked** when it is still allocated but **unreachable from every root**, i.e., the program no longer holds any pointer that could be used to `free` it.
   * Leak detection runs a **mark phase** (BFS/DFS from all roots) and reports every unmarked allocated block, the same idea used by mark-and-sweep garbage collectors.
   * **Leak velocity** = leaked bytes per simulated tick, tracked over time.
   * The user can manually `free` a block by address or reassign or drop a root pointer to create a leak.

---

## 2. Relevant zyBook Chapters & Course Topics

> Chapter and week numbers should be verified against the current CSE 20312 syllabus.

| zyBook Chapter / Weeks | Topics | Where It Is Used |
| :--- | :--- | :--- |
| **Ch. 2: Data Allocation in C** (Weeks 1–2) | Pointers, `malloc` / `free`, heap vs. stack, memory leaks | Conceptual model for the Memory Leak Simulator (roots = stack, blocks = heap) |
| **Ch. 6: Hash Tables** (Weeks 6–7) | Hash functions, chaining, load factor, resizing | Process registry (PID → process) and allocation registry (address → block) |
| **Ch. 7: Python Data Structures** (Weeks 7–9) | OOP design, debugging, `unittest` | Class architecture and the test suite |
| **Ch. 10: Heaps** (Week 12) | Binary heaps, priority queue ADT, `heapq` | Top-K resource hog ranking |
| **Ch. 11: Graphs** (Weeks 13–15) | Adjacency lists, directed graphs, BFS / DFS | Process subtree aggregation **and** leak detection by reachability |

---

## 3. Data Structures & Libraries

### Custom Data Structures (Built from Scratch)

| Structure | Design Decision | Purpose |
| :--- | :--- | :--- |
| **Max-Heap** | Array-backed; parent `(i-1)//2`, children `2i+1`, `2i+2`; `insert`, `extract_max`, `heapify_up`, `heapify_down`, `build_heap` (O(N)) | Ranking processes by a chosen metric (CPU or RAM) |
| **Size-K Min-Heap (top-K)** | Reuses the heap code with a reversed comparator; keeps only the K largest values seen | O(N log K) top-K selection without destroying the full dataset |
| **Hash Table** | **Separate chaining**; resize (double) when load factor > 0.75 | O(1) average PID lookup. Chaining was chosen over linear probing because processes exit constantly, and deletion under linear probing needs tombstones |
| **Directed Graph** | Adjacency list (`dict` of PID → list of child PIDs, wrapped in a class) | Process hierarchy and pointer reference graph |
| **Doubly-Linked List + Hash Map** | DLL holds allocation order; hash table maps `address → DLL node` | O(1) `malloc` (append) and O(1) `free` (look up node, unlink). A DLL alone would need an O(N) search to free by address |

### Handling Changing Metrics in the Heap

CPU and RAM values change on every poll, and a basic binary heap does not support updating a key in place. This project **rebuilds the ranking each poll**:

1. Gather the N current process snapshots: O(N).
2. Run top-K selection with a size-K min-heap: O(N log K).

At typical desktop process counts (N ≈ 300–800), this is fast and avoids the complexity of an indexed heap. An **indexed heap** (hash table of PID → heap index, with O(log N) `update_key`) is listed as a stretch goal.

### External Libraries

* **`psutil`**: Reading live process data (`pid`, `ppid`, `cpu_percent`, `memory_info`, `create_time`, `name`).
* **`matplotlib`**: Benchmark plots, resource usage over time, and leak velocity charts.
* **`pandas`** *(optional)*: Tabulating benchmark results and poll history.
* **`unittest`**: Test framework (standard library).

### Data Source Abstraction

All subsystems read from a `ProcessSource` interface with two implementations:

* `LiveSource`: wraps `psutil`.
* `SnapshotSource`: loads recorded or hand-written JSON snapshots.

Unit tests use `SnapshotSource` only, so results are deterministic and do not depend on what is running on the machine.

### Known `psutil` Edge Cases (Handled Explicitly)

| Issue | Handling |
| :--- | :--- |
| First `cpu_percent()` call returns `0.0` | Prime all processes once and discard the first reading |
| `AccessDenied` on system processes (common on macOS) | Skip the metric, mark the process as `restricted`, and continue |
| `NoSuchProcess` (process exits mid-poll) | Remove it from the hash table and graph; do not crash |
| PID reuse | Key processes by `(pid, create_time)` so a reused PID is treated as a new process |
| Orphaned children (parent exits, child re-parented to PID 1) | Graph is rebuilt from `ppid` each poll; orphans attach to their new parent |

---

## 4. Bootstrap Subproject

**Goal:** Understand heap and hash table mechanics before relying on Python's built-ins.

**Implementation:**
* `MaxHeap` using raw index arithmetic (no `heapq`).
* `ChainedHashTable` with a custom hash function, chaining, and resizing (no `dict` for storage).

**Benchmark Experiment:**

| Experiment | Custom | Built-in Baseline | Sizes |
| :--- | :--- | :--- | :--- |
| Heap push N items, then pop all | `MaxHeap` | `heapq` (values negated to simulate a max-heap) | N = 100; 1,000; 10,000; 100,000 |
| Build heap from N items | `MaxHeap.build_heap` | `heapq.heapify` | same |
| Top-K selection (K = 10) | Size-K min-heap | `heapq.nlargest` | same |
| Insert / lookup / delete N keys | `ChainedHashTable` | `dict` | same |

**Expected outcome and analysis:** Built-in `heapq` and `dict` are implemented in C and will be faster by a constant factor. The goal is to confirm that the custom structures **scale with the same Big-O growth rate**. This is shown by plotting time vs. N on log–log axes and comparing slopes, along with a discussion of memory overhead and implementation complexity.

---

## 5. Milestone Timeline (14 hours + 1 hour buffer)

| Phase | Hours | Deliverables |
| :--- | :---: | :--- |
| **1. Bootstrap** | 3.0 | `MaxHeap`, `ChainedHashTable`, unit tests for both, benchmark script and plots |
| **2. Ingestion & Ranking** | 3.0 | `ProcessSource` interface (`LiveSource`, `SnapshotSource`), `psutil` edge-case handling, process registry, top-K ranking, idle detection with configurable `X` and `T` |
| **3. Subtree Profiler** | 2.5 | `DirectedGraph`, BFS and DFS subtree aggregation, CLI command to show a process family's total footprint |
| **4. Leak Simulator** | 2.5 | DLL + hash map allocation registry, root/pointer model, mark-phase leak detection (reusing graph traversal), leak velocity tracking |
| **5. Testing & Report** | 3.0 | Full test suite, Big-O analysis write-up, `matplotlib` charts, README |
| **Buffer** | 1.0 | Debugging and polish |

### Scope Priorities

* **Must have:** Phases 1–3 (Core Engine and Subtree Profiler).
* **Should have:** Phase 4 (Leak Simulator).
* **Stretch goals:** Indexed heap with `update_key`; live-updating dashboard; historical resource trends.

---

## 6. Testing Plan (`unittest`)

All tests use `SnapshotSource` or hand-built fixtures, never live system data.

**Heap**
* `extract_max()` always returns the largest remaining value, across random insert sequences.
* The heap property holds for every index after each insert and extract.
* `build_heap` on random input yields a valid heap.
* Top-K matches `sorted(data, reverse=True)[:K]` for random data, including K > N and duplicate values.

**Hash Table**
* Insert, lookup, update, and delete work correctly, including keys that collide in the same bucket.
* Resizing triggers at the load factor threshold and preserves every entry.
* Deleting a missing key raises `KeyError`.

**Process Graph**
* Subtree sums on a known fixture tree match hand-calculated totals.
* BFS and DFS produce the same set of visited nodes and the same totals.
* An orphaned child re-parented to PID 1 appears in PID 1's subtree after rebuild.
* A reused PID with a different `create_time` is treated as a new process.

**Idle Detection**
* A process below `X` % CPU for `T − 1` seconds is **not** flagged; at `T` seconds it **is** flagged.
* A single CPU spike above `X` resets the idle timer.
* Processes raising `AccessDenied` or `NoSuchProcess` are skipped without crashing.

**Leak Simulator**
* Allocate a block, drop its only root pointer → reported as leaked.
* Allocate a block, `free` it → not reported as leaked and removed from the registry.
* A linked chain of blocks reachable from one root → none leaked; drop the root → the whole chain is leaked.
* A cycle of blocks with no root (A → B → A) → both leaked (the case reference counting misses).
* Double `free` and `free` of an unknown address raise errors.
* Leak velocity over a scripted sequence of ticks matches the expected bytes-per-tick values.

---

## 7. Complexity Analysis

N = number of processes, K = number of top results, V/E = graph vertices/edges, M = number of allocated blocks, R = number of roots.

| Operation | Structure / Algorithm | Time | Space | Notes |
| :--- | :--- | :---: | :---: | :--- |
| PID lookup / insert / delete | Chained hash table | O(1) avg, O(N) worst | O(N) | Worst case only when every key lands in one bucket; resizing keeps the expected chain length constant (amortized O(1) insert) |
| Build heap | Bottom-up heapify | O(N) | O(N) | Faster than N separate inserts (O(N log N)) |
| Heap insert / extract | Binary heap | O(log N) | — | |
| Top-K per poll | Size-K min-heap | O(N log K) | O(K) | Better than a full sort (O(N log N)) when K ≪ N; non-destructive |
| Subtree aggregation | BFS / DFS | O(V + E) | O(V) | For a process tree, E = V − 1, so effectively O(V) |
| Simulated `malloc` | DLL append + hash insert | O(1) avg | O(M) | |
| Simulated `free` | Hash lookup + DLL unlink | O(1) avg | — | DLL alone would be O(M) to find the node |
| Leak detection | Mark phase (BFS from roots) | O(R + M + P) | O(M) | P = number of pointer references between blocks |
| Idle check per poll | Hash table update per process | O(N) | O(N) | One counter per process |
