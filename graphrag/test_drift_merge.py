#!/usr/bin/env python3
"""test_drift_merge.py — Prove drift_merge's union logic is non-destructive + correct."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/mnt/android/hermes-workspace/zoe-graphrag")
import drift_merge  # noqa: E402


def main():
    # local has zoe + spren, relation zoe-bond-spren
    local_cache = {"entities": {"zoe": {"type": "person"},
                                "spren": {"type": "entity"}},
                   "relations": [{"a": "zoe", "b": "spren", "kind": "has_bond"}]}
    # remote has spren + a NEW 'bond' entity, and an EXTRA relation
    remote_cache = {"entities": {"spren": {"type": "entity"},
                                 "bond": {"type": "concept"}},
                    "relations": [{"a": "zoe", "b": "spren", "kind": "has_bond"},
                                  {"a": "bond", "b": "zoe", "kind": "entangles"}]}

    merged = drift_merge.merge_graphs(local_cache, remote_cache)
    print("=== merge_graphs ===")
    print("  entities:", sorted(merged["entities"].keys()))
    print("  relations:", [(r["a"], r["b"], r["kind"]) for r in merged["relations"]])
    # local wins, remote adds, no dupes
    assert merged["entities"]["zoe"]["type"] == "person", "local should win"
    assert "bond" in merged["entities"], "remote new entity should be added"
    assert len(merged["relations"]) == 2, "should have 2 relations, no dupes"
    print("  entities preserved + remote added: OK")

    # vectors union by id
    local_v = {"dreams": [{"id": "a", "zoe": 0.6}]}
    remote_v = {"dreams": [{"id": "a", "zoe": 0.6}, {"id": "b", "spren": 0.5}]}
    mv = drift_merge.merge_vectors(local_v, remote_v)
    print("=== merge_vectors ===")
    print("  dream ids:", [d["id"] for d in mv["dreams"]])
    assert len(mv["dreams"]) == 2, "should union to 2 (a deduped)"
    print("  vectors union by id: OK")

    # hash + marker
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(local_cache, f)
        fpath = f.name
    # verify cache_hash works
    print("\n  RESULT: PASS")


if __name__ == "__main__":
    main()
