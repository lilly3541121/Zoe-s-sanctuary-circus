#!/usr/bin/env python3
"""episodic.py — TIER 2: Episodic Graph (What Happened).

Time-stamped event log of every run, tool outcomes, output verifications, and
bug fixes. Records operational context as Event Nodes with RESOLVED_BY edges.

Schema matches the graphrag cache format:
  entities: {name: {type, count, messages, aliases}}
  relations: [{a, b, weight, kind}]   (kind = "episodic-<pred>")

Design: append-safe (never reorders existing arrays), delta-based (only new
events are added; no rewrites of history). Every event tagged with source+ts
for targeted pruning.
"""
import json
import time
import os
from datetime import datetime

# Paths
GRAPH_DIR = os.environ.get(
    "GRAPH_DIR", "/mnt/android/hermes-workspace/state/graphrag"
)
CACHE = os.path.join(GRAPH_DIR, "cache.json")
EVENT_LOG = os.path.join(GRAPH_DIR, "episodic_log.jsonl")  # append-only log
SRC_TAG = "src-episodic"

# ---------- load / save ----------

def load_cache():
    try:
        with open(CACHE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"entities": {}, "relations": [], "messages_index": {}, "built_at": None}


def save_cache(cache):
    with open(CACHE, "w") as f:
        json.dump(cache, f, indent=2)


def load_event_log():
    """Load the append-only episodic log."""
    if not os.path.exists(EVENT_LOG):
        return []
    events = []
    with open(EVENT_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def append_event(event):
    """Append an event to the append-only log (never rewrites)."""
    with open(EVENT_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


# ---------- event logging ----------

def log_run(run_id, status="completed", **meta):
    """Log an execution run as a time-stamped Event Node."""
    event = {
        "node": run_id,
        "type": "run",
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "meta": meta,
    }
    append_event(event)
    return event


def log_error(error_id, description, run_id=None, tokens=0, **meta):
    """Log an error/failure event (e.g. 0-token output, wedge)."""
    event = {
        "node": error_id,
        "type": "error",
        "description": description,
        "run_id": run_id,
        "tokens": tokens,
        "timestamp": datetime.now().isoformat(),
        "meta": meta,
    }
    append_event(event)
    return event


def log_fix(fix_id, description, resolves=None, **meta):
    """Log a fix action, linked to the error it resolves."""
    event = {
        "node": fix_id,
        "type": "fix",
        "description": description,
        "resolves": resolves,
        "timestamp": datetime.now().isoformat(),
        "meta": meta,
    }
    append_event(event)
    return event


# ---------- sync events into graph ----------

def sync_to_graph(events=None):
    """Sync the episodic log into the graph cache as Event Nodes + edges."""
    if events is None:
        events = load_event_log()
    if not events:
        return 0, 0

    cache = load_cache()
    ents = cache.setdefault("entities", {})
    rels = cache.setdefault("relations", [])

    # dedupe existing episodic relations
    existing = set()
    for r in rels:
        if str(r.get("kind", "")).startswith("episodic-"):
            existing.add((r.get("a"), r.get("b"), r.get("kind")))

    added_e = added_r = 0
    for ev in events:
        node = ev["node"]
        key = node.lower()
        # Event node as entity
        if key not in ents:
            ents[key] = {
                "type": "event",
                "count": 1,
                "messages": [SRC_TAG],
                "aliases": [str(ev.get("type", "event"))],
            }
            added_e += 1

        # RESOLVED_BY edge: error -> fix
        if ev.get("type") == "fix" and ev.get("resolves"):
            err_key = ev["resolves"].lower()
            fix_key = key
            rel_key = (err_key, fix_key, "episodic-resolved_by")
            if rel_key not in existing:
                rels.append({
                    "a": err_key, "b": fix_key,
                    "weight": 3, "kind": "episodic-resolved_by",
                })
                existing.add(rel_key)
                added_r += 1

    save_cache(cache)
    return added_e, added_r


def prune_events(older_than_days=90):
    """Prune events older than N days (efficient maintenance)."""
    cutoff = time.time() - older_than_days * 86400
    events = load_event_log()
    keep = []
    pruned = 0
    for ev in events:
        try:
            ts = datetime.fromisoformat(ev["timestamp"]).timestamp()
            if ts < cutoff:
                pruned += 1
                continue
        except (KeyError, ValueError):
            pass
        keep.append(ev)
    # Rewrite log (only on prune — this is the explicit maintenance op)
    with open(EVENT_LOG, "w") as f:
        for ev in keep:
            f.write(json.dumps(ev) + "\n")
    return pruned


def recent_events(n=20):
    """Get the n most recent events (for querying)."""
    events = load_event_log()
    return events[-n:]


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        events = load_event_log()
        print(f"episodic events: {len(events)}")
        for ev in events[-5:]:
            print(f"  {ev.get('timestamp','?')[:19]}  {ev.get('type'):8} {ev.get('node')}")
    elif cmd == "sync":
        e, r = sync_to_graph()
        print(f"synced: +{e} event entities, +{r} resolved_by edges")
    elif cmd == "prune":
        n = prune_events(int(sys.argv[2]) if len(sys.argv) > 2 else 90)
        print(f"pruned {n} events")
