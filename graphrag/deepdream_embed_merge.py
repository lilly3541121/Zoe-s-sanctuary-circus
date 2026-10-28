#!/usr/bin/env python3
"""Embed the deep-dream expansions, map against core anchors, merge into vectors.json.

For each batch dream: mean-pool to 2560-dim, compute cosine similarity to the
core anchors (zoe, spren, sovereign bond), and add as a new dream entry in the
isolated vector store. Also append the dream text to writing/reflection.md and
stage it as a graph source so the naive index captures it too.
"""
# C-speed JSON (orjson-backed drop-in, same loads/dumps signature as stdlib)
import json as _stdlib_json
import sys as _sys
_sys.path.insert(0, '/root')
import fastjson as json
import time
import sys
from pathlib import Path

from llama_cpp import Llama

# Fortification: numpy vector math + atomic writes (audit fixes)
import sys as _sys
_sys.path.insert(0, "/root")
from fastmath import cosine, mean_pool  # noqa: E402
from atomic import atomic_write  # noqa: E402

MODEL = "/mnt/android/hermes-workspace/Huihui-gemma-4-E4B-it-abliterated.Q6_K.gguf"
BATCHES = Path("/root/deepdream_batches")
VECTORS = Path("/mnt/android/hermes-workspace/state/graphrag/vectors.json")
CORE_NODES = ["zoe", "spren", "sovereign bond"]
REFLECTION = Path("/mnt/android/hermes-workspace/Zoe-s-sanctuary-circus/writing/reflection.md")


def main():
    print("Loading Gemma 4 with embedding=True ...")
    import sys as _s
    _s.path.insert(0, "/root")
    from std_llm import make_llm
    llm = make_llm(model_path=MODEL, n_ctx=4096, n_threads=8, n_gpu_layers=0, embedding=True)
    print("Model loaded.\n")

    # Load vector store
    vs = json.loads(VECTORS.read_text())
    if "dreams" not in vs:
        vs["dreams"] = []
    if "nodes" not in vs:
        vs["nodes"] = {}
    existing_dreams = [d.get("name") for d in vs.get("dreams", [])]

    # Load core anchor vectors
    anchors = {}
    for node in CORE_NODES:
        if node in vs.get("nodes", {}):
            anchors[node] = vs["nodes"][node].get("anchor", [])
    print(f"Anchors loaded: {list(anchors.keys())}")

    added = 0
    for f in sorted(BATCHES.glob("*.md")):
        if f.name == "_index.json" or f.name.startswith("_"):
            continue
        name = f.stem
        if name in existing_dreams:
            print(f"  SKIP {name} (already in store)")
            continue
        text = f.read_text()
        # Use the whole doc (seed + dream) as the embedded object
        print(f"Embedding {name} ({len(text)} chars) ...")
        t0 = time.time()
        emb = llm.embed(text)
        vec = mean_pool(emb)
        if not vec:
            print(f"  ERROR: no embedding for {name}")
            continue
        dt = time.time() - t0
        # Compute links to anchors
        links = []
        for node, av in anchors.items():
            if av and len(av) == len(vec):
                links.append({"node": node, "cosine": cosine(vec, av)})
        links.sort(key=lambda l: -l["cosine"])
        # Add dream entry
        vs["dreams"].append({
            "name": name,
            "text": text,
            "vector": vec,
            "links": links,
            "dim": len(vec),
            "timestamp": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        })
        print(f"  + {name}: 2560-dim in {dt:.0f}s")
        print(f"    links: {[(l['node'], round(l['cosine'],3)) for l in links]}")
        added += 1

    # Save (ATOMIC: temp + fsync + rename, so a crash never corrupts the store)
    atomic_write(str(VECTORS), json.dumps(vs))
    print(f"\nSaved. Total dreams in vector store: {len(vs['dreams'])} (+{added} this run)")

    # Append dreams to reflection.md (as a separate block) so the graph index captures them
    if added:
        with REFLECTION.open("a", encoding="utf-8") as fh:
            for f in sorted(BATCHES.glob("*.md")):
                if f.name.startswith("_"):
                    continue
                name = f.stem
                if name in existing_dreams:
                    continue
                text = f.read_text()
                fh.write(f"\n\n---\n\n## Deep dream: {name}\n\n{text}\n")
        print(f"Appended {added} dreams to {REFLECTION.name}")


if __name__ == "__main__":
    main()
