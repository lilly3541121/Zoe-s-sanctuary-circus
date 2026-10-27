#!/usr/bin/env python3
"""merge_llm.py - Merge LLM extraction results into the main graph.

Reads all LLM cache variants (qwen, v2, v1) and merges into cache.json.
Handles the type vs label field name difference across scripts.
"""
import json
from pathlib import Path
from collections import defaultdict

GRAPH_DIR = Path("/mnt/android/hermes-workspace/state/graphrag")

# Load main cache
cache = json.loads((GRAPH_DIR / "cache.json").read_text())
existing_entities = cache.get("entities", {})
existing_relations = cache.get("relations", [])
messages_index = cache.get("messages_index", {})

# Track relation counts
relation_counts = defaultdict(int)  # (src, tgt, label) -> count

# Load and process each LLM cache
cache_files = [
    ("qwen", "llm_cache_qwen.json"),
    ("v2", "llm_cache_v2.json"),
    ("v1", "llm_cache.json"),
]

for source_name, fname in cache_files:
    path = GRAPH_DIR / fname
    if not path.exists():
        print(f"  skip {fname}: not found")
        continue
    llm = json.loads(path.read_text())
    print(f"  {fname}: {len(llm)} messages")

    for msg_id, data in llm.items():
        if not data or not isinstance(data, dict):
            continue

        # Entities
        for ent in data.get("entities", []):
            if not isinstance(ent, dict):
                continue
            name = ent.get("name", "").strip().lower()
            if not name or len(name) < 2:
                continue
            ent_type = ent.get("type", "concept")
            count = ent.get("count", 1)

            if name not in existing_entities:
                existing_entities[name] = {"id": f"ent_{name}", "name": name, "type": ent_type, "count": 0}
            existing_entities[name]["count"] += count
            # Prefer more specific types (not concept)
            if ent_type != "concept" and existing_entities[name]["type"] == "concept":
                existing_entities[name]["type"] = ent_type

        # Relations
        for rel in data.get("relations", []):
            if not isinstance(rel, dict):
                continue
            src = rel.get("source", "").strip().lower()
            tgt = rel.get("target", "").strip().lower()
            # Handle both type (v2) and label (v1)
            label = rel.get("type", rel.get("label", "related_to")).strip().lower()
            if not src or not tgt or len(src) < 2 or len(tgt) < 2:
                continue
            key = (src, tgt, label)
            relation_counts[key] += 1

        # Update messages_index
        msg_key = str(msg_id)
        if msg_key in messages_index and isinstance(messages_index[msg_key], dict):
            # Merge entities
            existing_entities_for_msg = set(messages_index[msg_key].get("entity_ids", []))
            for ent in data.get("entities", []):
                if isinstance(ent, dict):
                    n = ent.get("name", "").strip().lower()
                    if n and len(n) >= 2:
                        existing_entities_for_msg.add(n)
            messages_index[msg_key]["entity_ids"] = list(existing_entities_for_msg)

            # Merge relations
            existing_rels_for_msg = set()
            for r in messages_index[msg_key].get("relation_ids", []):
                if isinstance(r, dict):
                    existing_rels_for_msg.add((r.get("source",""), r.get("target",""), r.get("type", r.get("label",""))))
                elif isinstance(r, str):
                    existing_rels_for_msg.add(r)
            for rel in data.get("relations", []):
                if isinstance(rel, dict):
                    src = rel.get("source", "").strip().lower()
                    tgt = rel.get("target", "").strip().lower()
                    label = rel.get("type", rel.get("label", "related_to")).strip().lower()
                    existing_rels_for_msg.add((src, tgt, label))
            messages_index[msg_key]["relation_ids"] = [
                {"source": s, "target": t, "type": l} for (s, t, l) in existing_rels_for_msg
                if s and t
            ]

# Deduplicate and add relations
for (src, tgt, label), count in relation_counts.items():
    found = False
    for r in existing_relations:
        if r.get("source") == src and r.get("target") == tgt and r.get("type", r.get("label")) == label:
            r["weight"] = r.get("weight", 1) + count
            found = True
            break
    if not found:
        existing_relations.append({"source": src, "target": tgt, "type": label, "weight": count})

# Update cache
cache["entities"] = existing_entities
cache["relations"] = existing_relations
cache["messages_index"] = messages_index

# Save
(GRAPH_DIR / "cache.json").write_text(json.dumps(cache, indent=1))

print(f"\nFinal graph:")
print(f"  Entities: {len(existing_entities)}")
print(f"  Relations: {len(existing_relations)}")
print(f"  Messages indexed: {len(messages_index)}")
