#!/usr/bin/env python3
"""zoe_watcher.py - Watches for user-dropped files + queued outputs + file events.

Scans every N minutes (default 2) for:
  1. New files in the drop folder (workspace root + ingest/) - models, notes, etc.
  2. New lines in the file-events log (.hermes_file_events.jsonl)
  3. Any *.md / *.txt notes the user dropped that need attention

When it finds something NEW, it logs it to a "for-zoe" inbox file with a
timestamp. The agent (me) reads that inbox to pick up user messages / files
that arrive outside the chat. This is the "hooks into the queued outputs from
you" mechanism - a persistent inbox the agent checks.

Writes:
  /mnt/android/hermes-workspace/state/watcher/inbox.jsonl   (new events)
  /mnt/android/hermes-workspace/state/watcher/seen.json     (dedup state)
"""
import json
import os
import time
from pathlib import Path

WS = Path("/mnt/android/hermes-workspace")
STATE = WS / "state" / "watcher"
STATE.mkdir(parents=True, exist_ok=True)
INBOX = STATE / "inbox.jsonl"
SEEN = STATE / "seen.json"

# Places to watch for user-dropped files
DROP_DIRS = [WS, WS / "ingest"]
# Known-good extensions that are "interesting" when dropped
INTERESTING_EXT = {".gguf", ".md", ".txt", ".pdf", ".json", ".csv", ".sh", ".py"}
# Skip these (model weights we already know about / runtime junk)
SKIP_NAMES = {"live.json", "history.log", "alerts.log", "inbox.jsonl",
              "seen.json", "cache.json", "cache_meta.json", "extraction.log"}

INTERVAL = int(os.environ.get("WATCHER_INTERVAL", "120"))  # seconds (2 min)


def load_seen():
    if SEEN.exists():
        try:
            return json.loads(SEEN.read_text())
        except Exception:
            pass
    return {}


def save_seen(seen):
    SEEN.write_text(json.dumps(seen, indent=1), encoding="utf-8")


def note(seen, key, payload):
    """Log an event to inbox if we haven't seen this key before."""
    if key in seen:
        return False
    seen[key] = time.time()
    with open(INBOX, "a") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **payload}) + "\n")
    return True


def scan_files(seen):
    """Detect new/changed files in the drop dirs."""
    events = 0
    for d in DROP_DIRS:
        if not d.exists():
            continue
        for p in d.iterdir():
            if not p.is_file():
                continue
            if p.name in SKIP_NAMES:
                continue
            if p.suffix.lower() not in INTERESTING_EXT:
                continue
            key = f"file:{p.name}:{p.stat().st_mtime}"
            if note(seen, key, {"kind": "file", "name": p.name,
                                "path": str(p), "size": p.stat().st_size,
                                "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))}):
                events += 1
    return events


def scan_events_log(seen):
    """Detect new file-manager events (the phone's file events log)."""
    elog = WS / ".hermes_file_events.jsonl"
    if not elog.exists():
        return 0
    events = 0
    try:
        with open(elog) as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                key = f"evt:{i}:{line[:60]}"
                if note(seen, key, {"kind": "file_event", "raw": line[:200]}):
                    events += 1
    except Exception:
        pass
    return events


def main():
    print(f"[zoe-watcher] starting: interval={INTERVAL}s, watching {[str(d) for d in DROP_DIRS]}", flush=True)
    seen = load_seen()
    while True:
        try:
            f = scan_files(seen)
            e = scan_events_log(seen)
            if f or e:
                print(f"[zoe-watcher] {f} file(s), {e} event(s) -> inbox", flush=True)
            save_seen(seen)
        except Exception as ex:
            print(f"[zoe-watcher] error: {ex}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
