"""Plot benchmark CSVs on log-log axes and print the fitted growth slopes.

Run from the project root after both bench scripts:
    python3 benchmarks/plot_benchmarks.py

Slope of log(time) vs. log(n):
    ~1.0  -> linear growth, O(N)
    ~1.1  -> N log N over this range of N
Custom and built-in lines should have similar slopes; the built-ins (written
in C) just sit lower on the chart by a constant factor.
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from _timing import RESULTS_DIR, ROOT  # noqa: E402

FIG_DIR = os.path.join(ROOT, "report", "figures")


def load(path):
    data = defaultdict(lambda: defaultdict(list))   # experiment -> impl -> [(n, s)]
    with open(path) as f:
        for row in csv.DictReader(f):
            data[row["experiment"]][row["impl"]].append((int(row["n"]), float(row["seconds"])))
    return data


def slope(points):
    ns = np.log10([p[0] for p in points])
    ts = np.log10([max(p[1], 1e-9) for p in points])
    return float(np.polyfit(ns, ts, 1)[0])


def plot_file(csv_name, fig_name, title):
    path = os.path.join(RESULTS_DIR, csv_name)
    if not os.path.exists(path):
        print(f"skip {csv_name}: run the benchmark first")
        return
    data = load(path)
    experiments = list(data)
    fig, axes = plt.subplots(1, len(experiments), figsize=(5 * len(experiments), 4.2))
    if len(experiments) == 1:
        axes = [axes]

    print(f"\n{title}")
    print(f"{'experiment':<14} {'impl':<18} {'slope':>6}  {'custom / built-in at max n':>26}")
    for ax, exp in zip(axes, experiments):
        impls = data[exp]
        max_times = {}
        for impl, points in impls.items():
            points.sort()
            ns = [p[0] for p in points]
            ts = [p[1] * 1000 for p in points]
            s = slope(points)
            ax.loglog(ns, ts, marker="o", label=f"{impl} (slope {s:.2f})")
            max_times[impl] = points[-1][1]
            print(f"{exp:<14} {impl:<18} {s:>6.2f}")
        names = list(max_times)
        if len(names) == 2:
            ratio = max_times[names[0]] / max_times[names[1]]
            print(f"{'':<14} {'':<18} {'':>6}  {ratio:>25.1f}x")
        ax.set_title(exp.replace("_", " "))
        ax.set_xlabel("n (items)")
        ax.set_ylabel("median time (ms)")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)

    fig.suptitle(title)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    out = os.path.join(FIG_DIR, fig_name)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    plot_file("heap.csv", "bench_heap.png", "Custom MaxHeap vs. heapq")
    plot_file("hash_table.csv", "bench_hash_table.png", "ChainedHashTable vs. dict")
