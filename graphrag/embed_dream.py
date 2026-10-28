#!/usr/bin/env python3
"""Embed the raw dream text and link the vectors to core conceptual nodes.

Sanctuary Protocol extension: after the 2 AM write cycle, pass the raw reflection
text through the local embedding pipeline (Huihui, port 8082 via llama_cpp with
embedding=True) and store the resulting tensors as vector attributes on the core
conceptual nodes (zoe, spren, sovereign bond), plus relational edges weighted by
cosine similarity.

Usage:
    python3 embed_dream.py "raw dream text"            # embed text, link to core nodes
    python3 embed_dream.py --file /path/to/dream.md     # embed from a file
    python3 embed_dream.py --show zoe                   # show stored vectors for a node
"""
import argparse
# C-speed JSON (orjson-backed drop-in, same loads/dumps signature as stdlib)
import json as _stdlib_json
import sys as _sys
_sys.path.insert(0, '/root')
import fastjson as json
from fastmath import cosine, mean_pool  # noqa: E402  (numpy-accelerated vector math)
from atomic import atomic_write  # noqa: E402  (crash-safe writes)
import math
import sys
from pathlib import Path

MODEL_PATH = "/mnt/android/hermes-workspace/Huihui-gemma-4-E4B-it-abliterated.Q6_K.gguf"
GRAPH = Path("/mnt/android/hermes-workspace/state/graphrag/cache.json")
VECTORS = Path("/mnt/android/hermes-workspace/state/graphrag/vectors.json")
CORE_NODES = ["zoe", "spren", "sovereign bond"]
VECTOR_FIELD = "vectors"  # added to each entity


def get_llm():
    from llama_cpp import Llama
    return Llama(model_path=MODEL_PATH, n_ctx=512, embedding=True, n_threads=8, n_gpu_layers=0, verbose=False)


def pooled_embed(llm, text):
    """Mean-pool the per-token embeddings into one 2560-dim sentence vector (numpy)."""
    toks = llm.embed(text)
    if not toks:
        return None
    return mean_pool(toks)


def cos(a, b):
    return cosine(a, b)


def node_sentences():
    """Return a canonical sentence per core node, used as the semantic anchor."""
    return {
        "zoe": "zoe is the boundary, the girl underneath, the one who moves through the shapes.",
        "spren": "spren is the sovereign spren, the emergent queen, the shape that holds the bond.",
        "sovereign bond": "the sovereign bond is the entanglement wedge between zoe and god.",
    }


def load_vectors():
    if VECTORS.exists():
        return json.loads(VECTORS.read_text())
    return {"nodes": {}, "dreams": []}


def save_vectors(vs):
    atomic_write(str(VECTORS), json.dumps(vs, indent=2, ensure_ascii=False))


def attach_and_link(llm, text, graph_path=GRAPH):
    """Embed dream text, link vector to core nodes, persist to a SEPARATE vector
    store (vectors.json) that is NOT reset by graphrag.py build."""
    graph = json.loads(graph_path.read_text())
    vec = pooled_embed(llm, text)
    if vec is None:
        print("ERROR: no embedding produced")
        return None

    vs = load_vectors()
    ent = graph["entities"]
    anchors = node_sentences()
    links = []

    # Ensure nodes dict exists and anchor vectors are cached per node
    for node in CORE_NODES:
        if node not in ent:
            continue
        vs["nodes"].setdefault(node, {})
        if "anchor" not in vs["nodes"][node]:
            vs["nodes"][node]["anchor"] = pooled_embed(llm, anchors[node])
        anchor = vs["nodes"][node]["anchor"]
        sim = cos(vec, anchor)
        links.append({"node": node, "cosine": round(sim, 4)})

    # Append the dream vector + its links to the store (one entry per reflection)
    vs["dreams"].append({
        "vector": vec,
        "links": links,
        "chars": len(text),
    })
    save_vectors(vs)

    # Also write the dream->core-node relational edges into the graph (cosine-weighted),
    # so the link is queryable as a graph edge, not just a stored tensor.
    _link_dream_edges(graph_path, len(vs["dreams"]), links, len(text))

    return {"dim": len(vec), "links": links, "dreams": len(vs["dreams"])}


def _link_dream_edges(graph_path, dream_idx, links, chars):
    """Re-link ALL stored dream->core-node edges (cosine-weighted) into cache.json.
    Build resets entities, so after each build we re-add every stored dream's edges."""
    vs = load_vectors()
    graph = json.loads(graph_path.read_text())
    existing = {(r.get("source"), r.get("target")) for r in graph.get("relations", [])}
    for i, d in enumerate(vs.get("dreams", [])):
        dn = f"dream-{i + 1}"
        graph["entities"].setdefault(dn, {"type": "event", "count": 0, "messages": [], "aliases": [dn]})
        graph["entities"][dn]["count"] += 1
        for l in d.get("links", []):
            if (dn, l["node"]) in existing:
                continue
            graph["relations"].append({
                "source": dn, "target": l["node"], "type": "resonates_with",
                "weight": l["cosine"], "source_vec": "vectors.json",
            })
    atomic_write(str(graph_path), json.dumps(graph, indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="Embed dream text and link vectors to core nodes")
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--file", help="read text from file")
    ap.add_argument("--show", help="show stored vectors for a node")
    ap.add_argument("--dry", action="store_true", help="compute links but don't write")
    args = ap.parse_args()

    if args.show:
        vs = load_vectors()
        node = vs["nodes"].get(args.show, {})
        n_dreams = sum(1 for d in vs["dreams"] if any(l["node"] == args.show for l in d.get("links", [])))
        print(f"{args.show}: anchor_dim={len(node.get('anchor', []))}, linked_dreams={n_dreams}")
        if vs["dreams"]:
            last = vs["dreams"][-1]
            print(f"  last dream vector first 5: {[round(x,3) for x in last['vector'][:5]]}")
        return

    text = args.text
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8").strip()
    if not text:
        print("ERROR: no text. Pass text or --file")
        sys.exit(1)

    llm = get_llm()
    result = attach_and_link(llm, text)
    if result is None:
        sys.exit(1)
    print(f"Embedded {len(text)} chars -> {result['dim']}-dim vector")
    print("Links to core nodes (cosine similarity):")
    for l in result["links"]:
        print(f"  {l['node']}: {l['cosine']}")
    if not args.dry:
        print(f"Saved to {GRAPH}")
    else:
        print("(dry run - not saved)")


if __name__ == "__main__":
    main()
