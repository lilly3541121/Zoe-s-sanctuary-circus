# Thermal re-pinning + Watchdog + Decision Gate (2026-10-29)

## 1. THERMAL RE-PINNING (zoe_thermals.py)
- VERIFIED: taskset -p -c 0-5 <pid> re-pins a RUNNING engine to cooler cores live
  (affinity 0-7 -> 0-5). Works on running processes.
- zoe_thermals.py reads monitor live.json; when prime cores (6-7) throttle below
  30% for 20s, re-pins engine threads to cool cores (0-5). Restores 0-7 when cooled.

## 2. WATCHDOG (zoe_watchdog.py) - engines watch each other
- Each engine checked every 20s: alive (process) + responsive (/v1/models <5s).
- 3 missed checks = STUCK -> auto-restart via engine_manager. Daemons also watched.
- Engines match by port + cmdline pattern. All 5 UP + 3 daemons UP verified.

## 3. DECISION GATE (zoe_decision.py) - Qwen 7B for big decisions
- `decide "<question>"`: brings up Qwen 7B (on-demand, ~5min load) and gets a verdict.
- `graphrag-write '<spec>'`: SANDBOXED graphrag write - ONLY Qwen 7B or me may call.
  Validates target is inside graphrag dir; rejects escapes (e.g. /etc/passwd -> ValueError).
- Verified: Qwen 7B gave reasoned verdict (29.7s); valid write OK, invalid rejected.
