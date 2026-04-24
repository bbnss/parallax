#!/bin/bash
# NotizieGeopolitica — tmux workspace
# Usage: bash scripts/tmux_notizie.sh
# Or:    make tmux

SESSION="notizie"
PROJECT="/Users/bbnss/kDrive2/Claude/NotizieGeopolitica"
VENV="$PROJECT/.venv/bin/python"
LOG="$PROJECT/data/pipeline.log"
OVERVIEW="$PROJECT/data/pipeline_overview.txt"

# Kill existing session if present
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create new session (detached), first window
tmux new-session -d -s "$SESSION" -n "control" -x 220 -y 50

# ─────────────────────────────────────────────────────────────────
# WINDOW 1: "control" — layout principale 3 panes
#
#  ┌─────────────────────┬──────────────────────────────────────┐
#  │                     │                                      │
#  │   PIPELINE OVERVIEW │   LIVE LOG  (tail -f pipeline.log)  │
#  │   (static display)  │                                      │
#  │                     ├──────────────────────────────────────┤
#  │                     │   DB STATUS  (watch ogni 30s)        │
#  │                     │                                      │
#  ├─────────────────────┴──────────────────────────────────────┤
#  │   CONTROL / COMMAND  (bash interattivo)                    │
#  └────────────────────────────────────────────────────────────┘
# ─────────────────────────────────────────────────────────────────

# Pane 0 (top-left): Pipeline Overview
tmux send-keys -t "$SESSION:control.0" \
    "cd '$PROJECT' && clear && cat '$OVERVIEW'" Enter

# Split vertical → crea pane 1 (top-right, 60% width)
tmux split-window -t "$SESSION:control.0" -h -p 60

# Pane 1 (top-right): Live Log
tmux send-keys -t "$SESSION:control.1" \
    "cd '$PROJECT' && touch '$LOG' && clear && echo '[ LIVE LOG — pipeline.log ]' && echo '' && tail -f '$LOG'" Enter

# Split pane 1 horizontal → crea pane 2 (middle-right, DB status)
tmux split-window -t "$SESSION:control.1" -v -p 40

# Pane 2 (middle-right): DB Status aggiornato ogni 30s
tmux send-keys -t "$SESSION:control.2" \
    "cd '$PROJECT' && source .venv/bin/activate && watch -n 30 'python -m src.cli status 2>/dev/null'" Enter

# Split pane 0 horizontal → crea pane 3 (bottom, full width)
tmux split-window -t "$SESSION:control.0" -v -p 30

# Pane 3 (bottom): Control bash con venv attivato e utility functions
tmux send-keys -t "$SESSION:control.3" \
    "cd '$PROJECT' && source .venv/bin/activate" Enter
tmux send-keys -t "$SESSION:control.3" \
    "clear && echo '╔══ NotizieGeopolitica — Control Shell ══╗' && echo '' && echo '  make collect       → raccolta RSS + scraping' && echo '  make collect-fast  → raccolta senza scraping (test)' && echo '  make analyze       → analisi LLM completa' && echo '  make status        → stato database' && echo '  make pipeline      → tutto in sequenza' && echo '' && echo '  python -m src.cli analyze --limit 20 -v' && echo '  python -m src.cli collect --skip-scrape -v' && echo ''" Enter

# ─────────────────────────────────────────────────────────────────
# WINDOW 2: "collect" — output raccolta articoli
# ─────────────────────────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "collect"
tmux send-keys -t "$SESSION:collect" \
    "cd '$PROJECT' && source .venv/bin/activate && clear && echo '[ COLLECT — premi INVIO per avviare, o usa: make collect ]' && echo ''" Enter

# ─────────────────────────────────────────────────────────────────
# WINDOW 3: "analyze" — output analisi LLM
# ─────────────────────────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "analyze"
tmux send-keys -t "$SESSION:analyze" \
    "cd '$PROJECT' && source .venv/bin/activate && clear && echo '[ ANALYZE — premi INVIO per avviare, o usa: make analyze ]' && echo ''" Enter

# ─────────────────────────────────────────────────────────────────
# WINDOW 4: "db" — SQLite browser interattivo
# ─────────────────────────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "db"

# Layout 2 panes: top = query veloci, bottom = sqlite3 shell
tmux split-window -t "$SESSION:db" -v -p 40
tmux send-keys -t "$SESSION:db.0" \
    "cd '$PROJECT' && source .venv/bin/activate && clear" Enter
tmux send-keys -t "$SESSION:db.0" \
    "echo '[ DB QUERIES RAPIDE ]'" Enter
tmux send-keys -t "$SESSION:db.0" \
    "echo 'Esempi:'" Enter
tmux send-keys -t "$SESSION:db.0" \
    "echo \"  python -m src.cli status\"" Enter
tmux send-keys -t "$SESSION:db.0" \
    "echo \"  sqlite3 data/notizie.db 'SELECT s.name, COUNT(*) FROM articles a JOIN sources s ON a.source_id=s.id GROUP BY s.name'\"" Enter
tmux send-keys -t "$SESSION:db.0" \
    "echo \"  sqlite3 data/notizie.db 'SELECT id, title FROM story_clusters ORDER BY created_at DESC LIMIT 5'\"" Enter
tmux send-keys -t "$SESSION:db.0" \
    "echo \"  sqlite3 data/notizie.db 'SELECT id, substr(comparison_text,1,200) FROM comparisons LIMIT 1'\"" Enter
tmux send-keys -t "$SESSION:db.0" \
    "echo ''" Enter

tmux send-keys -t "$SESSION:db.1" \
    "cd '$PROJECT' && sqlite3 data/notizie.db '.headers on' '.mode column'" Enter
tmux send-keys -t "$SESSION:db.1" \
    "echo '[ SQLite shell — database notizie.db ]'" Enter

# ─────────────────────────────────────────────────────────────────
# WINDOW 5: "log" — log file completo
# ─────────────────────────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "log"
tmux send-keys -t "$SESSION:log" \
    "cd '$PROJECT' && touch '$LOG' && clear && echo '[ LOG COMPLETO — pipeline.log ]' && echo '' && less +F '$LOG'" Enter

# Torna alla finestra principale
tmux select-window -t "$SESSION:control"
tmux select-pane -t "$SESSION:control.3"

# Attach alla sessione
tmux attach-session -t "$SESSION"
