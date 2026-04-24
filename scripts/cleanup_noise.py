#!/usr/bin/env python3
"""DB cleanup: identify and remove noise/irrelevant story clusters.

Flags clusters matching domestic-politics, crime, celebrity, or sports keywords.
Also flags clusters with very few articles from only 1 region (never had a
comparison generated).

Usage:
  python scripts/cleanup_noise.py           # dry-run: shows what would be deleted
  python scripts/cleanup_noise.py --execute # actually deletes
  python scripts/cleanup_noise.py --list    # list ALL clusters, no filtering
"""
import sys
import os
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import get_connection

# ── Noise keyword sets ────────────────────────────────────────────────────────

NOISE_KEYWORDS = {
    # US domestic politics
    "congressman", "congresswoman", "senate race", "governor race", "midterm",
    "primary election", "republican primary", "democrat primary", "ballot measure",
    "state legislature", "city council", "mayor race", "school board",
    "california governor", "democrat", "democrats", "swalwell", "kamala harris",
    # Celebrity / tabloid
    "epstein", "jeffrey epstein", "kardashian", "reality tv", "box office",
    "oscars", "grammy", "nba finals", "super bowl", "premier league",
    "formula 1", "transfer fee", "world cup qualifier", "celebrity",
    "maradona", "prince harry", "melania trump",
    # Domestic crime (non-geopolitical)
    "molotov cocktail", "armed robbery", "car crash", "home invasion",
    "serial killer", "murder suspect", "true crime", "grand central",
    "sexual misconduct", "laundering son",
    # Domestic politics (non-geopolitical)
    "local election", "municipal election", "county",
    "no-confidence vote", "amnesty plan for undocumented",
    "kerala", "assam", "puducherry",
}

NOISE_KEYWORDS_LOWER = {k.lower() for k in NOISE_KEYWORDS}


def _is_noise(title: str):
    """Return the matched keyword if the title is noise, else None."""
    t = title.lower()
    for kw in NOISE_KEYWORDS_LOWER:
        if kw in t:
            return kw
    return None


def fetch_all_clusters():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                sc.id,
                sc.title,
                sc.event_date,
                sc.published,
                COUNT(DISTINCT ca.article_id) as article_count,
                COUNT(DISTINCT c.id) as has_comparison,
                GROUP_CONCAT(DISTINCT s.region) as regions
            FROM story_clusters sc
            LEFT JOIN cluster_articles ca ON ca.cluster_id = sc.id
            LEFT JOIN comparisons c ON c.cluster_id = sc.id
            LEFT JOIN articles a ON a.id = ca.article_id
            LEFT JOIN sources s ON s.id = a.source_id
            GROUP BY sc.id
            ORDER BY sc.event_date ASC, sc.id ASC
        """).fetchall()
    return [dict(r) for r in rows]


def delete_clusters(cluster_ids: list[int], dry_run: bool = True):
    """Delete clusters and their comparisons. Reset matched=0 for orphaned articles."""
    if not cluster_ids:
        return

    ids_str = ",".join(str(i) for i in cluster_ids)

    with get_connection() as conn:
        # Find articles that are ONLY in these clusters (to reset matched flag)
        orphaned = conn.execute(f"""
            SELECT ca.article_id
            FROM cluster_articles ca
            WHERE ca.cluster_id IN ({ids_str})
              AND ca.article_id NOT IN (
                SELECT article_id FROM cluster_articles
                WHERE cluster_id NOT IN ({ids_str})
              )
        """).fetchall()
        orphaned_ids = [r[0] for r in orphaned]

        if dry_run:
            print(f"\n  Would delete {len(cluster_ids)} clusters")
            print(f"  Would reset matched=0 for {len(orphaned_ids)} orphaned articles")
            return

        # Delete comparisons
        conn.execute(f"DELETE FROM comparisons WHERE cluster_id IN ({ids_str})")
        # Delete cluster_articles
        conn.execute(f"DELETE FROM cluster_articles WHERE cluster_id IN ({ids_str})")
        # Delete clusters
        conn.execute(f"DELETE FROM story_clusters WHERE id IN ({ids_str})")
        # Reset matched flag for orphaned articles
        if orphaned_ids:
            oids = ",".join(str(i) for i in orphaned_ids)
            conn.execute(f"UPDATE articles SET matched=0 WHERE id IN ({oids})")

    print(f"\n  ✅ Deleted {len(cluster_ids)} clusters")
    print(f"  ✅ Reset matched=0 for {len(orphaned_ids)} orphaned articles")


def main():
    parser = argparse.ArgumentParser(description="Identify and remove noise clusters from the DB.")
    parser.add_argument("--execute", action="store_true", help="Actually delete (default: dry-run)")
    parser.add_argument("--list", action="store_true", help="List ALL clusters without filtering")
    args = parser.parse_args()

    dry_run = not args.execute

    clusters = fetch_all_clusters()
    print(f"Total clusters in DB: {len(clusters)}\n")

    if args.list:
        print(f"{'ID':>5}  {'Date':<12} {'Arts':>4}  {'Cmp':>3}  {'Regions':<30} Title")
        print("-" * 100)
        for c in clusters:
            regions = (c["regions"] or "").replace(",", "/")
            flag = "⚠️ " if _is_noise(c["title"]) else "   "
            print(f"{c['id']:>5}  {str(c['event_date']):<12} {c['article_count']:>4}  "
                  f"{'Y' if c['has_comparison'] else 'N':>3}  {regions:<30} {flag}{c['title'][:60]}")
        return

    # Identify noise clusters
    to_delete = []
    borderline = []

    for c in clusters:
        kw = _is_noise(c["title"])
        if kw:
            to_delete.append((c, f"keyword: '{kw}'"))
        elif c["has_comparison"] == 0 and c["article_count"] <= 2:
            borderline.append(c)

    print(f"{'=' * 60}")
    print(f"NOISE CLUSTERS TO DELETE ({len(to_delete)} found)")
    print(f"{'=' * 60}")
    for c, reason in to_delete:
        regions = (c["regions"] or "").replace(",", "/")
        cmp = "✓ has comparison" if c["has_comparison"] else "  no comparison"
        print(f"\n  #{c['id']} [{c['event_date']}] {c['article_count']} arts | {cmp} | {regions}")
        print(f"  Title:  {c['title']}")
        print(f"  Reason: {reason}")

    if borderline:
        print(f"\n{'=' * 60}")
        print(f"BORDERLINE (no comparison, ≤2 articles) — NOT auto-deleted")
        print(f"{'=' * 60}")
        for c in borderline:
            regions = (c["regions"] or "").replace(",", "/")
            print(f"  #{c['id']} [{c['event_date']}] {c['article_count']} arts | {regions} | {c['title'][:70]}")

    if not to_delete:
        print("No noise clusters found. DB is clean.")
        return

    cluster_ids = [c["id"] for c, _ in to_delete]

    if dry_run:
        print(f"\n{'=' * 60}")
        print(f"DRY RUN — no changes made")
        print(f"  {len(cluster_ids)} clusters would be deleted: {cluster_ids}")
        print(f"\nTo execute: python scripts/cleanup_noise.py --execute")
        delete_clusters(cluster_ids, dry_run=True)
    else:
        print(f"\n{'=' * 60}")
        print(f"DELETING {len(cluster_ids)} noise clusters: {cluster_ids}")
        delete_clusters(cluster_ids, dry_run=False)
        print("\nDone. Run generate_preview.py to refresh the preview.")


if __name__ == "__main__":
    main()
