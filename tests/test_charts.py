"""Tests for sysopt.viz.charts: each chart writes a real PNG and rejects empty input."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from sysopt.cli import main
from sysopt.engine.monitor import Monitor
from sysopt.leaksim.heap_sim import SimulatedHeap
from sysopt.leaksim.report import scenario_rows
from sysopt.leaksim.scenarios import run_scenario
from sysopt.profiler.subtree import ProcessTree
from sysopt.sources.snapshot import RecordingSource, SnapshotSource
from sysopt.viz import charts
from tests.helpers import fixture

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class ChartTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def path(self, name):
        return os.path.join(self.dir, name)

    def assertPng(self, path):
        self.assertTrue(os.path.exists(path), path)
        with open(path, "rb") as f:
            self.assertEqual(f.read(8), PNG_MAGIC)
        self.assertGreater(os.path.getsize(path), 5000)


class TestCharts(ChartTestCase):
    def _session(self):
        rec = RecordingSource(SnapshotSource(fixture("idle_sequence.json")))
        m = Monitor(rec, idle_seconds=300)
        m.run(interval=0)
        return rec.raw, m.history

    def test_resource_timeline(self):
        polls, _ = self._session()
        for metric in ("ram", "cpu"):
            self.assertPng(charts.plot_resource_timeline(polls, self.path(f"t_{metric}.png"),
                                                         metric=metric, top_n=3))

    def test_timeline_validation(self):
        polls, _ = self._session()
        with self.assertRaises(ValueError):
            charts.plot_resource_timeline([], self.path("x.png"))
        with self.assertRaises(ValueError):
            charts.plot_resource_timeline(polls, self.path("x.png"), metric="disk")

    def test_savings(self):
        _, history = self._session()
        self.assertPng(charts.plot_savings(history, self.path("s.png")))
        with self.assertRaises(ValueError):
            charts.plot_savings([], self.path("x.png"))

    def test_family_breakdown(self):
        tree = ProcessTree(SnapshotSource(fixture("small_tree.json")).poll()[1])
        self.assertPng(charts.plot_family_breakdown(tree.top_families(5), self.path("f.png")))
        with self.assertRaises(ValueError):
            charts.plot_family_breakdown([], self.path("x.png"))

    def test_leak_velocity(self):
        self.assertPng(charts.plot_leak_velocity(run_scenario("slow_leak"), self.path("v.png")))
        with self.assertRaises(ValueError):
            charts.plot_leak_velocity(SimulatedHeap(), self.path("x.png"))

    def test_leak_scenarios(self):
        rows = scenario_rows()
        self.assertEqual(dict(rows)["cycle_leak"], {"leaked_bytes": 96, "refcount_missed_bytes": 96})
        self.assertEqual(dict(rows)["partial_free"]["refcount_missed_bytes"], 0)
        self.assertPng(charts.plot_leak_scenarios(rows, self.path("l.png")))

    def test_creates_missing_folders(self):
        out = self.path("a/b/c/v.png")
        self.assertPng(charts.plot_leak_velocity(run_scenario("lost_head"), out))


class TestCliPlots(ChartTestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(list(argv))
        return code, out.getvalue()

    def test_watch_plot(self):
        code, out = self.run_cli("watch", "--source", fixture("idle_sequence.json"),
                                 "--plot", self.dir)
        self.assertEqual(code, 0)
        for name in ("timeline_ram.png", "timeline_cpu.png", "savings.png"):
            self.assertPng(self.path(name))

    def test_families_plot(self):
        code, _ = self.run_cli("families", "--source", fixture("small_tree.json"),
                               "--plot", self.path("f.png"))
        self.assertEqual(code, 0)
        self.assertPng(self.path("f.png"))

    def test_leaks_plots(self):
        self.run_cli("leaks", "--plot", self.path("all.png"))
        self.run_cli("leaks", "--scenario", "slow_leak", "--plot", self.path("one.png"))
        self.assertPng(self.path("all.png"))
        self.assertPng(self.path("one.png"))


if __name__ == "__main__":
    unittest.main()
