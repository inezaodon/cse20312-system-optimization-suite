"""Benchmark the custom ChainedHashTable against Python's dict.

Run from the project root:
    python3 benchmarks/bench_hash_table.py
"""
from __future__ import annotations

import random

from _timing import SEED, SIZES, median_time, print_row, write_csv

from sysopt.structures.hash_table import ChainedHashTable


def run() -> list:
    rows = []
    for n in SIZES:
        random.seed(SEED + n)
        # PID-like integer keys, unique, in random order.
        keys = random.sample(range(n * 10), n)
        state = {}

        # --- insert ---------------------------------------------------------
        def custom_insert():
            t = ChainedHashTable()
            for k in keys:
                t[k] = k
            state["custom"] = t

        def dict_insert():
            d = {}
            for k in keys:
                d[k] = k
            state["dict"] = d

        rows.append(("insert", "ChainedHashTable", n, median_time(custom_insert)))
        rows.append(("insert", "dict", n, median_time(dict_insert)))

        # --- lookup (tables built by the last insert run) ---------------------
        lookup_order = random.sample(keys, n)

        def custom_lookup():
            t = state["custom"]
            for k in lookup_order:
                t[k]

        def dict_lookup():
            d = state["dict"]
            for k in lookup_order:
                d[k]

        rows.append(("lookup", "ChainedHashTable", n, median_time(custom_lookup)))
        rows.append(("lookup", "dict", n, median_time(dict_lookup)))

        # --- delete (rebuild before each timed run; rebuild is not timed) -----
        def custom_delete():
            t = state["custom"]
            for k in lookup_order:
                del t[k]

        def dict_delete():
            d = state["dict"]
            for k in lookup_order:
                del d[k]

        rows.append(("delete", "ChainedHashTable", n,
                     median_time(custom_delete, setup=custom_insert)))
        rows.append(("delete", "dict", n,
                     median_time(dict_delete, setup=dict_insert)))

        for row in rows[-6:]:
            print_row(row)
    return rows


if __name__ == "__main__":
    path = write_csv("hash_table.csv", run())
    print(f"\nWrote {path}")
