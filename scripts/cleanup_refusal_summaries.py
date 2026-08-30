#!/usr/bin/env python3
"""Clear stored LLM refusals out of articles.summary.

Until the guard in src/analyzer/summarizer.py landed, an article whose scrape had
failed was still sent to the model, which answered "No content was provided in the
article, therefore a summary cannot be generated." — and that sentence was stored as
the summary. Two consequences:

  * the matcher (`summary IS NOT NULL`) treated those articles as summarized, and
  * because every refusal is near-identical text, they clustered *with each other*
    at near-perfect cosine similarity, manufacturing whole spurious story clusters.

This script nulls those summaries so the matcher skips the articles from now on.
It reuses `_is_refusal` from the summarizer, so detector and cleanup cannot drift.

Articles whose body is real (a transient model failure rather than a failed scrape)
are reset to processed=0 instead, so the next run re-summarizes them.

Usage:
    python scripts/cleanup_refusal_summaries.py            # dry run, prints a report
    python scripts/cleanup_refusal_summaries.py --apply    # write the changes
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import get_connection  # noqa: E402
from src import config  # noqa: E402
from src.analyzer.summarizer import _is_refusal  # noqa: E402

# A body this long that still drew a refusal is a real article the model failed on,
# not a failed scrape — worth one retry rather than permanent exclusion.
RETRY_CONTENT_CHARS = 800


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    with get_connection() as conn:
        rows = conn.execute(
            """SELECT a.id, a.title, a.summary, a.matched, s.name AS source_name,
                      LENGTH(TRIM(COALESCE(a.content_raw, ''))) AS clen
               FROM articles a
               JOIN sources s ON s.id = a.source_id
               WHERE a.summary IS NOT NULL"""
        ).fetchall()

    clear, retry = [], []
    for r in rows:
        if not _is_refusal(r["summary"]):
            continue
        (retry if r["clen"] >= RETRY_CONTENT_CHARS else clear).append(r)

    by_source = {}
    for r in clear:
        by_source[r["source_name"]] = by_source.get(r["source_name"], 0) + 1

    print(f"Scanned {len(rows)} articles with a stored summary.")
    print(f"  refusals to clear (no usable body): {len(clear)}")
    print(f"    of which already matched into a cluster: {sum(r['matched'] for r in clear)}")
    print(f"  refusals to retry (real body, model failed): {len(retry)}")
    print(f"\nBy source (threshold: MIN_CONTENT_CHARS={config.MIN_CONTENT_CHARS}):")
    for name, n in sorted(by_source.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<22} {n:>5}")

    if not args.apply:
        print("\nDry run — nothing written. Re-run with --apply to commit these changes.")
        return

    with get_connection() as conn:
        conn.executemany(
            "UPDATE articles SET summary=NULL, keywords=NULL, processed=1 WHERE id=?",
            [(r["id"],) for r in clear],
        )
        conn.executemany(
            "UPDATE articles SET summary=NULL, keywords=NULL, processed=0 WHERE id=?",
            [(r["id"],) for r in retry],
        )

    print(f"\nApplied: {len(clear)} cleared, {len(retry)} queued for re-summarization.")


if __name__ == "__main__":
    main()
