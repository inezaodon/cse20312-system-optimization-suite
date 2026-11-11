"""Core Engine: poll a source, rank resource hogs, and flag idle processes.

Nothing is ever terminated. Idle processes are only reported, with the memory
that would be freed if the user chose to close them.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..sources.base import ProcessSource
from ..structures.heap import top_k
from .idle import IdleTracker
from .registry import Key, ProcessRecord, ProcessRegistry

METRICS = ("cpu", "ram")


@dataclass
class PollResult:
    t: float
    metric: str
    top: List[ProcessRecord]              # top-K by the chosen metric, largest first
    idle: List[ProcessRecord]             # idle candidates, largest RSS first
    savings_rss_mb: float                 # RSS that closing every idle candidate would free
    process_count: int
    restricted_count: int
    added: List[Key] = field(default_factory=list)
    removed: List[Key] = field(default_factory=list)
    elapsed: float = 0.0                  # seconds since this monitor's first poll


def _cpu(rec: ProcessRecord) -> float:
    return rec.snap.cpu_percent or 0.0


def _rss(rec: ProcessRecord) -> float:
    return rec.snap.rss_mb or 0.0


class Monitor:
    def __init__(self, source: ProcessSource, k: int = 10, metric: str = "cpu",
                 cpu_threshold: float = 1.0, idle_seconds: float = 300.0,
                 mine_only: bool = True, idle_min_rss_mb: float = 0.0) -> None:
        """
        mine_only:        only the user's own processes can be idle candidates
                          (system daemons are almost always quiet, and the user
                          can't close them anyway).
        idle_min_rss_mb:  ignore idle processes smaller than this.
        """
        if metric not in METRICS:
            raise ValueError(f"metric must be one of {METRICS}")
        self.source = source
        self.k = k
        self.metric = metric
        self.mine_only = mine_only
        self.idle_min_rss_mb = idle_min_rss_mb
        self.registry = ProcessRegistry()
        self.tracker = IdleTracker(cpu_threshold, idle_seconds)
        self.history: List[PollResult] = []
        self._t0: Optional[float] = None

    def poll_once(self) -> Optional[PollResult]:
        data = self.source.poll()
        if data is None:
            return None
        t, snaps = data
        if self._t0 is None:
            self._t0 = t
        added, removed = self.registry.update(t, snaps)
        records = self.registry.records()
        for rec in records:
            self.tracker.update(rec, t)

        result = PollResult(
            t=t,
            metric=self.metric,
            top=self.rank(records),
            idle=self._idle_candidates(records),
            savings_rss_mb=0.0,
            process_count=len(records),
            restricted_count=sum(1 for r in records if r.snap.restricted),
            added=added,
            removed=removed,
            elapsed=t - self._t0,
        )
        result.savings_rss_mb = round(sum(_rss(r) for r in result.idle), 2)
        self.history.append(result)
        return result

    def rank(self, records: List[ProcessRecord]) -> List[ProcessRecord]:
        """Top-K by the chosen metric, using the size-K min-heap (O(N log K))."""
        if self.metric == "cpu":
            # PID 0 (kernel_task on macOS) reports idle CPU time as usage; skip it.
            candidates = (r for r in records
                          if r.snap.cpu_percent is not None and r.snap.pid != 0)
            return top_k(candidates, self.k, key=_cpu)
        candidates = (r for r in records if r.snap.rss_mb is not None)
        return top_k(candidates, self.k, key=_rss)

    def _idle_candidates(self, records: List[ProcessRecord]) -> List[ProcessRecord]:
        idle = [r for r in records
                if r.is_idle
                and (r.snap.is_mine or not self.mine_only)
                and _rss(r) >= self.idle_min_rss_mb]
        return top_k(idle, len(idle), key=_rss)

    def run(self, n_polls: Optional[int] = None, interval: float = 2.0,
            on_result: Optional[Callable[[PollResult], None]] = None,
            sleep: Callable[[float], None] = time.sleep) -> List[PollResult]:
        """Poll repeatedly until n_polls is reached or the source runs out."""
        results: List[PollResult] = []
        while n_polls is None or len(results) < n_polls:
            if results and interval > 0:
                sleep(interval)
            res = self.poll_once()
            if res is None:
                break
            results.append(res)
            if on_result is not None:
                on_result(res)
        return results

    def idle_seconds_for(self, rec: ProcessRecord, t: float) -> float:
        return self.tracker.idle_for(rec, t)


# ----- text output ------------------------------------------------------------

def _fmt(value: Optional[float], width: int, digits: int = 1) -> str:
    return f"{'—':>{width}}" if value is None else f"{value:>{width}.{digits}f}"


def format_poll_result(res: PollResult, idle_limit: int = 5) -> str:
    lines = []
    lines.append(f"t=+{res.elapsed:.1f}s   processes={res.process_count}   "
                 f"restricted={res.restricted_count}   "
                 f"+{len(res.added)} / -{len(res.removed)} since last poll")
    label = "CPU %" if res.metric == "cpu" else "RAM"
    lines.append(f"\nTop {len(res.top)} by {label}")
    lines.append(f"  {'PID':>7}  {'NAME':<32} {'CPU %':>7} {'RSS MB':>9}")
    for r in res.top:
        s = r.snap
        lines.append(f"  {s.pid:>7}  {s.name[:32]:<32} {_fmt(s.cpu_percent, 7)} "
                     f"{_fmt(s.rss_mb, 9)}")
    lines.append(f"\nIdle candidates: {len(res.idle)}   "
                 f"potential savings: {res.savings_rss_mb:,.1f} MB RAM")
    for r in res.idle[:idle_limit]:
        s = r.snap
        idle_min = (res.t - r.below_since) / 60 if r.below_since is not None else 0.0
        lines.append(f"  {s.pid:>7}  {s.name[:32]:<32} {_fmt(s.rss_mb, 9)} MB   "
                     f"idle {idle_min:.1f} min")
    if len(res.idle) > idle_limit:
        lines.append(f"  ... and {len(res.idle) - idle_limit} more")
    return "\n".join(lines)
