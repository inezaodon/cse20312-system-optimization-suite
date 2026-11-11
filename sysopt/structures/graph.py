"""Directed graph stored as adjacency lists, built on ChainedHashTable.

    _out : vertex -> list of out-neighbors (children)
    _in  : vertex -> list of in-neighbors  (parents)

Keeping both directions makes remove_vertex and roots() cheap. Traversals keep
a visited table, so they terminate even when the graph has cycles (the leak
simulator's pointer graph can; process trees can't).
"""
from __future__ import annotations

from collections import deque
from typing import Any, Hashable, Iterable, List, Set

from .hash_table import ChainedHashTable


class DirectedGraph:
    def __init__(self) -> None:
        self._out = ChainedHashTable()
        self._in = ChainedHashTable()
        self._edges = 0

    # ----- vertices ---------------------------------------------------------
    def add_vertex(self, v: Hashable) -> None:
        if v not in self._out:
            self._out[v] = []
            self._in[v] = []

    def has_vertex(self, v: Hashable) -> bool:
        return v in self._out

    def remove_vertex(self, v: Hashable) -> None:
        """Remove v and every edge touching it. O(deg(v) * avg degree)."""
        if v not in self._out:
            raise KeyError(v)
        out_list, in_list = self._out[v], self._in[v]
        self_loop = v in out_list
        # Count before mutating; a self-loop appears in both lists but is one edge.
        self._edges -= len(out_list) + len(in_list) - (1 if self_loop else 0)
        for child in out_list:
            if child != v:
                self._in[child].remove(v)
        for parent in in_list:
            if parent != v:
                self._out[parent].remove(v)
        del self._out[v]
        del self._in[v]

    def vertices(self) -> List[Any]:
        return list(self._out.keys())

    def __len__(self) -> int:
        return len(self._out)

    def __contains__(self, v: Hashable) -> bool:
        return self.has_vertex(v)

    # ----- edges ------------------------------------------------------------
    def add_edge(self, u: Hashable, v: Hashable) -> None:
        """Add u -> v, creating either vertex if needed. Duplicate edges are ignored."""
        self.add_vertex(u)
        self.add_vertex(v)
        if v not in self._out[u]:
            self._out[u].append(v)
            self._in[v].append(u)
            self._edges += 1

    def has_edge(self, u: Hashable, v: Hashable) -> bool:
        return u in self._out and v in self._out[u]

    def remove_edge(self, u: Hashable, v: Hashable) -> None:
        if not self.has_edge(u, v):
            raise KeyError((u, v))
        self._out[u].remove(v)
        self._in[v].remove(u)
        self._edges -= 1

    def neighbors(self, v: Hashable) -> List[Any]:
        """Out-neighbors (children) of v. Raises KeyError if v is missing."""
        return list(self._out[v])

    def predecessors(self, v: Hashable) -> List[Any]:
        return list(self._in[v])

    def edge_count(self) -> int:
        return self._edges

    def roots(self) -> List[Any]:
        """Vertices with no incoming edges."""
        return [v for v, parents in self._in.items() if not parents]

    # ----- traversal --------------------------------------------------------
    def bfs(self, start: Hashable) -> List[Any]:
        """Breadth-first visit order from start. O(V + E)."""
        if start not in self._out:
            raise KeyError(start)
        visited = ChainedHashTable()
        visited[start] = True
        order = []
        queue = deque([start])
        while queue:
            v = queue.popleft()
            order.append(v)
            for w in self._out[v]:
                if w not in visited:
                    visited[w] = True
                    queue.append(w)
        return order

    def dfs(self, start: Hashable) -> List[Any]:
        """Depth-first (preorder) visit order from start. O(V + E).

        Iterative with an explicit stack, so deep graphs can't hit Python's
        recursion limit. Children are pushed in reverse so they are visited
        in insertion order, like the recursive version would.
        """
        if start not in self._out:
            raise KeyError(start)
        visited = ChainedHashTable()
        order = []
        stack = [start]
        while stack:
            v = stack.pop()
            if v in visited:
                continue
            visited[v] = True
            order.append(v)
            for w in reversed(self._out[v]):
                if w not in visited:
                    stack.append(w)
        return order

    def reachable(self, starts: Iterable[Hashable]) -> Set[Any]:
        """Every vertex reachable from any start vertex (multi-source BFS).

        Start vertices that aren't in the graph are ignored.
        """
        visited = ChainedHashTable()
        queue = deque()
        for s in starts:
            if s in self._out and s not in visited:
                visited[s] = True
                queue.append(s)
        while queue:
            v = queue.popleft()
            for w in self._out[v]:
                if w not in visited:
                    visited[w] = True
                    queue.append(w)
        return set(visited.keys())
