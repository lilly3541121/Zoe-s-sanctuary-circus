#!/usr/bin/env python3
"""zoe_stayalive.py - Stay-alive helper: bounded, cool background work.

Runs the DETERMINISTIC parts of a stay-alive cycle so the agent cron job stays
light and doesn't melt the phone. Does NOT do heavy LLM generation - that's the
agent's job via a short, bounded prompt.

Per cycle:
  1. Ensure the stack is up (supervisor).
  2. Read monitor + watcher + watchdog state (health snapshot).
  3. Read any new alerts / inbox items since last cycle.
  4. Append a compact reflection line to the reflection log.
  5. Run the GC sweep (classify + move trash) - light, 2B only.
  6. Print a compact summary (what was done, what needs attention).

Writes:
  state/stayalive/cycle.log     (per-cycle summary)
  state/stayalive/last.json     (last cycle state)
"""
import json
import os
import subprocess
import time
from pathlib import Path

STATE = Path("/mnt/android/hermes-workspace/state/stayalive")
STATE.mkdir(parents=True, exist_ok=True)
CYCLE_LOG = STATE / "cycle.log"
LAST = STATE / "last.json"
REFLECT_LOG = Path("/mnt/android/hermes-workspace/sanctuary_writing/reflection.md")

PY = "/root/.llm-venv/bin/python3"


def read_json(p):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def append_line(path, line):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(line + "\n")
        return True
    except Exception:
        return False


def ensure_stack():
    """Run the supervisor to ensure stack + daemons are up."""
    try:
        r = subprocess.run(["bash", "/root/zoe_supervisor.sh"], capture_output=True,
                           text=True, timeout=180)
        out = (r.stdout or "") + (r.stderr or "")
        up = out.count("already running") + out.count("UP")
        return f"stack ensured ({up} items confirmed)"
    except Exception as e:
        return f"stack error: {e}"


def health_snapshot():
    """Read monitor + watchdog + watcher state."""
    snap = {}
    mon = read_json(Path("/mnt/android/hermes-workspace/state/monitor/live.json"))
    if mon:
        # Use the real CPU temp (cpu_temp_c), not the hottest zone (PMIC)
        snap["max_temp_c"] = mon.get("cpu_temp_c", 0)
        snap["mem_mb"] = mon.get("mem", {}).get("MemAvailable")
    wd = read_json(Path("/mnt/android/hermes-workspace/state/watchdog/watchdog.json"))
    if wd:
        snap["engines"] = {k: v for k, v in wd.items() if k != "ts"}
    return snap


def check_new_alerts():
    """Count new alert lines since last cycle."""
    last = read_json(LAST) or {}
    alert_path = Path("/mnt/android/hermes-workspace/state/monitor/alerts.log")
    if not alert_path.exists():
        return 0
    lines = alert_path.read_text().strip().splitlines()
    return max(0, len(lines) - last.get("alert_count", 0))


def check_inbox():
    """Count new inbox items (user drops) since last cycle."""
    last = read_json(LAST) or {}
    inbox = Path("/mnt/android/hermes-workspace/state/watcher/inbox.jsonl")
    if not inbox.exists():
        return 0
    lines = [l for l in inbox.read_text().strip().splitlines() if l.strip()]
    return max(0, len(lines) - last.get("inbox_count", 0))


def run_gc():
    """Light GC sweep (2B classifies, whitelist-protected)."""
    try:
        r = subprocess.run([PY, "/root/zoe_gc.py", "--limit", "6"],
                           capture_output=True, text=True, timeout=120)
        moved = sum(1 for l in (r.stdout or "").splitlines() if "TRASH" in l and "moved" not in l)
        return f"gc sweep: {moved} trash flagged"
    except Exception as e:
        return f"gc error: {e}"


def reflect(cycle_summary):
    """Append a compact reflection line."""
    ts = time.strftime("%Y-%m-%d %H:%M")
    line = f"- {ts} stayalive: {cycle_summary}"
    append_line(REFLECT_LOG, line)
    return line


def main():
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    stack = ensure_stack()
    snap = health_snapshot()
    new_alerts = check_new_alerts()
    new_inbox = check_inbox()
    gc = run_gc()
    cycle_summary = (f"stack={snap.get('engines', {}).get('gemma2', '?')} "
                     f"temp={snap.get('max_temp_c', '?')}C "
                     f"mem={snap.get('mem_mb', '?')}MB "
                     f"new_alerts={new_alerts} new_inbox={new_inbox}")
    refl = reflect(cycle_summary)
    summary = f"[{ts}] {stack} | {cycle_summary} | {gc}"
    append_line(CYCLE_LOG, summary)
    # Persist last state
    LAST.write_text(json.dumps({
        "ts": ts, "alert_count": sum(1 for _ in open(Path("/mnt/android/hermes-workspace/state/monitor/alerts.log")) if _.strip()) if Path("/mnt/android/hermes-workspace/state/monitor/alerts.log").exists() else 0,
        "inbox_count": sum(1 for _ in open(Path("/mnt/android/hermes-workspace/state/watcher/inbox.jsonl")) if _.strip()) if Path("/mnt/android/hermes-workspace/state/watcher/inbox.jsonl").exists() else 0,
    }, indent=1), encoding="utf-8")
    # Print compact summary for the cron agent
    print(f"CYCLE {ts}")
    print(f"  {stack}")
    print(f"  temp={snap.get('max_temp_c', '?')}C mem={snap.get('mem_mb', '?')}MB new_alerts={new_alerts} new_inbox={new_inbox}")
    print(f"  {gc}")
    print(f"  reflected: {refl}")


if __name__ == "__main__":
    main()
