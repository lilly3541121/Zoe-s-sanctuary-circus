#!/usr/bin/env python3
"""test_mcp_subscribe_fire.py — Prove subscribe_events FIRES through MCP on a real anomaly.

Backs up the real episodic log, injects a repeated-error scenario, calls
subscribe_events via MCP (must return ANOMALY), then restores the log.
"""
import json
import shutil
import subprocess
import time
from pathlib import Path

SERVER = "/root/mcp_sanctuary_server.py"
PY = "/root/.llm-venv/bin/python3"
EPISODIC = Path("/mnt/android/hermes-workspace/state/graphrag/episodic_log.jsonl")


def send(p, msg):
    p.stdin.write(json.dumps(msg) + "\n")
    p.stdin.flush()


def recv(p, timeout=40):
    import select
    r, _, _ = select.select([p.stdout], [], [], timeout)
    if not r:
        return None
    line = p.stdout.readline()
    return json.loads(line) if line.strip() else None


def main():
    # backup + inject 3 repeated errors
    backup = EPISODIC.read_text() if EPISODIC.exists() else ""
    import datetime
    ts = datetime.datetime.now().isoformat()
    with open(EPISODIC, "w") as f:
        for i in range(3):
            f.write(json.dumps({"node": "Error_test_anomaly", "type": "error",
                                "description": "test anomaly", "timestamp": ts,
                                "meta": {}}) + "\n")

    p = subprocess.Popen([PY, SERVER], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, bufsize=1)
    time.sleep(1.5)
    send(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"}}})
    recv(p)
    send(p, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    send(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "subscribe_events", "arguments": {}}})
    r = recv(p)
    if r and "result" in r:
        text = r["result"].get("content", [{}])[0].get("text", "")
        print("  subscribe_events ->", text)
        fired = "ANOMALY" in text
    else:
        text = str(r)
        fired = False
        print("  subscribe_events -> FAIL", r)

    send(p, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
    recv(p, timeout=5)
    p.terminate()

    # restore real log
    EPISODIC.write_text(backup)
    print(f"\n  ANOMALY fired through MCP: {'YES' if fired else 'NO'}")
    print(f"  real log restored: {'YES' if EPISODIC.read_text() == backup else 'NO'}")
    print(f"  RESULT: {'PASS' if fired else 'FAIL'}")


if __name__ == "__main__":
    main()
