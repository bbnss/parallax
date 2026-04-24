#!/usr/bin/env python3
"""AB Test — Version C: Preview-level title deduplication.

Strategy: the pipeline runs unchanged. After fetching comparisons from DB,
we group clusters that cover the same event (detected via proper-noun overlap
in their titles) and show only the one with the most articles.

No changes to DB or matching logic — purely a display filter.

Run AFTER ab_base.py:
  python scripts/ab_test_c.py

Input:  data/ab_base.db  (must exist)
Output: data/test_c.db, data/preview_c.html
"""
import os
import re
import sys
import shutil
import logging
from pathlib import Path
from datetime import datetime
import unicodedata

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_c")

BASE_DB = PROJECT_ROOT / "data" / "ab_base.db"
TEST_DB_REL = "data/test_c.db"
TEST_DB = PROJECT_ROOT / TEST_DB_REL
OUT_PATH = PROJECT_ROOT / "data" / "preview_c.html"

# Two cluster titles are "same event" if their embedding cosine similarity
# is above this threshold. 0.82 is tight enough to separate "Trump vs Pope"
# from "Iran blockade" while still grouping Islamabad talks variants.
TITLE_SIM_THRESHOLD = 0.78

if not BASE_DB.exists():
    print("ERROR: data/ab_base.db not found. Run ab_base.py first.", file=sys.stderr)
    sys.exit(1)

# ── Isolated DB ──────────────────────────────────────────────────────────────
if TEST_DB.exists():
    TEST_DB.unlink()
shutil.copy2(BASE_DB, TEST_DB)
print(f"Copied {BASE_DB.name} → {TEST_DB_REL}")

os.environ["DB_PATH"] = TEST_DB_REL

from src.db import get_connection
from src.analyzer.matcher import run_matching
from src.analyzer.comparator import process_unpublished_clusters
from src.analyzer.ollama_client import reset_token_stats, get_token_stats


# ── Deduplication logic ──────────────────────────────────────────────────────

def _get_title_embedding(text):
    """Reuse the same sentence-transformers model used for article matching."""
    from src.analyzer.matcher import _get_embedding
    return _get_embedding(text)


def _cosine_sim(a, b):
    from src.analyzer.matcher import _cosine_similarity
    return _cosine_similarity(a, b)


def deduplicate_clusters(comps):
    """For groups of clusters whose titles have embedding cosine sim >= threshold,
    keep only the one with the most articles.

    Uses the same all-MiniLM-L6-v2 model as article matching — semantically
    accurate enough to distinguish 'Trump criticizes Pope about Iran' from
    'US announces Iran blockade' even though both mention Iran.

    Returns (deduped_comps, removed_count, log_lines)
    """
    print(f"   Computing title embeddings for {len(comps)} clusters...")
    embeddings = [_get_title_embedding(c["title"]) for c in comps]

    # Union-Find
    parent = list(range(len(comps)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    sim_log = []
    for i in range(len(comps)):
        for j in range(i + 1, len(comps)):
            if embeddings[i] is None or embeddings[j] is None:
                continue
            sim = _cosine_sim(embeddings[i], embeddings[j])
            if sim >= TITLE_SIM_THRESHOLD:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
                sim_log.append((sim, comps[i]["title"][:55], comps[j]["title"][:55]))

    # Group and pick winner (most articles)
    groups = {}
    for i in range(len(comps)):
        root = find(i)
        groups.setdefault(root, []).append(i)

    kept = set()
    log_lines = []
    for group_indices in groups.values():
        if len(group_indices) == 1:
            kept.add(group_indices[0])
            continue
        # Pick winner: most articles
        winner = max(group_indices, key=lambda i: comps[i]["article_count"])
        kept.add(winner)
        for idx in group_indices:
            if idx != winner:
                log_lines.append(
                    f"  DROP cluster #{comps[idx]['id']} "
                    f"({comps[idx]['article_count']} arts): "
                    f"'{comps[idx]['title'][:60]}'"
                )
        log_lines.append(
            f"  KEEP cluster #{comps[winner]['id']} "
            f"({comps[winner]['article_count']} arts): "
            f"'{comps[winner]['title'][:60]}'"
        )

    if sim_log:
        log_lines.insert(0, f"  Matched pairs (sim >= {TITLE_SIM_THRESHOLD}):")
        for sim, ta, tb in sorted(sim_log, reverse=True)[:10]:
            log_lines.insert(1, f"    {sim:.3f}  '{ta}' ↔ '{tb}'")

    result = [c for i, c in enumerate(comps) if i in kept]
    removed = len(comps) - len(result)
    return result, removed, log_lines


# ── Main ─────────────────────────────────────────────────────────────────────

print("\n" + "=" * 50)
print("AB TEST — VERSION C (preview-level title dedup)")
print("=" * 50)

print("\nStep 1/2: Matching articles (standard pipeline)...")
match_stats = run_matching()
print(f"  {match_stats['pairs']} pairs → {match_stats['clusters']} new clusters")

reset_token_stats()
print("\nStep 2/2: Generating comparisons...")
comp_stats = process_unpublished_clusters()
tok = get_token_stats()
print(f"  Generated: {comp_stats['generated']} | Skipped: {comp_stats['skipped']} | Failed: {comp_stats['failed']}")
print(f"  LLM: {tok['calls']} calls, {tok['total_tokens']:,} tokens")

# ── Custom preview with dedup ─────────────────────────────────────────────────
print("\nGenerating preview_c.html with title deduplication...")

with get_connection() as conn:
    comps = conn.execute('''
        SELECT sc.id, sc.title, sc.event_date, c.comparison_text,
               GROUP_CONCAT(DISTINCT s.name || '@@' || s.region) as sources_raw,
               COUNT(DISTINCT a.id) as article_count
        FROM comparisons c
        JOIN story_clusters sc ON sc.id = c.cluster_id
        JOIN cluster_articles ca ON ca.cluster_id = sc.id
        JOIN articles a ON a.id = ca.article_id
        JOIN sources s ON s.id = a.source_id
        WHERE sc.event_date >= date('now', '-3 days')
        GROUP BY c.id
        ORDER BY sc.event_date DESC, sc.id DESC
    ''').fetchall()

comps = [dict(c) for c in comps]
print(f"  {len(comps)} comparisons before dedup")

comps, removed, log_lines = deduplicate_clusters(comps)
print(f"  {removed} duplicates removed → {len(comps)} shown")
if log_lines:
    print("\n  Dedup decisions:")
    for line in log_lines:
        print(line)

# Build preview HTML
import generate_preview

cards_html = ""
for comp in comps:
    cards_html += generate_preview.build_card(comp, None, None)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NotizieGeopolitica — Preview C (title dedup)</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f172a; color: #e2e8f0; line-height: 1.7;
  }}
  header {{
    background: linear-gradient(135deg, #1e293b, #0f172a);
    border-bottom: 1px solid #334155;
    padding: 2rem; text-align: center;
  }}
  header h1 {{ font-size: 2rem; color: #f1f5f9; letter-spacing: -0.5px; }}
  header p {{ color: #94a3b8; margin-top: 0.5rem; }}
  .badge-c {{
    display: inline-block; background: #065f46; color: #6ee7b7;
    border: 1px solid #6ee7b7; border-radius: 6px;
    font-size: 0.75rem; padding: 0.2rem 0.7rem; margin-top: 0.5rem;
  }}
  .stats {{ display: flex; gap: 1.5rem; justify-content: center; margin-top: 1rem; flex-wrap: wrap; }}
  .stat {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 0.5rem 1rem; font-size: 0.85rem; color: #94a3b8; }}
  .stat strong {{ color: #60a5fa; }}
  main {{ max-width: 900px; margin: 0 auto; padding: 2rem 1rem; }}
  .card {{
    background: #1e293b; border: 1px solid #334155;
    border-radius: 12px; margin-bottom: 2rem; overflow: hidden;
  }}
  .card-header {{
    padding: 1rem 1.5rem 0.5rem; display: flex;
    justify-content: space-between; align-items: center;
    flex-wrap: wrap; gap: 0.5rem; border-bottom: 1px solid #334155;
  }}
  .card-meta {{ display: flex; gap: 1rem; font-size: 0.8rem; color: #64748b; }}
  .card-title {{
    padding: 1rem 1.5rem 0.5rem; font-size: 1.2rem;
    color: #f1f5f9; font-weight: 600; line-height: 1.4;
  }}
  .sources {{ padding: 0.5rem 1.5rem 1rem; display: flex; flex-wrap: wrap; gap: 0.4rem; }}
  .badge {{
    display: inline-block; color: white; font-size: 0.72rem;
    padding: 0.2rem 0.6rem; border-radius: 20px; font-weight: 500; opacity: 0.9;
  }}
  .region-pill {{
    display: inline-block; font-size: 0.65rem; font-weight: 700;
    padding: 0.2rem 0.5rem; border-radius: 4px; border: 1px solid; letter-spacing: 0.5px;
  }}
  .comparison {{ padding: 0.5rem 1.5rem 1.5rem; border-top: 1px solid #334155; }}
  .comparison h3 {{
    font-size: 0.85rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1px; color: #60a5fa; margin: 1.2rem 0 0.4rem;
    padding-bottom: 0.3rem; border-bottom: 1px solid #1e3a5f;
  }}
  .comparison p {{ color: #cbd5e1; font-size: 0.92rem; margin-bottom: 0.3rem; }}
  .comparison li {{ color: #cbd5e1; font-size: 0.92rem; margin-left: 1.2rem; }}
  .comparison strong {{ color: #f1f5f9; }}
  .comparison em {{ color: #94a3b8; font-style: italic; }}
  .comparison br {{ display: block; margin: 0.2rem 0; }}
  footer {{
    text-align: center; padding: 2rem; color: #475569;
    font-size: 0.8rem; border-top: 1px solid #1e293b;
  }}
</style>
</head>
<body>
<header>
  <h1>🌍 NotizieGeopolitica</h1>
  <p>Global News · Multiple Perspectives · Generated by Gemma 4</p>
  <div><span class="badge-c">🧪 Version C — Title dedup ({removed} duplicates removed)</span></div>
  <div class="stats">
    <div class="stat"><strong>{len(comps)}</strong> story comparisons</div>
    <div class="stat"><strong>{removed}</strong> duplicates removed</div>
    <div class="stat"><strong>4</strong> factions</div>
  </div>
</header>
<main>
{cards_html}
</main>
<footer>
  Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} ·
  Version C: preview-level title dedup (title embedding sim >= {TITLE_SIM_THRESHOLD}) ·
  Powered by Gemma 4 via Ollama
</footer>
</body>
</html>"""

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅ Version C complete → {OUT_PATH}")
