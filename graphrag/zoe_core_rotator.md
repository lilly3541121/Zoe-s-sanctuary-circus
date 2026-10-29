# Core rotator - rotate to fresh cores after every output (2026-10-29)

User insight: models heat in bursts producing ~25 w/s. Instead of waiting for
throttle (reactive), proactively ROTATE to fresh cores after every output.

## HOW IT WORKS (zoe_core_rotator.py, daemon)
- Watches each engine's /proc/<pid>/stat tick rate every 2s (scale-free jiffies/sec).
- Detects BUSY (rate jumps, e.g. 315 t/s) = request arrived / thinking.
- Detects output DONE (rate drops to ~0) = generation finished.
- On BUSY: set affinity to next set (generation lands on fresh cores - "after
  thinking before responding").
- On output DONE: rotate schedule_index to next set (heat spreads - "after output").
- Rotation schedule: ["0-5" (perf cores), "0-7" (all 8)]. SKIPS 0-7 when prime
  cores (6,7) are throttled (monitor live.json) - stays on cool cores when hot.
- Verified end-to-end: BUSY(315t/s)->ready on 0-5, output DONE(0t/s)->rotate.
  Affinity changes stick (confirmed via /proc/<pid>/status, 0-5 and 0-7 both apply).

## KEY LESSON (CPU% calibration)
- /proc/<pid>/stat tick deltas on qroot count at an UNKNOWN scale (a short
  generation showed "39087%" with HZ=100 assumption). ABSOLUTE % thresholds are
  meaningless. Use scale-free tick-rate: idle ~0 t/s, busy = orders of magnitude
  higher. Compare to a rolling idle baseline (BUSY_MULTIPLE=5x) + absolute
  IDLE_TICKS_PER_SEC=8. This is the robust way to detect busy/idle here.
