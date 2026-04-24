"""Full-text article extraction using newspaper4k."""

import logging

from newspaper import Article

from src import config

logger = logging.getLogger(__name__)


def extract_article_text(url):
    """Extract the full article text from a URL using newspaper4k.

    Args:
        url: The article URL to extract text from

    Returns:
        Extracted article text, or empty string on failure
    """
    try:
        article = Article(url)
        article.config.browser_user_agent = config.USER_AGENT
        article.config.request_timeout = 15
        article.download()
        article.parse()

        text = article.text
        if text:
            logger.debug(f"Extracted {len(text)} chars from {url}")
            return text
        else:
            logger.warning(f"No text extracted from {url}")
            return ""

    except Exception as e:
        logger.warning(f"Failed to extract text from {url}: {e}")
        return ""
