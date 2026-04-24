#!/usr/bin/env python3
"""AB Test — Version B: Matching includes recently matched articles (<72h).

Strategy: the standard pipeline only matches unmatched articles (matched=0).
This causes fragmentation: if article X matches articles A+B but not C, and C
was already matched in a previous run, X forms a new cluster instead of joining
the existing one that contains C.

This version widens the matching pool to include articles that were matched in
the last 72 hours, so freshly processed articles can "attach" to recent clusters
instead of spawning duplicates.

Uses a copy of the current notizie.db so existing state is preserved.

Usage:
  python scripts/ab_test_b.py

Input:  data/notizie.db  (current live DB)
Output: data/test_b.db, data/preview_b.html
"""
import os
import sys
import shutil
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_b")

LIVE_DB = PROJECT_ROOT / "data" / "notizie.db"
TEST_DB_REL = "data/test_b.db"
TEST_DB = PROJECT_ROOT / TEST_DB_REL
OUT_PATH = PROJECT_ROOT / "data" / "preview_b.html"

# How many hours back to include already-matched articles
RECENT_HOURS = 72
# Limit on total articles (matched + unmatched) to avoid O(n²) blowup
ARTICLE_LIMIT = 700

if not LIVE_DB.exists():
    print("ERROR: data/notizie.db not found.", file=sys.stderr)
    sys.exit(1)

# ── Isolated DB ──────────────────────────────────────────────────────────────
if TEST_DB.exists():
    TEST_DB.unlink()
shutil.copy2(LIVE_DB, TEST_DB)
print(f"Copied {LIVE_DB.name} → {TEST_DB_REL}")

os.environ["DB_PATH"] = TEST_DB_REL

from src.db import get_connection
from src.analyzer.matcher import find_matching_pairs, build_clusters_from_pairs, save_clusters
from src.analyzer.comparator import process_unpublished_clusters
from src.analyzer.ollama_client import reset_token_stats, get_token_stats

# ── Main ─────────────────────────────────────────────────────────────────────

print("\n" + "=" * 50)
print("AB TEST — VERSION B (include recent matched articles)")
print("=" * 50)

print(f"\nStep 1/2: Matching (unmatched + matched in last {RECENT_HOURS}h)...")

with get_connection() as conn:
    total_unmatched = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE processed=1 AND matched=0 AND summary IS NOT NULL"
    ).fetchone()[0]
    total_recent_matched = conn.execute(
        f"""SELECT COUNT(*) FROM articles
            WHERE processed=1 AND matched=1 AND summary IS NOT NULL
              AND fetched_at >= datetime('now', '-{RECENT_HOURS} hours')"""
    ).fetchone()[0]
    print(f"  Pool: {total_unmatched} unmatched + {total_recent_matched} recently matched = {total_unmatched + total_recent_matched} articles")

    articles = conn.execute(
        f"""SELECT a.id, a.title, a.summary, a.keywords, a.published_at,
                  a.source_id, s.name as source_name, s.region, s.country
           FROM articles a
           JOIN sources s ON a.source_id = s.id
           WHERE a.processed = 1
             AND a.summary IS NOT NULL
             AND (
               a.matched = 0
               OR (a.matched = 1 AND a.fetched_at >= datetime('now', '-{RECENT_HOURS} hours'))
             )
           ORDER BY a.published_at DESC
           LIMIT {ARTICLE_LIMIT}"""
    ).fetchall()

articles = [dict(a) for a in articles]
articles_by_id = {a["id"]: a for a in articles}
print(f"  Loaded {len(articles)} articles (capped at {ARTICLE_LIMIT})")

pairs = find_matching_pairs(articles)
clusters = build_clusters_from_pairs(pairs, articles_by_id)
saved = save_clusters(clusters, articles_by_id)
print(f"  {len(pairs)} pairs → {len(clusters)} clusters → {saved} new saved")

if saved == 0 and len(clusters) > 0:
    print("  (All clusters already existed — no new comparisons needed)")

reset_token_stats()
print("\nStep 2/2: Generating comparisons for new clusters...")
comp_stats = process_unpublished_clusters()
tok = get_token_stats()
print(f"  Generated: {comp_stats['generated']} | Skipped: {comp_stats['skipped']} | Failed: {comp_stats['failed']}")
print(f"  LLM: {tok['calls']} calls, {tok['total_tokens']:,} tokens")

print("\nGenerating preview_b.html (no translation)...")
import generate_preview
generate_preview.OUT_PATH = str(OUT_PATH)
generate_preview.archive_previous_preview = lambda: None
generate_preview.generate(translate=False, days=3)

print(f"\n✅ Version B complete → {OUT_PATH}")
