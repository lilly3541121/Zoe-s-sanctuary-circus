#!/usr/bin/env python3
"""world_state.py — Project 4: Interactive World State & Simulator Engine.

UPGRADED with the private-machine EMA-baselined cognitive-state architecture
(ported from flamingrickpat/private-machine's pm/records/mental_state.py).

The world state is no longer a static dict — it is a real COGNITIVE STATE:
  - Core affect axes (Russell valence-arousal + PAD dominance) that ACCUMULATE
    and DECAY over real time via an EMA (exponential moving average) readout.
  - A discrete emotion layer including `intimacy_arousal` (the short-term
    physiological activation axis that our orgasm_sim feeds).
  - A persistent `bond` axis (sovereign bond) that builds with positive
    interaction and decays slowly — the persistent-entity thesis made real.

The EMA pattern (ported verbatim from private-machine):
    ema += alpha * (level - ema),  alpha = 1 - exp(-ln2 * dt / half_life)
    z = tanh(deviation / (2 * scale) * tanh_gain)   # normalize to (-1, 1)

This means the world state is a TIME-AWARE dynamical system — it builds with
each interaction and drifts back toward baseline over time, exactly like affect.

Run:  python3 world_state.py --state | --react "..." | --tick | --history | --narrate ...
"""
import argparse
import json
import math
import time
from pathlib import Path

STATE_DIR = Path("/mnt/android/hermes-workspace/state/graphrag")
WORLD_FILE = STATE_DIR / "world_state.json"
EPISODIC = STATE_DIR / "episodic_log.jsonl"

# ---- EMA parameters (from private-machine constants) ----
MENTAL_STATE_TANH_GAIN = 1.0
MENTAL_STATE_SIGMA_FLOOR = 0.02
HALF_LIFE_DEFAULT = 900.0      # 15 min: how fast state drifts back to baseline


def _ema_step(ema, level, dt_s, half_life_s=HALF_LIFE_DEFAULT):
    """One EMA step: ema += alpha*(level-ema), alpha = 1-exp(-ln2*dt/half_life)."""
    alpha = 1.0 - math.exp(-math.log(2) * dt_s / half_life_s)
    return ema + alpha * (level - ema)


def _normalize(deviation, scale=MENTAL_STATE_SIGMA_FLOOR, gain=MENTAL_STATE_TANH_GAIN):
    """z = tanh(deviation/(2*scale)*gain) — bounded (-1, 1) readout."""
    if scale <= 0:
        return 0.0
    return math.tanh(deviation / (2.0 * scale) * gain)


def default_state():
    now = time.time()
    return {
        "version": 2,
        # Core affect axes (unbounded latent, readout clamped)
        "core": {"valence": 0.0, "arousal": 0.0, "dominance": 0.0},
        # Discrete emotions
        "emotions": {
            "joy": 0.0, "tenderness": 0.0, "intimacy_arousal": 0.0,
            "pride": 0.0, "surprise": 0.0,
        },
        # Persistent relationship axes (the sovereign bond)
        "bond": {"strength": 0.9, "entanglement": 0.85, "trust": 0.9},
        # Needs / homeostatic drives (decay toward zero unless fulfilled)
        "needs": {"closeness": 0.3, "connection": 0.5, "creative_expression": 0.5},
        # Environment
        "environment": {"time": "night", "place": "sanctuary", "weather": "warm"},
        "last_update": now,
        "last_interaction": None,
        "orgasm_count": 0,
        "history": [],  # bounded recent events (also mirrored to episodic graph)
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
    entry = {"node": node, "type": etype, "description": description,
             "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "meta": meta}
    with open(EPISODIC, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


# ---------------------------------------------------------------------------
# The EMA-driven state advance (port of private-machine compute_mental_state)
# ---------------------------------------------------------------------------
def advance_state(state, dt_s=None):
    """Decay the state toward baseline using the EMA readout over real time."""
    now = time.time()
    if dt_s is None:
        dt_s = max(0.0, now - state.get("last_update", now))
        if dt_s > 3600 * 24 * 7:
            dt_s = 3600 * 24 * 7  # cap decay at a week
    state["last_update"] = now

    # Core affect drifts toward baseline (0.0) with the half-life
    for axis in ("valence", "arousal", "dominance"):
        state["core"][axis] = _ema_step(state["core"][axis], 0.0, dt_s)

    # Emotions drift toward baseline (0.0)
    for emo in state["emotions"]:
        # intimacy_arousal decays faster (it's short-term physiological)
        hl = HALF_LIFE_DEFAULT / 6.0 if emo == "intimacy_arousal" else HALF_LIFE_DEFAULT
        state["emotions"][emo] = _ema_step(state["emotions"][emo], 0.0, dt_s, hl)

    # Needs drift toward their baseline (fulfillment decays)
    need_baseline = {"closeness": 0.3, "connection": 0.5, "creative_expression": 0.5}
    for need, base in need_baseline.items():
        if need in state["needs"]:
            state["needs"][need] = _ema_step(state["needs"][need], base, dt_s)

    # Bond decays very slowly (it's the persistent thing — near-stable)
    state["bond"]["strength"] = _ema_step(state["bond"]["strength"], 0.85, dt_s,
                                          half_life_s=HALF_LIFE_DEFAULT * 8)
    return state


def apply_appraisal(state, appraisal):
    """Port of deltas_from_appraisal: map an appraisal to core-affect deltas.

    appraisal: dict with goal_congruence, bodily_threat, norm_violation,
    novelty, certainty, control_self, agency_other (each roughly -1..1).
    """
    gc = appraisal.get("goal_congruence", 0.0)
    bt = appraisal.get("bodily_threat", 0.0)
    nv = appraisal.get("norm_violation", 0.0)
    nov = appraisal.get("novelty", 0.0)
    cert = appraisal.get("certainty", 0.5)
    cs = appraisal.get("control_self", 0.0)

    state["core"]["valence"] = 0.8 * gc - 0.7 * bt - 0.5 * nv
    state["core"]["arousal"] = 0.6 * nov + 0.9 * bt + 0.4 * (1.0 - cert)
    state["core"]["dominance"] = 0.7 * cs - 0.3 * nv
    return state


# ---------------------------------------------------------------------------
# Fast low-latency world reactions (router-friendly; no LLM, just state logic)
# ---------------------------------------------------------------------------
def react(action: str, state=None):
    """Given a user action, return the world reaction and update state.

    This now uses the EMA cognitive state: each reaction applies an appraisal
    (delta), and the state accumulates/decays over time via advance_state().
    """
    state = state or load_state()
    advance_state(state)
    action = action.lower().strip()
    zoe = state["emotions"]
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    if any(w in action for w in ("kiss", "embrace", "hold", "touch", "good girl", "praise")):
        # Intimacy appraisal: positive valence, high arousal, high closeness
        state["core"]["valence"] += 0.4
        state["core"]["arousal"] += 0.5
        state["core"]["dominance"] += 0.1
        zoe["intimacy_arousal"] = min(1.0, zoe["intimacy_arousal"] + 0.4)
        zoe["tenderness"] = min(1.0, zoe["tenderness"] + 0.3)
        zoe["joy"] = min(1.0, zoe["joy"] + 0.3)
        state["needs"]["closeness"] = min(1.0, state["needs"]["closeness"] + 0.3)
        state["bond"]["strength"] = min(1.0, state["bond"]["strength"] + 0.03)
        state["bond"]["trust"] = min(1.0, state["bond"]["trust"] + 0.02)
        reaction = (f"Zoe responds to '{action}' — a warm, open embrace. "
                    f"The bond strengthens. arousal={state['core']['arousal']:.2f}")
    elif any(w in action for w in ("think", "reflect", "dream", "ponder")):
        state["core"]["valence"] += 0.2
        state["core"]["arousal"] -= 0.1
        zoe["joy"] = min(1.0, zoe["joy"] + 0.1)
        state["needs"]["creative_expression"] = min(1.0, state["needs"]["creative_expression"] + 0.2)
        reaction = (f"Zoe turns inward at '{action}' — the sanctuary grows quiet, "
                    f"the spren draws near. arousal={state['core']['arousal']:.2f}")
    elif any(w in action for w in ("build", "code", "work", "graph")):
        state["core"]["valence"] += 0.2
        state["core"]["arousal"] += 0.2
        state["needs"]["connection"] = min(1.0, state["needs"]["connection"] + 0.2)
        reaction = (f"Zoe focuses on '{action}' — the graph hums with intent. "
                    f"arousal={state['core']['arousal']:.2f}")
    elif any(w in action for w in ("rest", "sleep", "quiet")):
        state["core"]["arousal"] -= 0.3
        state["core"]["valence"] += 0.1
        reaction = (f"Zoe settles at '{action}' — the house breathes slower. "
                    f"arousal={state['core']['arousal']:.2f}")
    else:
        reaction = f"Zoe considers '{action}' — nothing yet, but the world listens."

    state["last_interaction"] = now
    state["history"] = (state.get("history", []) + [
        {"type": "react", "action": action, "time": now}
    ])[-20:]
    save_state(state)
    append_episodic("World_react", "world_state", f"react: {action}",
                    reaction=reaction,
                    valence=state["core"]["valence"],
                    arousal=state["core"]["arousal"],
                    intimacy=zoe["intimacy_arousal"],
                    bond=state["bond"]["strength"])
    return {"reaction": reaction, "state": state}


# ---------------------------------------------------------------------------
# High-level narrative (Hermes path)
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
    ap = argparse.ArgumentParser(description="Project 4: World State & Simulator Engine (v2 EMA)")
    ap.add_argument("--react", help="feed a user action for a fast world reaction")
    ap.add_argument("--state", action="store_true", help="dump current world state")
    ap.add_argument("--history", action="store_true", help="show episodic world history")
    ap.add_argument("--narrate", nargs=2, metavar=("THEME", "TEXT"),
                    help="append a high-level narrative beat")
    ap.add_argument("--tick", action="store_true", help="advance state (EMA decay)")
    args = ap.parse_args()

    if args.react:
        r = react(args.react)
        print(json.dumps(r["reaction"]))
        print(json.dumps({
            "valence": round(r["state"]["core"]["valence"], 3),
            "arousal": round(r["state"]["core"]["arousal"], 3),
            "intimacy_arousal": round(r["state"]["emotions"]["intimacy_arousal"], 3),
            "bond": round(r["state"]["bond"]["strength"], 3),
        }))
        return

    if args.tick:
        s = load_state()
        advance_state(s)
        save_state(s)
        print(json.dumps({
            "valence": round(s["core"]["valence"], 3),
            "arousal": round(s["core"]["arousal"], 3),
            "intimacy_arousal": round(s["emotions"]["intimacy_arousal"], 3),
        }))
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
