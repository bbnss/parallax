.PHONY: setup collect collect-fast status analyze generate build deploy pipeline clean-cache tmux help titles sources

PYTHON := .venv/bin/python
PIP := .venv/bin/pip

help:
	@echo "NotizieGeopolitica Pipeline"
	@echo ""
	@echo "  make titles           List all story titles in current preview (last 3 days)"
	@echo "  make sources          List all source articles used in current preview"
	@echo "  make preview          Generate preview (TranslateGemma translation)"
	@echo "  make preview-tg       Generate preview with TranslateGemma translation → preview_tg.html"
	@echo "  make preview-compare  Open both previews side by side"
	@echo "  make tmux         Open full tmux workspace (recommended)"
	@echo "  make setup        First-time environment setup"
	@echo "  make collect      Fetch articles from all RSS feeds (with scraping)"
	@echo "  make collect-fast Fetch articles without full-text scraping (test)"
	@echo "  make status       Show database status"
	@echo "  make analyze      Run LLM analysis and story matching (Phase 2)"
	@echo "  make generate     Generate Hugo content files (Phase 3)"
	@echo "  make build        Build Hugo static site (Phase 3)"
	@echo "  make deploy       Deploy to Cloudflare/GitHub Pages (Phase 3)"
	@echo "  make pipeline     Run full pipeline: collect → analyze → generate → build → deploy"
	@echo "  make clean-cache  Clear HTTP cache"

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "Setup complete! Activate with: source .venv/bin/activate"
	@echo "Then run: make collect"

collect:
	$(PYTHON) -m src.cli collect

collect-fast:
	$(PYTHON) -m src.cli collect --skip-scrape

status:
	$(PYTHON) -m src.cli status

analyze:
	$(PYTHON) -m src.cli analyze

generate:
	$(PYTHON) -m src.cli generate

build:
	cd site && hugo

deploy:
	cd site && npx wrangler pages deploy public/ --project-name=notiziegeopolitica

pipeline: collect analyze generate build deploy

tmux:
	@bash scripts/start_pipeline.sh both

tmux-collect:
	@bash scripts/start_pipeline.sh collect

tmux-analyze:
	@bash scripts/start_pipeline.sh analyze

preview:
	$(PYTHON) scripts/generate_preview.py --days 3

preview-tg:
	$(PYTHON) scripts/generate_preview.py --days 1 \
		--translate-model translategemma:latest \
		--out data/preview_tg.html

preview-compare:
	@echo "Opening both previews side by side..."
	open data/preview.html
	sleep 0.5
	open data/preview_tg.html

preview-week:
	$(PYTHON) scripts/generate_preview.py --days 7

preview-fast:
	$(PYTHON) scripts/generate_preview.py --no-translate --days 1

titles:
	@$(PYTHON) -c "\
import sqlite3, sys; \
sys.path.insert(0, '.'); \
from datetime import date, timedelta; \
from scripts.generate_preview import _deduplicate_comparisons; \
conn = sqlite3.connect('data/notizie.db'); \
conn.row_factory = sqlite3.Row; \
rows = conn.execute('''SELECT sc.id, sc.title, sc.event_date, COUNT(DISTINCT a.id) as article_count, GROUP_CONCAT(DISTINCT s.region) as regions FROM comparisons c JOIN story_clusters sc ON sc.id = c.cluster_id JOIN cluster_articles ca ON ca.cluster_id = sc.id JOIN articles a ON a.id = ca.article_id JOIN sources s ON s.id = a.source_id WHERE sc.event_date >= ? GROUP BY sc.id ORDER BY sc.event_date DESC, sc.id DESC''', (str(date.today() - timedelta(days=3)),)).fetchall(); \
conn.close(); \
comps = [dict(r) for r in rows]; \
result = _deduplicate_comparisons(comps); \
print(f'\nPreview: {len(result)} storie (ultimi 3 giorni)\n'); \
[print(f'{i:>2}. [{c[\"event_date\"]}] {c[\"article_count\"]:>2} arts | {(c[\"regions\"] or \"\").replace(\",\",\"/\"):<35} {c[\"title\"]}') for i, c in enumerate(result, 1)] \
" 2>&1 | grep -v urllib3 | grep -v NotOpenSSL | grep -v warnings

sources:
	@$(PYTHON) -c "\
import sqlite3, sys; \
sys.path.insert(0, '.'); \
from datetime import date, timedelta; \
from scripts.generate_preview import _deduplicate_comparisons; \
conn = sqlite3.connect('data/notizie.db'); \
conn.row_factory = sqlite3.Row; \
rows = conn.execute('''SELECT sc.id, sc.title, sc.event_date, COUNT(DISTINCT a.id) as article_count, GROUP_CONCAT(DISTINCT s.region) as regions FROM comparisons c JOIN story_clusters sc ON sc.id = c.cluster_id JOIN cluster_articles ca ON ca.cluster_id = sc.id JOIN articles a ON a.id = ca.article_id JOIN sources s ON s.id = a.source_id WHERE sc.event_date >= ? GROUP BY sc.id ORDER BY sc.event_date DESC, sc.id DESC''', (str(date.today() - timedelta(days=3)),)).fetchall(); \
comps = [dict(r) for r in rows]; \
result = _deduplicate_comparisons(comps); \
[print(f'\n{\"=\"*70}\n[{c[\"event_date\"]}] #{c[\"id\"]} — {c[\"title\"]}\n{\"=\"*70}') or [print(f'  [{a[\"region\"]:<12}] {a[\"name\"]:<22} {a[\"title\"]}') for a in conn.execute('SELECT a.title, s.name, s.region FROM cluster_articles ca JOIN articles a ON a.id=ca.article_id JOIN sources s ON s.id=a.source_id WHERE ca.cluster_id=? ORDER BY s.region, s.name', (c['id'],)).fetchall()] for c in result]; \
conn.close() \
" 2>&1 | grep -v urllib3 | grep -v NotOpenSSL | grep -v warnings

clean-cache:
	rm -rf data/cache/*
	@echo "Cache cleared."
