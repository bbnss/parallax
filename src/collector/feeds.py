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
    """Fetch and parse an RSS feed for a given source. Returns list of entries."""
    feed_url = source["feed_url"]
    logger.info(f"Fetching feed: {source['name']} ({feed_url})")

    feed = feedparser.parse(
        feed_url,
        agent=config.USER_AGENT,
    )

    if feed.bozo:
        if not feed.entries:
            logger.warning(f"Failed to parse feed for {source['name']}: {feed.bozo_exception}")
            return []
        else:
            logger.debug(f"Feed for {source['name']} has minor XML issues but entries were found, continuing")

    logger.info(f"  Found {len(feed.entries)} entries from {source['name']}")
    return feed.entries


def collect_from_source(source, skip_scrape=False):
    """Collect new articles from a single source.

    Args:
        source: Database row for the source
        skip_scrape: If True, skip full-text extraction (faster, for testing)

    Returns:
        Number of new articles collected
    """
    entries = fetch_feed(source)
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

    return new_count


def collect_all(skip_scrape=False):
    """Run the full collection pipeline: load sources, fetch all feeds, store articles.

    Args:
        skip_scrape: If True, skip full-text extraction (faster, for testing)

    Returns:
        Dict with collection statistics
    """
    init_db()
    load_sources()

    sources = get_active_sources()
    stats = {"total_new": 0, "sources_ok": 0, "sources_failed": 0, "details": []}

    for source in sources:
        try:
            new_count = collect_from_source(source, skip_scrape=skip_scrape)
            stats["total_new"] += new_count
            stats["sources_ok"] += 1
            stats["details"].append({"name": source["name"], "new": new_count})
            logger.info(f"  {source['name']}: {new_count} new articles")
        except Exception as e:
            stats["sources_failed"] += 1
            stats["details"].append({"name": source["name"], "error": str(e)})
            logger.error(f"  Error collecting from {source['name']}: {e}")

        # Delay between sources
        time.sleep(1)

    return stats
