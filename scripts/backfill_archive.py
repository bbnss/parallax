#!/usr/bin/env python3
"""One-off: replay every past run into the archive.

Before this, only the last 3 days of stories existed on the site. The archive
introduced with the JSON feed is append-only and built one nightly run at a
time, so the way to fill it with history is to replay those runs: for each day
that ever produced a comparison, take the same 3-day window `generate()` uses,
run the same dedup, and let site_build append whatever is new.

Replaying (rather than dumping all 707 comparisons at once) matters because the
cross-day dedup threshold has no notion of distance in time: run over the whole
archive at once it would happily merge stories months apart.

By default nothing is generated: translations and teasers come from the caches
in data/translations/ and data/teasers/, so this makes zero LLM calls and a
cluster whose translation was never cached simply falls back to English. Pass
--generate-missing to fill those gaps through Ollama instead (slow).

    python scripts/backfill_archive.py --dry-run
    PARALLAX_SITE_DIR=/tmp/parallax-site python scripts/backfill_archive.py
"""

import argparse
import glob
import json
import os
import shutil
import sys
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # project root, for src.*
sys.path.insert(0, _HERE)                    # scripts/, for generate_preview

from src.db import get_connection
from src.generator import site_build

import generate_preview as gp

WINDOW_DAYS = 3   # must match run_pipeline.sh's `--days 3`


def fetch_all_comparisons():
    """Every published comparison, oldest first — the same shape generate() uses."""
    with get_connection() as conn:
        rows = conn.execute('''
            SELECT sc.id, sc.slug, sc.title, sc.event_date, c.comparison_text,
                   c.generated_at,
                   GROUP_CONCAT(DISTINCT s.name || '@@' || s.region || '@@' || COALESCE(s.country,'')) as sources_raw,
                   COUNT(DISTINCT a.id)        as article_count,
                   COUNT(DISTINCT a.source_id) as source_count,
                   COUNT(DISTINCT s.region)    as region_count
            FROM comparisons c
            JOIN story_clusters sc ON sc.id = c.cluster_id
            JOIN cluster_articles ca ON ca.cluster_id = sc.id
            JOIN articles a ON a.id = ca.article_id
            JOIN sources s ON s.id = a.source_id
            WHERE sc.event_date IS NOT NULL
            GROUP BY c.id
            ORDER BY sc.event_date ASC, sc.id ASC
        ''').fetchall()
    return [dict(r) for r in rows]


def cached_translation(cluster_id, lang, model):
    """(title, body) from the on-disk translation cache, or (None, None)."""
    path = os.path.join(gp._translation_cache_dir(lang, model), f"{cluster_id}.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return (None, None)
    return (data.get("title"), data.get("body"))


def cached_teasers(cluster_id, langs, model):
    teasers = {}
    path = os.path.join(gp.TEASERS_CACHE_DIR, f"{cluster_id}.json")
    try:
        with open(path, encoding="utf-8") as f:
            teasers["en"] = json.load(f).get("teaser") or ""
    except (OSError, ValueError):
        teasers["en"] = ""
    for lang in langs:
        # Teaser translations ride on the body-translation machinery, so their
        # cache carries title/body — not a "teaser" key (_translate_teaser_lang).
        tpath = os.path.join(gp._translation_cache_dir(lang, model),
                             f"teaser_{cluster_id}.json")
        try:
            with open(tpath, encoding="utf-8") as f:
                data = json.load(f)
            teasers[lang] = (data.get("body") or data.get("title") or "").strip()
        except (OSError, ValueError):
            teasers[lang] = ""
    return teasers


def collect_assets(comps, langs, tmodel, gmodel, generate_missing):
    """{cid: {lang: (title, body)}}, {cid: {lang: teaser}} for these clusters."""
    translations, teasers = {}, {}
    for comp in comps:
        cid = comp["id"]
        translations[cid] = {}
        for lang in langs:
            if generate_missing:
                translations[cid][lang] = gp.translate_text(
                    cid, comp["title"], comp["comparison_text"], lang,
                    translate_model=tmodel)
            else:
                translations[cid][lang] = cached_translation(cid, lang, tmodel)
        if generate_missing:
            en_teaser = gp._load_or_generate_teaser_en(comp, gmodel)
            teasers[cid] = {"en": en_teaser}
            for lang in langs:
                teasers[cid][lang] = gp._translate_teaser_lang(
                    cid, en_teaser, lang, tmodel)
        else:
            teasers[cid] = cached_teasers(cid, langs, tmodel)
    return translations, teasers


def source_urls_for(cluster_ids):
    """{cluster_id: {source_name: newest article url}} — as build_card expects."""
    if not cluster_ids:
        return {}
    out = {}
    placeholders = ",".join("?" * len(cluster_ids))
    with get_connection() as conn:
        rows = conn.execute(f'''
            SELECT ca.cluster_id, s.name, a.url
            FROM cluster_articles ca
            JOIN articles a ON a.id = ca.article_id
            JOIN sources s ON s.id = a.source_id
            WHERE ca.cluster_id IN ({placeholders})
            ORDER BY ca.cluster_id, s.name, a.published_at DESC, a.id DESC
        ''', list(cluster_ids)).fetchall()
    for row in rows:
        out.setdefault(row["cluster_id"], {}).setdefault(row["name"], row["url"])
    return out


def replay_day(day, all_comps, urls, langs, tmodel, gmodel, generate_missing,
               site_dir, dry_run, seen):
    """Archive whatever the run of `day` would have added."""
    start = (datetime.strptime(day, "%Y-%m-%d")
             - timedelta(days=WINDOW_DAYS - 1)).strftime("%Y-%m-%d")
    window = [c for c in all_comps if start <= c["event_date"] <= day]
    if not window:
        return 0

    window = sorted(window, key=lambda c: (c["event_date"], c["id"]), reverse=True)
    for comp in window:
        comp["tier"] = gp.compute_tier(comp)
    survivors, groups = gp._deduplicate_comparisons(window, return_groups=True,
                                                    max_cards=None)

    translations, teasers = collect_assets(survivors, langs, tmodel, gmodel,
                                           generate_missing)
    card_html = {}
    for comp in survivors:
        card_html[comp["id"]] = gp.build_card(
            comp, translations.get(comp["id"], {}),
            teasers=teasers.get(comp["id"]),
            source_urls=urls.get(comp["id"]),
            include_body=False,
        )
    records = gp.build_records(survivors, translations, teasers, urls, groups,
                               card_html, languages=["en"] + langs)
    if dry_run:
        # Mirror site_build's append-only rule so the count means something.
        added = 0
        for r in records:
            ids = {r["id"]} | set(r.get("dupes") or [])
            if ids & seen:
                continue
            seen |= ids
            added += 1
        return added
    # No index and no feeds: a replayed feed would announce months-old stories
    # as fresh. The next real run writes both.
    summary = site_build.build_site(records, None, site_dir=site_dir,
                                    write_index=False, write_feeds=False)
    return summary["new"]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site-dir", default=None,
                        help="Site directory to fill (default: $PARALLAX_SITE_DIR)")
    parser.add_argument("--since", default=None,
                        help="Only replay runs from this date on (YYYY-MM-DD)")
    parser.add_argument("--generate-missing", action="store_true",
                        help="Call Ollama for translations/teasers absent from cache")
    parser.add_argument("--no-translate", action="store_true",
                        help="English only — skip translations entirely")
    parser.add_argument("--rebuild", action="store_true",
                        help="Discard the existing archive first and rebuild it from "
                             "scratch — the way to pick up a change to the card markup")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be archived; write nothing")
    args = parser.parse_args()

    from src import config as _cfg
    tmodel = _cfg.TRANSLATE_MODEL
    gmodel = _cfg.OLLAMA_MODEL
    langs = [] if args.no_translate else list(gp.TRANSLATION_LANGUAGES)
    site_dir = args.site_dir or site_build.site_dir_default()

    if args.rebuild and not args.dry_run:
        # Archive entries store rendered HTML and are never rewritten, so a
        # change to build_card only reaches past stories through a rebuild.
        archive_dir = os.path.join(site_dir, "archive")
        removed = 0
        for path in glob.glob(os.path.join(archive_dir, "[0-9]" * 4 + "-[0-9][0-9].json")):
            os.remove(path)
            removed += 1
        shutil.rmtree(os.path.join(archive_dir, "full"), ignore_errors=True)
        print(f"Rebuild: dropped {removed} shard(s) and every cached analysis")

    all_comps = fetch_all_comparisons()
    if not all_comps:
        print("No comparisons in the database — nothing to backfill.")
        return
    days = sorted({c["event_date"] for c in all_comps})
    if args.since:
        days = [d for d in days if d >= args.since]

    print(f"Backfilling {len(all_comps)} comparisons across {len(days)} run days "
          f"into {site_dir}")
    print(f"Translations: {'generate missing via Ollama' if args.generate_missing else 'cache only'}"
          f" | languages: {', '.join(['en'] + langs)}")
    if args.dry_run:
        print("DRY RUN — nothing will be written")

    urls = source_urls_for([c["id"] for c in all_comps])
    seen = set()
    total = 0
    for i, day in enumerate(days, 1):
        added = replay_day(day, all_comps, urls, langs, tmodel, gmodel,
                           args.generate_missing, site_dir, args.dry_run, seen)
        total += added
        print(f"   [{i}/{len(days)}] {day}: +{added} archived (running total {total})",
              end="\r")
    print(" " * 80, end="\r")
    print(f"Done: {total} stories archived out of {len(all_comps)} comparisons.")
    if not args.dry_run:
        manifest = site_build.load_manifest(site_dir) or {}
        print(f"Archive now holds {manifest.get('total', '?')} stories across "
              f"{len(manifest.get('months', []))} month(s).")
        print("Next: run generate_preview.py to write index.html and the feeds.")


if __name__ == "__main__":
    main()
