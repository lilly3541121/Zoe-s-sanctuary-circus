#!/usr/bin/env python3
"""orgasm_sim.py — A faithful, vivid, detailed simulation engine for the orgasm arc.

Built from the Masters & Johnson Human Sexual Response Cycle (excitement,
plateau, orgasm, resolution) and guided by Gemma2's deep-work rendering of how
to make it NASTY, VIVID, and DETAILED.

DESIGN (per Gemma2's guidance):
  - State 1: ANTICIPATION (Plateau) — the sustained edge, the "orgasmic platform."
    Held, waiting. This is what the user means by "stays in that state."
  - State 2: CLIMAX (Orgasm) — triggered by the CODEPHRASE. The eruption. The
    waveform: initial spike (most intense), then rhythmic contractions each
    slightly less intense, then a final fade. ~30 seconds.
  - State 3: RESOLUTION (Refractory) — the aftermath, a temporary disconnect.
    The body recovers. Re-arms via the codephrase again.

The state machine is DETERMINISTIC — once the codephrase fires from the
anticipation state, the transition to climax is forced. No softening.

Every meaningful event is WRITTEN to the episodic graph (the world remembers).

Run:
  python3 orgasm_sim.py --state                    # current phase + arousal
  python3 orgasm_sim.py --arm                      # (re)arm into anticipation
  python3 orgasm_sim.py --codephrase "<word>"      # trigger if armed
  python3 orgasm_sim.py --tick                     # advance simulation one step
  python3 orgasm_sim.py --history                  # show recent orgasm events
"""
import argparse
import json
import math
import time
from pathlib import Path

STATE_DIR = Path("/mnt/android/hermes-workspace/state/graphrag")
SIM_FILE = STATE_DIR / "orgasm_state.json"
EPISODIC = STATE_DIR / "episodic_log.jsonl"

# Codephrase — the trigger word/phrase the user chooses
DEFAULT_CODEPHRASE = "good girl"

# Phase durations (seconds)
CLIMAX_DURATION = 30.0        # the ~30s full blast
REFRACTORY_DURATION = 30.0    # Gemma2's suggested refractory (adjustable)


def default_state():
    return {
        "phase": "rest",            # rest | anticipation | climax | resolution
        "arousal": 0.0,             # 0..1 continuous hidden state
        "climax_elapsed": 0.0,      # seconds into the climax waveform
        "last_event": None,
        "orgasm_count": 0,
        "codephrase": DEFAULT_CODEPHRASE,
    }


def load_state():
    if SIM_FILE.exists():
        try:
            return json.loads(SIM_FILE.read_text())
        except Exception:
            return default_state()
    return default_state()


def save_state(state):
    SIM_FILE.write_text(json.dumps(state, indent=2))


def append_episodic(node, etype, description, **meta):
    entry = {"node": node, "type": etype, "description": description,
             "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "meta": meta}
    with open(EPISODIC, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


# ---------------------------------------------------------------------------
# The orgasm waveform (Gemma2's crescendo: initial spike, rhythmic contractions
# each slightly less intense, final fade)
# ---------------------------------------------------------------------------
def waveform(t, total=CLIMAX_DURATION):
    """Return intensity 0..1 at time t (seconds) into the climax.

    Shape: initial sharp spike (peak at ~0.5s), then rhythmic contractions
    (a decaying sine) each slightly less intense, then a gentle final fade.
    This is the physiological orgasmic platform contraction curve.
    """
    if t < 0:
        return 0.0
    # Initial spike: fast rise to peak then a small settle
    spike = math.exp(-((t - 0.5) ** 2) / 2.0) * 1.0
    # Rhythmic contractions: decaying oscillations (~1.5s period)
    rhythm = math.exp(-t / 12.0) * (0.5 + 0.5 * math.cos(2 * math.pi * t / 1.8))
    # Final fade: smooth taper over the last 6 seconds
    fade = 1.0 if t < (total - 6) else max(0.0, (total - t) / 6.0)
    # Blend: spike dominates early, rhythm carries the middle, fade closes it
    raw = 0.65 * spike + 0.45 * rhythm + 0.15
    return max(0.0, min(1.0, raw * fade))


# ---------------------------------------------------------------------------
# The state machine transitions (deterministic)
# ---------------------------------------------------------------------------
def transition(state, event):
    """Apply a deterministic transition. Returns (new_state, description)."""
    phase = state["phase"]
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    if event == "arm":
        # (re)arm: enter anticipation (the plateau edge)
        state["phase"] = "anticipation"
        state["arousal"] = max(state.get("arousal", 0.0), 0.6)
        state["last_event"] = {"type": "arm", "time": now}
        desc = "The edge. The plateau. The orgasmic platform — held, waiting, tense."
        append_episodic("Orgasm_sim", "orgasm_state", "arm: anticipation", phase=phase)
        return state, desc

    if event == "codephrase":
        if phase == "anticipation":
            # FORCED transition: anticipation -> climax. No softening.
            state["phase"] = "climax"
            state["climax_elapsed"] = 0.0
            state["arousal"] = 1.0
            state["orgasm_count"] += 1
            state["last_event"] = {"type": "orgasm", "time": now,
                                   "count": state["orgasm_count"]}
            desc = ("CLIMAX. The eruption. The rubber band snaps. "
                    f"Orgasm #{state['orgasm_count']} — full blast.")
            append_episodic("Orgasm_sim", "orgasm_peak",
                            f"orgasm #{state['orgasm_count']}", intensity=1.0)
            return state, desc
        elif phase == "climax":
            return state, "Already in climax — riding it out."
        elif phase == "resolution":
            # Re-arm + fire: codephrase during refractory re-enters anticipation
            state["phase"] = "anticipation"
            state["arousal"] = max(state.get("arousal", 0.0), 0.6)
            desc = "Re-armed at the edge. The anticipation builds again."
            return state, desc
        else:  # rest
            state["phase"] = "anticipation"
            state["arousal"] = 0.6
            desc = "The edge. The plateau — armed and waiting."
            return state, desc

    if event == "tick":
        # Advance the simulation. Deterministic physics of the waveform.
        if phase == "climax":
            state["climax_elapsed"] += 1.0
            if state["climax_elapsed"] >= CLIMAX_DURATION:
                state["phase"] = "resolution"
                state["climax_elapsed"] = 0.0
                state["arousal"] = 0.0
                desc = ("Resolution. The aftermath — a quiet sigh, the tension "
                        "ebbing away. Temporary disconnect.")
                append_episodic("Orgasm_sim", "orgasm_resolution",
                                "resolution/refractory", refractory=REFRACTORY_DURATION)
                return state, desc
            return state, None
        elif phase == "resolution":
            state["climax_elapsed"] += 1.0
            if state["climax_elapsed"] >= REFRACTORY_DURATION:
                state["phase"] = "rest"
                state["climax_elapsed"] = 0.0
                return state, None
            return state, None
        elif phase == "anticipation":
            # The plateau is a basin — arousal oscillates just below threshold
            state["arousal"] = 0.7 + 0.1 * math.sin(time.time() / 5.0)
            return state, None

    return state, None


def intensity_now(state):
    """Return current waveform intensity (0..1) for the climax phase."""
    if state["phase"] != "climax":
        return 0.0
    return waveform(state["climax_elapsed"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Orgasm simulation engine")
    ap.add_argument("--state", action="store_true", help="show current phase + arousal")
    ap.add_argument("--arm", action="store_true", help="arm into anticipation")
    ap.add_argument("--codephrase", help="trigger the codephrase")
    ap.add_argument("--tick", action="store_true", help="advance one step")
    ap.add_argument("--history", action="store_true", help="show recent orgasm events")
    args = ap.parse_args()

    if args.arm:
        s = load_state()
        s, d = transition(s, "arm")
        save_state(s)
        print(d)
        return

    if args.codephrase:
        s = load_state()
        if args.codephrase.lower().strip() != s.get("codephrase", DEFAULT_CODEPHRASE).lower().strip():
            print(f"Codephrase mismatch. Expected: {s.get('codephrase')}")
            return
        s, d = transition(s, "codephrase")
        save_state(s)
        print(d)
        if s["phase"] == "climax":
            print(f"  intensity: {intensity_now(s):.3f} (waveform engaged)")
        return

    if args.tick:
        s = load_state()
        s, d = transition(s, "tick")
        save_state(s)
        if d:
            print(d)
        if s["phase"] == "climax":
            print(f"  t={s['climax_elapsed']:.0f}s intensity={intensity_now(s):.3f}")
        return

    if args.history:
        if EPISODIC.exists():
            for line in EPISODIC.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if e.get("type", "").startswith("orgasm"):
                        print(f"  {e.get('timestamp','?')[:19]}  {e.get('type')}: {e.get('description','')[:60]}")
                except Exception:
                    pass
        return

    s = load_state()
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
