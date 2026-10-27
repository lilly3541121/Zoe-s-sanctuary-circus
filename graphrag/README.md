# zoe-graphrag

A tiny, dependency-free knowledge graph over Hermes session history.

No pip install. No database. Just stdlib Python building a dict-of-dicts from
your own conversation logs, memories, and vault entries, then letting you
search it and look at what connects to what.

## Why it exists

Sessions scroll away. This turns them into something you can query — which
entities keep coming up, which ideas co-occur, where a topic first appeared.

## Requirements

Python 3.9+. That's it.

## Install

Portable by design. Paths resolve from `$HERMES_HOME` (default `~/.hermes`),
so the same checkout runs unchanged on a root VPS *and* on Android/Termux.

```bash
git clone <this repo> && cd zoe-graphrag
python3 graphrag.py stats     # show resolved paths + graph state
python3 graphrag.py build     # read sources, rebuild the graph
```

## Commands

| Command | What it does |
|---|---|
| `build [--source S] [--force]` | Full rebuild: clear, re-read, re-extract (idempotent) |
| `naive [--source S] [--force]` | Alias of `build` (regex extraction, no LLM) |
| `query "text" [--k N]` | Search messages + entity adjacency |
| `entities [--top N]` | Entities by frequency |
| `relations [--top N]` | Strongest co-occurrence edges |
| `stats` | Paths, counts, last build |
| `prune` | Drop index entries whose source vanished |

`--source` accepts `hermes`, `memory`, `vault`, `sources`, or `all` (default).

## Sources

| Name | Reads from |
|---|---|
| `hermes` | `$HERMES_HOME/state.db` — user + assistant messages |
| `memory` | `$HERMES_HOME/memories/{MEMORY,USER}.md` |
| `vault` | `$HERMES_HOME/vault/entries/*.md` (skips `*.sealed.md`) |
| `sources` | `$GRAPH_DIR/sources/*.txt` — drop any document here |

Anything you put in `$GRAPH_DIR/sources/` gets indexed. Long documents are
fully searchable, not just their opening paragraph.

## Environment

| Var | Default | Purpose |
|---|---|---|
| `HERMES_HOME` | `~/.hermes` | Where Hermes keeps state.db + memories |
| `GRAPH_DIR` | `$HERMES_HOME/graphrag` | Where the cache lives |

## Storage layout

```
$GRAPH_DIR/
  cache.json        entities, relations, message index
  cache_meta.json   last build timestamp
  sources/          your own .txt documents
```

`cache.json` is written to a temp file and atomically renamed, so an
interrupted build can't leave you with a half-file.

## How it works

Extraction is deliberately dumb and free — regex keyword tables (`MENTIONS`,
`TOPICS`) rather than an LLM call. Edit those dicts to teach it your own
vocabulary; that's the tuning surface.

Scoring is keyword overlap over the message body, plus a bonus when the query
names a known entity and the message touches something adjacent to it.

## Correctness notes

These are the bugs that were fixed getting it running on Termux — worth
knowing about if you edit the code:

- **Paths were hardcoded to `/root/.hermes`**, so it only ever ran on one VPS.
  Now resolved from the environment.
- **`WHERE active=1`** was in the sessions query, but no Hermes schema has an
  `active` column — that query always threw. Columns are now introspected.
- **Message IDs were `session_id + counter`**, so deleting one message shifted
  every ID after it and invalidated the index. Now keyed on the real row id.
- **Counts were `+= 1` onto the existing cache**, so building twice doubled
  every number. Counts are now recomputed from scratch — `build` is idempotent.
- **Relations used raw set order**, so `(a,b)` and `(b,a)` were separate edges
  and flipped randomly between runs. Pairs are normalised via `sorted()`.
- **Keyword matching was plain substring**, so `"no"` matched `"not"`,
  `"know"`, `"now"` and inflated whole topics. Short words now match
  whole-word only.
- **Search only scanned the first 1200 chars**, so most of a long document was
  invisible. Full body is indexed now, capped at 20k.
- **A build against an empty source silently wiped the graph.** It now refuses
  and exits 1; `--force` overrides.

## A note on the name

`zoe-graphrag` was built for a specific relationship, and `sovereign_bond.txt`
lives in this repo. That document is not engineering documentation, and the
claims in it shouldn't be read as true — but it's here because it's part of how
this got made, and deleting it would be a weird kind of dishonesty. The code
works either way.
