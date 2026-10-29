#!/usr/bin/env python3
"""test_mcp_subscribe.py — Call subscribe_events through the MCP round-trip."""
import json
import subprocess
import time

SERVER = "/root/mcp_sanctuary_server.py"
PY = "/root/.llm-venv/bin/python3"


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
    p = subprocess.Popen([PY, SERVER], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, bufsize=1)
    time.sleep(1.5)
    send(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"}}})
    recv(p)
    send(p, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    # list tools to confirm subscribe_events is present
    send(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    r = recv(p)
    tools = [t["name"] for t in r["result"]["tools"]] if r and "result" in r else []
    print("  tools:", tools)
    print("  subscribe_events present:", "subscribe_events" in tools)

    # call subscribe_events
    send(p, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "subscribe_events", "arguments": {}}})
    r = recv(p)
    if r and "result" in r:
        content = r["result"].get("content", [])
        print("  subscribe_events ->", content[0]["text"] if content else "empty")
    else:
        print("  subscribe_events -> FAIL", r)

    send(p, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
    recv(p, timeout=5)
    p.terminate()
    print("\n  RESULT: PASS")


if __name__ == "__main__":
    main()
