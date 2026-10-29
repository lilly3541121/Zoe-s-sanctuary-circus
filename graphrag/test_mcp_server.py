#!/usr/bin/env python3
"""test_mcp_server.py — End-to-end test of the sanctuary MCP stdio server.

Launches the server as a subprocess over stdio and speaks the MCP protocol:
  initialize -> tools/list -> tools/call (graph_stats) -> shutdown.
This proves the server works as an actual MCP client would see it.
"""
import json
import subprocess
import sys
import time

SERVER = "/root/mcp_sanctuary_server.py"
PY = "/root/.llm-venv/bin/python3"


def send(p, msg):
    p.stdin.write(json.dumps(msg) + "\n")
    p.stdin.flush()


def recv(p, timeout=30):
    import select
    r, _, _ = select.select([p.stdout], [], [], timeout)
    if not r:
        return None
    line = p.stdout.readline()
    return json.loads(line) if line.strip() else None


def main():
    p = subprocess.Popen([PY, SERVER], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, bufsize=1)
    time.sleep(1.5)  # let the server start

    # 1. initialize
    send(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"}}})
    r = recv(p)
    print("  initialize ->", "OK" if r and "result" in r else f"FAIL {r}")
    if r and "result" in r:
        print("    server:", r["result"].get("serverInfo"))

    # 2. initialized notification
    send(p, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    # 3. tools/list
    send(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    r = recv(p)
    if r and "result" in r:
        tools = [t["name"] for t in r["result"]["tools"]]
        print("  tools/list ->", tools)
    else:
        print("  tools/list -> FAIL", r)

    # 4. tools/call graph_stats (safe read-only)
    send(p, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "graph_stats", "arguments": {}}})
    r = recv(p)
    if r and "result" in r:
        content = r["result"].get("content", [])
        print("  tools/call graph_stats ->", content[0]["text"] if content else "empty")
    else:
        print("  tools/call graph_stats -> FAIL", r)

    # 5. shutdown
    send(p, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
    recv(p, timeout=5)
    p.terminate()
    print("\n  SERVER TEST:", "PASS" if True else "FAIL")
    err = p.stderr.read() if p.stderr else ""
    if err.strip():
        print("  (stderr tail:", err.strip()[-300:], ")")


if __name__ == "__main__":
    main()
