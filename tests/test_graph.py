"""Unit tests for sysopt.structures.graph."""
from __future__ import annotations

import random
import unittest

from sysopt.structures.graph import DirectedGraph


def tree():
    """1 -> {10, 20}; 10 -> {11, 12}; 20 -> {21}; 21 -> {22, 23}"""
    g = DirectedGraph()
    for u, v in [(1, 10), (1, 20), (10, 11), (10, 12), (20, 21), (21, 22), (21, 23)]:
        g.add_edge(u, v)
    return g


class TestStructure(unittest.TestCase):
    def test_add_edge_creates_vertices(self):
        g = DirectedGraph()
        g.add_edge("a", "b")
        self.assertTrue(g.has_vertex("a"))
        self.assertTrue(g.has_vertex("b"))
        self.assertTrue(g.has_edge("a", "b"))
        self.assertFalse(g.has_edge("b", "a"))
        self.assertEqual(len(g), 2)
        self.assertEqual(g.edge_count(), 1)

    def test_duplicate_edge_ignored(self):
        g = DirectedGraph()
        g.add_edge(1, 2)
        g.add_edge(1, 2)
        self.assertEqual(g.neighbors(1), [2])
        self.assertEqual(g.edge_count(), 1)

    def test_add_vertex_idempotent(self):
        g = DirectedGraph()
        g.add_edge(1, 2)
        g.add_vertex(1)
        self.assertEqual(g.neighbors(1), [2])

    def test_neighbors_and_predecessors(self):
        g = tree()
        self.assertEqual(g.neighbors(1), [10, 20])
        self.assertEqual(g.neighbors(22), [])
        self.assertEqual(g.predecessors(21), [20])
        self.assertEqual(g.predecessors(1), [])

    def test_missing_vertex(self):
        g = tree()
        with self.assertRaises(KeyError):
            g.neighbors(999)
        with self.assertRaises(KeyError):
            g.bfs(999)
        with self.assertRaises(KeyError):
            g.dfs(999)
        with self.assertRaises(KeyError):
            g.remove_vertex(999)

    def test_roots(self):
        g = tree()
        g.add_vertex(50)            # isolated vertex is also a root
        self.assertEqual(sorted(g.roots()), [1, 50])

    def test_remove_edge(self):
        g = tree()
        g.remove_edge(1, 20)
        self.assertNotIn(20, g.neighbors(1))
        self.assertIn(20, g.roots())
        self.assertEqual(g.edge_count(), 6)
        with self.assertRaises(KeyError):
            g.remove_edge(1, 20)

    def test_remove_vertex_cleans_both_directions(self):
        g = tree()
        g.remove_vertex(21)
        self.assertFalse(g.has_vertex(21))
        self.assertEqual(g.neighbors(20), [])
        self.assertEqual(g.predecessors(22), [])
        self.assertEqual(sorted(g.roots()), [1, 22, 23])
        self.assertEqual(g.edge_count(), 4)

    def test_remove_vertex_with_self_loop(self):
        g = DirectedGraph()
        g.add_edge(1, 1)
        g.add_edge(1, 2)
        g.remove_vertex(1)
        self.assertEqual(g.edge_count(), 0)
        self.assertEqual(g.predecessors(2), [])


class TestTraversal(unittest.TestCase):
    def test_bfs_order(self):
        self.assertEqual(tree().bfs(1), [1, 10, 20, 11, 12, 21, 22, 23])

    def test_dfs_order(self):
        self.assertEqual(tree().dfs(1), [1, 10, 11, 12, 20, 21, 22, 23])

    def test_subtree_only(self):
        g = tree()
        self.assertEqual(g.bfs(20), [20, 21, 22, 23])
        self.assertEqual(g.dfs(10), [10, 11, 12])
        self.assertEqual(g.bfs(22), [22])

    def test_bfs_and_dfs_visit_same_set(self):
        random.seed(5)
        g = DirectedGraph()
        for v in range(1, 200):                       # random tree
            g.add_edge(random.randint(0, v - 1), v)
        for start in [0, 3, 50]:
            self.assertEqual(set(g.bfs(start)), set(g.dfs(start)))
        self.assertEqual(len(g.bfs(0)), 200)

    def test_cycle_terminates(self):
        g = DirectedGraph()
        g.add_edge("A", "B")
        g.add_edge("B", "C")
        g.add_edge("C", "A")
        self.assertEqual(g.bfs("A"), ["A", "B", "C"])
        self.assertEqual(g.dfs("B"), ["B", "C", "A"])

    def test_diamond_visits_once(self):
        g = DirectedGraph()
        for u, v in [(1, 2), (1, 3), (2, 4), (3, 4)]:
            g.add_edge(u, v)
        self.assertEqual(g.bfs(1), [1, 2, 3, 4])
        self.assertEqual(g.dfs(1), [1, 2, 4, 3])

    def test_reachable_multi_source(self):
        g = tree()
        g.add_edge(100, 101)
        self.assertEqual(g.reachable([10, 21]), {10, 11, 12, 21, 22, 23})
        self.assertEqual(g.reachable([100]), {100, 101})
        self.assertEqual(g.reachable([]), set())
        self.assertEqual(g.reachable([999]), set())   # unknown starts ignored

    def test_reachable_with_cycle_and_mixed_labels(self):
        # Shape of the leak simulator's pointer graph: roots are strings, blocks are ints.
        g = DirectedGraph()
        g.add_edge("root:head", 0x1000)
        g.add_edge(0x1000, 0x1010)
        g.add_edge(0x2000, 0x2010)
        g.add_edge(0x2010, 0x2000)     # cycle with no root pointing at it
        self.assertEqual(g.reachable(["root:head"]), {"root:head", 0x1000, 0x1010})

    def test_deep_chain_no_recursion_error(self):
        g = DirectedGraph()
        for i in range(5000):
            g.add_edge(i, i + 1)
        self.assertEqual(len(g.dfs(0)), 5001)


if __name__ == "__main__":
    unittest.main()
