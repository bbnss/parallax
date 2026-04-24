#!/usr/bin/env python3
"""AB Test — Step 0: Prepare base DB from existing notizie.db.

Instead of re-collecting and re-summarizing (slow), we simply copy the current
live DB. All 1800+ articles are already collected and summarized — the AB tests
only differ in the matching and comparison steps.

Usage:
  python scripts/ab_base.py

Creates: data/ab_base.db  (copy of data/notizie.db)
"""
import shutil
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LIVE_DB = PROJECT_ROOT / "data" / "notizie.db"
BASE_DB = PROJECT_ROOT / "data" / "ab_base.db"

if not LIVE_DB.exists():
    print(f"ERROR: {LIVE_DB} not found.", flush=True)
    raise SystemExit(1)

print("AB TEST — Step 0: Preparing base DB")
print("=" * 50)

if BASE_DB.exists():
    BASE_DB.unlink()
    print(f"Removed existing ab_base.db")

shutil.copy2(LIVE_DB, BASE_DB)
print(f"Copied notizie.db → ab_base.db")

# Quick stats
conn = sqlite3.connect(str(BASE_DB))
total     = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
processed = conn.execute("SELECT COUNT(*) FROM articles WHERE processed=1").fetchone()[0]
unmatched = conn.execute("SELECT COUNT(*) FROM articles WHERE processed=1 AND matched=0 AND summary IS NOT NULL").fetchone()[0]
clusters  = conn.execute("SELECT COUNT(*) FROM story_clusters").fetchone()[0]
sources   = conn.execute("SELECT COUNT(*) FROM sources WHERE active=1").fetchone()[0]
conn.close()

print(f"\nBase DB stats:")
print(f"  Articles:         {total}")
print(f"  Summarized:       {processed}")
print(f"  Ready to match:   {unmatched}")
print(f"  Existing clusters:{clusters}")
print(f"  Active sources:   {sources}")
print(f"  Size:             {BASE_DB.stat().st_size / 1024 / 1024:.1f} MB")
print(f"\n✅ Base DB ready: {BASE_DB}")
print("   Run ab_test_a.py, ab_test_b.py, ab_test_c.py next.")
