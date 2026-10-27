#!/bin/bash
# sync_graphrag.sh - Full GraphRAG sync: extract, merge, push to sanctuary

WORKSPACE="/mnt/android/hermes-workspace"
GRAPH_DIR="$WORKSPACE/state/graphrag"
SANCTUARY="$WORKSPACE/Zoe-s-sanctuary-circus"
LOG_FILE="$GRAPH_DIR/sync.log"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $1" | tee -a "$LOG_FILE"
}

cd "$GRAPH_DIR"
log "=== GraphRAG Sync Started ==="

# 1. Qwen extraction
log "Running Qwen extraction..."
python3 llm_extract_qwen.py >> "$LOG_FILE" 2>&1
log "Extraction complete."

# 2. Merge all caches
log "Merging LLM caches..."
python3 merge_llm.py >> "$LOG_FILE" 2>&1
log "Merge complete."

# 3. Stats
python3 -c "
import json
c = json.load(open('cache.json'))
print(f'Final: {len(c[\"entities\"])} entities, {len(c[\"relations\"])} relations, {len(c[\"messages_index\"])} messages')
" | tee -a "$LOG_FILE"

# 4. Push code to sanctuary repo
cd "$SANCTUARY"
mkdir -p graphrag
cp "$GRAPH_DIR"/*.py graphrag/
cp "$GRAPH_DIR"/*.sh graphrag/ 2>/dev/null
git add graphrag/
if git diff --cached --quiet; then
    log "No code changes to push."
else
    git commit -m "graphrag sync $(date -u +%Y-%m-%d)" >> "$LOG_FILE" 2>&1
    git push origin main >> "$LOG_FILE" 2>&1
    log "Pushed to sanctuary."
fi

log "=== GraphRAG Sync Complete ==="
