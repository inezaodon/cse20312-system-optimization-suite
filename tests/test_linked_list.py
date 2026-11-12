"""Unit tests for sysopt.structures.linked_list."""
from __future__ import annotations

import random
import unittest

from sysopt.structures.linked_list import DoublyLinkedList


class TestDoublyLinkedList(unittest.TestCase):
    def test_empty(self):
        dll = DoublyLinkedList()
        self.assertEqual(len(dll), 0)
        self.assertEqual(list(dll), [])
        with self.assertRaises(IndexError):
            dll.first()
        with self.assertRaises(IndexError):
            dll.last()

    def test_append_order(self):
        dll = DoublyLinkedList()
        for x in "abc":
            dll.append(x)
        self.assertEqual(list(dll), ["a", "b", "c"])
        self.assertEqual(list(reversed(dll)), ["c", "b", "a"])
        self.assertEqual((dll.first(), dll.last()), ("a", "c"))

    def test_appendleft(self):
        dll = DoublyLinkedList()
        dll.append(2)
        dll.appendleft(1)
        self.assertEqual(list(dll), [1, 2])

    def test_unlink_head_middle_tail(self):
        for target in range(3):
            dll = DoublyLinkedList()
            nodes = [dll.append(i) for i in range(3)]
            self.assertEqual(dll.unlink(nodes[target]), target)
            expected = [i for i in range(3) if i != target]
            self.assertEqual(list(dll), expected)
            self.assertEqual(list(reversed(dll)), expected[::-1])
            self.assertEqual(len(dll), 2)

    def test_unlink_only_node(self):
        dll = DoublyLinkedList()
        n = dll.append("x")
        dll.unlink(n)
        self.assertEqual(list(dll), [])
        self.assertEqual(len(dll), 0)
        dll.append("y")                 # still usable afterwards
        self.assertEqual(list(dll), ["y"])

    def test_double_unlink_rejected(self):
        dll = DoublyLinkedList()
        n = dll.append(1)
        dll.unlink(n)
        with self.assertRaises(ValueError):
            dll.unlink(n)

    def test_sentinels_cannot_be_unlinked(self):
        dll = DoublyLinkedList()
        dll.append(1)
        with self.assertRaises(ValueError):
            dll.unlink(dll._head)
        with self.assertRaises(ValueError):
            dll.unlink(dll._tail)

    def test_random_unlinks_match_list(self):
        random.seed(3)
        dll = DoublyLinkedList()
        nodes = {i: dll.append(i) for i in range(200)}
        ref = list(range(200))
        for i in random.sample(range(200), 120):
            dll.unlink(nodes[i])
            ref.remove(i)
        self.assertEqual(list(dll), ref)
        self.assertEqual(len(dll), 80)


if __name__ == "__main__":
    unittest.main()
