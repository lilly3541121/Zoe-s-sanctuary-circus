# Stay-alive + E4B speed (2026-10-29)

## STAY-ALIVE (zoe_stayalive.py + cron zoe-stay-alive every 30min)
- Helper runs: ensure stack (supervisor), health snapshot (temp/mem/engines),
  GC sweep, appends reflection line to sanctuary_writing/reflection.md.
- Cron forces an agent cycle every 30min while user is away: bounded, cool
  work (no big models, no >60-token gen, <5min total). Reflect/improve/maintain.
- 4 cron jobs now: huihui-reflection (2am), graph-maintenance (3am),
  zoe-stack-health (*/15min), zoe-stay-alive (*/30min).

## E4B SPEED (measured, on-demand 8082, KleidiAI + direct API + unique PORT)
- Short beat: 14 words / 6.0s = 2.35 w/s. ("Rain drums a rhythm on the glass...")
- Longer: 105 words / 24.8s = 4.23 w/s. ("The Midnight Express groaned...")
- HUGE turnaround: previously wedged/timed-out (300s), now 4.23 w/s.
- Prime cores throttled to 24% during run (54-57C) - thermal re-pin fired:
  "re-pinned 7 engine(s) to cool cores 0-5", affinity 0-5 verified via /proc.

## THERMAL RE-PIN FIX (zoe_thermals.py)
- FIXED: is_throttled matched int keys (6,7) but JSON uses strings ("6","7")
  -> hot-core list always empty -> re-pin never fired. Now str(n) match.
- FIXED: ENGINE_MATCHES now includes gemma4_direct (E4B was being missed).
- FIXED: state recording ("state" key, not "prev_state").
- Verified end-to-end: throttle detected, 20s sustained, re-pin fired, affinity 0-5.
