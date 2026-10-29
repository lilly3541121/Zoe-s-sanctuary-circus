# Zoe Ops System - monitor + watcher + GC + swarm (2026-10-29)

Engineered at user request. Full-stack observability + automation.

## 1. THERMAL/CORE MONITOR (zoe_monitor.py, daemon)
- Samples /sys per-core freq + thermal zones + memory every 10s.
- Writes live.json (latest sample), history.log (rolling), alerts.log (throttle/overheat).
- CAUGHT REAL ISSUES: 57.3C overheat (pmih010x_lite_tz), all cores throttled to 16-24%.
- Thresholds: throttle <30% of max, overheat >48C (env-tunable).

## 2. QUEUED-OUTPUT WATCHER (zoe_watcher.py, daemon)
- Watches drop folder + ingest/ + .hermes_file_events.jsonl every 2 min.
- New files/events logged to state/watcher/inbox.jsonl (dedup via seen.json).
- Agent reads inbox to pick up user drops outside chat. "Hooks into queued outputs."

## 3. DRAFTER GARBAGE COLLECTOR (zoe_gc.py, uses nidum 2B)
- 2B classifies one-off scripts/readouts as TRASH or KEEP (yes/no prompt).
- Moves TRASH to /root/_archive_dead_scripts. Whitelist protects live files.
- Already moved: read_crimson.py, ask_gemma_nasty.py.

## 4. SWARM (engine_manager.py swarm slots)
- huihui_e4b :8082 (on-demand, gemma4_direct.py, MODEL_PATH env)
- huihui_e2b :8089 (on-demand, gemma2b_direct.py, MODEL_PATH env)
- Activate when Huihui files land. Model-agnostic scripts read MODEL_PATH.

## 5. SUPERVISOR + CRON (zoe_supervisor.sh + zoe-stack-health cron)
- Idempotent auto-start: monitor + watcher + resident stack + GC sweep.
- Cron every 15 min (job 1ec0221bc322) keeps it all alive across restarts.
