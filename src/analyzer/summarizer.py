"""Summarize articles and extract keywords using Gemma 4 via Ollama."""

import json
import logging

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


def summarize_article(article_id, title, source_name, country, content_raw):
    """Generate a summary and keywords for one article via Ollama.

    Returns:
        (summary: str, keywords: list[str])
    """
    # Summary
    summary_prompt = prompts.summarize(title, source_name, country, content_raw or "")
    summary = ollama_client.generate(summary_prompt, temperature=0.2)

    # Keywords
    keyword_prompt = prompts.extract_keywords(title, content_raw or "")
    keywords_raw = ollama_client.generate(keyword_prompt, temperature=0.1)
    keywords = _parse_keywords(keywords_raw)

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
    logger.info(f"Processing {total} unprocessed articles...")

    processed = 0
    failed = 0

    for i, article in enumerate(articles, 1):
        try:
            summary, keywords = summarize_article(
                article_id=article["id"],
                title=article["title"],
                source_name=article["source_name"],
                country=article["country"] or "?",
                content_raw=article["content_raw"],
            )

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

    logger.info(f"Summarization complete: {processed} OK, {failed} failed")
    return {"processed": processed, "failed": failed, "total": total}
