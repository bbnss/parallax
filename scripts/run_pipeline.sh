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
# The built site lives next to the DB, outside kDrive: kDrive evicts files, and
# this directory is the local mirror of the append-only archive on gh-pages.
export PARALLAX_SITE_DIR="${PARALLAX_SITE_DIR:-/Users/bbnss/parallax-data/site}"
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

# Step 3: Generate preview (multi-language) + archive + feeds
# The archive is append-only and gh-pages is its only backup. If the local
# mirror went missing (new machine, wiped disk), pull it back before building —
# otherwise this run would produce an archive holding only the last 3 days and
# deploy_site.sh would rightly refuse to publish it.
if [ ! -f "$PARALLAX_SITE_DIR/archive/manifest.json" ]; then
    log "Step 3: Local site mirror absent — restoring from gh-pages..."
    rm -rf /tmp/parallax-restore
    if git clone --branch gh-pages --single-branch --depth 1 \
            "${PARALLAX_REPO_URL:-https://github.com/bbnss/parallax.git}" \
            /tmp/parallax-restore >> "$LOG_FILE" 2>&1; then
        mkdir -p "$PARALLAX_SITE_DIR"
        rsync -a --exclude '.git' /tmp/parallax-restore/ "$PARALLAX_SITE_DIR"/ >> "$LOG_FILE" 2>&1
        rm -rf /tmp/parallax-restore
        log "Step 3: Mirror restored"
    else
        log "Step 3: Restore FAILED (starting from an empty archive)"
    fi
fi

log "Step 3: Generating preview (5 languages, last 3 days) + archive + feeds..."
if $VENV scripts/generate_preview.py --days 3 --no-open >> "$LOG_FILE" 2>&1; then
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

# Step 6: v2 fact-extraction pipeline (parallel — runs on the same clusters
# v1 covered, writes to data/v2/ in the v2 worktree). Failure here does NOT
# affect v1's output, which is already deployed.
V2_DIR="$PROJECT_DIR/v2"
if [ "$PIPELINE_OK" = "1" ] && [ -x "$V2_DIR/.venv/bin/python" ]; then
    log "Step 6: Running v2 fact-extraction pipeline..."
    if (cd "$V2_DIR" && .venv/bin/python scripts/v2/run_daily.py) >> "$LOG_FILE" 2>&1; then
        log "Step 6: OK"
    else
        log "Step 6: FAILED (v2 only — v1 already deployed)"
    fi
else
    log "Step 6: SKIPPED (v2 worktree absent or v1 had errors)"
fi

# Step 7: Status
log "Final status:"
$VENV -m src.cli status >> "$LOG_FILE" 2>&1

log "Pipeline complete"
log "========================================"
