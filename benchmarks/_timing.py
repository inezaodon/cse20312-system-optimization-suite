"""Shared helpers for the benchmark scripts."""
from __future__ import annotations

import csv
import os
import statistics
import sys
import time
from typing import Callable, List, Tuple

# Let `python3 benchmarks/bench_*.py` import the sysopt package from the project root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

RESULTS_DIR = os.path.join(ROOT, "benchmarks", "results")
SIZES = [100, 1_000, 10_000, 100_000]
REPEATS = 5
SEED = 42

Row = Tuple[str, str, int, float]


def median_time(fn: Callable[[], None], setup: Callable[[], None] = None,
                repeats: int = REPEATS) -> float:
    """Run fn `repeats` times and return the median wall time in seconds.

    `setup` (if given) runs before each timed call and is not timed.
    """
    times = []
    for _ in range(repeats):
        if setup is not None:
            setup()
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def write_csv(name: str, rows: List[Row]) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, name)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["experiment", "impl", "n", "seconds"])
        w.writerows(rows)
    return path


def print_row(row: Row) -> None:
    exp, impl, n, secs = row
    print(f"{exp:<14} {impl:<18} n={n:>7,}  {secs * 1000:>10.3f} ms")
