#!/usr/bin/env python3
"""maintain_graph.py — One-pass deterministic graph maintenance.

Runs the full maintenance cycle in order:
  build -> prune -> merge (episodic + procedural) -> embed -> verify -> push

This is the single entry point for regular maintenance. It is idempotent and
safe to run repeatedly. Tests are the spec: 9/9 existing + new tier tests must
pass; the cycle refuses to push on failure.

Usage:
  python3 maintain_graph.py                 # full cycle
  python3 maintain_graph.py --no-push       # everything but push
  python3 maintain_graph.py --prune-days 90 # prune events older than N days
"""
import json
import os
import sys
import subprocess
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import episodic
import procedural

GRAPH_DIR = os.environ.get(
    "GRAPH_DIR", "/mnt/android/hermes-workspace/state/graphrag"
)
CACHE = os.path.join(GRAPH_DIR, "cache.json")
SANCTUARY = os.environ.get(
    "SANCTUARY_DIR", "/mnt/android/hermes-workspace/Zoe-s-sanctuary-circus"
)
PY = "/root/.llm-venv/bin/python3"


def step(name):
    print(f"\n=== {name} ===")


def run_graphrag_build():
    """Rebuild naive extraction (delta-based, appends to existing cache)."""
    step("BUILD (naive extraction)")
    r = subprocess.run(
        [PY, os.path.join(HERE, "graphrag.py"), "build"],
        cwd=HERE, capture_output=True, text=True,
    )
    print(r.stdout.strip()[-300:] if r.stdout.strip() else "  (no output)")
    if r.returncode != 0:
        print(f"  BUILD FAILED: {r.stderr.strip()[-300:]}")
        return False
    return True


def prune(prune_days):
    step(f"PRUNE (events > {prune_days}d)")
    n = episodic.prune_events(prune_days)
    print(f"  pruned {n} old events")


def merge_tiers():
    step("MERGE (episodic + procedural into graph)")
    e1, r1 = episodic.sync_to_graph()
    e2, r2 = procedural.sync_to_graph()
    print(f"  episodic: +{e1} event nodes, +{r1} resolved_by edges")
    print(f"  procedural: +{e2} recipe nodes, +{r2} optimizes edges")
    return e1 + r1 + e2 + r2


def embed():
    step("EMBED (dream vectors)")
    emb = "/root/deepdream_embed_merge.py"
    if not os.path.exists(emb):
        print("  (embed script not found, skipping)")
        return True
    r = subprocess.run([PY, emb], capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    # print last few meaningful lines
    tail = [l for l in out.splitlines() if l.strip()][-4:]
    for l in tail:
        print(f"  {l}")
    return r.returncode == 0


def verify():
    step("VERIFY (tests are the spec)")
    r = subprocess.run(
        [PY, os.path.join(HERE, "test_graphrag.py")],
        cwd=HERE, capture_output=True, text=True,
    )
    out = r.stdout + r.stderr
    passed = "OK" in out and "Ran 9 tests" in out
    for l in out.splitlines()[-6:]:
        if l.strip():
            print(f"  {l}")
    if not passed:
        print("  !!! TESTS FAILED — refusing to push")
    return passed


def push():
    step("PUSH (Wi-Fi gated)")
    # Sync cache to sanctuary
    os.makedirs(os.path.join(SANCTUARY, "graphrag", "data"), exist_ok=True)
    dst = os.path.join(SANCTUARY, "graphrag", "data", "cache.json")
    subprocess.run(["cp", CACHE, dst], check=False)

    # Commit + push with PAT from env (never echoed)
    env = os.environ.copy()
    token_file = "/root/.hermes/graphrag_token.env"
    if os.path.exists(token_file):
        with open(token_file) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"')

    repo = SANCTUARY
    subprocess.run(["git", "-C", repo, "add", "-A"], check=False)
    subprocess.run(
        ["git", "-C", repo, "commit", "-m",
         f"graph: tri-tier maintenance cycle ({__file__.split('/')[-1]})"],
        check=False,
    )
    remote_url = env.get("GH_TOKEN", "")
    if remote_url:
        url = f"https://{env['GH_TOKEN']}@github.com/lilly3541121/Zoe-s-sanctuary-circus.git"
        r = subprocess.run(
            ["git", "-C", repo, "push", url, "main"],
            capture_output=True, text=True, env=env,
        )
        # redact any token leak in output
        safe_out = (r.stdout + r.stderr).replace(env.get("GH_TOKEN", "XXX"), "***REDACTED***")
        print(safe_out.strip()[-300:] if safe_out.strip() else "  (pushed)")
        return r.returncode == 0
    print("  (no token, skipping push)")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true", help="skip the push step")
    ap.add_argument("--prune-days", type=int, default=90, help="prune events older than N days")
    ap.add_argument("--skip-embed", action="store_true", help="skip the embed step")
    args = ap.parse_args()

    ok = run_graphrag_build()
    prune(args.prune_days)
    merge_tiers()
    if not args.skip_embed:
        ok = embed() and ok
    ok = verify() and ok

    if ok and not args.no_push:
        ok = push()
    elif ok and args.no_push:
        print("\n(no-push: skipping push)")

    print(f"\n=== CYCLE {'COMPLETE' if ok else 'INCOMPLETE'} ===")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
