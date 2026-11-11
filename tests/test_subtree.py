"""Unit tests for sysopt.profiler.subtree."""
from __future__ import annotations

import json
import unittest

from sysopt.profiler.subtree import ProcessTree, format_families, format_totals
from sysopt.sources.base import ProcessSnapshot
from sysopt.sources.snapshot import SnapshotSource
from tests.helpers import fixture


def first_poll(name):
    return SnapshotSource(fixture(name)).poll()[1]


def all_polls(name):
    src = SnapshotSource(fixture(name))
    polls = []
    while True:
        data = src.poll()
        if data is None:
            return polls
        polls.append(data[1])


def snap(pid, ppid, name="p", cpu=1.0, rss=10.0, mine=False):
    return ProcessSnapshot(pid, ppid, name, float(pid), cpu, rss, is_mine=mine)


class TestSubtreeTotals(unittest.TestCase):
    def setUp(self):
        self.tree = ProcessTree(first_poll("small_tree.json"))
        with open(fixture("small_tree.json")) as f:
            self.expected = json.load(f)["expected_subtree_totals"]

    def test_matches_hand_calculated_totals(self):
        for pid, exp in self.expected.items():
            for method in ("bfs", "dfs"):
                with self.subTest(pid=pid, method=method):
                    t = self.tree.subtree_totals(int(pid), method)
                    self.assertEqual(t.process_count, exp["count"])
                    self.assertAlmostEqual(t.cpu_percent, exp["cpu_percent"])
                    self.assertAlmostEqual(t.rss_mb, exp["rss_mb"])

    def test_bfs_and_dfs_same_members(self):
        for pid in (1, 20, 21):
            b = self.tree.subtree_totals(pid, "bfs").members
            d = self.tree.subtree_totals(pid, "dfs").members
            self.assertEqual(sorted(b), sorted(d))

    def test_traversal_orders_differ_as_expected(self):
        self.assertEqual(self.tree.subtree_totals(20, "bfs").members, [20, 21, 22, 23])
        self.assertEqual(self.tree.subtree_totals(1, "bfs").members[:4], [1, 10, 20, 30])
        self.assertEqual(self.tree.subtree_totals(1, "dfs").members[:4], [1, 10, 11, 12])

    def test_leaf_is_just_itself(self):
        t = self.tree.subtree_totals(22)
        self.assertEqual((t.process_count, t.members), (1, [22]))

    def test_unknown_pid_and_method(self):
        with self.assertRaises(KeyError):
            self.tree.subtree_totals(999)
        with self.assertRaises(ValueError):
            self.tree.subtree_totals(1, "astar")

    def test_unknown_readings_counted_not_summed(self):
        tree = ProcessTree([snap(1, 0), snap(2, 1, cpu=None, rss=None), snap(3, 1, cpu=None)])
        t = tree.subtree_totals(1)
        self.assertEqual(t.process_count, 3)
        self.assertEqual(t.unknown_count, 2)
        self.assertEqual(t.cpu_percent, 1.0)
        self.assertEqual(t.rss_mb, 20.0)


class TestReparentingAndEdgeCases(unittest.TestCase):
    def test_orphan_reparented_to_launchd(self):
        polls = all_polls("edge_cases.json")
        before, after = ProcessTree(polls[0]), ProcessTree(polls[1])
        self.assertIn(61, before.subtree_totals(60).members)
        self.assertNotIn(60, after)
        self.assertIn(61, after.subtree_totals(1).members)
        self.assertIn(61, after.family_heads())

    def test_missing_parent_becomes_root(self):
        tree = ProcessTree([snap(5, 999), snap(6, 5)])
        self.assertEqual(tree.graph.roots(), [5])
        self.assertEqual(tree.subtree_totals(5).process_count, 2)

    def test_pid_zero_self_loop_ignored(self):
        tree = ProcessTree([snap(0, 0, "kernel_task"), snap(1, 0, "launchd"), snap(7, 1, "App")])
        self.assertFalse(tree.graph.has_edge(0, 0))
        self.assertEqual(tree.subtree_totals(0).process_count, 3)


class TestFamilies(unittest.TestCase):
    def setUp(self):
        self.tree = ProcessTree(first_poll("small_tree.json"))

    def test_family_heads_are_children_of_launchd(self):
        self.assertEqual(sorted(self.tree.family_heads()), [10, 20, 30])

    def test_family_heads_under_kernel_task(self):
        tree = ProcessTree([snap(0, 0), snap(1, 0), snap(7, 1), snap(8, 1), snap(9, 7)])
        self.assertEqual(sorted(tree.family_heads()), [7, 8])

    def test_top_families_by_ram(self):
        fams = self.tree.top_families(k=2, metric="ram")
        self.assertEqual([(f.root_pid, f.rss_mb) for f in fams], [(20, 900.0), (10, 150.0)])

    def test_top_families_by_cpu(self):
        fams = self.tree.top_families(k=3, metric="cpu")
        self.assertEqual([f.root_pid for f in fams], [20, 10, 30])

    def test_mine_only(self):
        fams = self.tree.top_families(k=10, mine_only=True)
        self.assertEqual(sorted(f.root_pid for f in fams), [20, 30])

    def test_families_cover_every_non_system_process(self):
        covered = sum(f.process_count for f in self.tree.families())
        self.assertEqual(covered, len(self.tree) - 1)   # everything except launchd

    def test_invalid_metric(self):
        with self.assertRaises(ValueError):
            self.tree.top_families(metric="disk")


class TestFindByName(unittest.TestCase):
    def setUp(self):
        self.tree = ProcessTree(first_poll("small_tree.json"))

    def test_case_insensitive_sorted_by_ram(self):
        self.assertEqual(self.tree.find_by_name("BROWSER"), [21, 23, 20, 22])

    def test_family_roots_skip_matching_children(self):
        self.assertEqual(self.tree.find_family_roots("browser"), [20])
        self.assertEqual(self.tree.find_family_roots("renderer"), [23, 22])

    def test_no_match(self):
        self.assertEqual(self.tree.find_by_name("photoshop"), [])
        self.assertEqual(self.tree.find_family_roots("photoshop"), [])


class TestRendering(unittest.TestCase):
    def setUp(self):
        self.tree = ProcessTree(first_poll("small_tree.json"))

    def test_render_full_subtree(self):
        text = self.tree.render(20)
        lines = text.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("Browser (20)"))
        self.assertIn("└── Browser Helper (GPU) (21)", lines[1])
        self.assertIn("├── Browser Helper (Renderer) (23)", lines[2])   # bigger child first
        self.assertIn("└── Browser Helper (Renderer) (22)", lines[3])

    def test_max_depth(self):
        text = self.tree.render(20, max_depth=1)
        self.assertIn("... 2 more below", text)
        self.assertNotIn("(22)", text)

    def test_max_children(self):
        text = self.tree.render(1, max_depth=0, max_children=1)
        self.assertIn("... 9 more below", text)
        text = self.tree.render(1, max_children=1)
        self.assertIn("... 2 more children", text)

    def test_format_helpers(self):
        t = self.tree.subtree_totals(20)
        self.assertIn("Browser (20) family: 4 processes, 40.0% CPU, 900.0 MB RAM", format_totals(t))
        table = format_families(self.tree.top_families(2), "ram")
        self.assertIn("Browser", table)
        self.assertIn("900.0", table)


if __name__ == "__main__":
    unittest.main()
