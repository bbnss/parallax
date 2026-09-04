"""Build the published site: home page, monthly archive shards, feeds.

The pipeline renders every card exactly once (see generate_preview.build_card
with include_body=False) and hands the result here. This module owns the
on-disk layout served by GitHub Pages:

    index.html                home page — freshest stories, bodies not inlined
    .nojekyll                 skip Jekyll: the archive is thousands of files
    feed.json                 JSON Feed 1.1 — only what this run added
    feed.xml                  RSS 2.0    — only what this run added
    archive/manifest.json     months available, counts, last run
    archive/YYYY-MM.json      collapsed cards for that month (append-only)
    archive/full/<id>.json    the full analysis in 5 languages, written once

The split is what keeps things small: a collapsed card is ~3 KB, its analysis
in 5 languages is ~25 KB. The browser fetches an analysis only when a reader
actually expands that card.

The archive is append-only and keyed on cluster id. A story already published
is never republished, not even under the id of a near-duplicate cluster that
the render-time dedup merged into it later (that is what `dupes` records).
"""

import io
import json
import os
import glob
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape

# Kept out of kDrive on purpose: kDrive evicts files, and this directory is the
# mirror of what is live on gh-pages.
DEFAULT_SITE_DIR = os.path.expanduser("~/parallax-data/site")
DEFAULT_SITE_URL = "https://bbnss.github.io/parallax/"

FEED_TITLE = "Parallax"
FEED_DESCRIPTION = ("Same event, different vantage points. Geopolitical news "
                    "compared across Western, Eastern, Middle Eastern and "
                    "Russian outlets.")
MAX_FEED_ITEMS = 50

# generate_preview emits `var MANIFEST = __PARALLAX_MANIFEST__;`; only this
# module knows the manifest that includes the entries written by this very run.
MANIFEST_PLACEHOLDER = "__PARALLAX_MANIFEST__"


def site_dir_default():
    return os.getenv("PARALLAX_SITE_DIR") or DEFAULT_SITE_DIR


def site_url_default():
    url = os.getenv("PARALLAX_SITE_URL") or DEFAULT_SITE_URL
    return url if url.endswith("/") else url + "/"


# ── small helpers ────────────────────────────────────────────────────────────

def _write_if_changed(path, content):
    """Write only on a real change: keeps mtimes, rsync and git history quiet."""
    if os.path.exists(path):
        try:
            if io.open(path, encoding="utf-8").read() == content:
                return False
        except (UnicodeDecodeError, OSError):
            pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _parse_ts(value):
    """SQLite CURRENT_TIMESTAMP ('2026-09-04 02:00:12', UTC) -> aware datetime."""
    if not value:
        return datetime.now(timezone.utc)
    text = str(value).strip().replace("T", " ").split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _month_of(date_str):
    return (date_str or "0000-00-00")[:7]


# ── archive ──────────────────────────────────────────────────────────────────

def _load_shards(archive_dir):
    """{month: [entry, ...]} for every archive/YYYY-MM.json already on disk."""
    shards = {}
    for path in glob.glob(os.path.join(archive_dir, "[0-9][0-9][0-9][0-9]-[0-9][0-9].json")):
        month = os.path.splitext(os.path.basename(path))[0]
        try:
            with io.open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                shards[month] = data
        except (ValueError, OSError) as exc:
            raise RuntimeError(f"archive shard {path} is unreadable: {exc}")
    return shards


def _covered_ids(shards):
    """Every cluster id the archive already accounts for, dupes included."""
    covered = set()
    for entries in shards.values():
        for e in entries:
            covered.add(e.get("id"))
            covered.update(e.get("dupes") or [])
    covered.discard(None)
    return covered


def _entry(record):
    return {
        "id": record["id"],
        "slug": record["slug"],
        "d": record["date"],
        "tier": record["tier"],
        "dupes": sorted(record.get("dupes") or []),
        "html": record["card_html"],
    }


def _sort_entries(entries):
    entries.sort(key=lambda e: (e.get("d") or "", e.get("id") or 0), reverse=True)
    return entries


def _manifest(shards, generated_at, last_run):
    months = []
    for month in sorted(shards, reverse=True):
        entries = shards[month]
        if not entries:
            continue
        dates = [e.get("d") for e in entries if e.get("d")]
        months.append({
            "m": month,
            "n": len(entries),
            "from": min(dates) if dates else month + "-01",
            "to": max(dates) if dates else month + "-01",
        })
    return {
        "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_run": last_run,
        "total": sum(m["n"] for m in months),
        "months": months,
    }


# ── feeds ────────────────────────────────────────────────────────────────────

def _permalink(site_url, slug):
    return f"{site_url}#/s/{slug}"


def _feed_records(records):
    ordered = sorted(records, key=lambda r: (r.get("date") or "", r["id"]),
                     reverse=True)
    return ordered[:MAX_FEED_ITEMS]


def _json_feed(records, site_url, generated_at):
    items = []
    for r in _feed_records(records):
        published = _parse_ts(r.get("generated_at"))
        items.append({
            "id": r["slug"],
            "url": _permalink(site_url, r["slug"]),
            "title": r["title"],
            "content_text": r["teaser"],
            "summary": r["teaser"],
            "date_published": published.isoformat(),
            "tags": sorted(set(r.get("regions") or [])) + [f"tier-{r['tier']}"],
            # JSON Feed reserves "_"-prefixed keys for extensions: this is the
            # structured payload for developers, so no second API file is needed.
            "_parallax": {
                "cluster_id": r["id"],
                "event_date": r["date"],
                "tier": r["tier"],
                "tier_label": r.get("tier_label"),
                "regions": sorted(set(r.get("regions") or [])),
                "article_count": r.get("article_count"),
                "source_count": len(r.get("sources") or []),
                "sources": r.get("sources") or [],
                "full_analysis_url": f"{site_url}archive/full/{r['id']}.json",
                "languages": r.get("languages") or [],
            },
        })
    return {
        "version": "https://jsonfeed.org/version/1.1",
        "title": FEED_TITLE,
        "home_page_url": site_url,
        "feed_url": f"{site_url}feed.json",
        "description": FEED_DESCRIPTION,
        "language": "en",
        "_generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": items,
    }


def _rss(records, site_url, generated_at):
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{xml_escape(FEED_TITLE)}</title>",
        f"<link>{xml_escape(site_url)}</link>",
        f"<description>{xml_escape(FEED_DESCRIPTION)}</description>",
        "<language>en</language>",
        f'<atom:link href="{xml_escape(site_url)}feed.xml" rel="self" '
        f'type="application/rss+xml"/>',
        f"<lastBuildDate>{format_datetime(generated_at)}</lastBuildDate>",
    ]
    for r in _feed_records(records):
        published = _parse_ts(r.get("generated_at"))
        parts.append("<item>")
        parts.append(f"<title>{xml_escape(r['title'])}</title>")
        parts.append(f"<link>{xml_escape(_permalink(site_url, r['slug']))}</link>")
        parts.append(f'<guid isPermaLink="false">{xml_escape(r["slug"])}</guid>')
        parts.append(f"<pubDate>{format_datetime(published)}</pubDate>")
        parts.append(f"<description>{xml_escape(r['teaser'] or '')}</description>")
        for region in sorted(set(r.get("regions") or [])):
            parts.append(f"<category>{xml_escape(region)}</category>")
        parts.append("</item>")
    parts += ["</channel>", "</rss>", ""]
    return "\n".join(parts)


# ── entry point ──────────────────────────────────────────────────────────────

def build_site(records, index_html, site_dir=None, site_url=None,
               generated_at=None, write_index=True, write_feeds=True):
    """Persist the site. `records` is every card of this run (new or not).

    Only the records the archive has never seen become new archive entries and
    feed items — that is the operational definition of "what this run added".
    write_index=False is for the one-off backfill, which replays past runs and
    has no home page to write. Returns a summary dict.
    """
    site_dir = site_dir or site_dir_default()
    site_url = site_url or site_url_default()
    generated_at = generated_at or datetime.now(timezone.utc)
    archive_dir = os.path.join(site_dir, "archive")
    full_dir = os.path.join(archive_dir, "full")
    os.makedirs(full_dir, exist_ok=True)

    shards = _load_shards(archive_dir)
    covered = _covered_ids(shards)

    new_records = []
    for r in records:
        ids = {r["id"]} | set(r.get("dupes") or [])
        if ids & covered:
            continue
        new_records.append(r)
        covered |= ids

    touched = set()
    for r in new_records:
        month = _month_of(r["date"])
        shards.setdefault(month, []).append(_entry(r))
        touched.add(month)
        _write_if_changed(os.path.join(full_dir, f"{r['id']}.json"),
                          _dump(r["bodies"]))

    written = 0
    for month in sorted(touched):
        path = os.path.join(archive_dir, f"{month}.json")
        if _write_if_changed(path, _dump(_sort_entries(shards[month]))):
            written += 1

    last_run = max((r["date"] for r in new_records), default=None)
    if last_run is None:
        previous = _read_json(os.path.join(archive_dir, "manifest.json"))
        last_run = (previous or {}).get("last_run")
    manifest = _manifest(shards, generated_at, last_run)
    _write_if_changed(os.path.join(archive_dir, "manifest.json"), _dump(manifest))

    # A run that added nothing leaves the feeds exactly as they were: an RSS
    # reader must not see yesterday's stories resurface as new. The exception
    # is the very first build after a backfill, where the archive is already
    # full and there is no feed yet — subscribers would get a 404.
    feed_path = os.path.join(site_dir, "feed.json")
    feed_records = new_records
    if write_feeds and not feed_records and not os.path.exists(feed_path):
        newest = max((r["date"] for r in records), default=None)
        feed_records = [r for r in records if r["date"] == newest]
    if write_feeds and feed_records:
        _write_if_changed(feed_path,
                          json.dumps(_json_feed(feed_records, site_url, generated_at),
                                     ensure_ascii=False, indent=1))
        _write_if_changed(os.path.join(site_dir, "feed.xml"),
                          _rss(feed_records, site_url, generated_at))

    if write_index:
        # The page embeds the manifest so the first "load more" costs no extra
        # request — and so it always knows about the month this run created.
        index_html = index_html.replace(MANIFEST_PLACEHOLDER, _dump(manifest))
        _write_if_changed(os.path.join(site_dir, "index.html"), index_html)
    _write_if_changed(os.path.join(site_dir, ".nojekyll"), "")

    return {
        "site_dir": site_dir,
        "new": len(new_records),
        "new_ids": [r["id"] for r in new_records],
        "months_written": written,
        "feed_items": len(feed_records) if write_feeds else 0,
        "total": sum(len(v) for v in shards.values()),
    }


def _read_json(path):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_manifest(site_dir=None):
    """The manifest as it is on disk — embedded into index.html at build time."""
    site_dir = site_dir or site_dir_default()
    return _read_json(os.path.join(site_dir, "archive", "manifest.json"))
