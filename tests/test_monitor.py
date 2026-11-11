"""Unit tests for sysopt.engine.monitor."""
from __future__ import annotations

import unittest

from sysopt.engine.monitor import Monitor, format_poll_result
from sysopt.sources.snapshot import SnapshotSource
from tests.helpers import fixture


def pids(records):
    return [r.snap.pid for r in records]


class TestRanking(unittest.TestCase):
    def test_top_k_by_cpu(self):
        m = Monitor(SnapshotSource(fixture("small_tree.json")), k=5, metric="cpu")
        res = m.poll_once()
        self.assertEqual(pids(res.top), [21, 20, 23, 10, 22])
        self.assertEqual(res.process_count, 10)

    def test_top_k_by_ram(self):
        m = Monitor(SnapshotSource(fixture("small_tree.json")), k=3, metric="ram")
        self.assertEqual(pids(m.poll_once().top), [21, 23, 20])

    def test_k_larger_than_process_count(self):
        m = Monitor(SnapshotSource(fixture("small_tree.json")), k=50, metric="ram")
        self.assertEqual(len(m.poll_once().top), 10)

    def test_unknown_cpu_excluded_from_cpu_ranking(self):
        m = Monitor(SnapshotSource(fixture("edge_cases.json")), k=10, metric="cpu")
        res = m.poll_once()
        self.assertNotIn(70, pids(res.top))   # restricted
        self.assertNotIn(80, pids(res.top))   # no reading yet
        self.assertEqual(res.restricted_count, 1)
        res = m.poll_once()
        self.assertEqual(pids(res.top)[0], 80)  # Spotlight has a reading now (7.5%)

    def test_unknown_ram_excluded_from_ram_ranking(self):
        m = Monitor(SnapshotSource(fixture("edge_cases.json")), k=10, metric="ram")
        self.assertNotIn(70, pids(m.poll_once().top))

    def test_pid_zero_excluded_from_cpu_ranking(self):
        data = {"polls": [{"t": 0, "processes": [
            {"pid": 0, "ppid": 0, "name": "kernel_task", "create_time": 0, "cpu_percent": 900.0},
            {"pid": 5, "ppid": 0, "name": "app", "create_time": 1, "cpu_percent": 2.0}]}]}
        m = Monitor(SnapshotSource(data), k=5)
        self.assertEqual(pids(m.poll_once().top), [5])

    def test_invalid_metric(self):
        with self.assertRaises(ValueError):
            Monitor(SnapshotSource(fixture("small_tree.json")), metric="disk")


class TestIdleAndSavings(unittest.TestCase):
    def setUp(self):
        m = Monitor(SnapshotSource(fixture("idle_sequence.json")), k=3,
                    cpu_threshold=1.0, idle_seconds=300)
        self.results = {r.t: r for r in m.run(interval=0)}

    def test_runs_all_polls(self):
        self.assertEqual(sorted(self.results), [60.0 * i for i in range(8)])

    def test_idle_candidates_sorted_by_ram(self):
        self.assertEqual(pids(self.results[240.0].idle), [])
        self.assertEqual(pids(self.results[300.0].idle), [200, 100])   # Slack 400 MB, Notes 120 MB
        self.assertEqual(pids(self.results[360.0].idle), [100])

    def test_savings(self):
        self.assertEqual(self.results[300.0].savings_rss_mb, 520.0)
        self.assertEqual(self.results[420.0].savings_rss_mb, 120.0)

    def test_mine_only_excludes_system_processes(self):
        # launchd (pid 1) is quiet the whole time but isn't the user's process.
        for res in self.results.values():
            self.assertNotIn(1, pids(res.idle))

    def test_include_system_processes(self):
        m = Monitor(SnapshotSource(fixture("idle_sequence.json")),
                    idle_seconds=300, mine_only=False)
        res = m.run(interval=0)[-1]
        self.assertIn(1, pids(res.idle))

    def test_min_rss_filter(self):
        m = Monitor(SnapshotSource(fixture("idle_sequence.json")),
                    idle_seconds=300, idle_min_rss_mb=200)
        res = m.run(interval=0)
        self.assertEqual(pids(res[5].idle), [200])   # t=300: Notes (120 MB) filtered out
        self.assertEqual(res[5].savings_rss_mb, 400.0)


class TestRunAndFormat(unittest.TestCase):
    def test_run_respects_n_polls_and_sleeps_between(self):
        sleeps, seen = [], []
        m = Monitor(SnapshotSource(fixture("idle_sequence.json")))
        res = m.run(n_polls=3, interval=2.0, on_result=seen.append, sleep=sleeps.append)
        self.assertEqual(len(res), 3)
        self.assertEqual(seen, res)
        self.assertEqual(sleeps, [2.0, 2.0])
        self.assertEqual(m.history, res)

    def test_elapsed_is_relative_to_first_poll(self):
        data = {"polls": [{"t": 1_700_000_000.0, "processes": []},
                          {"t": 1_700_000_002.5, "processes": []}]}
        res = Monitor(SnapshotSource(data)).run(interval=0)
        self.assertEqual([r.elapsed for r in res], [0.0, 2.5])
        self.assertIn("t=+2.5s", format_poll_result(res[1]))

    def test_poll_after_end_returns_none(self):
        m = Monitor(SnapshotSource(fixture("small_tree.json")))
        self.assertIsNotNone(m.poll_once())
        self.assertIsNone(m.poll_once())

    def test_add_remove_counts(self):
        m = Monitor(SnapshotSource(fixture("edge_cases.json")))
        res = m.run(interval=0)
        self.assertEqual([(len(r.added), len(r.removed)) for r in res], [(6, 0), (1, 2), (1, 0)])

    def test_format_contains_key_info(self):
        m = Monitor(SnapshotSource(fixture("idle_sequence.json")), idle_seconds=300)
        text = format_poll_result(m.run(interval=0)[5])
        self.assertIn("Top", text)
        self.assertIn("Xcode", text)
        self.assertIn("520.0 MB", text)
        self.assertIn("Slack", text)

    def test_format_handles_unknown_values(self):
        m = Monitor(SnapshotSource(fixture("edge_cases.json")), metric="ram")
        text = format_poll_result(m.poll_once())
        self.assertIn("—", text)   # Spotlight has no CPU reading yet


if __name__ == "__main__":
    unittest.main()
