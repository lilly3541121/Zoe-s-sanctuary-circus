#!/usr/bin/env python3
"""test_tiers.py — Tests for the episodic (Tier 2) and procedural (Tier 3) tiers.

Tests are the spec. Run with GRAPH_DIR set to a temp dir to avoid touching
production data:
  GRAPH_DIR=/tmp/test-graph python3 test_tiers.py
"""
import os
import sys
import tempfile
import unittest

# Point at a temp graph dir BEFORE importing the modules
_tmp = tempfile.mkdtemp(prefix="graphrag-test-")
os.environ["GRAPH_DIR"] = _tmp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import episodic
import procedural


class TestEpisodic(unittest.TestCase):
    def setUp(self):
        # fresh state per test
        if os.path.exists(episodic.EVENT_LOG):
            os.remove(episodic.EVENT_LOG)
        if os.path.exists(episodic.CACHE):
            os.remove(episodic.CACHE)

    def test_log_run_creates_event(self):
        episodic.log_run("Run_Test_01", status="completed", task="test")
        events = episodic.load_event_log()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["node"], "Run_Test_01")
        self.assertEqual(events[0]["type"], "run")

    def test_error_fix_creates_resolved_by_edge(self):
        episodic.log_error("Error_X", description="boom", tokens=0)
        episodic.log_fix("Fix_Y", description="fixed it", resolves="Error_X")
        e, r = episodic.sync_to_graph()
        self.assertGreaterEqual(r, 1)
        cache = episodic.load_cache()
        self.assertTrue(any(
            r_["kind"] == "episodic-resolved_by"
            and r_["a"] == "error_x" and r_["b"] == "fix_y"
            for r_ in cache["relations"]
        ))

    def test_append_safe(self):
        # syncing twice must not duplicate
        episodic.log_fix("Fix_A", "desc", resolves="Err_A")
        episodic.sync_to_graph()
        episodic.sync_to_graph()
        cache = episodic.load_cache()
        n = sum(1 for r_ in cache["relations"] if r_.get("kind") == "episodic-resolved_by")
        self.assertEqual(n, 1)


class TestProcedural(unittest.TestCase):
    def setUp(self):
        if os.path.exists(procedural.CACHE):
            os.remove(procedural.CACHE)
        if os.path.exists(procedural.RECIPE_LOG):
            os.remove(procedural.RECIPE_LOG)

    def test_recipes_load(self):
        recipes = procedural.load_recipes()
        self.assertGreaterEqual(len(recipes), 4)
        self.assertTrue(all(r.get("verified") for r in recipes))

    def test_unverified_recipe_refused(self):
        with self.assertRaises(ValueError):
            procedural.register_recipe({"name": "bad", "verified": False})

    def test_query_finds_best_recipe(self):
        best = procedural.query_best_recipe("embody a character card")
        self.assertIsNotNone(best)
        if best is not None:
            self.assertEqual(best.get("name"), "recipe_embody_card_v3")

    def test_sync_creates_recipe_nodes(self):
        e, r = procedural.sync_to_graph()
        self.assertGreaterEqual(e, 4)
        cache = procedural.load_cache()
        self.assertTrue(any(
            r_["kind"] == "procedural-optimizes"
            for r_ in cache["relations"]
        ))


if __name__ == "__main__":
    unittest.main()
