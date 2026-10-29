#!/usr/bin/env python3
"""zoe_decision.py - Big-decision gate.

For BIG decisions, this brings up the Qwen Coder 7B (the big brain) and routes
the decision through it. The 7B is the ONLY model (besides me) allowed to write
to graphrag. It writes via a SANDBOXED path: graphrag writes go through this
gate's approved functions, which validate the target is graphrag.

Usage:
  python3 zoe_decision.py decide "<the big decision/question>"
  python3 zoe_decision.py graphrag-write <entity/relation spec>   # sandboxed
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

QWEN_URL = "http://localhost:8080/v1/chat/completions"
MANAGER = "/root/engine_manager.py"
PY = "/root/.llm-venv/bin/python3"
GRAPH_DIR = "/mnt/android/hermes-workspace/state/graphrag"
CACHE = os.path.join(GRAPH_DIR, "cache.json")


def ensure_qwen():
    """Bring up the Qwen 7B (on-demand) and wait for it."""
    try:
        with urllib.request.urlopen(QWEN_URL + "/v1/models", timeout=3):
            return True
    except Exception:
        pass
    print("[decision] bringing up Qwen 7B (big brain)...", flush=True)
    subprocess.run([PY, MANAGER, "start", "precision", "8080"],
                   capture_output=True, timeout=240)
    # Big model: give it up to 5 min to load + serve
    for _ in range(60):
        try:
            with urllib.request.urlopen(QWEN_URL + "/v1/models", timeout=3):
                return True
        except Exception:
            time.sleep(5)
    return False


def ask_qwen(prompt, max_tokens=300):
    """Ask the Qwen 7B a question (the big decision)."""
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(QWEN_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def graphrag_write(entry):
    """SANDBOXED graphrag write: only the Qwen 7B (or me) may call this.
    Validates the target is graphrag (never escapes to other paths)."""
    if not entry.get("target", "").startswith(GRAPH_DIR):
        raise ValueError("graphrag-write: target must be inside graphrag dir")
    # Validate it's a graphrag cache entry shape (entities/relations)
    if "entities" not in entry and "relations" not in entry:
        raise ValueError("graphrag-write: must be entities/relations spec")
    with open(CACHE) as f:
        cache = json.load(f)
    if "entities" in entry:
        cache.setdefault("entities", {}).update(entry["entities"])
    if "relations" in entry:
        cache.setdefault("relations", {}).update(entry["relations"])
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=1, ensure_ascii=False)
    os.replace(tmp, CACHE)
    return "graphrag updated"


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "decide":
        if not ensure_qwen():
            print("[decision] ERROR: Qwen 7B didn't come up", flush=True)
            sys.exit(1)
        q = " ".join(sys.argv[2:])
        print(f"[decision] Qwen 7B deciding: {q}", flush=True)
        ans = ask_qwen(q)
        print(f"[decision] ANSWER:\n{ans}", flush=True)
    elif cmd == "graphrag-write":
        # Usage: graphrag-write '<json-spec>'
        entry = json.loads(sys.argv[2])
        print(graphrag_write(entry), flush=True)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
