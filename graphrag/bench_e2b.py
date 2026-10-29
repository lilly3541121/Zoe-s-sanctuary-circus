#!/usr/bin/env python3
"""Benchmark the E2B (Huihui gemma4 E2B) - short beat + longer generation."""
import json, urllib.request, time

def gen(prompt, max_tokens):
    body = json.dumps({"messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0.7}).encode()
    req = urllib.request.Request("http://localhost:8089/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    el = time.time() - t0
    text = d["choices"][0]["message"]["content"]
    words = len(text.split())
    return words, el, text

print("=== E2B short beat ===")
w, el, t = gen("Write one vivid line: a single candle in a dark room.", 60)
print(f"  {w} words in {el:.1f}s = {w/el:.2f} w/s")
print(f"  output: {t[:100]}")

print("=== E2B longer generation (105 words) ===")
w, el, t = gen("Write a vivid 100-word scene: a train station at night, a farewell.", 140)
print(f"  {w} words in {el:.1f}s = {w/el:.2f} w/s")
print(f"  output: {t[:110]}")
