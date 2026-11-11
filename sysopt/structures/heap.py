"""Array-backed binary heaps built from scratch (no heapq).

Index arithmetic for a node at index i:
    parent = (i - 1) // 2
    left   = 2 * i + 1
    right  = 2 * i + 2
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, List, Optional


def _identity(x: Any) -> Any:
    return x


class MaxHeap:
    """Binary max-heap. The item with the largest key(item) sits at the root."""

    def __init__(self, key: Optional[Callable[[Any], Any]] = None) -> None:
        self._key = key if key is not None else _identity
        self._data: List[Any] = []

    # ----- index arithmetic -------------------------------------------------
    @staticmethod
    def _parent(i: int) -> int:
        return (i - 1) // 2

    @staticmethod
    def _left(i: int) -> int:
        return 2 * i + 1

    @staticmethod
    def _right(i: int) -> int:
        return 2 * i + 2

    # ----- ordering ---------------------------------------------------------
    def _higher(self, a: Any, b: Any) -> bool:
        """True if item a belongs above item b in the heap."""
        return self._key(a) > self._key(b)

    # ----- basic queries ----------------------------------------------------
    def __len__(self) -> int:
        return len(self._data)

    def is_empty(self) -> bool:
        return len(self._data) == 0

    def peek(self) -> Any:
        if not self._data:
            raise IndexError("peek from empty heap")
        return self._data[0]

    # ----- mutation ---------------------------------------------------------
    def insert(self, item: Any) -> None:
        """O(log N): append at the end, then bubble up."""
        self._data.append(item)
        self._heapify_up(len(self._data) - 1)

    def extract_max(self) -> Any:
        """O(log N): remove and return the root item."""
        if not self._data:
            raise IndexError("extract from empty heap")
        root = self._data[0]
        last = self._data.pop()
        if self._data:
            self._data[0] = last
            self._heapify_down(0)
        return root

    def replace_root(self, item: Any) -> Any:
        """Pop the root and push item in one O(log N) step. Returns the old root."""
        if not self._data:
            raise IndexError("replace_root on empty heap")
        root = self._data[0]
        self._data[0] = item
        self._heapify_down(0)
        return root

    def build_heap(self, items: Iterable[Any]) -> None:
        """O(N) bottom-up construction. Replaces current contents."""
        self._data = list(items)
        for i in range(len(self._data) // 2 - 1, -1, -1):
            self._heapify_down(i)

    # ----- internal sifting -------------------------------------------------
    def _heapify_up(self, i: int) -> None:
        data = self._data
        while i > 0:
            p = self._parent(i)
            if self._higher(data[i], data[p]):
                data[i], data[p] = data[p], data[i]
                i = p
            else:
                break

    def _heapify_down(self, i: int) -> None:
        data = self._data
        n = len(data)
        while True:
            best = i
            left, right = self._left(i), self._right(i)
            if left < n and self._higher(data[left], data[best]):
                best = left
            if right < n and self._higher(data[right], data[best]):
                best = right
            if best == i:
                return
            data[i], data[best] = data[best], data[i]
            i = best

    # ----- testing helper ---------------------------------------------------
    def is_valid(self) -> bool:
        """Check that no child is higher than its parent, at every index."""
        data = self._data
        for i in range(1, len(data)):
            if self._higher(data[i], data[self._parent(i)]):
                return False
        return True


class MinHeap(MaxHeap):
    """Binary min-heap: same code as MaxHeap with the comparison reversed."""

    def _higher(self, a: Any, b: Any) -> bool:
        return self._key(a) < self._key(b)

    def extract_min(self) -> Any:
        return self.extract_max()


def top_k(items: Iterable[Any], k: int,
          key: Optional[Callable[[Any], Any]] = None) -> List[Any]:
    """Return the k largest items, largest first.

    Uses a size-k MinHeap whose root is the smallest of the current top k.
    Each new item either gets ignored (not bigger than the root) or replaces
    the root. Time O(N log k), extra space O(k). Does not modify `items`.
    """
    if k <= 0:
        return []
    keyf = key if key is not None else _identity
    heap = MinHeap(key=keyf)
    for item in items:
        if len(heap) < k:
            heap.insert(item)
        elif keyf(item) > keyf(heap.peek()):
            heap.replace_root(item)
    result = []
    while heap:
        result.append(heap.extract_min())
    result.reverse()
    return result
