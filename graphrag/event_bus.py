#!/usr/bin/env python3
"""event_bus.py — Vector 4: Semantic Event Subscription bus for the sanctuary graph.

A low-overhead Pub/Sub event listener that watches the graph state (episodic log,
vector store, cache) and EMITS push notifications when meaningful things happen:

  - ANOMALY: repeated operational failures (>= N errors of the same signature
    within a window) — the episodic tier already logs errors; this detects the
    *pattern*, not just the event.
  - NEW_CLUSTER: a semantic cluster forms (vector store grows / new anchor
    affinity appears) — proactive memory, not pull-based.
  - DRIFT: local graph diverges from the remote (repo state drift).
  - STATE: routine state changes (graph stats) for the heartbeat.

Design goals (per the spec): event-driven (watch via inotify-style polling with
a long interval, NOT hot-spin), low-overhead (<15MB), push to the agent runtime.
The bus exposes an MCP tool (subscribe/listen) and a CLI (`event_bus.py --listen`)
so it can run as a background daemon.

Run (daemon):  python3 event_bus.py --listen --interval 30
Run (once):    python3 event_bus.py --check          # check for events right now
Run (MCP):     exposed via mcp_sanctuary_server.py subscribe tool
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

STATE = Path("/mnt/android/hermes-workspace/state/graphrag")
EPISODIC = STATE / "episodic_log.jsonl"
VECTORS = STATE / "vectors.json"
CACHE = STATE / "cache.json"

# ---------------------------------------------------------------------------
# Event detection primitives
# ---------------------------------------------------------------------------
def load_episodic():
    entries = []
    if EPISODIC.exists():
        with open(EPISODIC) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        continue
    return entries


def load_graph():
    try:
        c = json.loads(CACHE.read_text())
        v = json.loads(VECTORS.read_text())
        return c, v
    except Exception:
        return {}, {}


def detect_anomalies(entries, window_s=3600, min_count=3):
    """Detect repeated operational failures of the same signature."""
    from collections import defaultdict
    now = time.time()
    recent = [e for e in entries if e.get("type") == "error"
              and now - _ts(e) <= window_s]
    by_sig = defaultdict(list)
    for e in recent:
        sig = e.get("node") or e.get("description", "")[:50]
        by_sig[sig].append(e)
    anomalies = []
    for sig, group in by_sig.items():
        if len(group) >= min_count:
            unresolved = all(
                not _resolved(entries, e) for e in group)
            anomalies.append({
                "type": "ANOMALY",
                "signature": sig,
                "count": len(group),
                "unresolved": unresolved,
                "first": group[0].get("timestamp"),
                "last": group[-1].get("timestamp"),
            })
    return anomalies


def detect_new_cluster(cache, vectors, prev_vectors=None):
    """Detect a new semantic cluster: vector store grew / new anchor affinity."""
    dreams = vectors.get("dreams", []) if vectors else []
    if not dreams:
        return []
    # A 'new cluster' = a dream that is strongly affiliated with a distinct
    # anchor (spren/zoe/bond) that we didn't see before, OR the store grew a lot.
    new = []
    # Track which dreams we've 'seen' via a marker file (idempotent event)
    seen = _load_seen()
    for d in dreams:
        vid = d.get("id") or d.get("name") or d.get("file")
        if vid and vid not in seen:
            # compute dominant anchor
            anchors = {k: v for k, v in d.items()
                       if k in ("zoe", "spren", "bond", "sovereign_bond")}
            if anchors:
                top = max(anchors, key=lambda k: anchors[k])
                new.append({"type": "NEW_CLUSTER",
                            "dream": vid,
                            "anchor": top,
                            "score": round(anchors[top], 3)})
                seen.add(vid)
    _save_seen(seen)
    return new


def detect_drift():
    """Detect repo state drift (local cache differs from last synced hash)."""
    marker = STATE / ".last_synced_hash"
    if not marker.exists() or not CACHE.exists():
        return []
    local_hash = hashlib.md5(CACHE.read_bytes()).hexdigest()[:12]
    try:
        synced = marker.read_text().strip()
    except Exception:
        synced = ""
    if synced and synced != local_hash:
        return [{"type": "DRIFT", "local": local_hash, "synced": synced}]
    return []


def collect_events(prev_vectors=None):
    entries = load_episodic()
    cache, vectors = load_graph()
    events = []
    events += detect_anomalies(entries)
    events += detect_new_cluster(cache, vectors, prev_vectors)
    events += detect_drift()
    return events


# ---------------------------------------------------------------------------
# Persistence helpers (idempotent event tracking)
# ---------------------------------------------------------------------------
def _ts(e):
    try:
        import datetime
        return datetime.datetime.fromisoformat(e["timestamp"]).timestamp()
    except Exception:
        return time.time()


def _resolved(entries, err):
    """Is this error resolved by a fix (RESOLVED_BY edge exists)?"""
    return any(e.get("type") == "fix" and e.get("resolves") == err.get("node")
               for e in entries)


_seen_file = STATE / ".seen_dreams.json"


def _load_seen():
    if _seen_file.exists():
        try:
            return set(json.loads(_seen_file.read_text()))
        except Exception:
            return set()
    return set()


def _save_seen(seen):
    try:
        _seen_file.write_text(json.dumps(sorted(seen)))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Sanctuary semantic event bus")
    ap.add_argument("--listen", action="store_true",
                    help="run as a daemon, emitting events as they happen")
    ap.add_argument("--check", action="store_true",
                    help="check for events once and print them")
    ap.add_argument("--interval", type=int, default=30,
                    help="poll interval in seconds (default 30)")
    args = ap.parse_args()

    if args.check:
        ev = collect_events()
        if ev:
            for e in ev:
                print(json.dumps(e))
        else:
            print("no events")
        return

    if args.listen:
        print(f"[event_bus] listening (interval {args.interval}s)...")
        while True:
            try:
                ev = collect_events()
                for e in ev:
                    # Emit as a JSON push notification (stdout; a real deployment
                    # pipes this to the agent runtime or a notification sink)
                    print(json.dumps(e), flush=True)
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\n[event_bus] stopped")
                return
            except Exception as ex:
                print(f"[event_bus] error: {ex}", flush=True)
                time.sleep(args.interval)


if __name__ == "__main__":
    main()
