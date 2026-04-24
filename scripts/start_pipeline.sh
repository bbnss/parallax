#!/bin/bash
# NotizieGeopolitica — Start full pipeline in tmux
# Usage: bash scripts/start_pipeline.sh [collect|analyze|both]
#        bash scripts/start_pipeline.sh collect  → apre tmux + avvia make collect
#        bash scripts/start_pipeline.sh analyze  → apre tmux + avvia make analyze
#        bash scripts/start_pipeline.sh both     → apre tmux + avvia collect poi analyze

set -euo pipefail

PROJECT="/Users/bbnss/kDrive2/Claude/NotizieGeopolitica"
SESSION="notizie"
ACTION="${1:-both}"

cd "$PROJECT"

# Kill existing session if present
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Start fresh tmux session
echo "🚀 Avviando NotizieGeopolitica tmux workspace..."
bash scripts/tmux_notizie.sh &
TMUX_PID=$!
sleep 3

# Function to send command to a window
send_to_window() {
    local window=$1
    local cmd=$2
    tmux send-keys -t "$SESSION:$window" "$cmd" Enter
}

case "$ACTION" in
    collect)
        echo "📥 Avviando COLLECT (raccolta RSS + scraping)..."
        send_to_window "collect" "make collect"
        echo ""
        echo "✅ Pipeline avviato:"
        echo "   • Window 0 (control): Panoramica + log live"
        echo "   • Window 2 (collect): In esecuzione..."
        echo ""
        echo "Per vedere tutti i log: Ctrl+B e poi:"
        echo "   :1 collect  → raccolta in tempo reale"
        echo "   :2 analyze  → (farà partire automaticamente dopo)"
        echo "   :0 log     → log file completo"
        ;;

    analyze)
        echo "🧠 Avviando ANALYZE (LLM summarize + match + compare)..."
        send_to_window "analyze" "make analyze"
        echo ""
        echo "✅ Pipeline avviato:"
        echo "   • Window 0 (control): Panoramica + log live"
        echo "   • Window 3 (analyze): In esecuzione..."
        ;;

    both)
        echo "🔄 Avviando FULL PIPELINE (collect → analyze)..."
        send_to_window "collect" "make collect && echo '✅ COLLECT complete!' && sleep 5 && tmux send-keys -t '$SESSION:analyze' 'make analyze' Enter"
        echo ""
        echo "✅ Pipeline avviato:"
        echo "   • Window 2 (collect): In esecuzione..."
        echo "   • Window 3 (analyze): Partirà automaticamente dopo collect"
        echo ""
        echo "Tempo stimato:"
        echo "   • Collect (scraping): ~20 minuti"
        echo "   • Analyze (LLM):      ~3-4 ore"
        echo "   • Totale:             ~4 ore"
        ;;

    *)
        echo "❌ Uso: $0 [collect|analyze|both]"
        exit 1
        ;;
esac

echo ""
echo "📺 Tmux session: tmux attach -t $SESSION"
echo "   Ctrl+B, poi:"
echo "   - 0: Control + Live Log"
echo "   - 1: Collect output"
echo "   - 2: Analyze output"
echo "   - 3: DB queries"
echo "   - 4: Full log"
echo ""
echo "⏸️  Per stoppare qualsiasi momento: Ctrl+C nel pane interessato"
echo ""
