#!/usr/bin/env python3
"""procedural.py — TIER 3: Procedural Graph (How She Works).

Extracts high-performance workflows into reusable "Recipe" nodes (exact command
sequences) for autonomous reuse. Before executing new tasks, query the procedural
graph for the optimal Recipe node.

Schema matches graphrag cache format:
  entities: {name: {type, count, messages, aliases}}
  relations: [{a, b, weight, kind}]   (kind = "procedural-<pred>")

Design: append-safe, delta-based. Recipes are the WORKING paths only (validated
by tests). Never stores a broken path.
"""
import json
import os
from datetime import datetime

GRAPH_DIR = os.environ.get(
    "GRAPH_DIR", "/mnt/android/hermes-workspace/state/graphrag"
)
CACHE = os.path.join(GRAPH_DIR, "cache.json")
RECIPE_LOG = os.path.join(GRAPH_DIR, "procedural_recipes.json")  # recipe registry
SRC_TAG = "src-procedural"

# The proven, TESTED workflows (the working paths only)
DEFAULT_RECIPES = [
    {
        "name": "recipe_embody_card_v3",
        "description": "Embody a character card with Gemma2 9B (clean v3 prompt, no scene markers). Best output verified.",
        "command": "/root/.llm-venv/bin/python3 /root/embody_card.py <card> <name> <maxtok>",
        "engine": "gemma2-9b-sweetspot",
        "verified": True,
        "tokens_avg": 550,
    },
    {
        "name": "recipe_extract_cards_chunked",
        "description": "Extract entities+relations from LONG cards via 1200-char chunks. Reliable for 7-14k char cards.",
        "command": "/root/.llm-venv/bin/python3 /root/extract_cards_chunked.py",
        "engine": "qwen-coder-7b",
        "verified": True,
        "tokens_avg": 400,
    },
    {
        "name": "recipe_qwen_restart",
        "description": "Recover a wedged Qwen 8080 (returns 5s timeout, no response). Kill port, restart engine.",
        "command": "fuser -k 8080/tcp && /root/.llm-venv/bin/python3 /root/engine.py start qwen 8080",
        "engine": "qwen-coder-7b",
        "verified": True,
        "tokens_avg": 0,
    },
    {
        "name": "recipe_wifi_push",
        "description": "Wi-Fi-gated git push with PAT from 600-perm env (URL form, token never echoed).",
        "command": "set -a; . /root/.hermes/graphrag_token.env; set +a; git push https://${GH_TOKEN}@github.com/lilly3541121/Zoe-s-sanctuary-circus.git main",
        "engine": "git",
        "verified": True,
        "tokens_avg": 0,
    },
]


def load_cache():
    try:
        with open(CACHE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"entities": {}, "relations": [], "messages_index": {}, "built_at": None}


def save_cache(cache):
    with open(CACHE, "w") as f:
        json.dump(cache, f, indent=2)


def load_recipes():
    if os.path.exists(RECIPE_LOG):
        try:
            return json.load(open(RECIPE_LOG))
        except json.JSONDecodeError:
            pass
    return list(DEFAULT_RECIPES)


def save_recipes(recipes):
    json.dump(recipes, open(RECIPE_LOG, "w"), indent=2)


def register_recipe(recipe):
    """Add or update a recipe (by name). Only stores the recipe if verified."""
    if not recipe.get("verified"):
        raise ValueError("refusing to store unverified recipe (broken path)")
    recipes = load_recipes()
    for i, r in enumerate(recipes):
        if r["name"] == recipe["name"]:
            recipes[i] = recipe
            save_recipes(recipes)
            return
    recipes.append(recipe)
    save_recipes(recipes)


def sync_to_graph(recipes=None):
    """Sync recipes into the graph as Recipe nodes + edges."""
    if recipes is None:
        recipes = load_recipes()
    cache = load_cache()
    ents = cache.setdefault("entities", {})
    rels = cache.setdefault("relations", [])

    existing = set()
    for r in rels:
        if str(r.get("kind", "")).startswith("procedural-"):
            existing.add((r.get("a"), r.get("b"), r.get("kind")))

    added_e = added_r = 0
    for rec in recipes:
        name = rec["name"]
        key = name.lower()
        if key not in ents:
            ents[key] = {
                "type": "recipe",
                "count": 1,
                "messages": [SRC_TAG],
                "aliases": [rec.get("engine", "unknown")],
            }
            added_e += 1
        # Recipe -[OPTIMIZES]-> engine edge
        engine = rec.get("engine", "").lower()
        if engine:
            rel_key = (key, engine, "procedural-optimizes")
            if rel_key not in existing:
                rels.append({
                    "a": key, "b": engine,
                    "weight": 5, "kind": "procedural-optimizes",
                })
                existing.add(rel_key)
                added_r += 1

    save_cache(cache)
    return added_e, added_r


def query_best_recipe(task, engine=None):
    """Query the procedural graph for the optimal recipe for a task.

    Returns the best matching recipe (by task keyword in description/name).
    """
    recipes = load_recipes()
    task_l = task.lower()
    best = None
    best_score = 0
    for rec in recipes:
        score = 0
        hay = (rec.get("name", "") + " " + rec.get("description", "")).lower()
        for word in task_l.split():
            if word in hay:
                score += 1
        if engine and rec.get("engine") == engine:
            score += 2
        if score > best_score:
            best_score = score
            best = rec
    return best


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        recipes = load_recipes()
        print(f"recipes: {len(recipes)}")
        for r in recipes:
            print(f"  {r['name']}  [{'verified' if r.get('verified') else 'UNVERIFIED'}] {r.get('engine','')}")
    elif cmd == "sync":
        e, r = sync_to_graph()
        print(f"synced: +{e} recipe entities, +{r} optimizes edges")
    elif cmd == "query":
        task = sys.argv[2]
        best = query_best_recipe(task)
        if best:
            print(f"BEST RECIPE for '{task}': {best['name']}")
            print(f"  command: {best['command']}")
        else:
            print(f"no recipe found for '{task}'")
