#!/bin/bash
# NotizieGeopolitica — Full nightly pipeline
# Runs: collect → analyze → (future: generate → build → deploy)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/data/pipeline.log"
VENV="$PROJECT_DIR/.venv/bin/python"
LIVE_DB="/Users/bbnss/parallax-data/notizie.db"
BACKUP_DB="$PROJECT_DIR/data/notizie.db"
PIPELINE_OK=1

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
    PIPELINE_OK=0
fi

# Step 2: Analyze
log "Step 2: Analyzing articles (summarize → match → compare)..."
if $VENV -m src.cli analyze >> "$LOG_FILE" 2>&1; then
    log "Step 2: OK"
else
    log "Step 2: FAILED"
    exit 1
fi

# Step 3: Generate preview (multi-language)
log "Step 3: Generating preview (5 languages, last 3 days)..."
if $VENV scripts/generate_preview.py --days 3 >> "$LOG_FILE" 2>&1; then
    log "Step 3: OK"
else
    log "Step 3: FAILED (continuing anyway)"
    PIPELINE_OK=0
fi

# Step 4: Deploy to GitHub Pages
log "Step 4: Deploying to GitHub Pages..."
if bash "$SCRIPT_DIR/deploy_site.sh" >> "$LOG_FILE" 2>&1; then
    log "Step 4: OK"
else
    log "Step 4: FAILED (site not updated)"
    PIPELINE_OK=0
fi

# Step 5: Backup DB to kDrive (only on full success — kDrive syncs a static file)
if [ "$PIPELINE_OK" = "1" ]; then
    log "Step 5: Backing up DB to kDrive..."
    if cp "$LIVE_DB" "$BACKUP_DB" >> "$LOG_FILE" 2>&1; then
        log "Step 5: OK"
    else
        log "Step 5: FAILED (backup not updated)"
    fi
else
    log "Step 5: SKIPPED (pipeline had errors — backup not refreshed)"
fi

# Step 6: Status
log "Final status:"
$VENV -m src.cli status >> "$LOG_FILE" 2>&1

log "Pipeline complete"
log "========================================"
