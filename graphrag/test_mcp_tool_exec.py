#!/usr/bin/env python3
"""test_mcp_tool_exec.py — Prove the MCP server's tool handlers EXECUTE real scripts.

Calls log_run (episodic tier, appends to the real episodic log) and graph_stats
through the MCP stdio round-trip, then verifies the episodic log grew.
This is the strongest proof: the MCP tool does actual work, not just discovery.
"""
import json
import subprocess
import time
from pathlib import Path

SERVER = "/root/mcp_sanctuary_server.py"
PY = "/root/.llm-venv/bin/python3"
LOG = Path("/mnt/android/hermes-workspace/state/graphrag/episodic_log.jsonl")


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
    before = LOG.stat().st_size if LOG.exists() else 0
    p = subprocess.Popen([PY, SERVER], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, bufsize=1)
    time.sleep(1.5)
    send(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"}}})
    recv(p)
    send(p, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    # call log_run (writes to the episodic log for real)
    send(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "log_run",
                        "arguments": {"name": "mcp_test_exec", "detail": "proving MCP tool execution"}}})
    r = recv(p)
    print("  tools/call log_run ->", r["result"]["content"][0]["text"] if r and "result" in r else r)

    time.sleep(0.5)
    after = LOG.stat().st_size if LOG.exists() else 0
    print(f"  episodic log: {before} -> {after} bytes  {'GREW (executed!)' if after > before else 'NO CHANGE'}")

    # call graph_stats
    send(p, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "graph_stats", "arguments": {}}})
    r = recv(p)
    print("  tools/call graph_stats ->", r["result"]["content"][0]["text"] if r and "result" in r else r)

    send(p, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
    recv(p, timeout=5)
    p.terminate()
    print("\n  RESULT:", "PASS — tools execute real work" if after > before else "CHECK")


if __name__ == "__main__":
    main()
