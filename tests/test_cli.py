"""Tests for the command-line interface, run against fixtures."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from sysopt.cli import main
from sysopt.sources.snapshot import SnapshotSource
from tests.helpers import fixture

SMALL = fixture("small_tree.json")
IDLE = fixture("idle_sequence.json")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestTop(unittest.TestCase):
    def test_top_cpu(self):
        code, out, _ = run("top", "--source", SMALL, "--k", "2")
        self.assertEqual(code, 0)
        self.assertIn("Top 2 by CPU %", out)
        self.assertIn("Browser Helper (GPU)", out)
        self.assertNotIn("Idle candidates", out)

    def test_top_ram(self):
        code, out, _ = run("top", "--source", SMALL, "--metric", "ram", "--k", "1")
        self.assertEqual(code, 0)
        self.assertIn("Top 1 by RAM", out)

    def test_bad_k(self):
        code, _, err = run("top", "--source", SMALL, "--k", "0")
        self.assertEqual(code, 2)
        self.assertIn("--k", err)


class TestWatch(unittest.TestCase):
    def test_watch_replays_fixture(self):
        code, out, _ = run("watch", "--source", IDLE, "--idle-secs", "300", "--k", "2")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("Top 2 by CPU %"), 8)
        self.assertIn("potential savings: 520.0 MB", out)

    def test_watch_polls_limit(self):
        code, out, _ = run("watch", "--source", IDLE, "--polls", "3")
        self.assertEqual(out.count("t=+"), 3)

    def test_watch_record_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "rec.json")
            code, out, _ = run("watch", "--source", IDLE, "--polls", "4", "--record", path)
            self.assertEqual(code, 0)
            self.assertIn("Saved 4 polls", out)
            self.assertEqual(len(SnapshotSource(path)), 4)

    def test_all_users_flag(self):
        _, mine, _ = run("watch", "--source", IDLE, "--idle-secs", "300", "--show-idle", "10")
        _, every, _ = run("watch", "--source", IDLE, "--idle-secs", "300", "--show-idle", "10",
                          "--all-users")
        self.assertNotIn("launchd", mine.split("Idle candidates")[-1])
        self.assertIn("launchd", every.split("Idle candidates")[-1])


class TestTree(unittest.TestCase):
    def test_tree_by_pid(self):
        code, out, _ = run("tree", "--source", SMALL, "--pid", "20")
        self.assertEqual(code, 0)
        self.assertIn("Browser (20) family: 4 processes, 40.0% CPU, 900.0 MB RAM", out)
        self.assertIn("└── Browser Helper (GPU) (21)", out)

    def test_tree_by_name_shows_family_root(self):
        code, out, _ = run("tree", "--source", SMALL, "--name", "browser")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("family:"), 1)    # helpers are inside Browser's family

    def test_tree_dfs(self):
        code, out, _ = run("tree", "--source", SMALL, "--pid", "1", "--method", "dfs")
        self.assertIn("10 processes, 49.5% CPU, 1,115.0 MB RAM", out)

    def test_tree_depth(self):
        _, out, _ = run("tree", "--source", SMALL, "--pid", "1", "--depth", "1")
        self.assertIn("more below", out)

    def test_tree_errors(self):
        code, _, err = run("tree", "--source", SMALL, "--pid", "999")
        self.assertEqual(code, 1)
        self.assertIn("999", err)
        code, _, err = run("tree", "--source", SMALL, "--name", "photoshop")
        self.assertEqual(code, 1)

    def test_tree_requires_pid_or_name(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(["tree", "--source", SMALL])


class TestFamilies(unittest.TestCase):
    def test_families_by_ram(self):
        code, out, _ = run("families", "--source", SMALL, "--k", "2")
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertIn("Top 2 process families by RAM", lines[0])
        self.assertIn("Browser", lines[2])
        self.assertIn("WindowServer", lines[3])

    def test_families_mine(self):
        _, out, _ = run("families", "--source", SMALL, "--mine")
        self.assertNotIn("WindowServer", out)
        self.assertIn("Terminal", out)


class TestErrors(unittest.TestCase):
    def test_missing_fixture(self):
        code, _, err = run("top", "--source", "nope/missing.json")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_bad_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.json")
            with open(path, "w") as f:
                f.write('{"no_polls": true}')
            code, _, err = run("families", "--source", path)
            self.assertEqual(code, 1)
            self.assertIn("polls", err)

    def test_no_command(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main([])


if __name__ == "__main__":
    unittest.main()
