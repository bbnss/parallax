#!/bin/bash
# NotizieGeopolitica — Full nightly pipeline
# Runs: collect → analyze → (future: generate → build → deploy)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/data/pipeline.log"
VENV="$PROJECT_DIR/.venv/bin/python"

cd "$PROJECT_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "========================================"
log "Pipeline started"

# Step 1: Collect
log "Step 1: Collecting RSS feeds (with full-text scraping)..."
if $VENV -m src.cli collect >> "$LOG_FILE" 2>&1; then
    log "Step 1: OK"
else
    log "Step 1: FAILED (continuing anyway)"
fi

# Step 2: Analyze
log "Step 2: Analyzing articles (summarize → match → compare)..."
if $VENV -m src.cli analyze >> "$LOG_FILE" 2>&1; then
    log "Step 2: OK"
else
    log "Step 2: FAILED"
    exit 1
fi

# Step 3: Status
log "Final status:"
$VENV -m src.cli status >> "$LOG_FILE" 2>&1

log "Pipeline complete"
log "========================================"
