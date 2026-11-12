"""Subtree Profiler: process families as a directed graph.

Each process is a vertex, with an edge parent -> child built from its ppid.
A process's "subtree" is everything reachable from it, found with BFS or DFS,
so a browser's total footprint includes every helper and renderer it spawned.

A "family" is the subtree of a top-level process: a direct child of launchd
(PID 1) or kernel_task (PID 0), or a process whose parent isn't in the data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from ..sources.base import ProcessSnapshot
from ..structures.graph import DirectedGraph
from ..structures.hash_table import ChainedHashTable
from ..structures.heap import top_k

SYSTEM_ROOTS = (0, 1)   # kernel_task and launchd on macOS
METHODS = ("bfs", "dfs")


@dataclass
class SubtreeTotals:
    root_pid: int
    root_name: str
    process_count: int
    cpu_percent: float          # sum over members with a known reading
    rss_mb: float               # sum over members with a known reading
    unknown_count: int          # members missing a CPU or RAM reading
    is_mine: bool               # the subtree's root belongs to the user
    members: List[int] = field(default_factory=list)


class ProcessTree:
    def __init__(self, snaps: Iterable[ProcessSnapshot]) -> None:
        self.graph = DirectedGraph()
        self._snaps = ChainedHashTable()      # pid -> ProcessSnapshot
        snaps = list(snaps)
        for s in snaps:
            self._snaps[s.pid] = s
            self.graph.add_vertex(s.pid)
        for s in snaps:
            # Skip self-loops (kernel_task reports ppid 0 == its own pid) and
            # parents that aren't in the data (the child becomes a root).
            # Each process has exactly one parent, so this edge can't already exist.
            # Skipping the duplicate scan keeps building O(V) instead of O(sum of deg^2).
            if s.ppid != s.pid and s.ppid in self._snaps:
                self.graph.add_edge(s.ppid, s.pid, check_duplicate=False)

    # ----- lookups ------------------------------------------------------------
    def snapshot(self, pid: int) -> ProcessSnapshot:
        snap = self._snaps.get(pid)
        if snap is None:
            raise KeyError(f"no process with PID {pid}")
        return snap

    def __contains__(self, pid: int) -> bool:
        return pid in self._snaps

    def __len__(self) -> int:
        return len(self._snaps)

    def children(self, pid: int) -> List[int]:
        return self.graph.neighbors(pid)

    def find_by_name(self, text: str) -> List[int]:
        """PIDs whose name contains `text` (case-insensitive), largest RSS first."""
        needle = text.lower()
        matches = [s for s in self._snaps.values() if needle in s.name.lower()]
        return [s.pid for s in top_k(matches, len(matches), key=lambda s: s.rss_mb or 0.0)]

    def find_family_roots(self, text: str) -> List[int]:
        """Matching processes whose parent does not also match.

        For "chrome", this returns the main Google Chrome process and not each
        of its "Google Chrome Helper" children, which are already in its subtree.
        """
        matches = self.find_by_name(text)
        matched = ChainedHashTable()
        for pid in matches:
            matched[pid] = True
        return [pid for pid in matches
                if not any(p in matched for p in self.graph.predecessors(pid))]

    # ----- aggregation --------------------------------------------------------
    def subtree_totals(self, pid: int, method: str = "bfs") -> SubtreeTotals:
        """Sum CPU and RAM over pid and all its descendants. O(V + E) of the subtree."""
        if method not in METHODS:
            raise ValueError(f"method must be one of {METHODS}")
        root = self.snapshot(pid)
        members = self.graph.bfs(pid) if method == "bfs" else self.graph.dfs(pid)
        cpu = rss = 0.0
        unknown = 0
        for m in members:
            s = self._snaps[m]
            if s.cpu_percent is not None:
                cpu += s.cpu_percent
            if s.rss_mb is not None:
                rss += s.rss_mb
            if s.cpu_percent is None or s.rss_mb is None:
                unknown += 1
        return SubtreeTotals(root_pid=pid, root_name=root.name,
                             process_count=len(members),
                             cpu_percent=round(cpu, 2), rss_mb=round(rss, 2),
                             unknown_count=unknown, is_mine=root.is_mine,
                             members=members)

    def family_heads(self) -> List[int]:
        """Top-level processes: each one's subtree is a family.

        System roots (PID 0 and 1) are looked through, so their children become
        the heads. On macOS that is kernel_task (0) -> launchd (1) -> apps.
        """
        heads: List[int] = []
        for r in self.graph.roots():
            if r not in SYSTEM_ROOTS:
                heads.append(r)        # parent not in the data
                continue
            for c in self.graph.neighbors(r):
                if c in SYSTEM_ROOTS:  # launchd under kernel_task
                    heads.extend(x for x in self.graph.neighbors(c) if x not in SYSTEM_ROOTS)
                else:
                    heads.append(c)
        return heads

    def families(self, method: str = "bfs", mine_only: bool = False) -> List[SubtreeTotals]:
        fams = [self.subtree_totals(h, method) for h in self.family_heads()]
        if mine_only:
            fams = [f for f in fams if f.is_mine]
        return fams

    def top_families(self, k: int = 5, metric: str = "ram", method: str = "bfs",
                     mine_only: bool = False) -> List[SubtreeTotals]:
        if metric not in ("cpu", "ram"):
            raise ValueError("metric must be 'cpu' or 'ram'")
        key = (lambda f: f.cpu_percent) if metric == "cpu" else (lambda f: f.rss_mb)
        return top_k(self.families(method, mine_only), k, key=key)

    # ----- text output --------------------------------------------------------
    def render(self, pid: int, max_depth: Optional[int] = None,
               max_children: int = 10) -> str:
        """Indented tree view of pid's subtree; children sorted by RSS."""
        lines: List[str] = []

        def label(s: ProcessSnapshot) -> str:
            cpu = "—" if s.cpu_percent is None else f"{s.cpu_percent:.1f}%"
            rss = "—" if s.rss_mb is None else f"{s.rss_mb:,.1f} MB"
            return f"{s.name} ({s.pid})  cpu {cpu}  ram {rss}"

        def walk(p: int, prefix: str, depth: int) -> None:
            kids = [self._snaps[c] for c in self.graph.neighbors(p)]
            if not kids:
                return
            if max_depth is not None and depth >= max_depth:
                total = len(self.graph.bfs(p)) - 1
                lines.append(f"{prefix}└── ... {total} more below")
                return
            kids = top_k(kids, len(kids), key=lambda s: s.rss_mb or 0.0)
            shown = kids[:max_children]
            hidden = len(kids) - len(shown)
            for i, kid in enumerate(shown):
                last = i == len(shown) - 1 and hidden == 0
                lines.append(f"{prefix}{'└── ' if last else '├── '}{label(kid)}")
                walk(kid.pid, prefix + ("    " if last else "│   "), depth + 1)
            if hidden:
                lines.append(f"{prefix}└── ... {hidden} more children")

        lines.append(label(self.snapshot(pid)))
        walk(pid, "", 0)
        return "\n".join(lines)


def format_totals(t: SubtreeTotals) -> str:
    note = f"   ({t.unknown_count} without readings)" if t.unknown_count else ""
    return (f"{t.root_name} ({t.root_pid}) family: {t.process_count} processes, "
            f"{t.cpu_percent:.1f}% CPU, {t.rss_mb:,.1f} MB RAM{note}")


def format_families(fams: List[SubtreeTotals], metric: str) -> str:
    label = "CPU %" if metric == "cpu" else "RAM"
    lines = [f"Top {len(fams)} process families by {label}",
             f"  {'PID':>7}  {'FAMILY':<32} {'PROCS':>5} {'CPU %':>7} {'RAM MB':>10}"]
    for f in fams:
        lines.append(f"  {f.root_pid:>7}  {f.root_name[:32]:<32} {f.process_count:>5} "
                     f"{f.cpu_percent:>7.1f} {f.rss_mb:>10,.1f}")
    return "\n".join(lines)
