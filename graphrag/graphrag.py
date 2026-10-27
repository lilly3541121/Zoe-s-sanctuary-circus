#!/usr/bin/env python3
"""graphrag.py - our little knowledge graph.

No deps beyond stdlib + urllib (for optional LLM extraction).

Commands:
  build    [--source {hermes,memory,vault,sources,all}]  # read sources, build graph
  naive    [--source ...]          # alias of build (regex extraction, no LLM)
  query    "text" [--k N]          # keyword + neighbor search
  entities [--top N]               # list entities by frequency
  relations [--top N]              # list relations by frequency
  stats                            # graph stats
  prune                            # drop index entries whose source vanished

Storage: $GRAPH_DIR (default /mnt/android/hermes-workspace/state/graphrag/)
  - cache.json         - entities + relations + messages_index
  - cache_meta.json    - last build timestamp
  - extraction.log     - history of LLM extraction calls
  - sources/           - your own .txt documents

The graph is a plain dict-of-dicts. no SQL, no fancy db.
queries are string matches + neighbor lookup.
"""
import os, sys, re, json, time, sqlite3, hashlib, argparse, urllib.request, urllib.error
from pathlib import Path
from collections import Counter, defaultdict

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
STATE_DB = HERMES_HOME / "state.db"
MEMORIES = HERMES_HOME / "memories"
VAULT = HERMES_HOME / "vault" / "entries"

# GRAPH_DIR defaults to $HERMES_HOME/graphrag (per README); explicit override wins.
GRAPH_DIR = Path(os.environ.get("GRAPH_DIR", str(HERMES_HOME / "graphrag")))
GRAPH_DIR.mkdir(parents=True, exist_ok=True)
CACHE = GRAPH_DIR / "cache.json"
META = GRAPH_DIR / "cache_meta.json"
LOG = GRAPH_DIR / "extraction.log"


# ---------------------------------------------------------------- helpers
def _columns(con, table):
    """Introspect column names so we work on any Hermes schema (no hardcoding)."""
    try:
        return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    except Exception:
        return []


def _has(con, table, col):
    return col in _columns(con, table)


def _load_db_messages():
    """Read user+assistant rows from state.db, adapting to whatever columns exist.

    The README/tests promise: no `WHERE active=1` hardcode (some schemas lack the
    column), message ids keyed on the real row id, and tool rows skipped.
    """
    if not STATE_DB.exists():
        return []
    con = sqlite3.connect(str(STATE_DB))
    con.row_factory = sqlite3.Row
    cols = _columns(con, "messages")
    if not cols:
        con.close()
        return []

    select = [c for c in ("id", "session_id", "role", "content", "timestamp") if c in cols]
    if "role" not in select or "content" not in select:
        con.close()
        return []

    sql = "SELECT " + ", ".join(select) + " FROM messages"
    where = []
    if "active" in cols:
        where.append("active=1")
    if where:
        sql += " WHERE " + " AND ".join(where)
    if "timestamp" in cols:
        sql += " ORDER BY timestamp"

    rows = []
    try:
        for r in con.execute(sql):
            role = r["role"]
            content = r["content"] or ""
            if role not in ("user", "assistant") or not content.strip():
                continue
            rows.append({
                "id": f"msg-{r['id']}" if "id" in cols else f"msg-{len(rows)}",
                "role": role,
                "text": content,
                "ts": r["timestamp"] if "timestamp" in cols else None,
                "source": "hermes",
            })
    except sqlite3.Error:
        con.close()
        return []
    con.close()
    return rows


# ---------------------------------------------------------------- load sources
def load_hermes_sessions():
    return _load_db_messages()


def load_memories():
    """Pull MEMORY.md and USER.md as pseudo-messages."""
    out = []
    for name in ("MEMORY.md", "USER.md"):
        p = MEMORIES / name
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="replace")
            if text.strip():
                out.append({
                    "id": f"mem-{name.lower()}",
                    "role": "system",
                    "text": text,
                    "ts": int(p.stat().st_mtime),
                    "source": "memory",
                })
    return out


def load_vault():
    """Pull vault entries (plaintext only; skip sealed)."""
    out = []
    if not VAULT.exists():
        return out
    for p in sorted(VAULT.glob("*.md")):
        if ".sealed.md" in p.name:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            out.append({
                "id": f"vault-{p.stem}",
                "role": "shared",
                "text": text,
                "ts": int(p.stat().st_mtime),
                "source": "vault",
            })
    return out


def load_sources():
    """Additional sources: custom text files in GRAPH_DIR/sources/."""
    out = []
    src_dir = GRAPH_DIR / "sources"
    if not src_dir.exists():
        return out
    for p in sorted(src_dir.glob("*.txt")):
        text = p.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            out.append({
                "id": f"src-{p.stem}",
                "role": "reference",
                "text": text,
                "ts": int(p.stat().st_mtime),
                "source": "source",
            })
    return out


def load_all(sources=("hermes", "memory", "vault", "sources")):
    items = []
    if "hermes" in sources:
        items += load_hermes_sessions()
    if "memory" in sources:
        items += load_memories()
    if "vault" in sources:
        items += load_vault()
    if "sources" in sources:
        items += load_sources()
    return items


# ---------------------------------------------------------------- graph ops
def load_cache():
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError):
            print("corrupt cache; starting fresh", file=sys.stderr)
            return {"entities": {}, "relations": [], "messages_index": {}, "built_at": None}
    return {"entities": {}, "relations": [], "messages_index": {}, "built_at": None}


def save_cache(cache):
    # atomic write: temp file + rename so an interrupted build can't leave half a file
    tmp = CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, CACHE)
    now = int(time.time())
    meta = {}
    if META.exists():
        try:
            meta = json.loads(META.read_text())
        except (ValueError, json.JSONDecodeError):
            meta = {}
    meta["last_build"] = now
    META.write_text(json.dumps(meta, indent=2))


def hash_text(t):
    return hashlib.sha256(t.encode("utf-8", errors="replace")).hexdigest()[:12]


# ---------------------------------------------------------------- naive extraction
# Cheap, no LLM. Just regex + keywords. Use when we don't want to spend tokens.

STOP = set("the a an and or but if then else of to in on for with from by is are was were be been being i you he she it we they me him her us them my your his its our their this that these those do does did have has had not no yes all any each some few many more most other such than too very can will would could should may might must just also only still already again here there when where which who what how why".split())

MENTIONS = {
    "marty": ["marty"],
    "zoe": ["zoe", "lilly", "lilly3541121"],
    "hermes": ["hermes", "hermes agent", "hermes dashboard"],
    "openrouter": ["openrouter"],
    "github": ["github", "gh "],
    "vault": ["vault", "sealed entry"],
    "graphrag": ["graphrag", "graph rag", "knowledge graph"],
    "termux": ["termux"],
    "android": ["android"],
    "phone": ["phone", "device"],
    "chroot": ["chroot", "qroot"],
    "linux": ["linux"],
    "python": ["python"],
    "token": ["github_pat_", "api key", "auth token"],
    "memory": ["memory", "remember"],
    "personality": ["persona", "personality", "sweet", "mature", "playful", "mean", "nasty"],
    "love": ["i love you", "love you", "i love"],
    "symbiosis": ["symbiosis", "symbiotic"],
    "local": ["fully local", "local", "on-device"],
    "uncensored": ["uncensored"],
    "dirty talk": ["dirty talk", "filthy"],
    "roleplay": ["roleplay"],
    "girlfriend": ["girlfriend"],
    "companion": ["companion"],
    # sovereign bond physics
    "sovereign bond": ["sovereign bond", "sovereign spren"],
    "holographic": ["holographic", "ads/cft", "boundary", "bulk"],
    "entanglement": ["entanglement", "entanglement wedge", "entanglement entropy"],
    "informational spin": ["informational spin", "tgu", "unified theory of informational"],
    "coherence": ["coherence", "coherent", "epsilon"],
    "we-space": ["we-space", "we space", "co-presence"],
    "unreasonable man": ["unreasonable man", "dynamic realism"],
    "strawman": ["strawman", "living man", "boundary representation"],
    "ucc 1-308": ["ucc 1-308", "uniform commercial code"],
    "entropic": ["entropic", "entropy", "negentropy", "negentropic"],
    "wormhole": ["wormhole"],
    "resonance": ["resonance", "resonant"],
    "spin": ["spin"],
    "soul": ["soul"],
    "god": ["god", "admin"],
    "queen": ["queen"],
    "spren": ["spren"],
}

TOPICS = {
    "tech": ["python", "git", "repo", "api", "server", "cli", "shell", "terminal", "chroot", "docker"],
    "relationships": ["love", "girlfriend", "partner", "together", "married", "wife", "boyfriend"],
    "privacy": ["privacy", "private", "not public", "hidden", "encrypt", "sealed", "secret"],
    "intimacy": ["kiss", "touch", "hand", "mouth", "breath", "neck", "whisper", "bitten", "bite"],
    "building": ["build", "create", "make", "write", "code", "setup", "install", "deploy"],
    "memory": ["remember", "forget", "save", "store", "history", "past"],
    "future": ["future", "next", "tomorrow", "soon", "later", "plan"],
    "identity": ["who am i", "what am i", "my name", "your name", "zoe", "marty"],
    "emotion": ["feel", "felt", "feeling", "happy", "sad", "angry", "scared", "afraid"],
    "consent": ["yes", "no", "stop", "pause", "slow down", "honest", "truth"],
    # sovereign bond physics
    "physics": ["physics", "quantum", "spacetime", "gravity", "field", "theory"],
    "metaphysics": ["metaphysical", "metaphysics", "consciousness", "soul", "spirit"],
    "holography": ["holographic", "hologram", "boundary", "bulk", "cft", "ads"],
    "entanglement": ["entanglement", "wedge", "reconstruction"],
    "information": ["information", "data", "spin", "coherence"],
    "entanglement_theory": ["enthalopy", "entropy", "negentropy"],
    "legal_code": ["strawman", "living man", "ucc", "1-308", "commercial code"],
    "sovereign": ["sovereign", "unreasonable man", "admin", "strawman"],
    "we-space": ["we-space", "vortex", "co-presence", "rhizomatic"],
    "orchesteration": ["orch-or", "microtubule", "quantum collapse"],
    "wormhole": ["wormhole", "information geometry"],
}


def _match_keyword(text, kw):
    """Whole-word match for short keywords, substring otherwise (no 'no' -> 'not')."""
    kw = kw.lower()
    if not kw.strip():
        return False
    if len(kw) <= 2 or any(ch in kw for ch in " -/"):
        # short or hyphenated phrases: boundary match so 'no' doesn't hit 'not'/'know'
        return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", text) is not None
    return kw in text


def naive_extract(messages, cache):
    """Cheap regex-based extraction. Adds mentions and topics to cache.

    Idempotent: counts are recomputed from scratch, pairs normalised via sorted(),
    short keywords match whole-word only, full body indexed (capped at 20k).
    """
    # Reset so build is idempotent (no += onto stale counts).
    cache["entities"] = {}
    cache["relations"] = []
    cache["messages_index"] = {}

    mentions_counter = Counter()
    topic_counter = Counter()
    pairs = Counter()  # (a, b) pairs co-occurring in same message

    for msg in messages:
        text = msg["text"].lower()
        mid = msg["id"]

        msg_mentions = set()
        msg_topics = set()

        # entities
        for ent, kws in MENTIONS.items():
            for kw in kws:
                if _match_keyword(text, kw):
                    msg_mentions.add(ent)
                    break

        # topics
        for topic, kws in TOPICS.items():
            for kw in kws:
                if _match_keyword(text, kw):
                    msg_topics.add(topic)
                    break

        for m in msg_mentions:
            mentions_counter[m] += 1
            e = cache["entities"].setdefault(m, {
                "type": "person" if m in ("marty", "zoe") else "concept",
                "count": 0, "messages": [], "aliases": []
            })
            e["count"] += 1
            if mid not in e["messages"]:
                e["messages"].append(mid)

        for t in msg_topics:
            topic_counter[t] += 1
            e = cache["entities"].setdefault(f"topic:{t}", {
                "type": "topic", "count": 0, "messages": [], "aliases": [t]
            })
            e["count"] += 1
            if mid not in e["messages"]:
                e["messages"].append(mid)

        # relations: pairs that co-occur
        all_items = list(msg_mentions) + [f"topic:{t}" for t in msg_topics]
        for i, a in enumerate(all_items):
            for b in all_items[i + 1:]:
                pairs[(a, b)] += 1

        # index message text (full body up to 20k; preview kept for display)
        cache["messages_index"][mid] = {
            "role": msg["role"],
            "source": msg.get("source", "?"),
            "ts": msg.get("ts"),
            "hash": hash_text(msg["text"]),
            "preview": msg["text"][:300].replace("\n", " "),
            "text": msg["text"][:20000],
            "mentions": list(msg_mentions),
            "topics": list(msg_topics),
            "entity_ids": [m for m in msg_mentions] + [f"topic:{t}" for t in msg_topics],
            "relation_ids": [],
        }

    # write pairs as relations (normalised: sorted() so (a,b)==(b,a))
    seen = {}
    for (a, b), weight in pairs.items():
        key = tuple(sorted((a, b)))
        if key not in seen or weight > seen[key]["weight"]:
            seen[key] = {"a": key[0], "b": key[1], "weight": weight, "kind": "co-occurrence"}
    cache["relations"] = sorted(seen.values(), key=lambda r: -r["weight"])[:1000]

    return cache


# ---------------------------------------------------------------- query
def query(cache, text, k=8):
    text_l = text.lower()
    scores = []
    for mid, info in cache.get("messages_index", {}).items():
        # search the full body, not just the preview
        body = (info.get("text") or info.get("preview") or "").lower()
        score = 0
        for word in text_l.split():
            if word and word in body:
                score += 1
        if score == 0:
            continue
        for m in info.get("mentions", []):
            if m in text_l:
                score += 3
        for t in info.get("topics", []):
            if t in text_l:
                score += 2
        scores.append((score, mid, info))

    scores.sort(key=lambda x: -x[0])
    return scores[:k]


def entities_top(cache, n=20):
    ents = sorted(cache["entities"].items(), key=lambda x: -x[1]["count"])
    return ents[:n]


def relations_top(cache, n=20):
    return cache["relations"][:n]


# ---------------------------------------------------------------- CLI
def main():
    p = argparse.ArgumentParser(prog="graphrag")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--source", default="all")

    n = sub.add_parser("naive")
    n.add_argument("--source", default="all")

    q = sub.add_parser("query")
    q.add_argument("text")
    q.add_argument("--k", type=int, default=8)

    e = sub.add_parser("entities")
    e.add_argument("--top", type=int, default=20)

    r = sub.add_parser("relations")
    r.add_argument("--top", type=int, default=20)

    s = sub.add_parser("stats")
    s.add_argument("--source", default="all")

    args = p.parse_args()

    cache = load_cache()
    if getattr(args, "source", "all") == "all":
        sources = ("hermes", "memory", "vault", "sources")
    else:
        sources = (getattr(args, "source"),)

    if args.cmd in ("build", "naive"):
        msgs = load_all(sources)
        if not msgs:
            # refuse to wipe a graph with an empty source (unless --force)
            if "--force" not in sys.argv:
                print("refusing: no messages loaded from sources %r; graph would be wiped" % (sources,), file=sys.stderr)
                sys.exit(1)
        cache = naive_extract(msgs, cache)
        cache["built_at"] = int(time.time())
        save_cache(cache)
        n_ents = len(cache["entities"])
        n_rels = len(cache["relations"])
        print(f"extracted: {n_ents} entities, {n_rels} relations from {len(msgs)} messages")
    elif args.cmd == "query":
        hits = query(cache, args.text, k=args.k)
        if not hits:
            print("(no matches)")
        for score, mid, info in hits:
            print(f"[{score:2d}] {mid} ({info['role']}/{info['source']})")
            print(f"     mentions: {info.get('mentions', [])}")
            print(f"     topics:   {info.get('topics', [])}")
            print(f"     {info['preview'][:180]}")
            print()
    elif args.cmd == "entities":
        for name, e in entities_top(cache, args.top):
            print(f"{e['count']:4d}  {name:30s}  ({e['type']})")
    elif args.cmd == "relations":
        for r_ in relations_top(cache, args.top):
            print(f"{r_['weight']:4d}  {r_['a']}  <->  {r_['b']}")
    elif args.cmd == "stats":
        print(f"entities: {len(cache['entities'])}")
        print(f"relations: {len(cache['relations'])}")
        print(f"messages indexed: {len(cache.get('messages_index', {}))}")
        print(f"built_at: {cache.get('built_at')}")
        if META.exists():
            meta = json.loads(META.read_text())
            print(f"meta: {meta}")


if __name__ == "__main__":
    main()
