"""Unit tests for sysopt.leaksim (simulated heap, leak detection, scenarios, reports)."""
from __future__ import annotations

import io
import random
import unittest
from contextlib import redirect_stderr, redirect_stdout

from sysopt.cli import main
from sysopt.leaksim.heap_sim import (DoubleFreeError, InvalidFreeError,
                                     InvalidPointerError, SimulatedHeap)
from sysopt.leaksim.report import format_heap_report, format_summary
from sysopt.leaksim.scenarios import SCENARIOS, get_scenario, run_scenario


def addrs(blocks):
    return [b.address for b in blocks]


class TestMallocFree(unittest.TestCase):
    def setUp(self):
        self.heap = SimulatedHeap(base_address=0x1000, alignment=16)

    def test_addresses_are_aligned_and_increasing(self):
        a = self.heap.malloc(10)
        b = self.heap.malloc(1)
        c = self.heap.malloc(32)
        self.assertEqual([a, b, c], [0x1000, 0x1010, 0x1020])
        self.assertEqual(self.heap.malloc(1), 0x1040)

    def test_invalid_size(self):
        for bad in (0, -5, 3.5, "8"):
            with self.assertRaises(ValueError):
                self.heap.malloc(bad)

    def test_free_removes_block(self):
        a = self.heap.malloc(8, "x")
        b = self.heap.malloc(8, "y")
        self.heap.free(a)
        self.assertFalse(self.heap.is_live(a))
        self.assertEqual(addrs(self.heap.blocks()), [b])
        self.assertEqual(self.heap.live_bytes(), 8)

    def test_double_free(self):
        a = self.heap.malloc(8)
        self.heap.free(a)
        with self.assertRaises(DoubleFreeError):
            self.heap.free(a)

    def test_invalid_free(self):
        with self.assertRaises(InvalidFreeError):
            self.heap.free(0xDEAD)

    def test_free_null_is_noop(self):
        self.heap.free(None)
        self.assertEqual(self.heap.free_count, 0)

    def test_blocks_in_allocation_order_after_frees(self):
        a = [self.heap.malloc(8) for _ in range(5)]
        self.heap.free(a[0])
        self.heap.free(a[3])
        self.assertEqual(addrs(self.heap.blocks()), [a[1], a[2], a[4]])

    def test_n_allocated_m_freed_roots_held(self):
        random.seed(1)
        n, m = 40, 15
        a = [self.heap.malloc(random.randint(1, 100)) for _ in range(n)]
        for i, addr in enumerate(a):
            self.heap.set_root(f"v{i}", addr)
        for addr in random.sample(a, m):
            self.heap.free(addr)
        self.assertEqual(len(self.heap.blocks()), n - m)
        self.assertEqual(self.heap.detect_leaks(), [])
        self.assertEqual(len(self.heap.dangling_pointers()), m)

    def test_invalid_alignment(self):
        with self.assertRaises(ValueError):
            SimulatedHeap(alignment=12)


class TestPointers(unittest.TestCase):
    def setUp(self):
        self.heap = SimulatedHeap()

    def test_roots(self):
        a = self.heap.malloc(8)
        self.heap.set_root("p", a)
        self.assertEqual(self.heap.root("p"), a)
        self.heap.set_root("p", None)
        self.assertIsNone(self.heap.root("p"))
        self.heap.drop_root("p")
        with self.assertRaises(KeyError):
            self.heap.root("p")
        with self.assertRaises(KeyError):
            self.heap.drop_root("p")

    def test_pointer_to_dead_block_rejected(self):
        a = self.heap.malloc(8)
        self.heap.free(a)
        with self.assertRaises(InvalidPointerError):
            self.heap.set_root("p", a)
        with self.assertRaises(InvalidPointerError):
            self.heap.set_root("p", 0xBEEF)

    def test_write_through_dead_block_rejected(self):
        a = self.heap.malloc(8)
        b = self.heap.malloc(8)
        self.heap.free(a)
        with self.assertRaises(InvalidPointerError):
            self.heap.set_pointer(a, "next", b)
        with self.assertRaises(InvalidPointerError):
            self.heap.get_pointer(a, "next")

    def test_fields(self):
        a = self.heap.malloc(8)
        b = self.heap.malloc(8)
        self.heap.set_pointer(a, "next", b)
        self.assertEqual(self.heap.get_pointer(a, "next"), b)
        self.assertIsNone(self.heap.get_pointer(a, "missing"))

    def test_refcount(self):
        a = self.heap.malloc(8)
        b = self.heap.malloc(8)
        self.heap.set_root("p", b)
        self.heap.set_root("q", b)
        self.heap.set_pointer(a, "x", b)
        self.assertEqual(self.heap.refcount(b), 3)
        self.assertEqual(self.heap.refcount(a), 0)


class TestLeakDetection(unittest.TestCase):
    def setUp(self):
        self.heap = SimulatedHeap()

    def test_unrooted_block_is_leaked(self):
        a = self.heap.malloc(8)
        self.assertEqual(addrs(self.heap.detect_leaks()), [a])

    def test_rooted_chain_not_leaked_until_root_dropped(self):
        a, b, c = (self.heap.malloc(8) for _ in range(3))
        self.heap.set_pointer(a, "next", b)
        self.heap.set_pointer(b, "next", c)
        self.heap.set_root("head", a)
        self.assertEqual(self.heap.detect_leaks(), [])
        self.heap.set_root("head", None)
        self.assertEqual(addrs(self.heap.detect_leaks()), [a, b, c])

    def test_freed_block_is_not_a_leak(self):
        a = self.heap.malloc(8)
        self.heap.free(a)
        self.assertEqual(self.heap.detect_leaks(), [])

    def test_cycle_without_root_is_leaked(self):
        a, b = self.heap.malloc(8), self.heap.malloc(8)
        self.heap.set_pointer(a, "n", b)
        self.heap.set_pointer(b, "n", a)
        self.assertEqual(addrs(self.heap.detect_leaks()), [a, b])
        self.assertEqual(addrs(self.heap.refcount_misses()), [a, b])

    def test_cycle_with_root_is_fine(self):
        a, b = self.heap.malloc(8), self.heap.malloc(8)
        self.heap.set_pointer(a, "n", b)
        self.heap.set_pointer(b, "n", a)
        self.heap.set_root("r", b)
        self.assertEqual(self.heap.detect_leaks(), [])
        self.assertEqual(self.heap.refcount_misses(), [])

    def test_refcount_cascade_frees_chain(self):
        # A plain leaked chain: reference counting frees it link by link.
        a, b, c = (self.heap.malloc(8) for _ in range(3))
        self.heap.set_pointer(a, "next", b)
        self.heap.set_pointer(b, "next", c)
        self.assertEqual(len(self.heap.detect_leaks()), 3)
        self.assertEqual(self.heap.refcount_misses(), [])

    def test_block_only_held_by_cycle_is_missed(self):
        a, b, c = (self.heap.malloc(8) for _ in range(3))
        self.heap.set_pointer(a, "n", b)
        self.heap.set_pointer(b, "n", a)
        self.heap.set_pointer(a, "data", c)
        self.assertEqual(addrs(self.heap.refcount_misses()), [a, b, c])

    def test_reference_graph_shape(self):
        a, b = self.heap.malloc(8), self.heap.malloc(8)
        self.heap.set_root("head", a)
        self.heap.set_pointer(a, "next", b)
        g = self.heap.reference_graph()
        self.assertTrue(g.has_edge("root:head", a))
        self.assertTrue(g.has_edge(a, b))
        self.assertEqual(len(g), 3)

    def test_dangling_pointers(self):
        a, b = self.heap.malloc(8), self.heap.malloc(8)
        self.heap.set_root("p", a)
        self.heap.set_pointer(b, "back", a)
        self.heap.set_root("keep", b)
        self.heap.free(a)
        self.assertEqual(sorted(self.heap.dangling_pointers()),
                         sorted([("p", a), (f"{b:#x}->back", a)]))


class TestTime(unittest.TestCase):
    def test_velocity(self):
        heap = SimulatedHeap()
        self.assertEqual(heap.average_velocity(), 0.0)
        heap.malloc(64)
        heap.tick()                    # 64 leaked
        heap.tick()                    # still 64
        heap.malloc(32)
        heap.tick()                    # 96
        self.assertEqual(heap.leak_history(), [64, 64, 96])
        self.assertEqual(heap.velocity_history(), [64, 0, 32])
        self.assertEqual(heap.average_velocity(), 32.0)

    def test_allocated_at_tick(self):
        heap = SimulatedHeap()
        a = heap.malloc(8)
        heap.tick()
        heap.tick()
        b = heap.malloc(8)
        self.assertEqual((heap.block(a).allocated_at, heap.block(b).allocated_at), (0, 2))

    def test_events_logged(self):
        heap = SimulatedHeap()
        a = heap.malloc(8, "buf")
        heap.set_root("p", a)
        heap.tick()
        heap.free(a)
        self.assertEqual(heap.events, ["[t=0] malloc(8) -> 0x1000  [buf]",
                                       "[t=0] p = 0x1000",
                                       "[t=1] free(0x1000)"])


class TestScenarios(unittest.TestCase):
    def test_each_scenario_matches_expected(self):
        for s in SCENARIOS:
            with self.subTest(scenario=s.name):
                st = run_scenario(s.name).stats()
                self.assertEqual(st["leaked_blocks"], s.expected_leaked_blocks)
                self.assertEqual(st["leaked_bytes"], s.expected_leaked_bytes)

    def test_clean_program_frees_everything(self):
        st = run_scenario("clean_program").stats()
        self.assertEqual((st["live_blocks"], st["frees"], st["dangling_pointers"]), (0, 5, 0))

    def test_slow_leak_constant_velocity(self):
        heap = run_scenario("slow_leak")
        self.assertEqual(heap.velocity_history(), [64] * 50)
        self.assertEqual(heap.average_velocity(), 64.0)
        self.assertTrue(heap.is_live(heap.root("config")))
        self.assertNotIn(heap.root("config"), addrs(heap.detect_leaks()))

    def test_cycle_leak_missed_by_refcounting(self):
        heap = run_scenario("cycle_leak")
        leaks = heap.detect_leaks()
        self.assertEqual([heap.refcount(a) for a in addrs(leaks)], [1, 1])
        self.assertEqual(addrs(heap.refcount_misses()), addrs(leaks))

    def test_partial_free(self):
        heap = run_scenario("partial_free")
        self.assertEqual([b.label for b in heap.detect_leaks()], ["node 2", "node 3", "node 4"])
        self.assertEqual(heap.dangling_pointers(), [("head", 0x1000)])
        self.assertEqual(heap.refcount_misses(), [])   # a chain, not a cycle

    def test_unknown_scenario(self):
        self.assertIsNone(get_scenario("nope"))
        with self.assertRaises(ValueError):
            run_scenario("nope")


class TestReportsAndCli(unittest.TestCase):
    def test_summary_lists_every_scenario(self):
        text = format_summary()
        for s in SCENARIOS:
            self.assertIn(s.name, text)

    def test_report_cycle_note(self):
        text = format_heap_report(run_scenario("cycle_leak"))
        self.assertIn("reference counting would never free them", text)
        text = format_heap_report(run_scenario("partial_free"))
        self.assertNotIn("reference counting", text)
        self.assertIn("head -> 0x1000 (freed)", text)

    def test_report_no_leaks(self):
        self.assertIn("No leaks", format_heap_report(run_scenario("clean_program")))

    def test_report_trace_and_row_limit(self):
        text = format_heap_report(run_scenario("slow_leak"), trace=True, max_rows=3)
        self.assertIn("malloc(256) -> 0x1000  [config]", text)
        self.assertIn("... and 47 more", text)

    def _run(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_cli(self):
        code, out, _ = self._run("leaks")
        self.assertEqual(code, 0)
        self.assertIn("slow_leak", out)
        code, out, _ = self._run("leaks", "--scenario", "lost_head")
        self.assertEqual(code, 0)
        self.assertIn("Leaked: 5 (160 B)", out)
        code, _, err = self._run("leaks", "--scenario", "nope")
        self.assertEqual(code, 1)
        self.assertIn("clean_program", err)


if __name__ == "__main__":
    unittest.main()
