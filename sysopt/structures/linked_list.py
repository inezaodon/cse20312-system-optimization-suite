"""Doubly linked list with sentinel head and tail nodes.

Sentinels mean every real node always has a prev and a next, so append and
unlink never need special cases for the first or last element. Both are O(1).
The leak simulator pairs this list with a hash table (address -> node) so it
can find and unlink any block in O(1).
"""
from __future__ import annotations

from typing import Any, Iterator, Optional


class DLLNode:
    __slots__ = ("value", "prev", "next")

    def __init__(self, value: Any = None) -> None:
        self.value = value
        self.prev: Optional[DLLNode] = None
        self.next: Optional[DLLNode] = None

    def __repr__(self) -> str:
        return f"DLLNode({self.value!r})"


class DoublyLinkedList:
    def __init__(self) -> None:
        self._head = DLLNode()          # sentinel before the first element
        self._tail = DLLNode()          # sentinel after the last element
        self._head.next = self._tail
        self._tail.prev = self._head
        self._size = 0

    def append(self, value: Any) -> DLLNode:
        """Add value at the end. O(1). Returns the new node (keep it to unlink later)."""
        node = DLLNode(value)
        last = self._tail.prev
        node.prev, node.next = last, self._tail
        last.next = node
        self._tail.prev = node
        self._size += 1
        return node

    def appendleft(self, value: Any) -> DLLNode:
        node = DLLNode(value)
        first = self._head.next
        node.prev, node.next = self._head, first
        first.prev = node
        self._head.next = node
        self._size += 1
        return node

    def unlink(self, node: DLLNode) -> Any:
        """Remove node from the list. O(1). Returns its value."""
        if node.prev is None or node.next is None or node is self._head or node is self._tail:
            raise ValueError("node is not in a list")
        node.prev.next = node.next
        node.next.prev = node.prev
        node.prev = node.next = None    # detach, so a second unlink is caught
        self._size -= 1
        return node.value

    def first(self) -> Any:
        if self._size == 0:
            raise IndexError("first from empty list")
        return self._head.next.value

    def last(self) -> Any:
        if self._size == 0:
            raise IndexError("last from empty list")
        return self._tail.prev.value

    def __iter__(self) -> Iterator[Any]:
        node = self._head.next
        while node is not self._tail:
            yield node.value
            node = node.next

    def __reversed__(self) -> Iterator[Any]:
        node = self._tail.prev
        while node is not self._head:
            yield node.value
            node = node.prev

    def __len__(self) -> int:
        return self._size

    def __repr__(self) -> str:
        return f"DoublyLinkedList({list(self)!r})"
