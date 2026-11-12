"""Text reports for the leak simulator."""
from __future__ import annotations

from typing import List, Optional

from .heap_sim import SimulatedHeap
from .scenarios import SCENARIOS, Scenario, run_scenario


def format_heap_report(heap: SimulatedHeap, scenario: Optional[Scenario] = None,
                       trace: bool = False, max_rows: int = 10) -> str:
    lines: List[str] = []
    if scenario is not None:
        lines.append(f"Scenario: {scenario.name}  ({scenario.summary})")
        lines.append("")
    if trace:
        lines.append("Trace")
        lines.extend(f"  {e}" for e in heap.events)
        lines.append("")

    st = heap.stats()
    lines.append(f"Ticks: {st['ticks']}   malloc: {st['mallocs']}   free: {st['frees']}   "
                 f"roots: {st['roots']}")
    lines.append(f"Live blocks: {st['live_blocks']} ({st['live_bytes']} B)   "
                 f"Leaked: {st['leaked_blocks']} ({st['leaked_bytes']} B)   "
                 f"Avg leak velocity: {st['avg_leak_velocity']:.1f} B/tick")

    leaks = heap.detect_leaks()
    if leaks:
        lines.append("")
        lines.append("Leaked blocks (allocated, but no root can reach them)")
        lines.append(f"  {'ADDRESS':>8}  {'SIZE':>5}  {'TICK':>4}  {'REFS':>4}  LABEL")
        for b in leaks[:max_rows]:
            lines.append(f"  {b.address:>#8x}  {b.size:>5}  {b.allocated_at:>4}  "
                         f"{heap.refcount(b.address):>4}  {b.label}")
        if len(leaks) > max_rows:
            lines.append(f"  ... and {len(leaks) - max_rows} more")
        missed = heap.refcount_misses()
        if missed:
            lines.append(f"  {len(missed)} of these are kept alive by a cycle: "
                         "reference counting would never free them.")
    else:
        lines.append("No leaks: every allocated block is reachable from a root.")

    dangling = heap.dangling_pointers()
    if dangling:
        lines.append("")
        lines.append("Dangling pointers (still holding a freed address)")
        for holder, addr in dangling:
            lines.append(f"  {holder} -> {addr:#x} (freed)")
    return "\n".join(lines)


def format_summary() -> str:
    lines = ["Leak simulator scenarios",
             f"  {'SCENARIO':<14} {'LEAKED':>6} {'BYTES':>6} {'B/TICK':>7} {'DANGLING':>8}  WHAT HAPPENS"]
    for s in SCENARIOS:
        st = run_scenario(s.name).stats()
        lines.append(f"  {s.name:<14} {st['leaked_blocks']:>6} {st['leaked_bytes']:>6} "
                     f"{st['avg_leak_velocity']:>7.1f} {st['dangling_pointers']:>8}  {s.summary}")
    lines.append("")
    lines.append("Details: python3 -m sysopt leaks --scenario NAME [--trace]")
    return "\n".join(lines)
