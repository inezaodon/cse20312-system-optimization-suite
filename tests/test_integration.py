"""End-to-end test: one data source feeding all three subsystems together."""
from __future__ import annotations

import unittest

from sysopt.engine.monitor import Monitor
from sysopt.leaksim.scenarios import SCENARIOS, run_scenario
from sysopt.profiler.subtree import ProcessTree
from sysopt.sources.snapshot import RecordingSource, SnapshotSource
from tests.helpers import fixture


class TestEndToEnd(unittest.TestCase):
    def test_monitor_then_profiler_on_every_poll(self):
        """Source -> Monitor (registry, idle, ranking) -> ProcessTree, for each fixture."""
        for name in ("small_tree.json", "idle_sequence.json", "edge_cases.json"):
            with self.subTest(fixture=name):
                rec = RecordingSource(SnapshotSource(fixture(name)))
                monitor = Monitor(rec, k=5, idle_seconds=300)
                results = monitor.run(interval=0)
                self.assertEqual(len(results), len(rec.raw))
                for (t, snaps), res in zip(rec.raw, results):
                    # Registry and source agree on what's running.
                    self.assertEqual(res.process_count, len(snaps))
                    tree = ProcessTree(snaps)
                    families = tree.families()
                    # Every process is in exactly one family or is a system root.
                    covered = sorted(m for f in families for m in f.members)
                    self.assertEqual(len(covered), len(set(covered)))
                    system = [s.pid for s in snaps if s.pid in (0, 1)]
                    self.assertEqual(sorted(covered + system), sorted(s.pid for s in snaps))
                    # Family RAM adds up to total RAM (excluding system roots).
                    total = sum(s.rss_mb or 0 for s in snaps if s.pid not in (0, 1))
                    self.assertAlmostEqual(sum(f.rss_mb for f in families), total, places=6)
                    # Top-K by CPU is really the top K.
                    cpus = sorted((s.cpu_percent for s in snaps
                                   if s.cpu_percent is not None and s.pid != 0), reverse=True)
                    self.assertEqual([r.snap.cpu_percent for r in res.top], cpus[:5])

    def test_idle_processes_belong_to_families(self):
        rec = RecordingSource(SnapshotSource(fixture("idle_sequence.json")))
        res = Monitor(rec, idle_seconds=300).run(interval=0)[5]   # t=300
        tree = ProcessTree(rec.raw[5][1])
        heads = set(tree.family_heads())
        self.assertTrue(all(r.snap.pid in heads for r in res.idle))

    def test_leak_simulator_uses_graph_reachability(self):
        for s in SCENARIOS:
            heap = run_scenario(s.name)
            reached = heap.reachable_addresses()
            leaked = {b.address for b in heap.detect_leaks()}
            live = {b.address for b in heap.blocks()}
            self.assertEqual(reached | leaked, live)
            self.assertEqual(reached & leaked, set())


if __name__ == "__main__":
    unittest.main()
