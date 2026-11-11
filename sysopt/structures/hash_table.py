"""Hash table with separate chaining, built from scratch (no dict storage).

Chaining was chosen over linear probing because processes exit constantly,
and deleting from a linear-probing table needs tombstones. With chaining,
delete just removes the pair from its bucket's list.
"""
from __future__ import annotations

from typing import Any, Iterator, List, Optional, Tuple

_MASK32 = 0xFFFFFFFF
_KNUTH = 2654435761  # multiplicative hashing constant (close to 2^32 / golden ratio)

_MISSING = object()


def hash_key(key: Any) -> int:
    """Custom 32-bit hash for the key types this project uses."""
    # bool is a subclass of int; treat it like an int.
    if isinstance(key, int):
        return (key * _KNUTH) & _MASK32
    if isinstance(key, float):
        # Process create_time is a float; millisecond precision is plenty.
        return hash_key(int(round(key * 1000)))
    if isinstance(key, str):
        h = 0
        for ch in key:
            h = (h * 31 + ord(ch)) & _MASK32
        return h
    if isinstance(key, tuple):
        h = 17
        for elem in key:
            h = (h * 31 + hash_key(elem)) & _MASK32
        return h
    raise TypeError(f"unsupported key type: {type(key).__name__}")


class ChainedHashTable:
    """Map keys to values. Average O(1) insert, lookup, and delete."""

    def __init__(self, capacity: int = 8, max_load: float = 0.75) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if max_load <= 0:
            raise ValueError("max_load must be positive")
        self._capacity = capacity
        self._max_load = max_load
        self._size = 0
        self._buckets: List[List[List[Any]]] = [[] for _ in range(capacity)]

    # ----- hashing ----------------------------------------------------------
    def _hash(self, key: Any) -> int:
        return hash_key(key)

    def _index(self, key: Any) -> int:
        return self._hash(key) % self._capacity

    def _find(self, bucket: List[List[Any]], key: Any) -> int:
        for i, pair in enumerate(bucket):
            if pair[0] == key:
                return i
        return -1

    # ----- core operations --------------------------------------------------
    def __setitem__(self, key: Any, value: Any) -> None:
        bucket = self._buckets[self._index(key)]
        i = self._find(bucket, key)
        if i >= 0:
            bucket[i][1] = value
            return
        bucket.append([key, value])
        self._size += 1
        if self.load_factor() > self._max_load:
            self._resize(self._capacity * 2)

    def __getitem__(self, key: Any) -> Any:
        bucket = self._buckets[self._index(key)]
        i = self._find(bucket, key)
        if i < 0:
            raise KeyError(key)
        return bucket[i][1]

    def __delitem__(self, key: Any) -> None:
        bucket = self._buckets[self._index(key)]
        i = self._find(bucket, key)
        if i < 0:
            raise KeyError(key)
        # Order inside a bucket doesn't matter: swap with last, then pop (O(1)).
        bucket[i] = bucket[-1]
        bucket.pop()
        self._size -= 1

    def __contains__(self, key: Any) -> bool:
        return self._find(self._buckets[self._index(key)], key) >= 0

    def __len__(self) -> int:
        return self._size

    def get(self, key: Any, default: Any = None) -> Any:
        bucket = self._buckets[self._index(key)]
        i = self._find(bucket, key)
        return bucket[i][1] if i >= 0 else default

    def pop(self, key: Any, default: Any = _MISSING) -> Any:
        bucket = self._buckets[self._index(key)]
        i = self._find(bucket, key)
        if i < 0:
            if default is _MISSING:
                raise KeyError(key)
            return default
        value = bucket[i][1]
        bucket[i] = bucket[-1]
        bucket.pop()
        self._size -= 1
        return value

    # ----- iteration --------------------------------------------------------
    def items(self) -> Iterator[Tuple[Any, Any]]:
        for bucket in self._buckets:
            for key, value in bucket:
                yield key, value

    def keys(self) -> Iterator[Any]:
        for key, _ in self.items():
            yield key

    def values(self) -> Iterator[Any]:
        for _, value in self.items():
            yield value

    def __iter__(self) -> Iterator[Any]:
        return self.keys()

    # ----- sizing -----------------------------------------------------------
    @property
    def capacity(self) -> int:
        return self._capacity

    def load_factor(self) -> float:
        return self._size / self._capacity

    def _resize(self, new_capacity: int) -> None:
        """Rehash every entry into a new bucket array. O(N), amortized O(1) per insert."""
        old = self._buckets
        self._capacity = new_capacity
        self._buckets = [[] for _ in range(new_capacity)]
        for bucket in old:
            for pair in bucket:
                self._buckets[self._index(pair[0])].append(pair)

    def longest_chain(self) -> int:
        """Length of the longest bucket (useful for analyzing collisions)."""
        return max((len(b) for b in self._buckets), default=0)

    def __repr__(self) -> str:
        inner = ", ".join(f"{k!r}: {v!r}" for k, v in self.items())
        return f"ChainedHashTable({{{inner}}})"
