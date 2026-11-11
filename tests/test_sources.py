"""Unit tests for sysopt.sources (snapshot model, SnapshotSource, recorder, LiveSource)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

import psutil

from sysopt.sources.base import ProcessSnapshot
from sysopt.sources.live import LiveSource
from sysopt.sources.snapshot import SnapshotSource, record_session
from tests.helpers import fixture


class TestProcessSnapshot(unittest.TestCase):
    def test_key_is_pid_and_create_time(self):
        s = ProcessSnapshot(pid=5, ppid=1, name="x", create_time=12.5)
        self.assertEqual(s.key, (5, 12.5))

    def test_dict_round_trip(self):
        s = ProcessSnapshot(pid=5, ppid=1, name="x", create_time=12.5,
                            cpu_percent=3.25, rss_mb=None, restricted=True, is_mine=True)
        self.assertEqual(ProcessSnapshot.from_dict(s.to_dict()), s)

    def test_from_dict_defaults(self):
        s = ProcessSnapshot.from_dict({"pid": 1, "ppid": 0, "name": "a", "create_time": 1})
        self.assertIsNone(s.cpu_percent)
        self.assertIsNone(s.rss_mb)
        self.assertFalse(s.restricted)
        self.assertFalse(s.is_mine)

    def test_from_dict_missing_field(self):
        with self.assertRaises(ValueError):
            ProcessSnapshot.from_dict({"pid": 1, "name": "a"})


class TestSnapshotSource(unittest.TestCase):
    def test_reads_polls_in_order_then_none(self):
        src = SnapshotSource(fixture("edge_cases.json"))
        self.assertEqual(len(src), 3)
        times = []
        while True:
            data = src.poll()
            if data is None:
                break
            times.append(data[0])
        self.assertEqual(times, [0.0, 10.0, 20.0])
        self.assertIsNone(src.poll())

    def test_reset(self):
        src = SnapshotSource(fixture("small_tree.json"))
        first = src.poll()
        self.assertIsNone(src.poll())
        src.reset()
        self.assertEqual(src.poll(), first)

    def test_nulls_and_flags_are_preserved(self):
        t, snaps = SnapshotSource(fixture("edge_cases.json")).poll()
        by_pid = {s.pid: s for s in snaps}
        self.assertTrue(by_pid[70].restricted)
        self.assertIsNone(by_pid[70].cpu_percent)
        self.assertIsNone(by_pid[80].cpu_percent)
        self.assertFalse(by_pid[80].restricted)
        self.assertTrue(by_pid[50].is_mine)

    def test_accepts_dict(self):
        src = SnapshotSource({"polls": [{"t": 0, "processes": []}]})
        self.assertEqual(src.poll(), (0.0, []))

    def test_invalid_data(self):
        with self.assertRaises(ValueError):
            SnapshotSource({"nope": []})
        with self.assertRaises(ValueError):
            SnapshotSource({"polls": [{"t": 0}]})
        with self.assertRaises(ValueError):
            SnapshotSource({"polls": [{"t": 5, "processes": []}, {"t": 1, "processes": []}]})

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            SnapshotSource(fixture("does_not_exist.json"))


class TestRecordSession(unittest.TestCase):
    def test_round_trip_through_recorder(self):
        original = SnapshotSource(fixture("idle_sequence.json"))
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "rec.json")
            n = record_session(original, n_polls=100, interval=0, out_path=out)
            self.assertEqual(n, 8)
            replay = SnapshotSource(out)
            original.reset()
            for _ in range(8):
                self.assertEqual(replay.poll(), original.poll())

    def test_timestamps_relative_to_first_poll(self):
        src = SnapshotSource({"polls": [{"t": 1000.0, "processes": []},
                                        {"t": 1002.5, "processes": []}]})
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "rec.json")
            record_session(src, 2, 0, out)
            with open(out) as f:
                self.assertEqual([p["t"] for p in json.load(f)["polls"]], [0.0, 2.5])

    def test_stops_at_n_polls_and_sleeps_between(self):
        sleeps = []
        src = SnapshotSource(fixture("idle_sequence.json"))
        with tempfile.TemporaryDirectory() as d:
            n = record_session(src, 3, 2.0, os.path.join(d, "r.json"), sleep=sleeps.append)
        self.assertEqual(n, 3)
        self.assertEqual(sleeps, [2.0, 2.0])


# ----- LiveSource: exception handling with fake psutil processes ------------------

class FakeMemInfo:
    def __init__(self, rss):
        self.rss = rss


class FakeProc:
    """Stands in for psutil.Process. cpu/mem can be a value or an exception to raise."""

    def __init__(self, pid, ppid=1, name="fake", create_time=100.0, username="me",
                 cpu=5.0, rss=10 * 1024 * 1024):
        self.info = {"pid": pid, "ppid": ppid, "name": name,
                     "create_time": create_time, "username": username}
        self._cpu, self._rss = cpu, rss

    def cpu_percent(self, interval=None):
        if isinstance(self._cpu, Exception):
            raise self._cpu
        return self._cpu

    def memory_info(self):
        if isinstance(self._rss, Exception):
            raise self._rss
        return FakeMemInfo(self._rss)


class TestLiveSourceLogic(unittest.TestCase):
    def test_normal_process(self):
        p = FakeProc(10, cpu=12.345, rss=50 * 1024 * 1024)
        s = LiveSource.snapshot_from(p, p.info, seen_before=True, current_user="me")
        self.assertEqual(s.cpu_percent, 12.35)
        self.assertEqual(s.rss_mb, 50.0)
        self.assertFalse(s.restricted)
        self.assertTrue(s.is_mine)

    def test_first_sample_has_no_cpu(self):
        p = FakeProc(10, cpu=0.0)
        s = LiveSource.snapshot_from(p, p.info, seen_before=False)
        self.assertIsNone(s.cpu_percent)
        self.assertFalse(s.restricted)

    def test_access_denied(self):
        p = FakeProc(10, cpu=psutil.AccessDenied(10), rss=psutil.AccessDenied(10))
        s = LiveSource.snapshot_from(p, p.info, seen_before=True)
        self.assertIsNone(s.cpu_percent)
        self.assertIsNone(s.rss_mb)
        self.assertTrue(s.restricted)

    def test_exited_process_is_skipped(self):
        for proc in (FakeProc(10, cpu=psutil.NoSuchProcess(10)),
                     FakeProc(10, rss=psutil.NoSuchProcess(10)),
                     FakeProc(10, cpu=psutil.ZombieProcess(10))):
            self.assertIsNone(LiveSource.snapshot_from(proc, proc.info, seen_before=True))

    def test_other_users_process(self):
        p = FakeProc(10, username="root")
        s = LiveSource.snapshot_from(p, p.info, seen_before=True, current_user="me")
        self.assertFalse(s.is_mine)

    def test_cache_gives_cpu_on_second_poll_and_drops_exited(self):
        procs = [FakeProc(1, cpu=3.0), FakeProc(2, cpu=4.0)]
        clock = iter([100.0, 102.0, 104.0])
        src = LiveSource(prime=False, clock=lambda: next(clock), process_iter=lambda: procs)
        t, first = src.poll()
        self.assertEqual(t, 100.0)
        self.assertTrue(all(s.cpu_percent is None for s in first))
        _, second = src.poll()
        self.assertEqual(sorted(s.cpu_percent for s in second), [3.0, 4.0])
        procs.pop()                 # process 2 exits
        procs.append(FakeProc(3))   # process 3 starts
        _, third = src.poll()
        by_pid = {s.pid: s for s in third}
        self.assertEqual(set(by_pid), {1, 3})
        self.assertEqual(by_pid[1].cpu_percent, 3.0)
        self.assertIsNone(by_pid[3].cpu_percent)


class TestLiveSourceSmoke(unittest.TestCase):
    """Reads the real OS once. Checks structure only, not specific values."""

    def test_finds_this_process(self):
        src = LiveSource(prime=True, prime_seconds=0.05)
        t, snaps = src.poll()
        self.assertGreater(t, 0)
        self.assertGreater(len(snaps), 1)
        me = [s for s in snaps if s.pid == os.getpid()]
        self.assertEqual(len(me), 1)
        self.assertTrue(me[0].is_mine)
        self.assertIsNotNone(me[0].rss_mb)
        self.assertIsNotNone(me[0].cpu_percent)   # primed, so it has a reading


if __name__ == "__main__":
    unittest.main()
