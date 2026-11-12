"""Memory Leak Simulator: a C-style heap with reachability-based leak detection.

Model
  * Roots are stack variables. Each holds one pointer (an address, or NULL).
  * Blocks are heap allocations from malloc. A block can hold pointers to
    other blocks in named fields (for example, node.next).
  * A block is LEAKED when it is still allocated but no chain of pointers
    from any root reaches it. The program can never free it again.

Detection is the "mark" phase of a mark-and-sweep garbage collector: build a
graph (roots and blocks as vertices, pointers as edges), run a multi-source
BFS from every root, and report every allocated block that wasn't reached.
Unlike reference counting, this also finds cycles of blocks that point at
each other but are unreachable from the program.

Data structures
  _live  : ChainedHashTable  address -> DLLNode(Block)    O(1) lookup for free()
  _order : DoublyLinkedList  of Blocks, allocation order   O(1) append and unlink
  _freed : ChainedHashTable  address -> True               tells double free from invalid free
  _roots : ChainedHashTable  name -> address or None
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..structures.graph import DirectedGraph
from ..structures.hash_table import ChainedHashTable
from ..structures.linked_list import DoublyLinkedList

ROOT_PREFIX = "root:"


class HeapError(Exception):
    """Base class for simulated memory errors."""


class InvalidFreeError(HeapError):
    """free() of an address that was never returned by malloc()."""


class DoubleFreeError(HeapError):
    """free() of an address that was already freed."""


class InvalidPointerError(HeapError):
    """A pointer operation on an address that isn't a live block."""


@dataclass
class Block:
    address: int
    size: int
    label: str
    allocated_at: int                       # tick number when malloc was called
    pointers: ChainedHashTable = field(default_factory=ChainedHashTable,
                                       repr=False, compare=False)  # field -> address


def _align_up(n: int, alignment: int) -> int:
    return (n + alignment - 1) // alignment * alignment


class SimulatedHeap:
    def __init__(self, base_address: int = 0x1000, alignment: int = 16) -> None:
        if alignment < 1 or alignment & (alignment - 1):
            raise ValueError("alignment must be a power of two")
        self._alignment = alignment
        self._next_addr = _align_up(base_address, alignment)
        self._live = ChainedHashTable()
        self._order = DoublyLinkedList()
        self._freed = ChainedHashTable()
        self._roots = ChainedHashTable()
        self.ticks = 0
        self._leak_history: List[int] = []   # leaked bytes recorded at each tick
        self.malloc_count = 0
        self.free_count = 0
        self.events: List[str] = []          # human-readable log of every operation

    # ----- C-style API -------------------------------------------------------------
    def malloc(self, size: int, label: str = "") -> int:
        """Allocate `size` bytes. O(1). Addresses are never reused."""
        if not isinstance(size, int) or size <= 0:
            raise ValueError("size must be a positive integer")
        addr = self._next_addr
        self._next_addr = _align_up(addr + size, self._alignment)
        node = self._order.append(Block(addr, size, label, self.ticks))
        self._live[addr] = node
        self.malloc_count += 1
        self._log(f"malloc({size}) -> {addr:#x}" + (f"  [{label}]" if label else ""))
        return addr

    def free(self, address: Optional[int]) -> None:
        """Release a block. O(1). free(NULL) does nothing, like in C."""
        if address is None:
            self._log("free(NULL)  (no-op)")
            return
        node = self._live.pop(address, None)
        if node is None:
            if address in self._freed:
                raise DoubleFreeError(f"double free of {address:#x}")
            raise InvalidFreeError(f"free of {address:#x}, which was never allocated")
        self._order.unlink(node)
        self._freed[address] = True
        self.free_count += 1
        self._log(f"free({address:#x})")

    # ----- pointer model --------------------------------------------------------
    def set_root(self, name: str, address: Optional[int]) -> None:
        """Point a stack variable at a live block, or at NULL (None)."""
        self._check_target(address)
        self._roots[name] = address
        self._log(f"{name} = {self._fmt(address)}")

    def drop_root(self, name: str) -> None:
        """The variable goes out of scope (for example, its function returned)."""
        if name not in self._roots:
            raise KeyError(f"no root named {name!r}")
        del self._roots[name]
        self._log(f"{name} goes out of scope")

    def root(self, name: str) -> Optional[int]:
        return self._roots[name]

    def roots(self) -> List[Tuple[str, Optional[int]]]:
        return list(self._roots.items())

    def set_pointer(self, src: int, field_name: str, dst: Optional[int]) -> None:
        """Store a pointer inside a live block: src->field = dst."""
        node = self._live.get(src)
        if node is None:
            raise InvalidPointerError(f"write through {src:#x}, which is not a live block")
        self._check_target(dst)
        node.value.pointers[field_name] = dst
        self._log(f"{src:#x}->{field_name} = {self._fmt(dst)}")

    def get_pointer(self, src: int, field_name: str) -> Optional[int]:
        node = self._live.get(src)
        if node is None:
            raise InvalidPointerError(f"read through {src:#x}, which is not a live block")
        return node.value.pointers.get(field_name)

    def _check_target(self, address: Optional[int]) -> None:
        if address is not None and address not in self._live:
            raise InvalidPointerError(f"{address:#x} is not a live block")

    # ----- queries ---------------------------------------------------------------
    def block(self, address: int) -> Block:
        node = self._live.get(address)
        if node is None:
            raise KeyError(f"{address:#x} is not a live block")
        return node.value

    def blocks(self) -> List[Block]:
        """Live blocks in allocation order."""
        return list(self._order)

    def is_live(self, address: int) -> bool:
        return address in self._live

    def live_bytes(self) -> int:
        return sum(b.size for b in self._order)

    # ----- analysis --------------------------------------------------------------
    def reference_graph(self) -> DirectedGraph:
        """Roots and live blocks as vertices; pointers to live blocks as edges."""
        g = DirectedGraph()
        for block in self._order:
            g.add_vertex(block.address)
        for name, addr in self._roots.items():
            label = ROOT_PREFIX + name
            g.add_vertex(label)
            if addr is not None and addr in self._live:
                g.add_edge(label, addr)
        for block in self._order:
            for target in block.pointers.values():
                if target is not None and target in self._live:
                    g.add_edge(block.address, target)
        return g

    def reachable_addresses(self) -> set:
        g = self.reference_graph()
        starts = [ROOT_PREFIX + name for name in self._roots.keys()]
        return {v for v in g.reachable(starts) if isinstance(v, int)}

    def detect_leaks(self) -> List[Block]:
        """Allocated blocks no root can reach, in allocation order. O(R + M + P)."""
        reachable = self.reachable_addresses()
        return [b for b in self._order if b.address not in reachable]

    def leaked_bytes(self) -> int:
        return sum(b.size for b in self.detect_leaks())

    def refcount(self, address: int) -> int:
        """How many roots and block fields point at address (what reference counting sees)."""
        count = sum(1 for _, a in self._roots.items() if a == address)
        for block in self._order:
            count += sum(1 for t in block.pointers.values() if t == address)
        return count

    def refcount_misses(self) -> List[Block]:
        """Leaked blocks that reference counting would NEVER reclaim.

        Simulates a reference-counting collector: any block whose count is 0 is
        freed, which lowers the counts of the blocks it points to, possibly to 0
        as well (a cascade). What's left over and also leaked is a cycle, or
        something only a cycle points to. Reachability (detect_leaks) finds
        these; reference counting can't.
        """
        counts = ChainedHashTable()
        for b in self._order:
            counts[b.address] = 0
        for _, addr in self._roots.items():
            if addr is not None and addr in self._live:
                counts[addr] += 1
        for b in self._order:
            for t in b.pointers.values():
                if t is not None and t in self._live:
                    counts[t] += 1
        reclaimed = ChainedHashTable()
        stack = [addr for addr, c in counts.items() if c == 0]
        while stack:
            addr = stack.pop()
            reclaimed[addr] = True
            for t in self._live[addr].value.pointers.values():
                if t is not None and t in self._live and t not in reclaimed:
                    counts[t] -= 1
                    if counts[t] == 0:
                        stack.append(t)
        return [b for b in self.detect_leaks() if b.address not in reclaimed]

    def dangling_pointers(self) -> List[Tuple[str, int]]:
        """Pointers that still hold the address of a freed block.

        Returns (holder, address) pairs. holder is "name" for a root, or
        "0x1000->next" for a field inside a live block.
        """
        found: List[Tuple[str, int]] = []
        for name, addr in self._roots.items():
            if addr is not None and addr in self._freed:
                found.append((name, addr))
        for block in self._order:
            for fname, addr in block.pointers.items():
                if addr is not None and addr in self._freed:
                    found.append((f"{block.address:#x}->{fname}", addr))
        return found

    # ----- time ------------------------------------------------------------------
    def tick(self) -> int:
        """Advance simulated time and record the current leaked bytes. Returns them."""
        self.ticks += 1
        leaked = self.leaked_bytes()
        self._leak_history.append(leaked)
        return leaked

    def leak_history(self) -> List[int]:
        """Leaked bytes measured at the end of each tick."""
        return list(self._leak_history)

    def velocity_history(self) -> List[int]:
        """Bytes newly leaked during each tick: history[i] - history[i-1]."""
        out, prev = [], 0
        for leaked in self._leak_history:
            out.append(leaked - prev)
            prev = leaked
        return out

    def average_velocity(self) -> float:
        """Leaked bytes per tick, averaged over the whole run."""
        if not self._leak_history:
            return 0.0
        return self._leak_history[-1] / self.ticks

    def stats(self) -> Dict[str, Any]:
        leaks = self.detect_leaks()
        return {
            "ticks": self.ticks,
            "mallocs": self.malloc_count,
            "frees": self.free_count,
            "live_blocks": len(self._order),
            "live_bytes": self.live_bytes(),
            "leaked_blocks": len(leaks),
            "leaked_bytes": sum(b.size for b in leaks),
            "roots": len(self._roots),
            "dangling_pointers": len(self.dangling_pointers()),
            "avg_leak_velocity": round(self.average_velocity(), 2),
        }

    # ----- helpers ---------------------------------------------------------------
    @staticmethod
    def _fmt(address: Optional[int]) -> str:
        return "NULL" if address is None else f"{address:#x}"

    def _log(self, text: str) -> None:
        self.events.append(f"[t={self.ticks}] {text}")
