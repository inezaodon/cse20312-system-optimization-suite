"""Process registry: every live process, keyed by (pid, create_time).

Two ChainedHashTables:
  _records : (pid, create_time) -> ProcessRecord   (main store)
  _by_pid  : pid -> (pid, create_time)             (lookup by PID alone)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..sources.base import ProcessSnapshot
from ..structures.hash_table import ChainedHashTable

Key = Tuple[int, float]


@dataclass
class ProcessRecord:
    snap: ProcessSnapshot
    first_seen: float
    last_seen: float
    below_since: Optional[float] = None   # when CPU last dropped below the idle threshold
    is_idle: bool = False

    @property
    def key(self) -> Key:
        return self.snap.key


class ProcessRegistry:
    def __init__(self) -> None:
        self._records = ChainedHashTable()
        self._by_pid = ChainedHashTable()

    def update(self, t: float, snaps: List[ProcessSnapshot]) -> Tuple[List[Key], List[Key]]:
        """Apply one poll. Returns (added_keys, removed_keys).

        New processes are inserted, existing ones get the new snapshot, and
        processes missing from this poll are deleted. O(N) average per poll.
        """
        added: List[Key] = []
        seen = ChainedHashTable(capacity=max(8, len(snaps) * 2))
        for snap in snaps:
            key = snap.key
            seen[key] = True
            rec = self._records.get(key)
            if rec is None:
                self._records[key] = ProcessRecord(snap=snap, first_seen=t, last_seen=t)
                added.append(key)
            else:
                rec.snap = snap
                rec.last_seen = t
            self._by_pid[snap.pid] = key   # newest process with this PID wins

        removed = [key for key in self._records.keys() if key not in seen]
        for key in removed:
            del self._records[key]
            pid = key[0]
            # Only drop the PID index if it still points at the process that exited
            # (a reused PID may already point at the new process).
            if self._by_pid.get(pid) == key:
                del self._by_pid[pid]
        return added, removed

    def get(self, key: Key) -> Optional[ProcessRecord]:
        return self._records.get(key)

    def by_pid(self, pid: int) -> Optional[ProcessRecord]:
        key = self._by_pid.get(pid)
        return None if key is None else self._records.get(key)

    def records(self) -> List[ProcessRecord]:
        return list(self._records.values())

    def __contains__(self, key: Key) -> bool:
        return key in self._records

    def __len__(self) -> int:
        return len(self._records)
