"""Summarize articles and extract keywords using Gemma 4 via Ollama."""

import json
import logging

from src import config
from src.analyzer import keyword_normalize
from src.analyzer import ollama_client
from src.analyzer import prompts
from src.db import get_connection

logger = logging.getLogger(__name__)


def _parse_keywords(raw):
    """Parse the LLM keyword output into a clean list."""
    if not raw:
        return []
    raw = raw.strip()
    # Strip markdown code fences if present
    for prefix in ("```json", "```"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return [str(k).strip() for k in result if k]
    except json.JSONDecodeError:
        pass
    # Fallback: split by comma if JSON parsing fails
    return [k.strip().strip('"') for k in raw.split(",") if k.strip()]


# The model, handed a body it considers unusable, does not fail — it answers in
# prose ("No content was provided in the article, therefore a summary cannot be
# generated."), which is then stored *as* the summary. MIN_CONTENT_CHARS catches the
# empty scrapes; this catches the ones that come back long enough to pass but hold
# only boilerplate — video-player errors, cookie notices, a bare title.
_REFUSAL_MARKERS = (
    "no content was provided",
    "cannot be generated",
    "please provide the article",
    "i need the content",
    "cannot summarize the article",
    "source text is unavailable",
    "unable to generate a summary",
    "no article text",
    "provide the content",
    "does not contain the content",
    "does not contain the article",
    "does not contain a substantive article",
)


def _is_refusal(summary):
    """True if the model declined to summarize instead of summarizing."""
    if not summary:
        return True
    low = summary.lower()
    return any(marker in low for marker in _REFUSAL_MARKERS)


def summarize_article(article_id, title, source_name, country, content_raw):
    """Generate a summary and keywords for one article via Ollama.

    Returns:
        (summary: str, keywords: list[str])
    """
    # Summary — use the fast model: this is bulk compression, quality not critical.
    summary_prompt = prompts.summarize(title, source_name, country, content_raw or "")
    summary = ollama_client.generate(summary_prompt, model=config.FAST_MODEL, temperature=0.2)

    # Keywords — also fast model.
    keyword_prompt = prompts.extract_keywords(title, content_raw or "")
    keywords_raw = ollama_client.generate(keyword_prompt, model=config.FAST_MODEL, temperature=0.1)
    keywords = keyword_normalize.normalize_keywords(_parse_keywords(keywords_raw))

    return summary, keywords


def process_unprocessed_articles(batch_size=50, limit=None):
    """Summarize all unprocessed articles in the database.

    Args:
        batch_size: Number of articles to process before logging progress
        limit: Maximum articles to process (None = all)

    Returns:
        Dict with processing statistics
    """
    with get_connection() as conn:
        query = """
            SELECT a.id, a.title, a.content_raw, s.name as source_name, s.country, s.region
            FROM articles a
            JOIN sources s ON a.source_id = s.id
            WHERE a.processed = 0
            ORDER BY a.published_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"
        articles = conn.execute(query).fetchall()

    total = len(articles)
    logger.info(f"Processing {total} unprocessed articles (model={config.FAST_MODEL})...")

    processed = 0
    failed = 0
    skipped = 0

    for i, article in enumerate(articles, 1):
        # Scrape failed (paywall/403/Cloudflare): there is no body to compress.
        # Mark it processed so it is not retried forever, but leave summary NULL —
        # the matcher's `summary IS NOT NULL` gate then keeps it out of clustering.
        if len((article["content_raw"] or "").strip()) < config.MIN_CONTENT_CHARS:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE articles SET processed=1 WHERE id=?", (article["id"],)
                )
            skipped += 1
            logger.debug(
                f"  Skipped (no body): {article['source_name']} — {article['title'][:60]}"
            )
            continue

        try:
            summary, keywords = summarize_article(
                article_id=article["id"],
                title=article["title"],
                source_name=article["source_name"],
                country=article["country"] or "?",
                content_raw=article["content_raw"],
            )

            if _is_refusal(summary):
                # Body passed the length gate but held nothing summarizable.
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE articles SET processed=1 WHERE id=?", (article["id"],)
                    )
                skipped += 1
                logger.debug(
                    f"  Skipped (model declined): {article['source_name']} — "
                    f"{article['title'][:60]}"
                )
                continue

            with get_connection() as conn:
                conn.execute(
                    """UPDATE articles
                       SET summary=?, keywords=?, processed=1
                       WHERE id=?""",
                    (summary, json.dumps(keywords), article["id"]),
                )

            processed += 1

            if i % batch_size == 0 or i == total:
                logger.info(f"  Progress: {i}/{total} articles processed")

        except Exception as e:
            failed += 1
            logger.error(f"  Failed to process article {article['id']} '{article['title'][:60]}': {e}")
            # Mark as processed to avoid retrying broken articles indefinitely
            with get_connection() as conn:
                conn.execute(
                    "UPDATE articles SET processed=1 WHERE id=?",
                    (article["id"],),
                )

    logger.info(
        f"Summarization complete: {processed} OK, {failed} failed, "
        f"{skipped} skipped (no body)"
    )
    return {"processed": processed, "failed": failed, "skipped": skipped, "total": total}
