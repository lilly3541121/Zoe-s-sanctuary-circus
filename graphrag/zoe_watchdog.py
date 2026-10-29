#!/usr/bin/env python3
"""zoe_watchdog.py - Engines watch each other for wedges/stalls.

Each engine process is monitored: it must be ALIVE (process running) and
RESPONSIVE (HTTP /v1/models answers within a timeout). If an engine is alive
but not responding for N consecutive checks, it's STUCK - the watchdog kills
and restarts it via engine_manager. This is the "make sure they're not stuck
all the way up" mechanism.

Also watches the daemons (monitor, watcher, thermals) and restarts them if
they die. Self-healing stack.

Writes state/watchdog/watchdog.json + alerts to state/watchdog/alerts.log.
"""
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

STATE = Path("/mnt/android/hermes-workspace/state/watchdog")
STATE.mkdir(parents=True, exist_ok=True)
WDOG = STATE / "watchdog.json"
ALERTS = STATE / "alerts.log"

ENGINES = {
    "gemma2": {"port": 8083, "match": "gemma2_direct.py"},
    "router": {"port": 8085, "match": "0.5b"},
    "reranker": {"port": 8086, "match": "reranker"},
    "embedder": {"port": 8087, "match": "embedding"},
    "nidum": {"port": 8088, "match": "gemma2b_direct.py"},
}
DAEMONS = {
    "monitor": "/root/zoe_monitor.py",
    "watcher": "/root/zoe_watcher.py",
    "thermals": "/root/zoe_thermals.py",
}
MANAGER = "/root/engine_manager.py"
PY = "/root/.llm-venv/bin/python3"

CHECK_INTERVAL = int(os.environ.get("WATCHDOG_INTERVAL", "20"))
STALL_CHECKS = int(os.environ.get("WATCHDOG_STALL_CHECKS", "3"))  # 3 missed = stuck
REQUEST_TIMEOUT = 5


def alert(msg):
    with open(ALERTS, "a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(f"[watchdog] {msg}", flush=True)


def is_responding(port):
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/v1/models", timeout=REQUEST_TIMEOUT):
            return True
    except Exception:
        return False


def process_alive(match):
    try:
        out = subprocess.check_output(["pgrep", "-f", match], text=True)
        return bool(out.strip())
    except Exception:
        return False


def restart_engine(name):
    alert(f"ENGINE STUCK: {name} - restarting via engine_manager")
    try:
        subprocess.run([PY, MANAGER, "stop", name], capture_output=True, timeout=30)
        time.sleep(3)
        subprocess.run([PY, MANAGER, "start", name], capture_output=True, timeout=120)
        time.sleep(5)
        ok = is_responding(ENGINES[name]["port"])
        alert(f"  {name} {'restarted OK' if ok else 'FAILED to restart'}")
        return ok
    except Exception as e:
        alert(f"  restart {name} error: {e}")
        return False


def restart_daemon(name, path):
    if process_alive(path):
        return True
    alert(f"DAEMON DOWN: {name} - restarting")
    try:
        subprocess.Popen([PY, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        alert(f"  daemon {name} start error: {e}")
        return False


def main():
    print(f"[watchdog] starting: check every {CHECK_INTERVAL}s, stall after {STALL_CHECKS} missed", flush=True)
    stall = {name: 0 for name in ENGINES}
    while True:
        state = {"ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        # Engines: alive + responsive?
        for name, cfg in ENGINES.items():
            alive = process_alive(cfg["match"])
            resp = is_responding(cfg["port"])
            if not resp:
                stall[name] += 1
                if stall[name] >= STALL_CHECKS:
                    restart_engine(name)
                    stall[name] = 0
            else:
                stall[name] = 0
            state[name] = "up" if (alive and resp) else ("stalled" if stall[name] > 0 else "down")
        # Daemons: alive?
        for name, path in DAEMONS.items():
            ok = restart_daemon(name, path)
            state[f"daemon_{name}"] = "up" if ok else "down"
        WDOG.write_text(json.dumps(state, indent=1), encoding="utf-8")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
