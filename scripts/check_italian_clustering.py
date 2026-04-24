"""Diagnostic: verify Italian-language articles cluster with their English counterparts.

Run after `analyze` completes to answer the key question:
  Does the new multilingual embedding model actually match IT articles to EN ones?

Output interpretation:
  - Zero mixed clusters → multilingual model is NOT matching IT↔EN; lower
    EMBEDDING_THRESHOLD in src/analyzer/matcher.py from 0.75 to ~0.65 and re-run.
  - Some mixed clusters → open them manually, verify the stories are actually
    the same event (sometimes LLM clusters by topic not event).
  - Many mixed clusters → multilingual is working; proceed to preview update.

Run: .venv/bin/python scripts/check_italian_clustering.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import get_connection


def main():
    with get_connection() as conn:
        total_articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        processed = conn.execute("SELECT COUNT(*) FROM articles WHERE processed=1").fetchone()[0]
        it_articles = conn.execute(
            "SELECT COUNT(*) FROM articles a JOIN sources s ON s.id=a.source_id WHERE s.language='it'"
        ).fetchone()[0]
        it_processed = conn.execute(
            "SELECT COUNT(*) FROM articles a JOIN sources s ON s.id=a.source_id "
            "WHERE s.language='it' AND a.processed=1"
        ).fetchone()[0]
        total_clusters = conn.execute("SELECT COUNT(*) FROM story_clusters").fetchone()[0]

        print(f"=== Corpus status ===")
        print(f"  Articles total:        {total_articles:>4}")
        print(f"  Articles processed:    {processed:>4} ({100*processed/max(total_articles,1):.0f}%)")
        print(f"  Italian-lang articles: {it_articles:>4}")
        print(f"  Italian processed:     {it_processed:>4}")
        print(f"  Total clusters:        {total_clusters:>4}")
        print()

        # Clusters with Italian articles only
        it_only = conn.execute("""
            SELECT COUNT(DISTINCT sc.id)
            FROM story_clusters sc
            JOIN cluster_articles ca ON ca.cluster_id=sc.id
            JOIN articles a ON a.id=ca.article_id
            JOIN sources s ON s.id=a.source_id
            WHERE sc.id NOT IN (
                SELECT DISTINCT sc2.id
                FROM story_clusters sc2
                JOIN cluster_articles ca2 ON ca2.cluster_id=sc2.id
                JOIN articles a2 ON a2.id=ca2.article_id
                JOIN sources s2 ON s2.id=a2.source_id
                WHERE s2.language != 'it'
            )
            AND s.language = 'it'
        """).fetchone()[0]

        # Clusters with EN articles only
        en_only = conn.execute("""
            SELECT COUNT(DISTINCT sc.id)
            FROM story_clusters sc
            WHERE sc.id NOT IN (
                SELECT DISTINCT sc2.id
                FROM story_clusters sc2
                JOIN cluster_articles ca2 ON ca2.cluster_id=sc2.id
                JOIN articles a2 ON a2.id=ca2.article_id
                JOIN sources s2 ON s2.id=a2.source_id
                WHERE s2.language = 'it'
            )
        """).fetchone()[0]

        # Mixed clusters (the critical success signal)
        mixed = conn.execute("""
            SELECT sc.id, sc.title,
                SUM(CASE WHEN s.language='it' THEN 1 ELSE 0 END) as n_it,
                SUM(CASE WHEN s.language='en' THEN 1 ELSE 0 END) as n_en,
                COUNT(DISTINCT s.region) as n_regions,
                GROUP_CONCAT(DISTINCT s.name) as source_names
            FROM story_clusters sc
            JOIN cluster_articles ca ON ca.cluster_id=sc.id
            JOIN articles a ON a.id=ca.article_id
            JOIN sources s ON s.id=a.source_id
            GROUP BY sc.id
            HAVING n_it > 0 AND n_en > 0
            ORDER BY n_regions DESC, n_it+n_en DESC
        """).fetchall()

        print(f"=== Clustering outcome ===")
        print(f"  IT-only clusters:    {it_only:>4}   (bad sign — isolated Italian stories)")
        print(f"  EN-only clusters:    {en_only:>4}   (normal for non-IT-covered stories)")
        print(f"  Mixed IT+EN clusters:{len(mixed):>4}   ← CRITICAL METRIC")
        print()

        if not mixed:
            print("⚠️  ZERO mixed clusters — multilingual embedding is NOT working as expected.")
            print("   Likely cause: threshold 0.75 too strict for cross-lingual cosine sim.")
            print("   Fix: lower EMBEDDING_THRESHOLD in src/analyzer/matcher.py to 0.65,")
            print("        wipe story_clusters + cluster_articles + comparisons,")
            print("        re-run `.venv/bin/python -m src.cli analyze`.")
            return

        print(f"=== Top mixed clusters (the wins) ===\n")
        for row in mixed[:15]:
            print(f"  [#{row['id']:>3}] IT:{row['n_it']} EN:{row['n_en']} regions:{row['n_regions']}")
            print(f"         {row['title']}")
            print(f"         sources: {row['source_names']}")
            print()

        # Quality check: list Italian articles that ended up ALONE (no cluster match)
        lonely_it = conn.execute("""
            SELECT a.id, a.title, s.name as source
            FROM articles a
            JOIN sources s ON s.id=a.source_id
            WHERE s.language='it'
              AND a.processed=1
              AND a.id NOT IN (
                SELECT article_id FROM cluster_articles
              )
            ORDER BY a.id DESC
            LIMIT 10
        """).fetchall()

        if lonely_it:
            print(f"=== Italian articles unclustered (sample) ===")
            print(f"  Likely either (a) real scoop with no foreign coverage,")
            print(f"              or (b) multilingual embedding failed to match.\n")
            for row in lonely_it:
                print(f"  [{row['source']}] {row['title'][:100]}")
            print()

        # Summary verdict
        if len(mixed) >= 10:
            print("✅ Multilingual embedding appears to be working well.")
            print("   Proceed to generate preview with IT priority.")
        elif len(mixed) >= 3:
            print("🟡 Some cross-lingual matching, but fewer than expected.")
            print("   Consider lowering EMBEDDING_THRESHOLD to 0.70 and re-running matching.")
        else:
            print("🔴 Very few mixed clusters — threshold likely too strict.")


if __name__ == "__main__":
    main()
