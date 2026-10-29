#!/usr/bin/env python3
"""test_event_bus.py — Prove the event bus DETECTS anomalies, not just runs quietly.

Injects a synthetic scenario (repeated errors + a new dream) into a temp state,
then asserts the bus emits ANOMALY and NEW_CLUSTER events. This proves the
detection logic is real, not a silent no-op.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "/mnt/android/hermes-workspace/zoe-graphrag")

# Redirect STATE to a temp dir so we don't pollute the real store
TMP = Path(tempfile.mkdtemp(prefix="eventbus-test-"))
TMP.mkdir(parents=True, exist_ok=True)

import event_bus  # noqa: E402
event_bus.STATE = TMP
event_bus.EPISODIC = TMP / "episodic_log.jsonl"
event_bus.VECTORS = TMP / "vectors.json"
event_bus.CACHE = TMP / "cache.json"
event_bus._seen_file = TMP / ".seen_dreams.json"


def write_episodic(entries):
    with open(event_bus.EPISODIC, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def now_iso():
    import datetime
    return datetime.datetime.now().isoformat()


def main():
    # --- Scenario: 3 repeated errors (same signature), unresolved ---
    errors = []
    for i in range(3):
        errors.append({"node": "Error_qwen_wedge",
                       "type": "error",
                       "description": "qwen wedge on 8080",
                       "timestamp": now_iso(),
                       "meta": {}})
    write_episodic(errors)

    # --- Scenario: a new dream with strong spren affinity ---
    with open(event_bus.VECTORS, "w") as f:
        json.dump({"dreams": [
            {"id": "gemma2-spren-new", "zoe": 0.3, "spren": 0.62, "bond": 0.25}
        ]}, f)
    with open(event_bus.CACHE, "w") as f:
        json.dump({"entities": {"zoe": {"type": "person"}},
                   "relations": []}, f)

    events = event_bus.collect_events()
    print("=== detected events ===")
    for e in events:
        print(" ", json.dumps(e))

    anomaly = any(e["type"] == "ANOMALY" for e in events)
    cluster = any(e["type"] == "NEW_CLUSTER" for e in events)

    print(f"\n  ANOMALY detected: {'YES' if anomaly else 'NO'}")
    print(f"  NEW_CLUSTER detected: {'YES' if cluster else 'NO'}")

    # --- idempotency: second call should NOT re-emit NEW_CLUSTER (seen set) ---
    events2 = event_bus.collect_events()
    cluster2 = any(e["type"] == "NEW_CLUSTER" for e in events2)
    print(f"  NEW_CLUSTER on re-check (should be NO - idempotent): {'YES' if cluster2 else 'NO'}")

    ok = anomaly and cluster and not cluster2
    print(f"\n  RESULT: {'PASS' if ok else 'FAIL'}")

    # cleanup
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
