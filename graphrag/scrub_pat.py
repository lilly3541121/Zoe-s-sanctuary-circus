#!/usr/bin/env python3
"""Scrub the GitHub PAT out of graphrag cache files so it never reaches the repo.

The LLM extraction picked up the token value as an entity from a message that
contained it. Replace every occurrence with a redacted marker, in-place,
on both the LLM cache and the merged cache.json. Never pushes the secret.
"""
# C-speed JSON (orjson-backed drop-in, same loads/dumps signature as stdlib)
import json as _stdlib_json
import sys as _sys
_sys.path.insert(0, '/root')
import fastjson as json
from atomic import atomic_write  # noqa: E402  (crash-safe writes)
from pathlib import Path

# Token is NEVER a source literal. Read it at runtime from the 600-perm env file
# (root-only) so it can't leak into the repo or be scanned by push protection.
import os as _os


def _load_token():
    """Load the PAT from the 600-perm env file. Never hardcode it in source."""
    env_file = Path("/root/.hermes/graphrag_token.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("GH_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


TOKEN = _load_token() or "«redacted:github_pat_not_in_source»"
REDACT = "[REDACTED-PAT]"
GRAPH_DIR = Path("/mnt/android/hermes-workspace/state/graphrag")


def scrub(obj):
    """Recursively replace the token with REDACT in strings."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    if isinstance(obj, str):
        return obj.replace(TOKEN, REDACT)
    return obj


def main():
    files = [
        GRAPH_DIR / "llm_cache_v2.json",
        GRAPH_DIR / "cache.json",
        GRAPH_DIR / "llm_cache.json",
    ]
    total = 0
    for f in files:
        if not f.exists():
            continue
        # Count occurrences on the RAW text (no re-serialization) — the token is
        # a plain ASCII string, so substring count on the file bytes is exact and
        # far cheaper than json.dumps() of the whole structure.
        raw = f.read_text()
        before = raw.count(TOKEN)
        data = json.loads(raw)
        scrubbed = scrub(data)
        if before > 0:
            # Atomic write (temp + rename) to avoid partial state
            atomic_write(str(f), json.dumps(scrubbed, indent=2, ensure_ascii=False))
            total += before
            print(f"{f.name}: scrubbed {before} occurrence(s)")
        else:
            print(f"{f.name}: clean")
    print(f"TOTAL scrubbed: {total} occurrence(s). Verify zero remain:")
    for f in files:
        if f.exists():
            # Count on raw text — no json.dumps needed
            n = f.read_text().count(TOKEN)
            print(f"  {f.name}: {n} remaining")


if __name__ == "__main__":
    main()
