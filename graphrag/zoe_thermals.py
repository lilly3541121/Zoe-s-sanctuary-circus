#!/usr/bin/env python3
"""zoe_thermals.py - Adaptive thermal manager.

Reads the monitor's live.json. When cores warm up (temp rising toward throttle),
re-pins engine threads to the COOLER cores via taskset. This is the "change
threads to the cool ones" mechanism.

Logic:
  - Identify the 2 prime Oryon cores (highest max MHz) as "hot" - they throttle first.
  - Identify the 6 perf cores as "cool".
  - If the hot cores are throttled (<30% max) AND there's a warm thermal zone,
    re-pin engine processes to the cool cores (cpu0-5).
  - Restore full affinity (0-7) when the system has cooled down.

Writes state to state/monitor/thermals.json (last action).
"""
import json
import os
import subprocess
import time
from pathlib import Path

MONITOR = Path("/mnt/android/hermes-workspace/state/monitor/live.json")
STATE = Path("/mnt/android/hermes-workspace/state/monitor/thermals.json")

# Engine processes to manage (matched by these cmdline fragments)
ENGINE_MATCHES = ["gemma2_direct", "gemma2b_direct", "llama_cpp.server"]
# Cool cores (perf cores, lower max freq = less likely to overheat)
COOL_CORES = "0-5"
# Hot cores (prime Oryon cores - throttle first)
HOT_CORES = "6-7"
# Throttle threshold: below this fraction = throttled
THROTTLE_FRAC = float(os.environ.get("THERMAL_THROTTLE_FRAC", "0.30"))
# How long must it stay throttled before we re-pin (avoid flapping)
MIN_THROTTLED_SECONDS = float(os.environ.get("THERMAL_MIN_SECONDS", "20"))


def read_json(p):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def get_engine_pids():
    """Find PIDs of engine processes."""
    pids = []
    for m in ENGINE_MATCHES:
        try:
            out = subprocess.check_output(["pgrep", "-f", m], text=True)
            pids.extend(int(x) for x in out.strip().split() if x.isdigit())
        except Exception:
            pass
    return list(set(pids))


def set_affinity(pid, cores):
    """Set a process's CPU affinity to a core mask via taskset."""
    try:
        subprocess.run(["taskset", "-p", "-c", cores, str(pid)],
                       check=True, capture_output=True)
        return True
    except Exception:
        return False


def is_throttled(live):
    """True if the hot (prime) cores are throttled below threshold."""
    if not live:
        return False
    hot = [c for n, c in live.get("cores", {}).items() if n in (6, 7)]
    if not hot:
        return False
    return all(c["frac"] < THROTTLE_FRAC for c in hot)


def max_temp(live):
    """Highest thermal zone temp in C (ignore absurd values)."""
    ts = live.get("thermals", [])
    temps = [t["temp_c"] for t in ts if -20 < t["temp_c"] < 100]
    return max(temps) if temps else 0


def main():
    # Load previous state (to track how long throttled)
    prev = read_json(STATE) or {}
    throttled_since = prev.get("throttled_since")

    while True:
        live = read_json(MONITOR)
        if live:
            throttled = is_throttled(live)
            now = time.time()
            if throttled and throttled_since is None:
                throttled_since = now
            elif not throttled:
                throttled_since = None

            # Decide action
            action = "none"
            if throttled_since and (now - throttled_since) >= MIN_THROTTLED_SECONDS:
                # Re-pin engines to cool cores
                pids = get_engine_pids()
                moved = sum(1 for p in pids if set_affinity(p, COOL_CORES))
                action = f"re-pinned {moved} engine(s) to cool cores {COOL_CORES}"
                throttled_since = None  # reset until next sustained event
                # Don't spam: after re-pin, wait longer
                time.sleep(60)
            elif not throttled and prev.get("state") == "re-pinned":
                # System cooled - restore full affinity
                pids = get_engine_pids()
                restored = sum(1 for p in pids if set_affinity(p, "0-7"))
                action = f"cooled - restored {restored} engine(s) to full affinity"

            state = {
                "ts": now, "iso": time.strftime("%Y-%m-%d %H:%M:%S"),
                "throttled": throttled, "throttled_for_s": round(now - throttled_since, 1) if throttled_since else 0,
                "max_temp_c": max_temp(live), "action": action,
                "cores": {n: c["frac"] for n, c in live.get("cores", {}).items()},
            }
            if action != "none" or prev.get("state") != state.get("prev_state"):
                print(f"[zoe-thermals] {state['iso']} throttled={throttled} "
                      f"max_temp={state['max_temp_c']}C action={action}", flush=True)
            STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
            prev = state
        time.sleep(int(os.environ.get("THERMAL_INTERVAL", "15")))


if __name__ == "__main__":
    main()
