"""Idle detection.

The OS does not report when a user last interacted with an app, so idleness
is inferred from CPU activity: a process is idle when its CPU usage has stayed
strictly below `cpu_threshold` percent for at least `idle_seconds`.

A process with no CPU reading (restricted, or first sample) is never idle:
its activity is unknown.
"""
from __future__ import annotations

from .registry import ProcessRecord


class IdleTracker:
    def __init__(self, cpu_threshold: float = 1.0, idle_seconds: float = 300.0) -> None:
        if cpu_threshold <= 0:
            raise ValueError("cpu_threshold must be positive")
        if idle_seconds < 0:
            raise ValueError("idle_seconds must not be negative")
        self.cpu_threshold = cpu_threshold
        self.idle_seconds = idle_seconds

    def update(self, rec: ProcessRecord, t: float) -> None:
        cpu = rec.snap.cpu_percent
        if cpu is None or cpu >= self.cpu_threshold:
            rec.below_since = None
            rec.is_idle = False
            return
        if rec.below_since is None:
            rec.below_since = t
        rec.is_idle = (t - rec.below_since) >= self.idle_seconds

    def idle_for(self, rec: ProcessRecord, t: float) -> float:
        """Seconds the process has been below the threshold (0 if it isn't)."""
        return 0.0 if rec.below_since is None else t - rec.below_since
