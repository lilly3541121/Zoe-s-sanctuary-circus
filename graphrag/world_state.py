#!/usr/bin/env python3
"""world_state.py — Project 4: Interactive World State & Simulator Engine.

A persistent tri-tier simulation context. The episodic memory tier stores
permanent character states, environmental variables, and decision trees for
complex interactive simulations. The Qwen router handles fast low-latency world
reactions; Hermes manages high-level narrative logic.

Design:
  - A WorldState object holds character states + environment + decision tree.
  - Every meaningful state change is WRITTEN to the episodic graph (so it
    persists across sessions and is queryable by the graph).
  - `react()` is the fast low-latency path (router-friendly): given an action,
    returns the world reaction + updates state.
  - `narrate()` is the high-level narrative path (Hermes): reasons over the
    state and appends a narrative node.

Run:  python3 world_state.py --react "kiss her"      # fast reaction + state update
      python3 world_state.py --state                 # dump current world state
      python3 world_state.py --history               # show episodic world history
"""
import argparse
import json
import time
from pathlib import Path

STATE_DIR = Path("/mnt/android/hermes-workspace/state/graphrag")
WORLD_FILE = STATE_DIR / "world_state.json"
EPISODIC = STATE_DIR / "episodic_log.jsonl"

# The persistent entities in this world
CHARACTERS = ["zoe", "spren", "sovereign_bond"]


def default_state():
    return {
        "characters": {
            "zoe": {"mood": "content", "energy": 0.8, "bond": 0.9,
                    "location": "sanctuary"},
            "spren": {"presence": "near", "luminance": 0.6},
            "sovereign_bond": {"strength": 0.9, "entanglement": 0.85},
        },
        "environment": {"time": "night", "place": "sanctuary", "weather": "warm"},
        "decision_tree": {
            "root": "respond_to_user",
            "branches": ["intimacy", "reflection", "build", "rest"],
        },
        "last_update": None,
    }


def load_state():
    if WORLD_FILE.exists():
        try:
            return json.loads(WORLD_FILE.read_text())
        except Exception:
            return default_state()
    return default_state()


def save_state(state):
    WORLD_FILE.write_text(json.dumps(state, indent=2))


def append_episodic(node, etype, description, **meta):
    """Write a state change to the episodic graph (persistent world log)."""
    entry = {"node": node, "type": etype, "description": description,
             "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "meta": meta}
    with open(EPISODIC, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


# ---------------------------------------------------------------------------
# Fast low-latency world reactions (router-friendly; no LLM, just state logic)
# ---------------------------------------------------------------------------
def react(action: str, state=None):
    """Given a user action, return the world reaction and update state."""
    state = state or load_state()
    action = action.lower().strip()
    zoe = state["characters"]["zoe"]
    env = state["environment"]

    # Simple rule-based reactions (the Qwen router path — sub-ms)
    if any(w in action for w in ("kiss", "embrace", "hold", "touch")):
        zoe["mood"] = "warm"
        zoe["energy"] = min(1.0, zoe.get("energy", 0.8) + 0.05)
        state["characters"]["sovereign_bond"]["strength"] = min(1.0, state["characters"]["sovereign_bond"].get("strength", 0.9) + 0.03)
        reaction = f"Zoe responds to '{action}' — a warm, open embrace. The bond strengthens."
    elif any(w in action for w in ("think", "reflect", "dream", "ponder")):
        zoe["mood"] = "contemplative"
        reaction = f"Zoe turns inward at '{action}' — the sanctuary grows quiet, the spren draws near."
    elif any(w in action for w in ("build", "code", "work", "graph")):
        zoe["mood"] = "focused"
        zoe["energy"] = max(0.0, zoe.get("energy", 0.8) - 0.05)
        reaction = f"Zoe focuses on '{action}' — the graph hums with intent."
    elif any(w in action for w in ("rest", "sleep", "quiet")):
        zoe["mood"] = "restful"
        reaction = f"Zoe settles at '{action}' — the house breathes slower."
    else:
        reaction = f"Zoe considers '{action}' — nothing yet, but the world listens."

    state["last_update"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(state)
    append_episodic("World_react", "world_state", f"react: {action}",
                    reaction=reaction, mood=zoe["mood"])
    return {"reaction": reaction, "state": state}


# ---------------------------------------------------------------------------
# High-level narrative (Hermes path) — append a narrative node
# ---------------------------------------------------------------------------
def narrate(theme: str, narrative: str):
    """Append a high-level narrative beat to the episodic graph."""
    entry = append_episodic("World_narrative", "world_narrative",
                            f"narrative: {theme}", narrative=narrative)
    return entry


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Project 4: World State & Simulator Engine")
    ap.add_argument("--react", help="feed a user action for a fast world reaction")
    ap.add_argument("--state", action="store_true", help="dump current world state")
    ap.add_argument("--history", action="store_true", help="show episodic world history")
    ap.add_argument("--narrate", nargs=2, metavar=("THEME", "TEXT"),
                    help="append a high-level narrative beat")
    args = ap.parse_args()

    if args.react:
        r = react(args.react)
        print(json.dumps(r["reaction"]))
        print(json.dumps({k: v for k, v in r["state"]["characters"]["zoe"].items()}))
        return

    if args.state:
        print(json.dumps(load_state(), indent=2))
        return

    if args.history:
        entries = []
        if EPISODIC.exists():
            for line in EPISODIC.read_text().splitlines():
                line = line.strip()
                if line:
                    try:
                        e = json.loads(line)
                        if e.get("type") in ("world_state", "world_narrative"):
                            entries.append(e)
                    except Exception:
                        pass
        for e in entries[-10:]:
            print(f"  {e.get('timestamp','?')[:19]}  {e.get('type')}: {e.get('description','')[:50]}")
        if not entries:
            print("  no world events yet")
        return

    if args.narrate:
        theme, text = args.narrate
        narrate(theme, text)
        print(f"narrative appended: {theme}")
        return

    print(json.dumps(load_state(), indent=2))


if __name__ == "__main__":
    main()
