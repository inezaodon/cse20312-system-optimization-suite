"""Unit tests for sysopt.structures.heap."""
from __future__ import annotations

import random
import unittest

from sysopt.structures.heap import MaxHeap, MinHeap, top_k


class TestMaxHeap(unittest.TestCase):
    def setUp(self) -> None:
        random.seed(20312)

    def test_empty_heap(self):
        h = MaxHeap()
        self.assertEqual(len(h), 0)
        self.assertTrue(h.is_empty())
        with self.assertRaises(IndexError):
            h.peek()
        with self.assertRaises(IndexError):
            h.extract_max()

    def test_single_item(self):
        h = MaxHeap()
        h.insert(7)
        self.assertEqual(h.peek(), 7)
        self.assertEqual(h.extract_max(), 7)
        self.assertTrue(h.is_empty())

    def test_index_arithmetic(self):
        self.assertEqual(MaxHeap._parent(1), 0)
        self.assertEqual(MaxHeap._parent(2), 0)
        self.assertEqual(MaxHeap._parent(5), 2)
        self.assertEqual(MaxHeap._left(0), 1)
        self.assertEqual(MaxHeap._right(0), 2)
        self.assertEqual(MaxHeap._left(3), 7)
        self.assertEqual(MaxHeap._right(3), 8)

    def test_extract_order_matches_sorted(self):
        for _ in range(20):
            data = [random.randint(-1000, 1000) for _ in range(random.randint(1, 200))]
            h = MaxHeap()
            for x in data:
                h.insert(x)
            out = [h.extract_max() for _ in range(len(data))]
            self.assertEqual(out, sorted(data, reverse=True))

    def test_heap_property_after_every_operation(self):
        h = MaxHeap()
        for _ in range(300):
            h.insert(random.random())
            self.assertTrue(h.is_valid())
        while h:
            h.extract_max()
            self.assertTrue(h.is_valid())

    def test_duplicates(self):
        h = MaxHeap()
        for x in [5, 5, 5, 1, 1, 9, 9]:
            h.insert(x)
        self.assertEqual([h.extract_max() for _ in range(7)], [9, 9, 5, 5, 5, 1, 1])

    def test_build_heap_is_valid(self):
        for n in [0, 1, 2, 3, 10, 101, 1000]:
            data = [random.randint(0, 50) for _ in range(n)]
            h = MaxHeap()
            h.build_heap(data)
            self.assertTrue(h.is_valid())
            self.assertEqual(len(h), n)
            self.assertEqual([h.extract_max() for _ in range(n)], sorted(data, reverse=True))

    def test_build_heap_does_not_alias_input(self):
        data = [3, 1, 2]
        h = MaxHeap()
        h.build_heap(data)
        h.extract_max()
        self.assertEqual(data, [3, 1, 2])

    def test_key_function(self):
        procs = [{"pid": 1, "cpu": 3.0}, {"pid": 2, "cpu": 40.0}, {"pid": 3, "cpu": 12.5}]
        h = MaxHeap(key=lambda p: p["cpu"])
        for p in procs:
            h.insert(p)
        self.assertEqual([h.extract_max()["pid"] for _ in range(3)], [2, 3, 1])

    def test_replace_root(self):
        h = MaxHeap()
        h.build_heap([10, 4, 8])
        self.assertEqual(h.replace_root(1), 10)
        self.assertTrue(h.is_valid())
        self.assertEqual(h.peek(), 8)


class TestMinHeap(unittest.TestCase):
    def test_extract_min_order(self):
        random.seed(7)
        data = [random.randint(0, 100) for _ in range(100)]
        h = MinHeap()
        for x in data:
            h.insert(x)
            self.assertTrue(h.is_valid())
        self.assertEqual([h.extract_min() for _ in range(100)], sorted(data))


class TestTopK(unittest.TestCase):
    def setUp(self) -> None:
        random.seed(99)
        self.data = [random.randint(0, 500) for _ in range(250)]

    def test_matches_sorted_slice(self):
        for k in [1, 5, 10, 249, 250]:
            self.assertEqual(top_k(self.data, k), sorted(self.data, reverse=True)[:k])

    def test_k_zero_or_negative(self):
        self.assertEqual(top_k(self.data, 0), [])
        self.assertEqual(top_k(self.data, -3), [])

    def test_k_larger_than_n(self):
        self.assertEqual(top_k([3, 1, 2], 10), [3, 2, 1])

    def test_empty_input(self):
        self.assertEqual(top_k([], 5), [])

    def test_duplicates(self):
        self.assertEqual(top_k([4, 4, 4, 2, 9], 3), [9, 4, 4])

    def test_input_not_modified(self):
        copy = list(self.data)
        top_k(self.data, 10)
        self.assertEqual(self.data, copy)

    def test_with_key(self):
        procs = [{"pid": i, "rss": r} for i, r in enumerate([100, 900, 50, 400, 900])]
        result = top_k(procs, 3, key=lambda p: p["rss"])
        self.assertEqual([p["rss"] for p in result], [900, 900, 400])

    def test_works_on_generator(self):
        self.assertEqual(top_k((x for x in range(100)), 3), [99, 98, 97])


if __name__ == "__main__":
    unittest.main()
