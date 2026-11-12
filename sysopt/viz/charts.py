"""matplotlib charts for the suite. Every function saves a PNG and returns its path.

Uses the non-interactive Agg backend, so charts save without opening a window
(and work in tests and over SSH).
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from ..engine.monitor import PollResult  # noqa: E402
from ..leaksim.heap_sim import SimulatedHeap  # noqa: E402
from ..profiler.subtree import SubtreeTotals  # noqa: E402
from ..sources.base import PollData  # noqa: E402
from ..structures.hash_table import ChainedHashTable  # noqa: E402
from ..structures.heap import top_k  # noqa: E402

DPI = 150


def _save(fig, out_path: str) -> str:
    folder = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(folder, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI)
    plt.close(fig)
    return out_path


def _short(name: str, n: int = 28) -> str:
    return name if len(name) <= n else name[: n - 1] + "…"


# ----- Core Engine ---------------------------------------------------------------------

def plot_resource_timeline(polls: Sequence[PollData], out_path: str,
                           metric: str = "ram", top_n: int = 5,
                           title: Optional[str] = None) -> str:
    """Line chart of the top_n processes over time.

    Processes are chosen by their average value across all polls, using top_k.
    A gap in a line means the process had no reading (or wasn't running) then.
    """
    if metric not in ("cpu", "ram"):
        raise ValueError("metric must be 'cpu' or 'ram'")
    if not polls:
        raise ValueError("no polls to plot")
    attr = "cpu_percent" if metric == "cpu" else "rss_mb"

    series = ChainedHashTable()   # (pid, create_time) -> {"name", "points": [(t, v)]}
    for t, snaps in polls:
        for s in snaps:
            value = getattr(s, attr)
            if value is None:
                continue
            entry = series.get(s.key)
            if entry is None:
                entry = {"name": s.name, "pid": s.pid, "points": []}
                series[s.key] = entry
            entry["points"].append((t, value))

    def mean(entry) -> float:
        return sum(v for _, v in entry["points"]) / len(entry["points"])

    chosen = top_k(list(series.values()), top_n, key=mean)
    t0 = polls[0][0]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for entry in chosen:
        xs = [t - t0 for t, _ in entry["points"]]
        ys = [v for _, v in entry["points"]]
        ax.plot(xs, ys, marker="o", markersize=3,
                label=f"{_short(entry['name'])} ({entry['pid']})")
    ax.set_xlabel("seconds since first poll")
    ax.set_ylabel("CPU %" if metric == "cpu" else "RAM (MB)")
    ax.set_title(title or f"Top {len(chosen)} processes by {'CPU' if metric == 'cpu' else 'RAM'}")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1))
    return _save(fig, out_path)


def plot_savings(results: Sequence[PollResult], out_path: str,
                 title: str = "Idle candidates and potential RAM savings") -> str:
    """Potential savings (MB) over time, with the number of idle candidates."""
    if not results:
        raise ValueError("no poll results to plot")
    xs = [r.elapsed for r in results]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.fill_between(xs, [r.savings_rss_mb for r in results], step="post", alpha=0.3)
    ax.step(xs, [r.savings_rss_mb for r in results], where="post", label="potential savings (MB)")
    ax.set_xlabel("seconds since first poll")
    ax.set_ylabel("RAM held by idle processes (MB)")
    ax.grid(True, alpha=0.3)
    ax2 = ax.twinx()
    ax2.step(xs, [len(r.idle) for r in results], where="post", color="tab:orange",
             label="idle candidates")
    ax2.set_ylabel("idle candidates")
    ax2.set_ylim(bottom=0, top=max(1, max(len(r.idle) for r in results)) * 1.15)
    ax2.yaxis.set_major_locator(MaxNLocator(integer=True))
    lines = ax.get_legend_handles_labels()
    lines2 = ax2.get_legend_handles_labels()
    ax.legend(lines[0] + lines2[0], lines[1] + lines2[1], fontsize=8, loc="upper left")
    ax.set_title(title)
    return _save(fig, out_path)


# ----- Subtree Profiler ------------------------------------------------------------------

def plot_family_breakdown(families: Sequence[SubtreeTotals], out_path: str,
                          metric: str = "ram", title: Optional[str] = None) -> str:
    """Horizontal bars, one per process family, largest at the top."""
    if not families:
        raise ValueError("no families to plot")
    values = [f.rss_mb if metric == "ram" else f.cpu_percent for f in families]
    labels = [f"{_short(f.root_name, 32)}  ({f.process_count} proc)" for f in families]
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(families) + 1.5))
    ax.barh(range(len(families)), values)
    ax.set_yticks(range(len(families)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("RAM (MB)" if metric == "ram" else "CPU %")
    for i, v in enumerate(values):
        ax.text(v, i, f" {v:,.0f}", va="center", fontsize=8)
    ax.set_title(title or f"Process families by {'RAM' if metric == 'ram' else 'CPU'}")
    ax.grid(True, axis="x", alpha=0.3)
    return _save(fig, out_path)


# ----- Memory Leak Simulator -------------------------------------------------------------

def plot_leak_velocity(heap: SimulatedHeap, out_path: str, title: str = "Leak velocity") -> str:
    """Top: total leaked bytes after each tick. Bottom: bytes newly leaked per tick."""
    history = heap.leak_history()
    if not history:
        raise ValueError("the heap has no ticks to plot")
    ticks = list(range(1, len(history) + 1))
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True)
    top.plot(ticks, history, marker="o", markersize=3)
    top.set_ylabel("total leaked (bytes)")
    top.grid(True, alpha=0.3)
    top.set_title(f"{title}  (average {heap.average_velocity():.1f} B/tick)")
    bottom.bar(ticks, heap.velocity_history())
    bottom.set_ylabel("new leaks (bytes/tick)")
    bottom.set_xlabel("tick")
    bottom.grid(True, axis="y", alpha=0.3)
    return _save(fig, out_path)


def plot_leak_scenarios(rows: List[Tuple[str, Dict]], out_path: str,
                        title: str = "Leak detection: reachability vs. reference counting") -> str:
    """Grouped bars per scenario: leaked bytes found by reachability, and the
    part of it reference counting could never reclaim.

    rows: (scenario name, {"leaked_bytes": int, "refcount_missed_bytes": int})
    """
    if not rows:
        raise ValueError("no scenarios to plot")
    names = [r[0] for r in rows]
    found = [r[1]["leaked_bytes"] for r in rows]
    missed = [r[1]["refcount_missed_bytes"] for r in rows]
    x = range(len(rows))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar([i - w / 2 for i in x], found, w, label="leaked (found by reachability)")
    ax.bar([i + w / 2 for i in x], missed, w, label="never freed by reference counting")
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, fontsize=8)
    ax.set_ylabel("bytes")
    ax.set_yscale("symlog", linthresh=100)
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_title(title)
    return _save(fig, out_path)
