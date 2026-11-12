"""Scripted programs for the leak simulator.

Each scenario acts like a small C program: it calls malloc, sets pointers,
frees (or forgets to free), and calls tick() to mark the passage of time.
The comments show the equivalent C code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from .heap_sim import SimulatedHeap

NODE_SIZE = 32


def _build_list(heap: SimulatedHeap, n: int, root: str, label: str = "node") -> List[int]:
    """head = node1 -> node2 -> ... -> nodeN, with `root` pointing at node1."""
    addrs = [heap.malloc(NODE_SIZE, f"{label} {i + 1}") for i in range(n)]
    for a, b in zip(addrs, addrs[1:]):
        heap.set_pointer(a, "next", b)
    heap.set_root(root, addrs[0])
    return addrs


def clean_program(heap: SimulatedHeap) -> None:
    """Build a 5-node linked list, then free every node correctly."""
    _build_list(heap, 5, "head")
    heap.tick()
    # while (head) { Node *next = head->next; free(head); head = next; }
    while heap.root("head") is not None:
        cur = heap.root("head")
        nxt = heap.get_pointer(cur, "next")
        heap.set_root("head", nxt)
        heap.free(cur)
        heap.tick()


def lost_head(heap: SimulatedHeap) -> None:
    """Build a 5-node list, then set head = NULL without freeing anything."""
    _build_list(heap, 5, "head")
    heap.tick()
    heap.set_root("head", None)      # head = NULL;  every node is now unreachable
    heap.tick()


def cycle_leak(heap: SimulatedHeap) -> None:
    """Two blocks point at each other, then the only root pointing at them is dropped.

    Each block still has a reference count of 1, so reference counting would
    never free them. Reachability from the roots shows both are leaked.
    """
    a = heap.malloc(48, "A")
    b = heap.malloc(48, "B")
    heap.set_pointer(a, "next", b)   # a->next = b;
    heap.set_pointer(b, "prev", a)   # b->prev = a;
    heap.set_root("a", a)
    heap.tick()
    heap.drop_root("a")              # function returns; local `a` is gone
    heap.tick()


def slow_leak(heap: SimulatedHeap, ticks: int = 50) -> None:
    """A request loop that forgets to free a 64-byte buffer on every iteration.

    A long-lived config block stays reachable the whole time and is not a leak.
    """
    heap.set_root("config", heap.malloc(256, "config"))
    for i in range(ticks):
        # void handle_request() { char *buf = malloc(64); ...; return; }  // no free(buf)
        heap.set_root("buf", heap.malloc(64, f"request {i + 1} buffer"))
        heap.drop_root("buf")
        heap.tick()


def partial_free(heap: SimulatedHeap) -> None:
    """free(head) on a 4-node list frees only the first node.

    The other 3 nodes become unreachable (the only pointer to node 2 lived in
    the freed node), and `head` is left dangling at freed memory.
    """
    _build_list(heap, 4, "head")
    heap.tick()
    heap.free(heap.root("head"))     # free(head);  but head still holds the old address
    heap.tick()


@dataclass(frozen=True)
class Scenario:
    name: str
    run: Callable[[SimulatedHeap], None]
    summary: str
    expected_leaked_blocks: int
    expected_leaked_bytes: int


SCENARIOS = [
    Scenario("clean_program", clean_program,
             "5-node list, every node freed", 0, 0),
    Scenario("lost_head", lost_head,
             "5-node list, head set to NULL without freeing", 5, 5 * NODE_SIZE),
    Scenario("cycle_leak", cycle_leak,
             "A <-> B cycle with no root (reference counting misses this)", 2, 96),
    Scenario("slow_leak", slow_leak,
             "a 64-byte buffer leaked on every tick for 50 ticks", 50, 50 * 64),
    Scenario("partial_free", partial_free,
             "free(head) on a 4-node list: 3 nodes leak, head dangles", 3, 3 * NODE_SIZE),
]


def get_scenario(name: str) -> Optional[Scenario]:
    for s in SCENARIOS:
        if s.name == name:
            return s
    return None


def run_scenario(name: str) -> SimulatedHeap:
    scenario = get_scenario(name)
    if scenario is None:
        names = ", ".join(s.name for s in SCENARIOS)
        raise ValueError(f"unknown scenario {name!r}; choose from: {names}")
    heap = SimulatedHeap()
    scenario.run(heap)
    return heap
