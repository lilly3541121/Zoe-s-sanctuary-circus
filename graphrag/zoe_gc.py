#!/usr/bin/env python3
"""zoe_gc.py - Garbage collector that uses a small model (nidum 2B) to classify
one-off scripts / readouts as TRASH or KEEP, then moves trash to archive.

The drafter does DOUBLE duty here (as you suggested):
  1. Normally it's the fast storyteller for short beats.
  2. Periodically it sweeps the scripts dir and classifies anything that looks
     like a one-off experiment / junk readout as TRASH, moving it to archive.

Runs the 2B's /v1/chat/completions endpoint with a strict yes/no prompt. Only
moves files the 2B judges TRASH. Always keeps whitelisted live files.

Usage: python3 zoe_gc.py [--dry-run] [--limit N]
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

GC_STATE = Path("/mnt/android/hermes-workspace/state/gc")
GC_STATE.mkdir(parents=True, exist_ok=True)
GC_LOG = GC_STATE / "gc.log"
ARCHIVE = Path("/root/_archive_dead_scripts")

# NEVER touch these (live pipeline / engine / monitor / watcher)
WHITELIST = {
    "engine.py", "engine_manager.py", "gemma2_direct.py", "gemma2b_direct.py",
    "zoe_monitor.py", "zoe_watcher.py", "zoe_gc.py", "mcp_sanctuary_server.py",
    "embed_dream.py", "reflect.py", "deepdream_embed_merge.py", "fastjson.py",
    "fastmath.py", "atomic.py", "scrub_pat.py", "wifi_sync.py", "sync_graphrag.sh",
    "verify_stack.sh", "port_audit.sh", "kill_12b.sh", "thermal_check.sh",
    "bench_gemma2.py", "bench_gemma2b.py", "bench_threads.py", "bench_kleidi.py",
    "bench_9b_lookup.py", "embody_card.py", "read_cards.py", "extract_all_cards.py",
}

NIDUM_URL = "http://localhost:8088/v1/chat/completions"
SCRIPTS_DIR = Path("/root")

def gc_log(msg):
    with open(GC_LOG, "a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(f"[gc] {msg}", flush=True)

def ask_2b(prompt):
    """Ask the nidum 2B a yes/no question. Returns True if it says trash."""
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 20, "temperature": 0,
    }).encode()
    req = urllib.request.Request(NIDUM_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        text = d["choices"][0]["message"]["content"].strip().lower()
        return any(w in text for w in ("yes", "trash", "junk", "delete", "remove"))
    except Exception as e:
        gc_log(f"  (2B unavailable: {e})")
        return False

def classify_file(path):
    """Ask the 2B whether this file is trash. Returns True if trash."""
    name = path.name
    # Skip whitelist + non-scripts
    if name in WHITELIST or path.suffix not in (".py", ".sh", ".log", ".txt"):
        return False
    # Skip very large files (models)
    if path.stat().st_size > 500_000:
        return False
    # Read a sample
    try:
        sample = path.read_text(encoding="utf-8", errors="replace")[:600]
    except Exception:
        return False
    prompt = (
        "You are a code/file janitor. A file is TRASH if it is a one-off "
        "benchmark, a junk readout, a debug script, or a leftover that serves "
        "no purpose. It is KEEP if it looks like a real tool or script.\n\n"
        f"File: {name}\nContent snippet:\n{sample}\n\n"
        "Answer only YES if TRASH, NO if KEEP."
    )
    return ask_2b(prompt)

def main():
    dry_run = "--dry-run" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 20
    candidates = [p for p in SCRIPTS_DIR.iterdir() if p.is_file() and p.suffix in (".py", ".sh")]
    # Sort by size (smallest first - most likely junk) and take the limit
    candidates.sort(key=lambda p: p.stat().st_size)
    candidates = candidates[:limit]
    gc_log(f"sweeping {len(candidates)} scripts (dry_run={dry_run})")
    moved = 0
    for p in candidates:
        if p.name in WHITELIST:
            continue
        if classify_file(p):
            gc_log(f"TRASH: {p.name}")
            if not dry_run:
                ARCHIVE.mkdir(parents=True, exist_ok=True)
                try:
                    p.rename(ARCHIVE / p.name)
                    moved += 1
                except Exception as e:
                    gc_log(f"  move failed: {e}")
        else:
            gc_log(f"KEEP: {p.name}")
    gc_log(f"done: {moved} moved to archive")

if __name__ == "__main__":
    main()
