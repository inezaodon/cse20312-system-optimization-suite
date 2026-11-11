"""The shared process data model and the ProcessSource interface.

Every subsystem reads processes through a ProcessSource, so the same code runs
on live psutil data (LiveSource) or on recorded JSON fixtures (SnapshotSource).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ProcessSnapshot:
    """One process at one moment in time.

    cpu_percent / rss_mb are None when the value is unknown:
      * restricted=True  -> the OS denied access (psutil.AccessDenied)
      * restricted=False -> no reading yet (a process's first CPU sample is
        meaningless, because psutil measures CPU since the previous call)
    """
    pid: int
    ppid: int
    name: str
    create_time: float
    cpu_percent: Optional[float] = None
    rss_mb: Optional[float] = None
    restricted: bool = False
    is_mine: bool = False   # owned by the user running the tool

    @property
    def key(self) -> Tuple[int, float]:
        """(pid, create_time) is unique even when the OS reuses a PID."""
        return (self.pid, self.create_time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "ppid": self.ppid,
            "name": self.name,
            "create_time": self.create_time,
            "cpu_percent": self.cpu_percent,
            "rss_mb": self.rss_mb,
            "restricted": self.restricted,
            "is_mine": self.is_mine,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProcessSnapshot":
        missing = [f for f in ("pid", "ppid", "name", "create_time") if f not in d]
        if missing:
            raise ValueError(f"process entry missing fields {missing}: {d}")
        cpu = d.get("cpu_percent")
        rss = d.get("rss_mb")
        return cls(
            pid=int(d["pid"]),
            ppid=int(d["ppid"]),
            name=str(d["name"]),
            create_time=float(d["create_time"]),
            cpu_percent=None if cpu is None else float(cpu),
            rss_mb=None if rss is None else float(rss),
            restricted=bool(d.get("restricted", False)),
            is_mine=bool(d.get("is_mine", False)),
        )


PollData = Tuple[float, List[ProcessSnapshot]]


class ProcessSource(ABC):
    """Anything that can be polled for the current list of processes."""

    @abstractmethod
    def poll(self) -> Optional[PollData]:
        """Return (timestamp_seconds, snapshots), or None when no data is left."""
