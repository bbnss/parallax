"""RSS feed fetcher and article collector for NotizieGeopolitica."""

import time
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
import feedparser
from dateutil import parser as dateparser

from src import config
from src.db import (
    init_db,
    upsert_source,
    get_active_sources,
    article_exists,
    insert_article,
)
from src.collector.scraper import extract_article_text

logger = logging.getLogger(__name__)

# Maximum articles to collect per source per run (keeps processing time manageable)
MAX_ARTICLES_PER_SOURCE = 40

# Retry tuning for transient network outages at cron time.
# If >= RETRY_THRESHOLD of feeds come back empty/failed, sleep RETRY_SLEEP_SECONDS
# and retry only the problematic ones. Up to RETRY_MAX_ROUNDS extra rounds.
RETRY_THRESHOLD = 0.50
RETRY_SLEEP_SECONDS = 7 * 60
RETRY_MAX_ROUNDS = 3


def load_sources():
    """Load RSS sources from YAML config and sync them to the database."""
    with open(config.SOURCES_FILE, "r") as f:
        sources_data = yaml.safe_load(f)

    for region, feeds in sources_data.items():
        for feed in feeds:
            upsert_source(
                name=feed["name"],
                feed_url=feed["feed_url"],
                region=region,
                country=feed.get("country"),
                language=feed.get("language", "en"),
            )

    logger.info("Sources synced to database")


def parse_published_date(entry):
    """Extract and parse the publication date from a feed entry."""
    for field in ("published", "updated", "created"):
        value = getattr(entry, field, None)
        if value:
            try:
                return dateparser.parse(value)
            except (ValueError, TypeError):
                continue
    return None


def fetch_feed(source):
    """Fetch and parse an RSS feed.

    Returns:
        (entries, status, error) tuple where status is one of:
          - "ok": feed parsed and returned >=1 entry
          - "empty": feed parsed cleanly but returned 0 entries
          - "failed": network/parse error or bozo with no entries
    """
    feed_url = source["feed_url"]
    logger.info(f"Fetching feed: {source['name']} ({feed_url})")

    try:
        feed = feedparser.parse(feed_url, agent=config.USER_AGENT)
    except Exception as e:
        logger.warning(f"  Exception fetching {source['name']}: {e}")
        return [], "failed", str(e)

    if feed.bozo and not feed.entries:
        err = str(getattr(feed, "bozo_exception", "parse error"))
        logger.warning(f"  Failed to parse feed for {source['name']}: {err}")
        return [], "failed", err

    if feed.bozo:
        logger.debug(f"Feed for {source['name']} has minor XML issues but entries were found")

    n = len(feed.entries)
    logger.info(f"  Found {n} entries from {source['name']}")
    if n == 0:
        return [], "empty", None
    return feed.entries, "ok", None


def collect_from_source(source, skip_scrape=False):
    """Collect new articles from a single source.

    Returns:
        dict {name, status, new, error} where status is:
          - "ok": fetch succeeded and >=1 NEW article was inserted
          - "ok_no_new": fetch succeeded but every entry was already in DB
          - "empty": feed returned 0 entries (genuine or feed-side issue)
          - "failed": network or parse error
    """
    entries, fetch_status, fetch_err = fetch_feed(source)
    if fetch_status != "ok":
        return {"name": source["name"], "status": fetch_status, "new": 0, "error": fetch_err}

    new_count = 0
    last_domain = None

    # Sort entries by date (newest first) so the cap keeps the most recent
    entries_with_dates = []
    for e in entries:
        d = parse_published_date(e)
        entries_with_dates.append((d or datetime.min.replace(tzinfo=timezone.utc), e))
    entries_with_dates.sort(key=lambda x: x[0], reverse=True)
    entries = [e for _, e in entries_with_dates]

    for entry in entries:
        # Per-source cap: stop collecting once we hit the limit
        if new_count >= MAX_ARTICLES_PER_SOURCE:
            logger.info(f"  Cap reached ({MAX_ARTICLES_PER_SOURCE}) for {source['name']}, stopping")
            break

        url = entry.get("link")
        if not url:
            continue

        # Deduplicate by URL
        if article_exists(url):
            continue

        title = entry.get("title", "").strip()
        if not title:
            continue

        author = entry.get("author")
        published_at = parse_published_date(entry)

        # Skip articles older than 48h (keep pipeline focused on recent news)
        if published_at:
            try:
                pub_aware = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
                age = datetime.now(timezone.utc) - pub_aware
                if age > timedelta(hours=48):
                    continue
            except (TypeError, ValueError):
                pass

        # Extract full text (with rate limiting)
        content_raw = ""
        if not skip_scrape:
            # Rate limit: delay between requests to same domain
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            if domain == last_domain:
                time.sleep(config.FETCH_DELAY_SECONDS)
            last_domain = domain

            content_raw = extract_article_text(url)

        article_id = insert_article(
            source_id=source["id"],
            url=url,
            title=title,
            author=author,
            published_at=published_at,
            content_raw=content_raw,
        )

        if article_id:
            new_count += 1
            logger.debug(f"  New: {title[:80]}")

    status = "ok" if new_count > 0 else "ok_no_new"
    return {"name": source["name"], "status": status, "new": new_count, "error": None}


def _run_collection_round(sources, skip_scrape):
    """Run one collection pass over the given sources. Returns list of per-source results."""
    results = []
    for source in sources:
        try:
            res = collect_from_source(source, skip_scrape=skip_scrape)
        except Exception as e:
            res = {"name": source["name"], "status": "failed", "new": 0, "error": str(e)}
            logger.error(f"  Error collecting from {source['name']}: {e}")
        # Structured per-feed line that pmon can parse
        logger.info(
            f"[FEED] {res['name']}: status={res['status']} new={res['new']}"
            + (f" error={res['error']}" if res.get("error") else "")
        )
        results.append(res)
        time.sleep(1)
    return results


def collect_all(skip_scrape=False):
    """Run the full collection pipeline with retry on transient outages.

    If >= RETRY_THRESHOLD of feeds come back empty/failed in a round, sleep
    RETRY_SLEEP_SECONDS and re-attempt only those problematic feeds, up to
    RETRY_MAX_ROUNDS extra rounds.
    """
    init_db()
    load_sources()

    sources = get_active_sources()
    total = len(sources)

    # Round 0 (initial): all sources
    results_by_name = {}
    round_log = []

    current_batch = list(sources)
    for round_idx in range(RETRY_MAX_ROUNDS + 1):
        round_results = _run_collection_round(current_batch, skip_scrape)
        for r in round_results:
            results_by_name[r["name"]] = r

        problematic = [r for r in results_by_name.values() if r["status"] in ("empty", "failed")]
        n_problem = len(problematic)
        empty = sum(1 for r in problematic if r["status"] == "empty")
        failed = sum(1 for r in problematic if r["status"] == "failed")
        round_log.append({
            "round": round_idx,
            "attempted": len(current_batch),
            "problematic_after": n_problem,
            "empty": empty,
            "failed": failed,
        })

        if round_idx >= RETRY_MAX_ROUNDS:
            break
        if total == 0 or (n_problem / total) < RETRY_THRESHOLD:
            break

        logger.warning(
            f"[RETRY] round={round_idx + 1}/{RETRY_MAX_ROUNDS} "
            f"problematic={n_problem}/{total} (empty={empty} failed={failed}) "
            f"sleeping={RETRY_SLEEP_SECONDS}s"
        )
        time.sleep(RETRY_SLEEP_SECONDS)
        # Retry only problematic ones
        problem_names = {r["name"] for r in problematic}
        current_batch = [s for s in sources if s["name"] in problem_names]

    # Aggregate stats (last status wins for each source)
    final = list(results_by_name.values())
    stats = {
        "total_new": sum(r["new"] for r in final),
        "sources_ok": sum(1 for r in final if r["status"] in ("ok", "ok_no_new")),
        "sources_empty": sum(1 for r in final if r["status"] == "empty"),
        "sources_failed": sum(1 for r in final if r["status"] == "failed"),
        "details": final,
        "retry_rounds": round_log,
    }
    for d in final:
        logger.info(f"  {d['name']}: {d['new']} new articles [{d['status']}]")
    if len(round_log) > 1:
        logger.info(f"[RETRY] completed {len(round_log) - 1} retry round(s)")
    return stats
