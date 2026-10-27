#!/usr/bin/env python3
"""Smoke tests for graphrag.py. Stdlib unittest, no deps.

Runs against a throwaway HERMES_HOME built in a temp dir, so it never touches
a real install.

    python3 -m unittest test_graphrag -v
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class GraphRagTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "hermes"
        (self.home / "memories").mkdir(parents=True)
        (self.home / "graphrag" / "sources").mkdir(parents=True)
        self.db = self.home / "state.db"
        self._make_db()

    def tearDown(self):
        self.tmp.cleanup()

    def _make_db(self):
        """Mirror the real schema: a REAL timestamp, and no `active` column."""
        con = sqlite3.connect(self.db)
        con.execute("""CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_call_id TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            timestamp REAL NOT NULL,
            token_count INTEGER,
            finish_reason TEXT
        )""")
        rows = [
            ("s1", "user", "hello there, how are you today"),
            ("s1", "assistant", "I am fine. the github token works now"),
            ("s1", "assistant", "let us build the knowledge graph tonight"),
            ("s2", "user", "no"),                      # whole-word "no"
            ("s2", "user", "I know nothing about xylophones"),
            ("s2", "tool", "SHOULD BE IGNORED - tool rows are not messages"),
        ]
        con.executemany(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)",
            [(s, r, c, 1000 + i) for i, (s, r, c) in enumerate(rows)],
        )
        con.commit()
        con.close()

    def run_cli(self, *args):
        env = dict(os.environ, HERMES_HOME=str(self.home))
        return subprocess.run(
            [sys.executable, str(HERE / "graphrag.py"), *args],
            capture_output=True, text=True, env=env, timeout=120,
        )

    # -- tests ---------------------------------------------------------
    def test_reads_messages_and_skips_tool_rows(self):
        r = self.run_cli("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        cache = json.loads((self.home / "graphrag" / "cache.json").read_text())
        self.assertEqual(len(cache["messages_index"]), 5)  # 6 rows - 1 tool row

    def test_schema_without_active_column(self):
        """The old query used WHERE active=1, which never existed."""
        r = self.run_cli("build")
        self.assertNotIn("no such column", r.stderr.lower())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_build_is_idempotent(self):
        a = self.run_cli("build")
        first = json.loads((self.home / "graphrag" / "cache.json").read_text())
        b = self.run_cli("build")
        second = json.loads((self.home / "graphrag" / "cache.json").read_text())
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(b.returncode, 0, b.stderr)
        self.assertEqual(
            {k: v["count"] for k, v in first["entities"].items()},
            {k: v["count"] for k, v in second["entities"].items()},
        )

    def test_short_keyword_does_not_match_substring(self):
        """'no' must not fire on 'know' or 'nothing'."""
        self.run_cli("build")
        cache = json.loads((self.home / "graphrag" / "cache.json").read_text())
        consent = cache["entities"].get("topic:consent")
        self.assertIsNotNone(consent)
        self.assertEqual(consent["count"], 1)  # only the bare "no" message

    def test_relations_are_normalised(self):
        self.run_cli("build")
        cache = json.loads((self.home / "graphrag" / "cache.json").read_text())
        keys = [(r["a"], r["b"]) for r in cache["relations"]]
        for a, b in keys:
            self.assertLessEqual(a, b, f"edge not normalised: {a} <-> {b}")

    def test_query_finds_deep_text(self):
        """Body past the old 1200-char preview window must be searchable."""
        big = "intro. " + ("filler words here. " * 200) + " deepwater marker phrase"
        (self.home / "graphrag" / "sources" / "big.txt").write_text(big)
        self.run_cli("build")
        r = self.run_cli("query", "deepwater marker")
        self.assertIn("src-big", r.stdout)

    def test_empty_source_refuses_to_wipe(self):
        self.run_cli("build")
        before = (self.home / "graphrag" / "cache.json").read_text()
        r = self.run_cli("build", "--source", "vault")  # vault dir doesn't exist
        self.assertEqual(r.returncode, 1)
        self.assertIn("refusing", r.stderr.lower())
        after = (self.home / "graphrag" / "cache.json").read_text()
        self.assertEqual(json.loads(before)["built_at"],
                         json.loads(after)["built_at"])

    def test_corrupt_cache_recovers(self):
        self.run_cli("build")
        (self.home / "graphrag" / "cache.json").write_text("{{{ not json")
        r = self.run_cli("stats")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("corrupt", r.stderr.lower())

    def test_message_ids_stable_by_row_id(self):
        self.run_cli("build")
        cache = json.loads((self.home / "graphrag" / "cache.json").read_text())
        ids = sorted(cache["messages_index"])
        self.assertEqual(ids, [f"msg-{i}" for i in range(1, 6)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
