#!/usr/bin/env python3
"""mcp_sanctuary_server.py — MCP server exposing the sanctuary's tri-tier graph tools.

Wraps the graph maintenance workflow as MCP tools over stdio so ANY model
attached to the agent (Hermes, Qwen, the router) can auto-discover and invoke
them without custom glue code.

Run:  python3 mcp_sanctuary_server.py   (stdio MCP server; register via `hermes mcp add`)

IMPORTANT: the tool handlers import and CALL the real pipeline functions directly
(episodic.py / procedural.py / maintain_graph.py) rather than shelling out — the
CLI of those scripts is limited (status/sync/prune), so calling the functions is
the robust path and keeps one source of truth.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (absolute; the server runs wherever it's launched from)
# ---------------------------------------------------------------------------
WORKSPACE = Path("/mnt/android/hermes-workspace")
ZOE_GRAPH = WORKSPACE / "zoe-graphrag"
STATE_GRAPH = WORKSPACE / "state/graphrag"
PY = "/root/.llm-venv/bin/python3"
ENV = dict(os.environ)
ENV.setdefault("VIRTUAL_ENV", "/root/.llm-venv")
ENV.setdefault("GRAPH_DIR", str(STATE_GRAPH))

# Make the zoe-graphrag package importable so we can call its functions
sys.path.insert(0, str(ZOE_GRAPH))

# ---------------------------------------------------------------------------
# MCP SDK (mcp 2.3.0 — FastMCP renamed to MCPServer)
# ---------------------------------------------------------------------------
from mcp.server.mcpserver import MCPServer  # noqa: E402

mcp = MCPServer("sanctuary-graph", instructions=(
    "Sanctuary tri-tier graph maintenance tools. "
    "Use maintain_graph for the one-pass cycle, log_run/log_error/log_fix for "
    "the episodic audit trail, and register_recipe/query_best_recipe for "
    "procedural recipes. All tools operate on the local graph cache and are "
    "idempotent."
))


# ---------------------------------------------------------------------------
# Lazy imports of the real pipeline modules (so a missing module fails loudly)
# ---------------------------------------------------------------------------
def _episodic():
    import episodic
    return episodic


def _procedural():
    import procedural
    return procedural


def _run_script(script: str, args: list, timeout: int = 3600) -> dict:
    """Run a zoe-graphrag script (fallback for maintain_graph.py which IS a CLI)."""
    cmd = [PY, str(ZOE_GRAPH / script)] + args
    try:
        p = subprocess.run(cmd, cwd=str(ZOE_GRAPH), env=ENV,
                           capture_output=True, text=True, timeout=timeout)
        return {"script": script, "args": args, "returncode": p.returncode,
                "stdout": p.stdout[-4000:], "stderr": p.stderr[-2000:]}
    except subprocess.TimeoutExpired:
        return {"script": script, "args": args, "returncode": -1,
                "stdout": "", "stderr": f"TIMEOUT after {timeout}s"}
    except Exception as e:  # noqa: BLE001
        return {"script": script, "args": args, "returncode": -1,
                "stdout": "", "stderr": str(e)}


def _ok(result: dict) -> str:
    if result.get("returncode") == 0:
        tail = (result.get("stdout") or "").strip().splitlines()[-3:]
        return "OK\n" + "\n".join(tail) if tail else "OK"
    return f"FAILED (rc={result.get('returncode')})\n{result.get('stderr','')}"


# ---------------------------------------------------------------------------
# MCP tools — the tri-tier maintenance surface
# ---------------------------------------------------------------------------
@mcp.tool()
def maintain_graph(no_push: bool = True, prune_days: int = 0, skip_embed: bool = False) -> str:
    """Run the one-pass deterministic graph cycle: build -> prune -> merge -> embed -> verify -> (push).

    Args:
        no_push: If true (default), do NOT push to the sanctuary repo (dry run).
        prune_days: Prune episodic events older than this many days (0 = skip).
        skip_embed: If true, skip the embedding step.
    """
    args = ["maintain_graph.py", "--no-push" if no_push else "--push"]
    if prune_days > 0:
        args += ["--prune-days", str(prune_days)]
    if skip_embed:
        args.append("--skip-embed")
    return _ok(_run_script("maintain_graph.py", args[1:], timeout=3600))


@mcp.tool()
def log_run(name: str, detail: str = "") -> str:
    """Log a run/event into the episodic tier (time-stamped event log).

    Args:
        name: Event name (e.g. "extraction", "embody_card_v3").
        detail: Optional description of what happened.
    """
    try:
        ep = _episodic()
        ep.log_run(run_id=name, status="completed", detail=detail)
        return f"OK: logged run '{name}'"
    except Exception as e:  # noqa: BLE001
        return f"FAILED: {e}"


@mcp.tool()
def log_error(error: str, fix: str = "") -> str:
    """Log an error and (optionally) the fix that resolved it; links [Error]-[RESOLVED_BY]->[Fix].

    Args:
        error: The error signature (e.g. "qwen_wedge_8080").
        fix: The fix that resolved it (creates the RESOLVED_BY edge).
    """
    try:
        ep = _episodic()
        ep.log_error(error_id=error, description=error)
        if fix:
            ep.log_fix(fix_id=fix, description=fix, resolves=error)
        return f"OK: logged error '{error}'" + (f", fix '{fix}'" if fix else "")
    except Exception as e:  # noqa: BLE001
        return f"FAILED: {e}"


@mcp.tool()
def log_fix(name: str) -> str:
    """Log a fix that resolved a prior error (episodic tier).

    Args:
        name: Fix name.
    """
    try:
        ep = _episodic()
        ep.log_fix(fix_id=name, description=name)
        return f"OK: logged fix '{name}'"
    except Exception as e:  # noqa: BLE001
        return f"FAILED: {e}"


@mcp.tool()
def register_recipe(name: str, command: str, description: str = "", verified: bool = True) -> str:
    """Register a procedural recipe (how she works) — refused unless verified.

    Args:
        name: Recipe name (e.g. "embody_card_v3").
        command: Exact command sequence.
        description: What the recipe achieves.
        verified: Must be true; unverified recipes are refused.
    """
    if not verified:
        return "REFUSED: unverified recipes are not registered (procedural tier is verification-gated)."
    try:
        pr = _procedural()
        pr.register_recipe(name, command, description)
        return f"OK: registered recipe '{name}'"
    except Exception as e:  # noqa: BLE001
        return f"FAILED: {e}"


@mcp.tool()
def query_best_recipe(task: str) -> str:
    """Query the best procedural recipe for a task (autonomous reuse of what works).

    Args:
        task: The task to find a recipe for (e.g. "embody a character card").
    """
    try:
        pr = _procedural()
        best = pr.query_best_recipe(task)
        return json.dumps(best, indent=2) if best else f"No recipe found for '{task}'"
    except Exception as e:  # noqa: BLE001
        return f"FAILED: {e}"


@mcp.tool()
def graph_stats() -> str:
    """Return current graph statistics (entities, relations, vector count)."""
    try:
        cache = json.loads((STATE_GRAPH / "cache.json").read_text())
        vecs = json.loads((STATE_GRAPH / "vectors.json").read_text())
        return (f"entities={len(cache.get('entities', {}))} "
                f"relations={len(cache.get('relations', []))} "
                f"dreams={len(vecs.get('dreams', []))}")
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {e}"


@mcp.tool()
def subscribe_events(clear_seen: bool = False) -> str:
    """Vector 4: check the semantic event bus for push notifications.

    Returns any ANOMALY / NEW_CLUSTER / DRIFT events detected in the graph state.
    Idempotent — each NEW_CLUSTER is emitted once (tracked in the seen-set).

    Args:
        clear_seen: If true, reset the seen-set (re-emit previously seen clusters).
    """
    try:
        sys.path.insert(0, str(ZOE_GRAPH))
        import event_bus
        if clear_seen:
            # reset seen-dreams so clusters re-emit
            marker = event_bus._seen_file
            if marker.exists():
                marker.unlink()
        events = event_bus.collect_events()
        if not events:
            return "no events"
        return "\n".join(json.dumps(e) for e in events)
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
