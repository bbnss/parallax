"""Dry-run the LLM geopolitical gate against the current 35 clusters.

Read-only: classifies each cluster as YES/NO without touching the DB.

Use the output to decide:
  - If it filters known noise (#2 trains, #5 FBI/NYT, #15 Lufthansa, #18 Pope, #23 Booking,
    #34 OpenAI, #35 Mexico shooting) and KEEPS the geopolitical ones → integrate in
    comparator.py and re-run pipeline.
  - If it kills genuine geopolitical clusters → tighten the prompt before integrating.

Run: .venv/bin/python scripts/dryrun_geopolitical_gate.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer import ollama_client, prompts
from src.db import get_connection


def classify(title, summaries):
    prompt = prompts.is_geopolitical_cluster(title, summaries)
    raw = ollama_client.generate(prompt, temperature=0.0).strip().upper()
    # Take first word, strip punctuation
    first = raw.split()[0].rstrip(".,:;!?") if raw else ""
    return first == "YES", raw


def main():
    with get_connection() as conn:
        clusters = conn.execute(
            "SELECT id, title FROM story_clusters ORDER BY id"
        ).fetchall()

        rows = []
        for c in clusters:
            summaries = conn.execute(
                """SELECT a.summary FROM articles a
                   JOIN cluster_articles ca ON ca.article_id=a.id
                   WHERE ca.cluster_id=? AND a.summary IS NOT NULL
                   LIMIT 3""",
                (c["id"],),
            ).fetchall()
            rows.append((c["id"], c["title"], [s["summary"] for s in summaries]))

    print(f"Classifying {len(rows)} clusters...\n")
    kept, dropped = [], []
    for cid, title, summaries in rows:
        is_geo, raw = classify(title, summaries)
        marker = "✅ KEEP" if is_geo else "❌ DROP"
        print(f"{marker} [#{cid:>2}] {title[:90]}")
        (kept if is_geo else dropped).append((cid, title))

    print(f"\n=== Summary: {len(kept)} kept, {len(dropped)} dropped ===")
    print("\nDropped clusters (these would be filtered out):")
    for cid, title in dropped:
        print(f"  #{cid}: {title}")


if __name__ == "__main__":
    main()
