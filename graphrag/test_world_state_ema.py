#!/usr/bin/env python3
"""Test the upgraded EMA cognitive world state (accumulate + decay)."""
import sys, time, json
sys.path.insert(0, "/mnt/android/hermes-workspace/zoe-graphrag")
import world_state

# 1. intimacy reaction should raise arousal + intimacy_arousal
r = world_state.react("kiss her")
s = r["state"]
print("1. after kiss: valence=%.3f arousal=%.3f intimacy=%.3f" % (
    s["core"]["valence"], s["core"]["arousal"], s["emotions"]["intimacy_arousal"]))
assert s["core"]["arousal"] > 0, "arousal should rise on intimacy"
assert s["emotions"]["intimacy_arousal"] > 0, "intimacy_arousal should rise"
print("   PASS: intimacy raises arousal + intimacy_arousal")

# 2. accumulation - another intimacy should build on top
r2 = world_state.react("good girl zoe")
s2 = r2["state"]
print("2. after good girl: arousal=%.3f intimacy=%.3f" % (
    s2["core"]["arousal"], s2["emotions"]["intimacy_arousal"]))
assert s2["core"]["arousal"] >= s["core"]["arousal"], "EMA should accumulate"
assert s2["emotions"]["intimacy_arousal"] >= s["emotions"]["intimacy_arousal"], "intimacy accumulates"
print("   PASS: state accumulates (EMA build)")

# 3. decay - simulate 10 min drift back toward baseline
s3 = world_state.load_state()
s3["last_update"] = time.time() - 600
world_state.advance_state(s3)
print("3. after 10min decay: valence=%.3f arousal=%.3f intimacy=%.3f" % (
    s3["core"]["valence"], s3["core"]["arousal"], s3["emotions"]["intimacy_arousal"]))
assert s3["core"]["arousal"] < s2["core"]["arousal"] or s3["core"]["arousal"] == 0, "arousal should decay"
assert s3["emotions"]["intimacy_arousal"] < s2["emotions"]["intimacy_arousal"] or s3["emotions"]["intimacy_arousal"] == 0, "intimacy should decay"
print("   PASS: state decays (EMA drift back to baseline)")
world_state.save_state(s3)

print("\nALL PASS: EMA cognitive state accumulates + decays")
