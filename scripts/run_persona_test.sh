#!/bin/bash
# run_persona_test.sh — Run all 3 journalist persona tests sequentially.
#
# Usage:
#   ./scripts/run_persona_test.sh           # run A, B, C
#   ./scripts/run_persona_test.sh --a       # only persona A
#   ./scripts/run_persona_test.sh --b       # only persona B
#   ./scripts/run_persona_test.sh --c       # only persona C

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

[ -d ".venv" ] && source .venv/bin/activate

log() { echo -e "\n\033[1;36m>>> $1\033[0m"; }
ok()  { echo -e "\033[1;32m✅ $1\033[0m"; }
err() { echo -e "\033[1;31m❌ $1\033[0m" >&2; }

RUN_A=false; RUN_B=false; RUN_C=false; RUN_ALL=false
[ $# -eq 0 ] && RUN_ALL=true
for arg in "$@"; do
    case "$arg" in
        --a) RUN_A=true ;; --b) RUN_B=true ;; --c) RUN_C=true ;;
        *) err "Unknown: $arg"; exit 1 ;;
    esac
done
$RUN_ALL && RUN_A=true && RUN_B=true && RUN_C=true

if [ ! -f "data/ab_base.db" ]; then
    log "Base DB not found — building it first..."
    python scripts/ab_base.py
fi

if $RUN_A; then
    log "Persona A — Populist / Anti-Establishment (Tucker Carlson school)"
    python scripts/ab_persona_test.py --persona A
    ok "Persona A done → data/preview_persona_A.html"
fi

if $RUN_B; then
    log "Persona B — Investigative / Civil-Liberties (Greenwald school)"
    python scripts/ab_persona_test.py --persona B
    ok "Persona B done → data/preview_persona_B.html"
fi

if $RUN_C; then
    log "Persona C — Policy-Analytical / Internationalist (Zakaria school)"
    python scripts/ab_persona_test.py --persona C
    ok "Persona C done → data/preview_persona_C.html"
fi

echo ""
echo "============================================"
echo " Persona Test Results"
echo "============================================"
for letter in A B C; do
    f="data/preview_persona_${letter}.html"
    [ -f "$f" ] && echo "  preview_persona_${letter}.html ✓"
done
echo ""

# Open all generated previews side by side
for letter in A B C; do
    f="data/preview_persona_${letter}.html"
    [ -f "$f" ] && open "$f" && sleep 0.5
done
