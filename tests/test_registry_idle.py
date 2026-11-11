"""Unit tests for sysopt.engine.registry and sysopt.engine.idle."""
from __future__ import annotations

import unittest

from sysopt.engine.idle import IdleTracker
from sysopt.engine.registry import ProcessRecord, ProcessRegistry
from sysopt.sources.base import ProcessSnapshot
from sysopt.sources.snapshot import SnapshotSource
from tests.helpers import fixture


def run_polls(path, tracker=None):
    """Replay a fixture through a registry (and tracker). Yields (t, registry, added, removed)."""
    src = SnapshotSource(fixture(path))
    reg = ProcessRegistry()
    while True:
        data = src.poll()
        if data is None:
            return
        t, snaps = data
        added, removed = reg.update(t, snaps)
        if tracker is not None:
            for rec in reg.records():
                tracker.update(rec, t)
        yield t, reg, added, removed


class TestProcessRegistry(unittest.TestCase):
    def setUp(self):
        self.states = {}
        for t, reg, added, removed in run_polls("edge_cases.json"):
            self.states[t] = (sorted(added), sorted(removed),
                              {r.key: (r.snap.name, r.snap.ppid, r.first_seen, r.last_seen)
                               for r in reg.records()})
        self.reg = reg

    def test_first_poll_adds_everything(self):
        added, removed, recs = self.states[0.0]
        self.assertEqual(len(added), 6)
        self.assertEqual(removed, [])
        self.assertEqual(len(recs), 6)

    def test_exited_processes_are_removed(self):
        added, removed, recs = self.states[10.0]
        self.assertEqual(removed, [(50, 1000.0), (60, 1000.0)])
        self.assertEqual(added, [(51, 1500.0)])
        self.assertNotIn((50, 1000.0), recs)

    def test_reparented_child(self):
        _, _, recs = self.states[10.0]
        self.assertEqual(recs[(61, 1001.0)][1], 1)

    def test_existing_process_keeps_first_seen(self):
        _, _, recs = self.states[20.0]
        name, ppid, first_seen, last_seen = recs[(61, 1001.0)]
        self.assertEqual((first_seen, last_seen), (0.0, 20.0))

    def test_pid_reuse_is_a_new_process(self):
        added, _, recs = self.states[20.0]
        self.assertEqual(added, [(50, 2000.0)])
        rec = self.reg.by_pid(50)
        self.assertEqual(rec.snap.name, "Calculator")
        self.assertEqual(rec.first_seen, 20.0)
        self.assertIsNone(self.reg.get((50, 1000.0)))

    def test_by_pid(self):
        self.assertEqual(self.reg.by_pid(61).snap.name, "Child")
        self.assertIsNone(self.reg.by_pid(60))      # exited
        self.assertIsNone(self.reg.by_pid(99999))   # never existed

    def test_reused_pid_in_same_poll_keeps_index(self):
        # Old process (5, 1.0) exits and new (5, 2.0) appears in the same poll.
        reg = ProcessRegistry()
        reg.update(0, [ProcessSnapshot(5, 1, "old", 1.0)])
        reg.update(1, [ProcessSnapshot(5, 1, "new", 2.0)])
        self.assertEqual(reg.by_pid(5).snap.name, "new")
        self.assertEqual(len(reg), 1)

    def test_contains_and_len(self):
        self.assertIn((51, 1500.0), self.reg)
        self.assertEqual(len(self.reg), 6)


class TestIdleTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = IdleTracker(cpu_threshold=1.0, idle_seconds=300)
        self.idle_at = {}   # pid -> list of times it was idle
        for t, reg, _, _ in run_polls("idle_sequence.json", self.tracker):
            for rec in reg.records():
                if rec.is_idle:
                    self.idle_at.setdefault(rec.snap.pid, []).append(t)

    def test_quiet_process_becomes_idle_exactly_at_T(self):
        # Below threshold from t=0; 240 s is not enough, 300 s is.
        self.assertEqual(self.idle_at[100], [300.0, 360.0, 420.0])

    def test_spike_resets_timer(self):
        self.assertEqual(self.idle_at[200], [300.0])

    def test_busy_process_never_idle(self):
        self.assertNotIn(300, self.idle_at)

    def test_threshold_is_strict(self):
        self.assertNotIn(400, self.idle_at)   # exactly 1.0% is not "below" 1.0%

    def _rec(self, cpu):
        return ProcessRecord(ProcessSnapshot(1, 0, "p", 1.0, cpu_percent=cpu), 0, 0)

    def test_unknown_cpu_is_never_idle(self):
        rec = self._rec(None)
        tr = IdleTracker(1.0, 0)
        tr.update(rec, 0)
        tr.update(rec, 1000)
        self.assertFalse(rec.is_idle)
        self.assertIsNone(rec.below_since)

    def test_unknown_cpu_resets_timer(self):
        tr = IdleTracker(1.0, 10)
        rec = self._rec(0.0)
        tr.update(rec, 0)
        rec.snap = ProcessSnapshot(1, 0, "p", 1.0, cpu_percent=None, restricted=True)
        tr.update(rec, 5)
        rec.snap = ProcessSnapshot(1, 0, "p", 1.0, cpu_percent=0.0)
        tr.update(rec, 10)
        self.assertFalse(rec.is_idle)          # timer restarted at t=10
        self.assertEqual(tr.idle_for(rec, 15), 5)

    def test_zero_idle_seconds(self):
        tr = IdleTracker(1.0, 0)
        rec = self._rec(0.5)
        tr.update(rec, 42)
        self.assertTrue(rec.is_idle)

    def test_invalid_settings(self):
        with self.assertRaises(ValueError):
            IdleTracker(cpu_threshold=0)
        with self.assertRaises(ValueError):
            IdleTracker(idle_seconds=-1)


if __name__ == "__main__":
    unittest.main()
