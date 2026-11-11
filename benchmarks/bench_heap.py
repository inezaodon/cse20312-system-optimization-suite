"""Benchmark the custom MaxHeap / top_k against Python's heapq.

Run from the project root:
    python3 benchmarks/bench_heap.py
"""
from __future__ import annotations

import heapq
import random

from _timing import SEED, SIZES, median_time, print_row, write_csv

from sysopt.structures.heap import MaxHeap, top_k

K = 10


def run() -> list:
    rows = []
    for n in SIZES:
        random.seed(SEED + n)
        data = [random.random() * 100 for _ in range(n)]

        # --- push all, then pop all ---------------------------------------
        def custom_push_pop():
            h = MaxHeap()
            for x in data:
                h.insert(x)
            while h:
                h.extract_max()

        def heapq_push_pop():
            h = []
            for x in data:
                heapq.heappush(h, -x)        # negate: heapq is a min-heap
            while h:
                -heapq.heappop(h)

        rows.append(("push_pop", "custom MaxHeap", n, median_time(custom_push_pop)))
        rows.append(("push_pop", "heapq", n, median_time(heapq_push_pop)))

        # --- build heap -----------------------------------------------------
        def custom_build():
            MaxHeap().build_heap(data)

        def heapq_build():
            heapq.heapify([-x for x in data])

        rows.append(("build_heap", "custom MaxHeap", n, median_time(custom_build)))
        rows.append(("build_heap", "heapq", n, median_time(heapq_build)))

        # --- top-K selection ------------------------------------------------
        rows.append(("top_k", "custom top_k", n, median_time(lambda: top_k(data, K))))
        rows.append(("top_k", "heapq.nlargest", n, median_time(lambda: heapq.nlargest(K, data))))

        for row in rows[-6:]:
            print_row(row)
    return rows


if __name__ == "__main__":
    path = write_csv("heap.csv", run())
    print(f"\nWrote {path}")
