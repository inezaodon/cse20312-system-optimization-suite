"""Live process data from the operating system, via psutil.

macOS details this class handles:
  * cpu_percent(None) measures CPU use since the previous call on the same
    Process object, so the first reading for any process is meaningless.
    Processes seen during priming (or a previous poll) get real readings;
    a process seen for the first time reports cpu_percent=None.
  * Many system processes raise AccessDenied for CPU or memory. Those
    metrics become None and the snapshot is marked restricted=True.
  * Processes can exit while we are reading them (NoSuchProcess /
    ZombieProcess). They are skipped.
"""
from __future__ import annotations

import getpass
import time
from typing import Any, Callable, Iterable, List, Optional

import psutil

from ..structures.hash_table import ChainedHashTable
from .base import PollData, ProcessSnapshot, ProcessSource

_ATTRS = ["pid", "ppid", "name", "create_time", "username"]
_MB = 1024 * 1024


class LiveSource(ProcessSource):
    def __init__(self, prime: bool = True, prime_seconds: float = 1.0,
                 clock: Callable[[], float] = time.time,
                 process_iter: Optional[Callable[[], Iterable[Any]]] = None) -> None:
        self._clock = clock
        self._process_iter = process_iter or (
            lambda: psutil.process_iter(_ATTRS, ad_value=None))
        self._user = getpass.getuser()
        # (pid, create_time) -> psutil.Process. Reusing the same object keeps
        # psutil's CPU baseline, so the next cpu_percent() call is meaningful.
        self._cache = ChainedHashTable()
        if prime:
            self._read_all()
            if prime_seconds > 0:
                time.sleep(prime_seconds)

    def poll(self) -> PollData:
        t = self._clock()
        return t, self._read_all()

    def _read_all(self) -> List[ProcessSnapshot]:
        new_cache = ChainedHashTable(capacity=max(8, len(self._cache) * 2))
        snaps: List[ProcessSnapshot] = []
        for proc in self._process_iter():
            info = getattr(proc, "info", {}) or {}
            if info.get("pid") is None:
                continue
            key = (int(info["pid"]), float(info.get("create_time") or 0.0))
            cached = self._cache.get(key)
            snap = self.snapshot_from(cached if cached is not None else proc,
                                      info, seen_before=cached is not None,
                                      current_user=self._user)
            if snap is None:
                continue
            new_cache[key] = cached if cached is not None else proc
            snaps.append(snap)
        # Processes that exited are dropped by replacing the cache.
        self._cache = new_cache
        return snaps

    @staticmethod
    def snapshot_from(proc: Any, info: dict, seen_before: bool,
                      current_user: str = "") -> Optional[ProcessSnapshot]:
        """Build one snapshot. Returns None if the process has exited."""
        restricted = False

        try:
            cpu: Optional[float] = float(proc.cpu_percent(None))
            if not seen_before:
                cpu = None          # first sample has no baseline
        except psutil.AccessDenied:
            cpu, restricted = None, True
        except psutil.NoSuchProcess:   # also covers ZombieProcess
            return None

        try:
            rss: Optional[float] = round(proc.memory_info().rss / _MB, 2)
        except psutil.AccessDenied:
            rss, restricted = None, True
        except psutil.NoSuchProcess:
            return None

        username = info.get("username")
        return ProcessSnapshot(
            pid=int(info["pid"]),
            ppid=int(info.get("ppid") or 0),
            name=info.get("name") or "?",
            create_time=float(info.get("create_time") or 0.0),
            cpu_percent=None if cpu is None else round(cpu, 2),
            rss_mb=rss,
            restricted=restricted,
            is_mine=bool(username) and username == current_user,
        )
