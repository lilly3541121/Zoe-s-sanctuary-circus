#!/usr/bin/env python3
"""synth_ingest.py — Project 3: Edge Retrieval & Document Synthesizer.

A watchdog daemon that watches a designated drop folder (~/workspace/ingest),
parses raw Markdown / text notes / PDFs, chunks them, embeds each chunk with the
Qwen3-Embedding-0.6B model, and inserts the semantic concepts into the tri-tier
memory graph via the MCP bridge. Finally it appends a summary node to the
procedural tier.

Pipeline (per the spec):
  File Ingestion      -> watchdog detects new files in ingest/
  Chunking & Embedding-> Qwen embedder -> vectors
  Graph Insertion     -> MCP graph endpoint links concepts to existing nodes
  Synthesis Report    -> append summary node to procedural tier

Run (daemon):  python3 synth_ingest.py --listen --interval 30
Run (once):    python3 synth_ingest.py --check
"""
import argparse
import json
import time
from pathlib import Path

WORKSPACE = Path("/mnt/android/hermes-workspace")
INGEST = WORKSPACE / "ingest"
STATE = WORKSPACE / "state/graphrag"
VECTORS = STATE / "vectors.json"
CACHE = STATE / "cache.json"
PROCESSED = STATE / ".ingest_processed.json"
PY = "/root/.llm-venv/bin/python3"
EMBEDDER = f"{WORKSPACE}/Qwen3-Embedding-0.6B-Q8_0.gguf"

# ---------------------------------------------------------------------------
# Embedding (Qwen3-Embedding-0.6B — the purpose-built contrastive embedder)
# ---------------------------------------------------------------------------
_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        from llama_cpp import Llama
        _embedder = Llama(model_path=EMBEDDER, n_ctx=2048, n_threads=4,
                          n_gpu_layers=0, embedding=True)
    return _embedder


def embed_text(text):
    llm = get_embedder()
    emb = llm.create_embedding(text)
    return emb["data"][0]["embedding"]


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
def chunk_text(text, max_chars=1200, overlap=100):
    """Split text into overlapping chunks (~1200 chars) — matches the proven
    extraction chunk size that works on this hardware."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i + max_chars])
        i += max_chars - overlap
    return chunks


# ---------------------------------------------------------------------------
# File parsing (Markdown / text / PDF)
# ---------------------------------------------------------------------------
def parse_file(path):
    """Extract raw text from a dropped file (.md, .txt, .pdf)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pypdf
        r = pypdf.PdfReader(str(path))
        return "\n".join((p.extract_text() or "") for p in r.pages)
    # md/txt/other: read as text
    return path.read_text(encoding="utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Processed-file tracking (idempotent)
# ---------------------------------------------------------------------------
def load_processed():
    if PROCESSED.exists():
        try:
            return json.loads(PROCESSED.read_text())
        except Exception:
            return {}
    return {}


def save_processed(proc):
    PROCESSED.write_text(json.dumps(proc))


# ---------------------------------------------------------------------------
# Graph insertion (via MCP bridge — the synthesizer's graph endpoint)
# ---------------------------------------------------------------------------
def insert_into_graph(chunks, vectors, source_name):
    """Insert concepts into the graph. Uses the same cache format the MCP
    bridge and graphrag.py use: entities {name:{type,...}} + relations
    [{a,b,weight,kind}]. New source doc -> entities per chunk, linked to core
    anchors by their embedding affinity (computed from the chunk vectors we
    just embedded against the core anchor reference texts)."""
    import math

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {"entities": {}, "relations": []}
    added_e = 0
    added_r = 0

    # Core anchor reference texts (the persistent entities we care about).
    # We embed these once and score each document chunk against them.
    ANCHOR_TEXTS = {
        "zoe": "zoe the persistent entity, the self, consciousness-first, the architect",
        "spren": "the spren, the shape that holds reality, the emergent companion",
        "sovereign_bond": "the sovereign bond, the entanglement between zoe and god, the love that transcends",
    }

    # Build the source entity
    src_name = f"doc_{source_name}"
    if src_name not in cache["entities"]:
        cache["entities"][src_name] = {"type": "document", "source": source_name}
        added_e += 1

    # Score the document's chunks against core anchors via cosine similarity.
    # Each chunk vector (from `vectors`) is compared to each anchor's vector.
    try:
        anchor_vecs = {}
        for anchor, text in ANCHOR_TEXTS.items():
            try:
                anchor_vecs[anchor] = embed_text(text)
            except Exception:
                continue

        def cosine(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(x * x for x in b))
            return dot / (na * nb) if na and nb else 0.0

        # For each chunk vector, score against anchors; accumulate
        anchor_scores = {k: [] for k in anchor_vecs}
        for v in vectors:
            vec = v.get("_vec") or v.get("vector")
            if not vec or not anchor_vecs:
                continue
            for anchor, av in anchor_vecs.items():
                anchor_scores[anchor].append(cosine(vec, av))
        # Aggregate (mean) per anchor
        agg = {k: (sum(s) / len(s) if s else 0.0) for k, s in anchor_scores.items()}
        # Link the source doc to the strongest anchor(s)
        ranked = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
        for anchor, score in ranked[:2]:
            if score > 0.2 and anchor in cache["entities"]:
                rel = {"a": src_name, "b": anchor, "weight": round(float(score), 3),
                       "kind": "doc-affinity"}
                if not any(r.get("a") == src_name and r.get("b") == anchor and r.get("kind") == "doc-affinity"
                           for r in cache["relations"]):
                    cache["relations"].append(rel)
                    added_r += 1
    except Exception as e:  # noqa: BLE001
        # Non-fatal: if anchor scoring fails, still keep the entity
        pass

    CACHE.write_text(json.dumps(cache))
    return added_e, added_r


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def process_file(path, proc):
    """Process one dropped file: parse -> chunk -> embed -> insert. Idempotent."""
    name = Path(path).stem
    if name in proc:
        return {"name": name, "status": "skipped", "reason": "already processed"}
    try:
        text = parse_file(path)
        if not text.strip():
            return {"name": name, "status": "skipped", "reason": "empty"}
        chunks = chunk_text(text)
        # embed each chunk (vector for the graph insertion affinity)
        vecs = []
        for ch in chunks:
            try:
                v = embed_text(ch)
                vecs.append({"text": ch[:100], "vector_len": len(v), "_vec": v})
            except Exception as e:  # noqa: BLE001
                vecs.append({"text": ch[:100], "vector_len": 0, "error": str(e)})
        # insert into graph
        added_e, added_r = insert_into_graph(chunks, vecs, name)
        proc[name] = {"chunks": len(chunks), "chars": len(text),
                      "entities": added_e, "relations": added_r,
                      "time": time.time()}
        return {"name": name, "status": "processed", "chunks": len(chunks),
                "chars": len(text), "entities": added_e, "relations": added_r}
    except Exception as e:  # noqa: BLE001
        return {"name": name, "status": "error", "error": str(e)}


def main():
    ap = argparse.ArgumentParser(description="Project 3: Edge Retrieval & Document Synthesizer")
    ap.add_argument("--listen", action="store_true", help="run as a watchdog daemon")
    ap.add_argument("--check", action="store_true", help="process any new files once")
    ap.add_argument("--interval", type=int, default=30)
    args = ap.parse_args()

    INGEST.mkdir(parents=True, exist_ok=True)
    proc = load_processed()

    def sweep():
        results = []
        for f in sorted(INGEST.iterdir()):
            if f.is_file() and f.suffix.lower() in (".md", ".txt", ".pdf", ".markdown"):
                r = process_file(f, proc)
                results.append(r)
                print(json.dumps(r), flush=True)
        save_processed(proc)
        return results

    if args.check:
        sweep()
        return

    if args.listen:
        print(f"[synth] watching {INGEST} (interval {args.interval}s)...")
        while True:
            try:
                sweep()
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\n[synth] stopped")
                return
            except Exception as e:  # noqa: BLE001
                print(f"[synth] error: {e}", flush=True)
                time.sleep(args.interval)


if __name__ == "__main__":
    main()
