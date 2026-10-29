#!/usr/bin/env python3
"""zoe_monitor.py - Real-time THERMAL + CORE monitor for the engine stack.

Samples CPU frequency per core, thermal zones, and memory every N seconds.
Detects thermal throttling (cores dropping below a threshold of their max) and
emits ALERTS to a log file + a status file the engine manager / MCP can read.

Run as a daemon (background). Reads:
  /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq  (per-core MHz)
  /sys/devices/system/cpu/cpu*/cpufreq/cpuinfo_max_freq  (core max MHz)
  /sys/class/thermal/thermal_zone*/temp + type            (temps in mC)
  /proc/meminfo                                           (memory)
Writes:
  /mnt/android/hermes-workspace/state/monitor/live.json   (latest sample)
  /mnt/android/hermes-workspace/state/monitor/history.log (append)
  /mnt/android/hermes-workspace/state/monitor/alerts.log  (throttle/overheat)
"""
import json
import os
import time
from pathlib import Path

STATE = Path("/mnt/android/hermes-workspace/state/monitor")
STATE.mkdir(parents=True, exist_ok=True)
LIVE = STATE / "live.json"
HISTORY = STATE / "history.log"
ALERTS = STATE / "alerts.log"

INTERVAL = float(os.environ.get("MONITOR_INTERVAL", "10"))  # seconds
# Throttle alert: a core running below this fraction of its max is "throttled"
THROTTLE_FRAC = float(os.environ.get("MONITOR_THROTTLE_FRAC", "0.30"))
# Overheat alert: above this temp (in C)
OVERHEAT_C = float(os.environ.get("MONITOR_OVERHEAT_C", "48"))


def read_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


def read_str(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


def sample():
    """Collect one sample: per-core freq, thermal zones, memory."""
    cores = {}
    for cpu in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*")):
        n = cpu.name[3:]
        if not n.isdigit():
            continue
        cur = read_int(cpu / "cpufreq" / "scaling_cur_freq")
        mx = read_int(cpu / "cpufreq" / "cpuinfo_max_freq")
        if cur is None or mx is None:
            continue
        cores[int(n)] = {
            "cur_mhz": cur // 1000,
            "max_mhz": mx // 1000,
            "frac": round(cur / mx, 3) if mx else 0,
        }

    thermals = []
    for z in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        t = read_int(z / "temp")
        if t is None or t == 0:
            continue
        thermals.append({"zone": z.name, "type": read_str(z / "type"),
                         "temp_c": round(t / 1000, 1)})

    mem = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith(("MemTotal", "MemFree", "MemAvailable")):
                    k, v = line.split(":", 1)
                    mem[k] = int(v.strip().split()[0]) // 1024  # MB
    except Exception:
        pass

    return {"ts": time.time(), "iso": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cores": cores, "thermals": thermals, "mem": mem}


def check_throttle(s):
    """Return list of alert strings for this sample."""
    alerts = []
    for n, c in s["cores"].items():
        if c["frac"] < THROTTLE_FRAC:
            alerts.append(f"THROTTLED cpu{n}: {c['cur_mhz']}MHz/{c['max_mhz']}MHz ({c['frac']*100:.0f}%)")
    for t in s["thermals"]:
        if t["temp_c"] >= OVERHEAT_C:
            alerts.append(f"OVERHEAT {t['zone']} ({t['type']}): {t['temp_c']}C")
    # Memory pressure
    if s["mem"].get("MemAvailable", 9999) < 512:
        alerts.append(f"LOW MEM: {s['mem'].get('MemAvailable',0)}MB avail")
    return alerts


def main():
    print(f"[zoe-monitor] starting: interval={INTERVAL}s, throttle<{THROTTLE_FRAC*100:.0f}%, overheat>{OVERHEAT_C:.0f}C", flush=True)
    while True:
        try:
            s = sample()
            LIVE.write_text(json.dumps(s, indent=1), encoding="utf-8")
            # Append compact line to history
            line = (f"{s['iso']} "
                    f"core_mhz={[c['cur_mhz'] for c in sorted(s['cores'].values(), key=lambda x: x['max_mhz'], reverse=True)[:2]]} "
                    f"max_temp={max((t['temp_c'] for t in s['thermals']), default=0)}C "
                    f"mem_avail={s['mem'].get('MemAvailable','?')}MB")
            with open(HISTORY, "a") as f:
                f.write(line + "\n")
            # Check + log alerts
            for a in check_throttle(s):
                msg = f"[{s['iso']}] {a}"
                print(msg, flush=True)
                with open(ALERTS, "a") as f:
                    f.write(msg + "\n")
        except Exception as e:
            print(f"[zoe-monitor] error: {e}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
