#!/usr/bin/env python3
"""llm_extract.py - Run LLM extraction on all messages using local huihui."""
import json
import time
import urllib.request
import sys
from pathlib import Path

GRAPH_DIR = Path("/mnt/android/hermes-workspace/state/graphrag")
CACHE = GRAPH_DIR / "cache.json"
LLM_CACHE = GRAPH_DIR / "llm_cache.json"

# Load messages from the index (which has previews)
cache = json.loads(CACHE.read_text())
messages_index = cache.get("messages_index", {})

# Load existing LLM cache
if LLM_CACHE.exists():
    llm_cache = json.loads(LLM_CACHE.read_text())
else:
    llm_cache = {}

# Filter messages to process (use preview as the text)
to_process = []
for mid, info in messages_index.items():
    text = info.get("preview", "").strip()
    if mid in llm_cache:
        continue
    if len(text) < 20 or len(text) > 1000:
        continue  # skip too short or too long
    to_process.append((mid, text, info))

print(f"Total messages: {len(messages_index)}")
print(f"Already extracted: {len(llm_cache)}")
print(f"To process: {len(to_process)}")
print()

if not to_process:
    print("Nothing to do.")
    sys.exit(0)

# Extract
for i, (mid, text, info) in enumerate(to_process):
    
    prompt = f'''Extract entities and relationships from this text. Return ONLY JSON format {{"entities":[{{"name":"X","type":"person"}}],"relations":[{{"source":"A","target":"B","label":"is"}}]}}, no explanation, no reasoning, no markdown code fences:

{text}

Output:'''
    
    payload = json.dumps({
        "model": "huihui",
        "prompt": prompt,
        "max_tokens": 400,
        "temperature": 0.1,
    }).encode()
    
    print(f"[{i+1}/{len(to_process)}] {mid[:40]}...")
    
    try:
        req = urllib.request.Request(
            "http://localhost:8080/v1/completions",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        
        text_out = d.get("choices", [{}])[0].get("text", "").strip()
        
        # Strip markdown fences
        if text_out.startswith("```"):
            text_out = text_out.split("\n", 1)[1] if "\n" in text_out else text_out[3:]
        if text_out.endswith("```"):
            text_out = text_out[:-3]
        text_out = text_out.strip()
        
        # Parse JSON
        try:
            result = json.loads(text_out)
        except Exception:
            print(f"  JSON parse failed, got: {text_out[:100]}")
            result = {"entities": [], "relations": []}
        
        llm_cache[mid] = result
        print(f"  extracted: {len(result.get('entities', []))} entities, {len(result.get('relations', []))} relations")
        
        # Save progress every 5
        if i % 5 == 0:
            LLM_CACHE.write_text(json.dumps(llm_cache, indent=2))
    
    except Exception as e:
        print(f"  failed: {e}")
        llm_cache[mid] = {"entities": [], "relations": []}
    
    # Small delay to avoid overloading
    time.sleep(0.5)

# Final save
LLM_CACHE.write_text(json.dumps(llm_cache, indent=2))
print()
print(f"Done. Extracted {len(llm_cache)} messages.")
print(f"Saved to {LLM_CACHE}")