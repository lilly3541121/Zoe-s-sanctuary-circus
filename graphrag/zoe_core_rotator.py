#!/usr/bin/env python3
"""zoe_core_rotator.py - Rotate engine threads to FRESH cores after every output.

The user's insight: models heat up in bursts while producing. Instead of waiting
for cores to throttle (reactive), proactively move the engine to a different
(fresh/cool) core set right after each output completes. That way no core set
gets saturated - heat spreads, and every generation starts on cool cores.

How it detects "output done": watches each engine's CPU usage via /proc/<pid>/stat.
When CPU transitions from HIGH (generating/thinking) to LOW (idle), the output is
done -> rotate affinity to the next core set.

How it picks the next set: round-robin through a schedule, but SKIP any set whose
prime cores are currently throttled (from the monitor's live.json). So when cool,
it rotates through all cores; when hot, it stays on the cool perf cores.

Rotation schedule:
  A: "0-5"  (6 perf cores - cool, primary workhorse)
  B: "0-7"  (all 8 cores - full throughput, only when prime cores aren't throttled)
When a set is skipped, the engine just stays where it is (already fresh).

Also rotates on request-arrival (CPU low->high): that's "after thinking, before
responding" - the next generation starts on whatever cores are freshest.

Writes:
  state/rotator/rotator.json   (last rotation state)
  state/rotator/rotator.log    (rotation history)
"""
import json
import os
import subprocess
import time
from pathlib import Path

STATE = Path("/mnt/android/hermes-workspace/state/rotator")
STATE.mkdir(parents=True, exist_ok=True)
ROTATOR_JSON = STATE / "rotator.json"
ROTATOR_LOG = STATE / "rotator.log"

MONITOR = Path("/mnt/android/hermes-workspace/state/monitor/live.json")

# Engine processes to rotate (cmdline fragments)
ENGINE_MATCHES = ["gemma2_direct", "gemma2b_direct", "gemma4_direct", "llama_cpp.server"]
# Rotation schedule: sets of cores to cycle through
CORE_SETS = ["0-5", "0-7"]
# Prime cores (index 6,7) - if these are throttled, skip the "all cores" set
PRIME = ("6", "7")

# CPU detection: we measure delta-ticks-per-second (jiffies/sec). The absolute
# scale is unknown (qroot bridge counts differently than HZ=100), so we don't use
# a fixed % threshold. Instead: compare the CURRENT tick rate to a CALIBRATED
# baseline. When the engine is idle, ticks/sec is near 0. When generating, it
# jumps by orders of magnitude. We detect BUSY when ticks/sec exceeds a multiple
# of the idle baseline, and IDLE when it drops back near 0.
BUSY_MULTIPLE = 5.0    # ticks/sec must be >5x idle baseline to count as busy
IDLE_TICKS_PER_SEC = 8.0  # below this (absolute) counts as idle
# Consecutive samples to confirm a transition (avoid flapping)
BUSY_SAMPLES = 2
IDLE_SAMPLES = 3

POLL_INTERVAL = float(os.environ.get("ROTATOR_POLL", "2"))  # seconds


def log(msg):
    with open(ROTATOR_LOG, "a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(f"[rotator] {msg}", flush=True)


def get_engine_pids():
    """Find engine PIDs (the real Python processes, not the qroot bridge)."""
    pids = []
    for m in ENGINE_MATCHES:
        try:
            out = subprocess.check_output(["pgrep", "-f", m], text=True)
            pids.extend(int(x) for x in out.strip().split() if x.isdigit())
        except Exception:
            pass
    return list(set(pids))


def cpu_usage(pid):
    """Read CPU% for a process from /proc/<pid>/stat (utime+stime delta)."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            parts = f.read().split()
        utime, stime = int(parts[13]), int(parts[14])  # fields 14,15 (1-indexed)
        return utime + stime
    except Exception:
        return None


def read_monitor():
    try:
        return json.loads(MONITOR.read_text())
    except Exception:
        return None


def prime_throttled(live):
    """True if the prime cores (6,7) are throttled (<30% of max)."""
    if not live:
        return False
    cores = live.get("cores", {})
    hot = [c for n, c in cores.items() if str(n) in PRIME]
    if not hot:
        return False
    return all(c["frac"] < 0.30 for c in hot)


def pick_next_set(schedule_index, live):
    """Pick the next core set, skipping any with throttled prime cores."""
    for i in range(len(CORE_SETS)):
        idx = (schedule_index + i) % len(CORE_SETS)
        s = CORE_SETS[idx]
        if s == "0-7" and prime_throttled(live):
            continue  # skip all-cores when the prime cores are throttled
        return s, idx
    return CORE_SETS[0], 0  # fallback: perf cores


def set_affinity(pid, cores):
    try:
        subprocess.run(["taskset", "-p", "-c", cores, str(pid)],
                       check=True, capture_output=True)
        return True
    except Exception:
        return False


def main():
    log(f"starting: rotate after every output. sets={CORE_SETS}, poll={POLL_INTERVAL}s")
    schedule_index = 0
    # Track per-pid CPU + busy/idle state
    track = {}  # pid -> {"last_ticks": int, "last_wall": float, "cpu": float, "state": "idle"/"busy", "busy_ct": int, "idle_ct": int}

    while True:
        pids = get_engine_pids()
        live = read_monitor()
        now = time.time()
        for pid in pids:
            ticks = cpu_usage(pid)
            if ticks is None:
                continue
            t = track.setdefault(pid, {"last_ticks": None, "last_wall": None,
                                       "rate": 0.0, "state": "idle",
                                       "busy_ct": 0, "idle_ct": 0})
            if t["last_ticks"] is not None and t["last_wall"] is not None:
                dt = now - t["last_wall"]
                if dt > 0:
                    rate = (ticks - t["last_ticks"]) / dt  # ticks/sec (scale-free)
                    t["rate"] = rate
                    # Detect transitions using the scale-free tick rate
                    if rate > IDLE_TICKS_PER_SEC and rate > (t.get("baseline", 1.0) * BUSY_MULTIPLE):
                        t["busy_ct"] += 1
                        t["idle_ct"] = 0
                        if t["busy_ct"] >= BUSY_SAMPLES and t["state"] != "busy":
                            # Transitioned idle -> busy: request arrived, about to think/generate.
                            # "After thinking but before responding": rotate to fresh cores NOW
                            # so the generation lands on cool cores.
                            set_affinity(pid, CORE_SETS[schedule_index % len(CORE_SETS)])
                            t["state"] = "busy"
                            log(f"pid {pid} BUSY (rate={rate:.0f} t/s) -> ready on {CORE_SETS[schedule_index % len(CORE_SETS)]}")
                    elif rate <= IDLE_TICKS_PER_SEC:
                        t["idle_ct"] += 1
                        t["busy_ct"] = 0
                        if t["idle_ct"] >= IDLE_SAMPLES and t["state"] == "busy":
                            # Transitioned busy -> idle: OUTPUT DONE. Rotate to fresh cores.
                            schedule_index = (schedule_index + 1) % len(CORE_SETS)
                            nxt, schedule_index = pick_next_set(schedule_index, live)
                            set_affinity(pid, nxt)
                            t["state"] = "idle"
                            log(f"pid {pid} output DONE (rate={rate:.0f} t/s) -> rotate to {nxt}")
                    else:
                        t["busy_ct"] = 0
                        t["idle_ct"] = 0
                    # Track a rolling idle baseline (the "resting" tick rate)
                    if rate <= IDLE_TICKS_PER_SEC:
                        t["baseline"] = max(0.5, rate)
            t["last_ticks"] = ticks
            t["last_wall"] = now
        # Persist state
        ROTATOR_JSON.write_text(json.dumps({
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "schedule_index": schedule_index,
            "prime_throttled": prime_throttled(live),
            "engines": {str(p): {"rate": round(t["rate"], 1), "state": t["state"]}
                        for p, t in track.items()},
        }, indent=1), encoding="utf-8")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
