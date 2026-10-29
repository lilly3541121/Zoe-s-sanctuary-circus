#!/bin/bash
# zoe_supervisor.sh - Auto-starts the engine stack + monitor + watcher + GC daemons.
# Run at boot / after restart. Idempotent: only starts what's not already running.
set -u

PY=/root/.llm-venv/bin/python3
ENGINE_MANAGER=/root/engine_manager.py
MONITOR=/root/zoe_monitor.py
WATCHER=/root/zoe_watcher.py
THERMALS=/root/zoe_thermals.py
WATCHDOG=/root/zoe_watchdog.py

echo "[zoe-supervisor] $(date '+%F %T') starting supervision..."

# 1. Ensure monitor daemon is running
if pgrep -f "zoe_monitor.py" >/dev/null 2>&1; then
  echo "[zoe-supervisor] monitor already running"
else
  echo "[zoe-supervisor] starting monitor..."
  nohup "$PY" "$MONITOR" >> /mnt/android/hermes-workspace/state/monitor/supervisor.log 2>&1 &
fi

# 2. Ensure watcher daemon is running
if pgrep -f "zoe_watcher.py" >/dev/null 2>&1; then
  echo "[zoe-supervisor] watcher already running"
else
  echo "[zoe-supervisor] starting watcher..."
  nohup "$PY" "$WATCHER" >> /mnt/android/hermes-workspace/state/watcher/supervisor.log 2>&1 &
fi

# 3. Ensure thermal manager is running
if pgrep -f "zoe_thermals.py" >/dev/null 2>&1; then
  echo "[zoe-supervisor] thermals already running"
else
  echo "[zoe-supervisor] starting thermals..."
  nohup "$PY" "$THERMALS" >> /mnt/android/hermes-workspace/state/monitor/thermals_supervisor.log 2>&1 &
fi

# 4. Ensure watchdog is running
if pgrep -f "zoe_watchdog.py" >/dev/null 2>&1; then
  echo "[zoe-supervisor] watchdog already running"
else
  echo "[zoe-supervisor] starting watchdog..."
  nohup "$PY" "$WATCHDOG" >> /mnt/android/hermes-workspace/state/watchdog/supervisor.log 2>&1 &
fi

# 3. Bring the resident engine stack up (idempotent - only starts what's down)
echo "[zoe-supervisor] ensuring resident stack..."
"$PY" "$ENGINE_MANAGER" start-resident 2>&1 | grep -E "UP|down|WARNING" || true

# 4. Run the GC once (classify + move trash; safe, whitelist-protected)
echo "[zoe-supervisor] running GC sweep..."
"$PY" /root/zoe_gc.py --limit 10 2>&1 | grep -E "TRASH|KEEP|done|sweeping" | tail -5 || true

echo "[zoe-supervisor] done. Stack + monitor + watcher up."
