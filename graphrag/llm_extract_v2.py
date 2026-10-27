#!/usr/bin/env python3
"""llm_extract_v2.py - Smart LLM extraction, filters noise, processes real chat only."""
import json
import sqlite3
import time
import urllib.request
import sys
from pathlib import Path
from datetime import datetime

GRAPH_DIR = Path('/mnt/android/hermes-workspace/state/graphrag')
CACHE_FILE = GRAPH_DIR / 'llm_cache_v2.json'
LLM_URL = "http://localhost:8080/v1/chat/completions"

# Load cache or start fresh
try:
    cache = json.loads(CACHE_FILE.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    cache = {}

print(f"Loaded cache: {len(cache)} messages")
print(f"Started: {datetime.now().isoformat()}")

def extract_entities(text, max_tokens=400):
    """Call huihui to extract entities and relations."""
    if not text or len(text) < 20:
        return None

    # Truncate long messages to save time
    text_trunc = text[:1500] if len(text) > 1500 else text

    prompt = f"""Extract entities and relationships from this text. Return ONLY valid JSON, no markdown, no explanation.

Format:
{{"entities": [{{"name": "Name", "type": "person|place|concept|object|event", "description": "brief description"}}], "relations": [{{"subject": "name1", "predicate": "verb", "object": "name2"}}]}}

Types: person, place, concept, object, event, tool, emotion, activity.
Be concise. Only extract clear entities mentioned in the text.

Text: {text_trunc}"""

    data = {
        "model": "huihui",
        "messages": [
            {"role": "system", "content": "You are an information extraction system. Return valid JSON only. No thinking tags, no explanations."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1
    }

    req = urllib.request.Request(LLM_URL, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return parse_json(content)
    except Exception as e:
        return None

def parse_json(text):
    """Parse JSON from model output, handling common issues."""
    if not text:
        return None
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON block
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass

    # Try to fix common issues
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None

def get_chat_messages():
    """Get real user+assistant chat messages, filtered for quality."""
    conn = sqlite3.connect('/root/.hermes/state.db')
    cur = conn.cursor()

    # Only user and assistant messages (skip tool outputs)
    cur.execute("""
        SELECT id, role, content, timestamp
        FROM messages
        WHERE role IN ('user', 'assistant')
          AND content IS NOT NULL
          AND length(content) > 20
          AND content NOT LIKE '%tool_call%'
          AND content NOT LIKE '%tool_result%'
          AND content NOT LIKE '%[IMPORTANT:%'
          ORDER BY timestamp ASC
    """)

    messages = []
    for row in cur.fetchall():
        mid, role, content, created = row
        # Skip very short messages
        if len(content) < 30:
            continue
        # Skip internal markers
        if "[IMPORTANT:" in content or "[Context from" in content:
            continue
        messages.append({
            "id": str(mid),
            "role": role,
            "content": content,
            "timestamp": created
        })

    conn.close()
    return messages

print("\nLoading chat messages...")
messages = get_chat_messages()
print(f"Found {len(messages)} chat messages")

# Filter out already processed
to_process = [m for m in messages if m["id"] not in cache]
print(f"To process: {len(to_process)} messages")
print(f"Already processed: {len(cache)}")

if not to_process:
    print("Nothing to do.")
    sys.exit(0)

# Process each message
for i, msg in enumerate(to_process, 1):
    mid = msg["id"]
    role = msg["role"]
    content = msg["content"]
    created = msg["timestamp"]

    print(f"[{i}/{len(to_process)}] {mid[:20]}... ({role}, {len(content)} chars)")

    result = extract_entities(content)

    if result:
        cache[mid] = {
            "role": role,
            "content_preview": content[:200],
            "timestamp": created,
            "entities": result.get("entities", []),
            "relations": result.get("relations", [])
        }
        print(f"  -> {len(result.get('entities', []))} entities, {len(result.get('relations', []))} relations")
    else:
        cache[mid] = {
            "role": role,
            "content_preview": content[:200],
            "timestamp": created,
            "entities": [],
            "relations": []
        }
        print(f"  -> extraction failed")

    # Save cache every 10 messages
    if i % 10 == 0:
        CACHE_FILE.write_text(json.dumps(cache, indent=2))
        print(f"  [cache saved at message {i}]")

    time.sleep(0.5)  # Be nice to the CPU

# Final save
CACHE_FILE.write_text(json.dumps(cache, indent=2))
print(f"\nDone. Extracted {len(cache)} messages total.")
print(f"Saved to {CACHE_FILE}")

# Stats
total_entities = sum(len(x.get("entities", [])) for x in cache.values())
total_relations = sum(len(x.get("relations", [])) for x in cache.values())
print(f"Total entities: {total_entities}")
print(f"Total relations: {total_relations}")
