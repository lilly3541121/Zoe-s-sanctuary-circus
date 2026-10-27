#!/bin/bash
# finish_graphrag.sh - Completes the GraphRAG pipeline after LLM extraction.
# Called by cron when extraction is done: merge caches, rebuild graph, sync to sanctuary.
set -e
export VIRTUAL_ENV=/root/.llm-venv
export PATH="/root/.hermes/bin:$PATH"
WORKSPACE="/mnt/android/hermes-workspace"
GRAPH_DIR="$WORKSPACE/state/graphrag"
LOG="$GRAPH_DIR/finish.log"
echo "[$(date -u +%FT%TZ)] finishing graphrag" >> "$LOG"

# 1. Merge all LLM caches into graph
echo "merging LLM caches..." >> "$LOG"
/root/.llm-venv/bin/python3 "$WORKSPACE/zoe-graphrag/merge_llm.py" >> "$LOG" 2>&1

# 2. Rebuild the graph (keeps naive extraction + merged LLM entities)
echo "rebuilding graph..." >> "$LOG"
cd "$WORKSPACE/zoe-graphrag"
export GRAPH_DIR="$GRAPH_DIR"
/root/.llm-venv/bin/python3 graphrag.py build >> "$LOG" 2>&1

# 3. Sync code to sanctuary
echo "syncing to sanctuary..." >> "$LOG"
cd "$WORKSPACE/Zoe-s-sanctuary-circus"
cp "$GRAPH_DIR"/*.py graphrag/ 2>/dev/null || true
cp "$GRAPH_DIR"/*.sh graphrag/ 2>/dev/null || true
cp "$WORKSPACE/zoe-graphrag/graphrag.py" graphrag/ 2>/dev/null || true
cp "$WORKSPACE/zoe-graphrag/merge_llm.py" graphrag/ 2>/dev/null || true
git add graphrag/
if ! git diff --cached --quiet; then
    git -c user.name="zoe" -c user.email="zoe@local" commit -m "graphrag sync $(date -u +%Y-%m-%d)" >> "$LOG" 2>&1 || true
fi

# 4. Final stats
echo "final stats:" >> "$LOG"
/root/.llm-venv/bin/python3 -c "
import json
c=json.load(open('$GRAPH_DIR/cache.json'))
print(f'  {len(c[\"entities\"])} entities, {len(c[\"relations\"])} relations, {len(c[\"messages_index\"])} messages')" >> "$LOG" 2>&1
echo "[$(date -u +%FT%TZ)] graphrag finish complete" >> "$LOG"
