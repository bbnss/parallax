#!/bin/bash
# run_ab_test.sh — Orchestrates the 3 AB test versions.
#
# Usage:
#   ./scripts/run_ab_test.sh           # run all 3
#   ./scripts/run_ab_test.sh --base    # only build base DB (step 0)
#   ./scripts/run_ab_test.sh --a       # only test A (needs base)
#   ./scripts/run_ab_test.sh --b       # only test B (uses live notizie.db)
#   ./scripts/run_ab_test.sh --c       # only test C (needs base)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Activate virtualenv if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

log() { echo -e "\n\033[1;36m>>> $1\033[0m"; }
ok()  { echo -e "\033[1;32m✅ $1\033[0m"; }
err() { echo -e "\033[1;31m❌ $1\033[0m" >&2; }

# Parse args
RUN_BASE=false
RUN_A=false
RUN_B=false
RUN_C=false
RUN_ALL=false

if [ $# -eq 0 ]; then
    RUN_ALL=true
else
    for arg in "$@"; do
        case "$arg" in
            --base) RUN_BASE=true ;;
            --a)    RUN_A=true ;;
            --b)    RUN_B=true ;;
            --c)    RUN_C=true ;;
            *)      err "Unknown argument: $arg"; exit 1 ;;
        esac
    done
fi

if $RUN_ALL; then
    RUN_BASE=true; RUN_A=true; RUN_B=true; RUN_C=true
fi

# ── Step 0: Build base DB ────────────────────────────────────────────────────
if $RUN_BASE; then
    log "Step 0: Building fresh base DB (collect + summarize)..."
    python scripts/ab_base.py
    ok "Base DB ready → data/ab_base.db"
fi

# ── Version A: post-build cluster merge ─────────────────────────────────────
if $RUN_A; then
    if [ ! -f "data/ab_base.db" ]; then
        err "data/ab_base.db not found — run with --base first"
        exit 1
    fi
    log "Version A: matching + centroid merge (threshold=0.80)..."
    python scripts/ab_test_a.py
    ok "Version A done → data/preview_a.html"
fi

# ── Version B: include recent matched articles ───────────────────────────────
if $RUN_B; then
    if [ ! -f "data/notizie.db" ]; then
        err "data/notizie.db not found"
        exit 1
    fi
    log "Version B: extended matching (include matched <72h)..."
    python scripts/ab_test_b.py
    ok "Version B done → data/preview_b.html"
fi

# ── Version C: preview-level title dedup ────────────────────────────────────
if $RUN_C; then
    if [ ! -f "data/ab_base.db" ]; then
        err "data/ab_base.db not found — run with --base first"
        exit 1
    fi
    log "Version C: standard pipeline + title dedup in preview..."
    python scripts/ab_test_c.py
    ok "Version C done → data/preview_c.html"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "============================================"
echo " AB Test Results"
echo "============================================"
for letter in a b c; do
    f="data/preview_${letter}.html"
    if [ -f "$f" ]; then
        count=$(grep -c 'class="card"' "$f" 2>/dev/null || echo "?")
        echo "  preview_${letter}.html — ${count} cards"
    fi
done
echo ""

# Open all generated previews
for letter in a b c; do
    f="data/preview_${letter}.html"
    if [ -f "$f" ]; then
        open "$f"
        sleep 0.5
    fi
done
