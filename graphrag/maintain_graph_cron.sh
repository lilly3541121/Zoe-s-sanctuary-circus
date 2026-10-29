#!/usr/bin/env bash
# maintain_graph_cron.sh — run the tri-tier maintenance cycle.
# Wi-Fi-gated: only pushes when connected (maintain_graph.py's push step handles
# the git side; this script gates the whole cycle to keep battery/thermal sane).
# Sourced from cron shells which lack GH_TOKEN — maintain_graph.py reads it from
# /root/.hermes/graphrag_token.env itself.

set -euo pipefail

GRAPH_DIR="/mnt/android/hermes-workspace/state/graphrag"
PY="/root/.llm-venv/bin/python3"
SCRIPT="/mnt/android/hermes-workspace/zoe-graphrag/maintain_graph.py"

# Wi-Fi gate (only run the full cycle if connected, to avoid battery/thermal)
if command -v nmcli >/dev/null 2>&1; then
  state=$(nmcli -t -f WIFI-STATE g 2>/dev/null || echo "unknown")
  if [ "$state" != "enabled" ] && [ "$state" != "connected" ]; then
    echo "[maintain-graph] Wi-Fi inactive ($state). Skipping cycle."
    exit 0
  fi
fi

echo "[maintain-graph] $(date -Iseconds) — starting maintenance cycle"

# Self-heal: Qwen wedges under sustained load (process alive, no response).
# Check + restart her BEFORE the cycle so the build/merge never finds her dead.
"$PY" /root/engine.py watchdog 2>&1 | grep -vE "llama_kv|pad V"

"$PY" "$SCRIPT" 2>&1 | grep -vE "llama_kv|pad V"
CYCLE_EXIT=$?
echo "[maintain-graph] cycle exit: $CYCLE_EXIT"

# Vector 3: after a successful cycle, record the pushed baseline so drift
# detection has a reference. Also check for drift (auto-merge if the remote moved).
if [ "$CYCLE_EXIT" -eq 0 ]; then
  echo "[maintain-graph] recording synced hash baseline"
  "$PY" /mnt/android/hermes-workspace/zoe-graphrag/drift_merge.py --record 2>&1 | tail -1
fi
echo "[maintain-graph] drift check:"
"$PY" /mnt/android/hermes-workspace/zoe-graphrag/drift_merge.py --check 2>&1 | tail -1
