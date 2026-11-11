"""Replay process data from JSON, and record any source into that JSON format.

Fixture format:
    {
      "description": "...",            (optional; any extra keys are ignored)
      "polls": [
        {"t": 0.0, "processes": [ {pid, ppid, name, create_time,
                                   cpu_percent, rss_mb, restricted, is_mine}, ... ]},
        ...
      ]
    }
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional, Union

from .base import PollData, ProcessSnapshot, ProcessSource


class SnapshotSource(ProcessSource):
    """Returns the recorded polls one at a time, then None."""

    def __init__(self, path_or_data: Union[str, Dict[str, Any]]) -> None:
        if isinstance(path_or_data, str):
            with open(path_or_data) as f:
                data = json.load(f)
            self.path: Optional[str] = path_or_data
        else:
            data = path_or_data
            self.path = None
        self._polls: List[PollData] = self._parse(data)
        self._next = 0

    @staticmethod
    def _parse(data: Dict[str, Any]) -> List[PollData]:
        if not isinstance(data, dict) or not isinstance(data.get("polls"), list):
            raise ValueError("snapshot data must be an object with a 'polls' list")
        polls: List[PollData] = []
        last_t = float("-inf")
        for i, poll in enumerate(data["polls"]):
            if "t" not in poll or "processes" not in poll:
                raise ValueError(f"poll {i} needs 't' and 'processes'")
            t = float(poll["t"])
            if t < last_t:
                raise ValueError(f"poll {i}: timestamps must not go backwards")
            last_t = t
            polls.append((t, [ProcessSnapshot.from_dict(p) for p in poll["processes"]]))
        return polls

    def poll(self) -> Optional[PollData]:
        if self._next >= len(self._polls):
            return None
        result = self._polls[self._next]
        self._next += 1
        return result

    def reset(self) -> None:
        self._next = 0

    def __len__(self) -> int:
        return len(self._polls)


class RecordingSource(ProcessSource):
    """Wraps another source and keeps a copy of every poll, to save later."""

    def __init__(self, inner: ProcessSource) -> None:
        self.inner = inner
        self._polls: List[Dict[str, Any]] = []
        self._t0: Optional[float] = None

    def poll(self) -> Optional[PollData]:
        data = self.inner.poll()
        if data is not None:
            t, snaps = data
            if self._t0 is None:
                self._t0 = t
            self._polls.append({"t": round(t - self._t0, 3),
                                "processes": [s.to_dict() for s in snaps]})
        return data

    def __len__(self) -> int:
        return len(self._polls)

    def save(self, out_path: str, description: str = "") -> int:
        doc = {"description": description or f"Recorded session: {len(self._polls)} polls.",
               "polls": self._polls}
        with open(out_path, "w") as f:
            json.dump(doc, f, indent=1)
        return len(self._polls)


def record_session(source: ProcessSource, n_polls: int, interval: float, out_path: str,
                   description: str = "",
                   sleep: Callable[[float], None] = time.sleep) -> int:
    """Poll `source` up to n_polls times and save the results as a fixture.

    Timestamps are stored relative to the first poll, so recordings start at t=0.
    Returns the number of polls written.
    """
    rec = RecordingSource(source)
    for i in range(n_polls):
        if i > 0 and interval > 0:
            sleep(interval)
        if rec.poll() is None:
            break
    return rec.save(out_path, description or
                    f"Recorded session: {len(rec)} polls, {interval}s apart.")
