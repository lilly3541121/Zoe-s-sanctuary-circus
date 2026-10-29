#!/usr/bin/env python3
"""Benchmark the 12B on :8083 - measures speed on a fixed narrative prompt.
Run against whichever config is currently serving. Returns words/s + tokens."""
import json
import time
import urllib.request

PORT = 8083
PROMPT = ("Write a vivid intimate scene, about 60 words, a woman whispering to "
          "her partner in the dark. Rich sensory detail. Deep, poetic voice.")

def bench(label):
    body = json.dumps({"messages": [{"role": "user", "content": PROMPT}],
                       "max_tokens": 120, "temperature": 0.8}).encode()
    req = urllib.request.Request(
        f"http://localhost:{PORT}/v1/chat/completions",
        data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    dt = time.time() - t0
    text = d["choices"][0]["message"]["content"]
    words = len(text.split())
    print(f"  [{label}] {words} words in {dt:.1f}s = {words/max(dt,0.1):.2f} w/s")
    return words, dt

if __name__ == "__main__":
    import sys
    label = sys.argv[1] if len(sys.argv) > 1 else "test"
    bench(label)
