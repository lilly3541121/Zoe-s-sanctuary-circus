#!/usr/bin/env python3
"""llm_extract_qwen.py - Extract entities/relations using Qwen via OpenRouter.
import os
Simple version - no json_extract in SQL, filters in Python instead."""
import json
import sqlite3
import time
import urllib.request
import sys
from pathlib import Path

GRAPH_DIR = Path('/mnt/android/hermes-workspace/state/graphrag')
STATE_DB = Path('/root/.hermes/state.db')
LLM_CACHE = GRAPH_DIR / 'llm_cache_qwen.json'
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "qwen/qwen3-coder-flash"

def call_qwen(prompt, max_tokens=400):
    """Call Qwen via OpenRouter API. Returns text or None."""
    data = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens
    }
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(data).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {OPENROUTER_KEY}'
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return result.get('choices', [{}])[0].get('message', {}).get('content', '')
    except Exception as e:
        return f"ERROR: {e}"

def parse_json_response(text):
    """Parse JSON from LLM response, with retries."""
    try:
        return json.loads(text)
    except:
        pass
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        return json.loads(text[start:end])
    except:
        return None

def extract_entities(text):
    """Extract entities and relations from text."""
    prompt = f"""Extract entities and relations from this text.

Return ONLY valid JSON in this format:
{{
  "entities": [
    {{"name": "entity_name", "type": "person|place|concept|object|event", "mention_count": 1}}
  ],
  "relations": [
    {{"source": "entity1", "target": "entity2", "type": "relationship_type", "count": 1}}
  ]
}}

Rules:
- Entities: proper nouns, important concepts, people, places, projects
- Relations: connections between entities (is_a, has, created, owns, etc.)
- Focus on meaningful entities, not common words
- If nothing meaningful, return empty lists

Text: {text}

Return JSON only:"""

    result = call_qwen(prompt, max_tokens=400)
    parsed = parse_json_response(result)
    if parsed:
        return {
            "entities": parsed.get('entities', []),
            "relations": parsed.get('relations', [])
        }
    return None

def get_chat_messages():
    """Get chat messages from state DB, filtered in Python."""
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Simple query - no json_extract
    cur.execute("""
        SELECT id, role, content, timestamp FROM messages
        WHERE role IN ('user', 'assistant')
          AND content IS NOT NULL
          AND LENGTH(content) > 20
        ORDER BY timestamp ASC
    """)
    
    all_msgs = cur.fetchall()
    conn.close()
    
    # Filter in Python
    filtered = []
    skip_patterns = [
        '[tool_call', '[tool_result', '[terminal]', '[vision_analyze]',
        '<function_calls>', '[IMPORTANT: Background', '[CONTEXT COMPACTION',
        'tool_call:', 'tool_result:', 'function_call',
        'Output:', 'Traceback (most recent call last)',
        'Files were changed', 'Orphan recovery'
    ]
    
    for row in all_msgs:
        text = row['content'][:2000]
        should_skip = any(p in text for p in skip_patterns)
        if not should_skip:
            filtered.append({
                'id': row['id'],
                'role': row['role'],
                'content': text,
                'timestamp': row['timestamp']
            })
    
    return filtered

def load_cache():
    if LLM_CACHE.exists():
        return json.loads(LLM_CACHE.read_text())
    return {}

def save_cache(cache):
    LLM_CACHE.write_text(json.dumps(cache, indent=2))

def main():
    cache = load_cache()
    print(f"Loaded cache: {len(cache)} messages", flush=True)
    
    messages = get_chat_messages()
    print(f"Total chat messages: {len(messages)}", flush=True)
    
    to_process = [m for m in messages if m['id'] not in cache]
    print(f"To process: {len(to_process)}", flush=True)
    
    if not to_process:
        print("Nothing to do.", flush=True)
        return
    
    print(f"\nStarting Qwen extraction ({len(to_process)} messages)...", flush=True)
    start_time = time.time()
    
    for i, msg in enumerate(to_process):
        if i > 0 and i % 10 == 0:
            elapsed = time.time() - start_time
            avg = elapsed / i
            remaining = avg * (len(to_process) - i)
            print(f"\n[{i}/{len(to_process)}] Elapsed: {elapsed:.0f}s, "
                  f"Remaining: {remaining:.0f}s", flush=True)
            save_cache(cache)
        
        result = extract_entities(msg['content'])
        if result:
            cache[msg['id']] = result
            ent = len(result.get('entities', []))
            rel = len(result.get('relations', []))
            print(f"[{i+1}/{len(to_process)}] {msg['role'][:3]}: {ent}E {rel}R",
                  flush=True)
        
        time.sleep(0.5)
    
    save_cache(cache)
    
    elapsed = time.time() - start_time
    total_ent = sum(len(x.get('entities', [])) for x in cache.values())
    total_rel = sum(len(x.get('relations', [])) for x in cache.values())
    
    print(f"\nDone.", flush=True)
    print(f"Extracted: {len(cache)} messages", flush=True)
    print(f"Total entities: {total_ent}", flush=True)
    print(f"Total relations: {total_rel}", flush=True)
    print(f"Time: {elapsed:.0f}s", flush=True)

if __name__ == "__main__":
    main()
