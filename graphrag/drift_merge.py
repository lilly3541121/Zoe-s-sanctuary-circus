#!/usr/bin/env python3
"""drift_merge.py — Vector 3: repository state drift auto-merge.

Detects when the LOCAL graph cache diverges from what was last synced to the
remote, and auto-merges local changes with upstream. This is the "Repository
State Drift -> Git Hook Daemon -> Auto-merge local graph changes with upstream
remote" row of the Vector 3 trigger table.

Flow:
  1. Record the synced hash after every successful push (record_synced()).
  2. On each run, compare local cache hash vs the recorded synced hash.
  3. If they differ AND the remote has moved (drift), fetch + merge upstream
     graph changes into the local store (non-destructive: entities/relations
     union, dreams union by id).
  4. Re-sync the merged result back up.

Run after push:   python3 drift_merge.py --record   # remember the pushed hash
Run on schedule:  python3 drift_merge.py            # check + auto-merge if drifted
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path("/mnt/android/hermes-workspace")
STATE = WORKSPACE / "state/graphrag"
CACHE = STATE / "cache.json"
VECTORS = STATE / "vectors.json"
MARKER = STATE / ".last_synced_hash"
REPO = WORKSPACE / "Zoe-s-sanctuary-circus"
PY = "/root/.llm-venv/bin/python3"


def cache_hash():
    return hashlib.md5(CACHE.read_bytes()).hexdigest()[:12]


def record_synced():
    MARKER.write_text(cache_hash())
    return cache_hash()


def read_marker():
    if MARKER.exists():
        return MARKER.read_text().strip()
    return ""


def fetch_remote_graph():
    """git pull the sanctuary, then read the upstream graph data."""
    try:
        r = subprocess.run(["git", "-C", str(REPO), "pull", "--ff-only", "origin", "main"],
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0, r.stdout
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def merge_graphs(local_cache, remote_cache):
    """Non-destructive union: entities dict + relations list (by a-b-kind key)."""
    merged = {"entities": dict(local_cache.get("entities", {})),
              "relations": []}
    # relations keyed by (a,b,kind) to dedupe
    seen = set()
    for rel in local_cache.get("relations", []):
        k = (rel.get("a"), rel.get("b"), rel.get("kind"))
        if k not in seen:
            seen.add(k)
            merged["relations"].append(rel)
    for rel in remote_cache.get("relations", []):
        k = (rel.get("a"), rel.get("b"), rel.get("kind"))
        if k not in seen:
            seen.add(k)
            merged["relations"].append(rel)
    # entities: local wins on conflict, remote adds missing
    for name, val in remote_cache.get("entities", {}).items():
        merged["entities"].setdefault(name, val)
    return merged


def merge_vectors(local_v, remote_v):
    """Union dreams by id; local wins on conflict."""
    by_id = {}
    for d in local_v.get("dreams", []):
        by_id[d.get("id") or d.get("name") or str(id(d))] = d
    for d in remote_v.get("dreams", []):
        key = d.get("id") or d.get("name") or str(id(d))
        by_id.setdefault(key, d)
    return {"dreams": list(by_id.values())}


def main():
    ap = argparse.ArgumentParser(description="Repo state drift auto-merge")
    ap.add_argument("--record", action="store_true",
                    help="record the current local hash as the synced baseline")
    ap.add_argument("--check", action="store_true",
                    help="check for drift and report (no merge)")
    args = ap.parse_args()

    if args.record:
        h = record_synced()
        print(f"recorded synced hash: {h}")
        return

    local_h = cache_hash()
    synced_h = read_marker()
    if not synced_h:
        print("no baseline recorded; run --record after next push")
        return

    if args.check:
        if local_h == synced_h:
            print(f"no drift (local {local_h} == synced {synced_h})")
        else:
            print(f"DRIFT: local {local_h} != synced {synced_h}")
        return

    if local_h == synced_h:
        print(f"no drift (local {local_h} == synced {synced_h})")
        return

    print(f"drift detected: local {local_h} != synced {synced_h}")
    ok, out = fetch_remote_graph()
    if not ok:
        print(f"could not fetch remote: {out}")
        return
    print(f"fetched remote: {out.strip()[:80]}")

    # read the remote graph from the pulled repo
    remote_cache_p = REPO / "graphrag/data/cache.json"
    remote_vectors_p = REPO / "graphrag/data/vectors.json"
    if remote_cache_p.exists():
        remote_cache = json.loads(remote_cache_p.read_text())
        local_cache = json.loads(CACHE.read_text())
        merged = merge_graphs(local_cache, remote_cache)
        # write merged back to local + remote (atomic-ish)
        CACHE.write_text(json.dumps(merged))
        remote_cache_p.write_text(json.dumps(merged))
        print(f"merged cache: {len(merged['entities'])} entities, {len(merged['relations'])} relations")

    if remote_vectors_p.exists():
        remote_v = json.loads(remote_vectors_p.read_text())
        local_v = json.loads(VECTORS.read_text())
        mv = merge_vectors(local_v, remote_v)
        VECTORS.write_text(json.dumps(mv))
        remote_vectors_p.write_text(json.dumps(mv))
        print(f"merged vectors: {len(mv['dreams'])} dreams")

    # commit + push the merged result back
    try:
        subprocess.run(["git", "-C", str(REPO), "add", "-A"],
                       capture_output=True, timeout=60)
        subprocess.run(["git", "-C", str(REPO), "commit", "-m", "drift-merge: reconciled local+remote graph"],
                       capture_output=True, timeout=60)
        # push via PAT URL form (never echo token)
        tok = Path("/root/.hermes/graphrag_token.env").read_text()
        token = None
        for line in tok.splitlines():
            if line.startswith("GH_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
        if token:
            url = f"https://{token}@github.com/lilly3541121/Zoe-s-sanctuary-circus.git"
            r = subprocess.run(["git", "-C", str(REPO), "push", url, "main"],
                               capture_output=True, text=True, timeout=120)
            print(f"push: {'OK' if r.returncode == 0 else r.stderr[:80]}")
    except Exception as e:  # noqa: BLE001
        print(f"sync error: {e}")

    record_synced()
    print("drift resolved")


if __name__ == "__main__":
    main()
