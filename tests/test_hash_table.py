"""Unit tests for sysopt.structures.hash_table."""
from __future__ import annotations

import random
import unittest

from sysopt.structures.hash_table import ChainedHashTable, hash_key


class TestHashFunction(unittest.TestCase):
    def test_deterministic(self):
        for key in [0, 42, -7, "chrome", (501, 1731300000.123), 3.5]:
            self.assertEqual(hash_key(key), hash_key(key))

    def test_32_bit_range(self):
        for key in [0, 10**12, -1, "a" * 500, (1, 2, 3)]:
            h = hash_key(key)
            self.assertGreaterEqual(h, 0)
            self.assertLessEqual(h, 0xFFFFFFFF)

    def test_tuple_order_matters(self):
        self.assertNotEqual(hash_key((1, 2)), hash_key((2, 1)))

    def test_unsupported_type(self):
        with self.assertRaises(TypeError):
            hash_key([1, 2])
        with self.assertRaises(TypeError):
            hash_key(None)


class TestChainedHashTable(unittest.TestCase):
    def test_basic_set_get(self):
        t = ChainedHashTable()
        t[1] = "launchd"
        t[501] = "Finder"
        self.assertEqual(t[1], "launchd")
        self.assertEqual(t[501], "Finder")
        self.assertEqual(len(t), 2)

    def test_update_does_not_grow(self):
        t = ChainedHashTable()
        t["a"] = 1
        t["a"] = 2
        self.assertEqual(t["a"], 2)
        self.assertEqual(len(t), 1)

    def test_missing_key(self):
        t = ChainedHashTable()
        with self.assertRaises(KeyError):
            t["nope"]
        with self.assertRaises(KeyError):
            del t["nope"]
        self.assertIsNone(t.get("nope"))
        self.assertEqual(t.get("nope", 5), 5)
        self.assertNotIn("nope", t)

    def test_delete(self):
        t = ChainedHashTable()
        for i in range(10):
            t[i] = i * i
        del t[3]
        self.assertNotIn(3, t)
        self.assertEqual(len(t), 9)
        for i in range(10):
            if i != 3:
                self.assertEqual(t[i], i * i)

    def test_pop(self):
        t = ChainedHashTable()
        t["x"] = 10
        self.assertEqual(t.pop("x"), 10)
        self.assertEqual(len(t), 0)
        self.assertEqual(t.pop("x", None), None)
        with self.assertRaises(KeyError):
            t.pop("x")

    def test_forced_collisions(self):
        # Capacity 1 with a huge max_load: every key lands in the same bucket.
        t = ChainedHashTable(capacity=1, max_load=1000)
        for i in range(50):
            t[i] = str(i)
        self.assertEqual(t.capacity, 1)
        self.assertEqual(t.longest_chain(), 50)
        for i in range(50):
            self.assertEqual(t[i], str(i))
        for i in range(0, 50, 2):
            del t[i]
        self.assertEqual(len(t), 25)
        for i in range(50):
            self.assertEqual(i in t, i % 2 == 1)

    def test_resize_triggers_after_load_factor(self):
        t = ChainedHashTable(capacity=8, max_load=0.75)
        for i in range(6):          # 6 / 8 = 0.75, not over the limit yet
            t[i] = i
        self.assertEqual(t.capacity, 8)
        t[6] = 6                    # 7 / 8 = 0.875 > 0.75, so it doubles
        self.assertEqual(t.capacity, 16)
        self.assertLessEqual(t.load_factor(), 0.75)
        for i in range(7):
            self.assertEqual(t[i], i)

    def test_tuple_keys_for_processes(self):
        t = ChainedHashTable()
        t[(501, 1731300000.25)] = "old process"
        t[(501, 1731309999.75)] = "new process, reused PID"
        self.assertEqual(len(t), 2)
        self.assertEqual(t[(501, 1731300000.25)], "old process")
        self.assertEqual(t[(501, 1731309999.75)], "new process, reused PID")

    def test_iteration(self):
        t = ChainedHashTable()
        expected = {f"k{i}": i for i in range(30)}
        for k, v in expected.items():
            t[k] = v
        self.assertEqual(dict(t.items()), expected)
        self.assertEqual(sorted(t.keys()), sorted(expected))
        self.assertEqual(sorted(t.values()), sorted(expected.values()))
        self.assertEqual(sorted(t), sorted(expected))

    def test_random_operations_match_dict(self):
        """1,000 random operations, checked against Python's dict as a reference."""
        random.seed(20312)
        t = ChainedHashTable()
        ref = {}
        for _ in range(1000):
            key = random.randint(0, 300)
            op = random.random()
            if op < 0.6:
                val = random.random()
                t[key] = val
                ref[key] = val
            elif op < 0.9:
                if key in ref:
                    del t[key]
                    del ref[key]
                else:
                    with self.assertRaises(KeyError):
                        del t[key]
            else:
                self.assertEqual(t.get(key), ref.get(key))
            self.assertEqual(len(t), len(ref))
        self.assertEqual(dict(t.items()), ref)

    def test_invalid_construction(self):
        with self.assertRaises(ValueError):
            ChainedHashTable(capacity=0)
        with self.assertRaises(ValueError):
            ChainedHashTable(max_load=0)


if __name__ == "__main__":
    unittest.main()
