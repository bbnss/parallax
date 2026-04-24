#!/usr/bin/env python3
"""AB Test — Version A: Post-build cluster merging.

Strategy: after Union-Find clustering, compute a centroid embedding for each
cluster (average of article summary embeddings). Merge any pair of clusters
whose centroid cosine similarity >= MERGE_THRESHOLD before saving to DB.

This prevents the same event from appearing in 3 separate clusters because
Union-Find never found a direct pair connecting them.

Run AFTER ab_base.py:
  python scripts/ab_test_a.py

Input:  data/ab_base.db  (must exist)
Output: data/test_a.db, data/preview_a.html
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
logger = logging.getLogger("test_a")

BASE_DB = PROJECT_ROOT / "data" / "ab_base.db"
TEST_DB_REL = "data/test_a.db"
TEST_DB = PROJECT_ROOT / TEST_DB_REL
OUT_PATH = PROJECT_ROOT / "data" / "preview_a.html"
MERGE_THRESHOLD = 0.73

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
from src.analyzer.matcher import (
    find_matching_pairs, build_clusters_from_pairs, save_clusters,
    _get_embedding, _cosine_similarity,
)
from src.analyzer.comparator import process_unpublished_clusters
from src.analyzer.ollama_client import reset_token_stats, get_token_stats


# ── Cluster merge function ───────────────────────────────────────────────────

def merge_similar_clusters(clusters, articles_by_id, threshold=MERGE_THRESHOLD):
    """Merge clusters whose centroid embeddings have cosine sim >= threshold.

    Returns a (possibly shorter) list of merged clusters.
    """
    if len(clusters) < 2:
        return clusters

    logger.info(f"Merge pass: {len(clusters)} clusters, threshold={threshold}")

    # Build centroid for each cluster
    centroids = []
    for cluster_ids in clusters:
        texts = [
            (articles_by_id[aid].get("summary") or articles_by_id[aid].get("title", ""))[:300]
            for aid in cluster_ids if aid in articles_by_id
        ]
        texts = [t for t in texts if t]
        if not texts:
            centroids.append(None)
            continue
        embs = [_get_embedding(t) for t in texts]
        embs = [e for e in embs if e is not None]
        if not embs:
            centroids.append(None)
            continue
        dim = len(embs[0])
        n = len(embs)
        centroids.append([sum(e[i] for e in embs) / n for i in range(dim)])

    # Union-Find on cluster indices
    parent = list(range(len(clusters)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    merges = 0
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            if centroids[i] is None or centroids[j] is None:
                continue
            sim = _cosine_similarity(centroids[i], centroids[j])
            if sim >= threshold:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
                    merges += 1
                    logger.info(
                        f"  Merge (sim={sim:.3f}): "
                        f"cluster[{i}] ({len(clusters[i])} arts) "
                        f"↔ cluster[{j}] ({len(clusters[j])} arts)"
                    )

    if merges == 0:
        logger.info("Merge pass: nothing to merge")
        return clusters

    groups = {}
    for i in range(len(clusters)):
        root = find(i)
        groups.setdefault(root, set()).update(clusters[i])

    merged = [sorted(ids) for ids in groups.values()]
    logger.info(f"Merge pass: {len(clusters)} → {len(merged)} clusters ({merges} merges)")
    return merged


# ── Main ─────────────────────────────────────────────────────────────────────

print("\n" + "=" * 50)
print("AB TEST — VERSION A (post-build cluster merge)")
print("=" * 50)

print("\nStep 1/2: Matching articles...")
with get_connection() as conn:
    articles = conn.execute(
        """SELECT a.id, a.title, a.summary, a.keywords, a.published_at,
                  a.source_id, s.name as source_name, s.region, s.country
           FROM articles a
           JOIN sources s ON a.source_id = s.id
           WHERE a.processed = 1
             AND a.matched = 0
             AND a.summary IS NOT NULL
           ORDER BY a.published_at DESC
           LIMIT 500"""
    ).fetchall()

articles = [dict(a) for a in articles]
articles_by_id = {a["id"]: a for a in articles}
print(f"  {len(articles)} articles to match")

pairs = find_matching_pairs(articles)
clusters = build_clusters_from_pairs(pairs, articles_by_id)
print(f"  Before merge: {len(clusters)} clusters from {len(pairs)} pairs")

clusters = merge_similar_clusters(clusters, articles_by_id)
saved = save_clusters(clusters, articles_by_id)
print(f"  After merge:  {len(clusters)} clusters → {saved} saved to DB")

reset_token_stats()
print("\nStep 2/2: Generating comparisons...")
comp_stats = process_unpublished_clusters()
tok = get_token_stats()
print(f"  Generated: {comp_stats['generated']} | Skipped: {comp_stats['skipped']} | Failed: {comp_stats['failed']}")
print(f"  LLM: {tok['calls']} calls, {tok['total_tokens']:,} tokens")

print("\nGenerating preview_a.html (no translation)...")
import generate_preview
generate_preview.OUT_PATH = str(OUT_PATH)
generate_preview.archive_previous_preview = lambda: None
generate_preview.generate(translate=False, days=3)

print(f"\n✅ Version A complete → {OUT_PATH}")
