"""Command-line interface.

    python3 -m sysopt top       [--k 10] [--metric cpu|ram]
    python3 -m sysopt watch     [--interval 2] [--polls N] [--idle-cpu 1.0] [--idle-secs 300]
                                [--min-rss 50] [--all-users] [--record PATH]
    python3 -m sysopt tree      (--pid N | --name TEXT) [--method bfs|dfs] [--depth 3]
    python3 -m sysopt families  [--k 5] [--metric ram|cpu] [--mine]
    python3 -m sysopt leaks     [--scenario NAME] [--trace]

Every process command takes --source: "live" (default) reads this computer through
psutil; a path to a JSON fixture replays recorded data instead.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .engine.monitor import Monitor, format_poll_result
from .profiler.subtree import ProcessTree, format_families, format_totals
from .sources.base import ProcessSource
from .sources.snapshot import RecordingSource, SnapshotSource


def make_source(spec: str) -> ProcessSource:
    if spec == "live":
        from .sources.live import LiveSource   # imports psutil only when needed
        return LiveSource()
    return SnapshotSource(spec)


def first_snapshots(spec: str):
    data = make_source(spec).poll()
    if data is None:
        raise SystemExit(f"error: no data in {spec}")
    return data[1]


# ----- commands -------------------------------------------------------------------

def cmd_top(args) -> int:
    m = Monitor(make_source(args.source), k=args.k, metric=args.metric)
    res = m.poll_once()
    if res is None:
        print(f"error: no data in {args.source}", file=sys.stderr)
        return 1
    print(format_poll_result(res, show_idle=False))
    return 0


def cmd_watch(args) -> int:
    live = args.source == "live"
    source = make_source(args.source)
    recorder = RecordingSource(source) if args.record else None
    m = Monitor(recorder if recorder is not None else source, k=args.k, metric=args.metric,
                cpu_threshold=args.idle_cpu, idle_seconds=args.idle_secs,
                mine_only=not args.all_users, idle_min_rss_mb=args.min_rss)

    def show(res) -> None:
        print("=" * 72)
        print(format_poll_result(res, idle_limit=args.show_idle))

    try:
        m.run(n_polls=args.polls, interval=args.interval if live else 0, on_result=show)
    except KeyboardInterrupt:
        print("\nstopped")
    if recorder is not None:
        n = recorder.save(args.record)
        print(f"Saved {n} polls to {args.record}")
    return 0


def cmd_tree(args) -> int:
    tree = ProcessTree(first_snapshots(args.source))
    if args.pid is not None:
        if args.pid not in tree:
            print(f"error: no process with PID {args.pid}", file=sys.stderr)
            return 1
        roots = [args.pid]
    else:
        roots = tree.find_family_roots(args.name)
        if not roots:
            print(f"error: no process name contains {args.name!r}", file=sys.stderr)
            return 1
        roots = roots[:args.max_matches]
    for i, pid in enumerate(roots):
        if i:
            print()
        print(format_totals(tree.subtree_totals(pid, args.method)))
        print(tree.render(pid, max_depth=args.depth, max_children=args.max_children))
    return 0


def cmd_leaks(args) -> int:
    from .leaksim.report import format_heap_report, format_summary
    from .leaksim.scenarios import get_scenario, run_scenario

    if args.scenario is None:
        print(format_summary())
        return 0
    scenario = get_scenario(args.scenario)
    if scenario is None:
        run_scenario(args.scenario)   # raises ValueError listing valid names
    heap = run_scenario(args.scenario)
    print(format_heap_report(heap, scenario, trace=args.trace, max_rows=args.max_rows))
    return 0


def cmd_families(args) -> int:
    tree = ProcessTree(first_snapshots(args.source))
    fams = tree.top_families(k=args.k, metric=args.metric, method=args.method,
                             mine_only=args.mine)
    print(format_families(fams, args.metric))
    return 0


# ----- argument parsing -------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sysopt",
        description="System resource monitor and process family profiler.")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--source", default="live",
                        help='"live" (default) or a path to a JSON fixture')

    sp = sub.add_parser("top", help="rank processes by CPU or RAM")
    common(sp)
    sp.add_argument("--k", type=int, default=10, help="how many to show (default 10)")
    sp.add_argument("--metric", choices=("cpu", "ram"), default="cpu")
    sp.set_defaults(func=cmd_top)

    sp = sub.add_parser("watch", help="poll repeatedly; show top processes and idle candidates")
    common(sp)
    sp.add_argument("--k", type=int, default=10)
    sp.add_argument("--metric", choices=("cpu", "ram"), default="cpu")
    sp.add_argument("--interval", type=float, default=2.0, help="seconds between live polls")
    sp.add_argument("--polls", type=int, default=None, help="stop after N polls (default: Ctrl-C)")
    sp.add_argument("--idle-cpu", type=float, default=1.0,
                    help="CPU %% below which a process counts as quiet (default 1.0)")
    sp.add_argument("--idle-secs", type=float, default=300.0,
                    help="seconds a process must stay quiet to be idle (default 300)")
    sp.add_argument("--min-rss", type=float, default=0.0,
                    help="ignore idle processes smaller than this many MB")
    sp.add_argument("--all-users", action="store_true",
                    help="include other users' and system processes as idle candidates")
    sp.add_argument("--show-idle", type=int, default=5, help="idle candidates to list (default 5)")
    sp.add_argument("--record", metavar="PATH", help="also save every poll to a JSON fixture")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("tree", help="show a process family and its total CPU and RAM")
    common(sp)
    which = sp.add_mutually_exclusive_group(required=True)
    which.add_argument("--pid", type=int)
    which.add_argument("--name", help="case-insensitive part of a process name")
    sp.add_argument("--method", choices=("bfs", "dfs"), default="bfs")
    sp.add_argument("--depth", type=int, default=None, help="limit tree depth shown")
    sp.add_argument("--max-children", type=int, default=8)
    sp.add_argument("--max-matches", type=int, default=3,
                    help="with --name, how many matching families to show")
    sp.set_defaults(func=cmd_tree)

    sp = sub.add_parser("families", help="rank app families (a process plus everything it spawned)")
    common(sp)
    sp.add_argument("--k", type=int, default=10)
    sp.add_argument("--metric", choices=("cpu", "ram"), default="ram")
    sp.add_argument("--method", choices=("bfs", "dfs"), default="bfs")
    sp.add_argument("--mine", action="store_true", help="only your own apps")
    sp.set_defaults(func=cmd_families)

    sp = sub.add_parser("leaks", help="run the memory leak simulator")
    sp.add_argument("--scenario", help="scenario to run (omit for a summary of all)")
    sp.add_argument("--trace", action="store_true", help="print every malloc/free/pointer step")
    sp.add_argument("--max-rows", type=int, default=10, help="leaked blocks to list")
    sp.set_defaults(func=cmd_leaks)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "k", 1) < 1:
        print("error: --k must be at least 1", file=sys.stderr)
        return 2
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"error: file not found: {e.filename}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
