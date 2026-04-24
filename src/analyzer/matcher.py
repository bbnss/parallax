"""2-tier story matching: keywords → embeddings (no LLM tier)."""

import json
import logging
import re
import time
import unicodedata
from datetime import timedelta
from itertools import combinations

from src.db import get_connection

logger = logging.getLogger(__name__)

# Maximum hours between two articles to be considered the same event
MAX_HOURS_APART = 48

# Cosine similarity threshold — raised to 0.75 to compensate for no LLM confirmation
EMBEDDING_THRESHOLD = 0.75

# Minimum keyword overlap to proceed to embedding check
MIN_KEYWORD_OVERLAP = 2

# Keywords that strongly suggest pure domestic politics — skip these articles
DOMESTIC_POLITICS_SIGNALS = {
    # US domestic
    "congressman", "congresswoman", "senate race", "governor race", "midterm",
    "primary election", "republican primary", "democrat primary", "ballot measure",
    "state legislature", "city council", "mayor race", "school board",
    # Generic domestic signals
    "local election", "municipal election", "regional election", "county",
    "domestic policy", "national assembly vote", "parliament vote",
    # Tabloid / celebrity / sport / crime (no geopolitical value)
    "celebrity", "box office", "oscars", "grammy", "nba finals", "super bowl",
    "premier league", "formula 1", "transfer fee", "world cup qualifier",
    "sexual misconduct", "molotov cocktail", "armed robbery", "car crash",
    "epstein", "reality tv", "kardashian", "entertainment news",
    "true crime", "serial killer", "murder suspect", "home invasion",
}

# Geopolitical relevance signals — always keep
GEOPOLITICAL_SIGNALS = {
    "war", "conflict", "military", "troops", "sanctions", "diplomat", "diplomacy",
    "treaty", "summit", "united nations", "nato", "nuclear", "missile", "invasion",
    "ceasefire", "peace talks", "bilateral", "foreign minister", "secretary of state",
    "trade war", "embargo", "refugee", "humanitarian", "coup", "protest", "uprising",
    "election", "president", "prime minister", "government", "crisis", "alliance",
    "geopolit", "strategic", "terrorism", "attack", "airstrike", "drone",
}


def _is_geopolitical(article):
    """Return True if the article is geopolitically relevant."""
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()

    for sig in GEOPOLITICAL_SIGNALS:
        if sig in text:
            return True

    for sig in DOMESTIC_POLITICS_SIGNALS:
        if sig in text:
            return False

    return True


def _normalize(text):
    """Lowercase, remove punctuation, normalize unicode."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return text


def _keyword_set(title, keywords_json):
    """Build a set of normalized tokens from title + stored keywords."""
    tokens = set()
    for w in _normalize(title).split():
        if len(w) >= 3 and w not in STOPWORDS:
            tokens.add(w)
    if keywords_json:
        try:
            kws = json.loads(keywords_json)
            for k in kws:
                for w in _normalize(k).split():
                    if len(w) >= 3:
                        tokens.add(w)
        except (json.JSONDecodeError, TypeError):
            pass
    return tokens


def _cosine_similarity(vec_a, vec_b):
    """Compute cosine similarity between two lists of floats."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _get_embedding(text):
    """Get a sentence embedding via sentence-transformers (lazy import, Apple MPS)."""
    try:
        from sentence_transformers import SentenceTransformer
        if not hasattr(_get_embedding, "_model"):
            logger.info("Loading sentence-transformers model (first time)...")
            # NOTE: We use the EN-only model because all summaries/keywords are forced to
            # English by the Gemma prompts (see prompts.py). The multilingual model would
            # require a HuggingFace download — kept the EN-only one which is already cached.
            _get_embedding._model = SentenceTransformer("all-MiniLM-L6-v2")
        embedding = _get_embedding._model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    except ImportError:
        logger.warning("sentence-transformers not installed, skipping embedding tier")
        return None


def find_matching_pairs(articles):
    """Find all pairs of articles that cover the same event.

    Uses 2-tier approach (no LLM):
    1. Temporal filter + keyword overlap (fast)
    2. Embedding cosine similarity ≥ 0.75 (fast, runs on MPS)

    Args:
        articles: List of article dicts from the database

    Returns:
        List of (article_id_a, article_id_b) tuples that are confirmed matches
    """
    t_start = time.time()
    confirmed_pairs = []
    tier1_candidates = []

    logger.info(f"Matching {len(articles)} articles for story clusters...")

    # Pre-filter: keep only geopolitically relevant articles
    before = len(articles)
    articles = [a for a in articles if _is_geopolitical(a)]
    skipped = before - len(articles)
    if skipped:
        logger.info(f"  Geopolitical filter: dropped {skipped} articles ({len(articles)} remain)")

    # Count articles per faction for logging
    faction_counts = {}
    for a in articles:
        r = a.get("region", "unknown")
        faction_counts[r] = faction_counts.get(r, 0) + 1
    logger.info(f"  Articles by faction: {faction_counts}")

    # Total potential pairs
    n = len(articles)
    total_potential = n * (n - 1) // 2
    logger.info(f"  Potential pairs (C({n},2)): {total_potential:,}")

    # Build keyword sets for all articles
    kw_sets = {}
    for a in articles:
        kw_sets[a["id"]] = _keyword_set(a["title"], a.get("keywords"))

    # Tier 1: temporal + keyword overlap
    t1_start = time.time()
    skipped_same_source = 0
    skipped_temporal = 0

    for a, b in combinations(articles, 2):
        if a["source_id"] == b["source_id"]:
            skipped_same_source += 1
            continue

        ta = a["published_at"]
        tb = b["published_at"]
        if ta and tb:
            try:
                from dateutil import parser as dp
                dt_a = dp.parse(str(ta)) if isinstance(ta, str) else ta
                dt_b = dp.parse(str(tb)) if isinstance(tb, str) else tb
                if abs((dt_a - dt_b).total_seconds()) > MAX_HOURS_APART * 3600:
                    skipped_temporal += 1
                    continue
            except Exception:
                pass

        overlap = kw_sets[a["id"]] & kw_sets[b["id"]]
        if len(overlap) >= MIN_KEYWORD_OVERLAP:
            tier1_candidates.append((a, b, overlap))

    t1_elapsed = time.time() - t1_start
    logger.info(
        f"  Tier 1 (keyword): {len(tier1_candidates):,} candidates "
        f"({t1_elapsed:.1f}s) — skipped {skipped_same_source:,} same-source, "
        f"{skipped_temporal:,} temporal"
    )

    # Tier 2: embedding similarity (this is now the FINAL tier — no LLM confirmation)
    t2_start = time.time()
    passed = 0
    failed = 0

    for i, (a, b, overlap) in enumerate(tier1_candidates):
        text_a = (a["summary"] or a["title"])[:300]
        text_b = (b["summary"] or b["title"])[:300]

        emb_a = _get_embedding(text_a)
        emb_b = _get_embedding(text_b)

        if emb_a is None or emb_b is None:
            # sentence-transformers not available — accept on keyword match alone
            confirmed_pairs.append((a["id"], b["id"]))
            passed += 1
            continue

        sim = _cosine_similarity(emb_a, emb_b)
        if sim >= EMBEDDING_THRESHOLD:
            confirmed_pairs.append((a["id"], b["id"]))
            passed += 1
            logger.debug(
                f"    Match (sim={sim:.3f}): '{a['title'][:50]}' ↔ '{b['title'][:50]}'"
            )
        else:
            failed += 1

        # Progress log every 500 pairs
        if (i + 1) % 500 == 0:
            logger.info(
                f"    Tier 2 progress: {i+1}/{len(tier1_candidates)} "
                f"({passed} matched, {failed} rejected)"
            )

    t2_elapsed = time.time() - t2_start
    total_elapsed = time.time() - t_start

    logger.info(
        f"  Tier 2 (embedding ≥{EMBEDDING_THRESHOLD}): "
        f"{passed} matched, {failed} rejected ({t2_elapsed:.1f}s)"
    )
    logger.info(
        f"  Matching complete: {len(confirmed_pairs)} confirmed pairs "
        f"in {total_elapsed:.1f}s (no LLM used)"
    )

    return confirmed_pairs


def _generate_slug(title, date):
    """Generate a URL-friendly slug from title and date."""
    slug = _normalize(title)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = slug[:60].strip("-")
    date_str = str(date)[:10] if date else "unknown"
    return f"{date_str}-{slug}"


def build_clusters_from_pairs(confirmed_pairs, articles_by_id):
    """Group matched pairs into story clusters using union-find.

    Returns:
        List of clusters, each a list of article IDs
    """
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    for a_id, b_id in confirmed_pairs:
        union(a_id, b_id)

    groups = {}
    for a_id, b_id in confirmed_pairs:
        for aid in (a_id, b_id):
            root = find(aid)
            groups.setdefault(root, set()).add(aid)

    # Only keep clusters with articles from at least 2 different regions
    valid_clusters = []
    for root, ids in groups.items():
        regions = set()
        for aid in ids:
            a = articles_by_id.get(aid)
            if a:
                regions.add(a["region"])
        if len(regions) >= 2:
            valid_clusters.append(sorted(ids))

    logger.info(
        f"  Clusters: {len(valid_clusters)} valid (≥2 factions) "
        f"out of {len(groups)} total groups"
    )

    return valid_clusters


def save_clusters(clusters, articles_by_id):
    """Persist story clusters and their article associations to the database."""
    saved = 0
    for cluster_ids in clusters:
        articles = [articles_by_id[aid] for aid in cluster_ids if aid in articles_by_id]
        if not articles:
            continue

        dates = [a["published_at"] for a in articles if a["published_at"]]
        event_date = str(sorted(dates)[-1])[:10] if dates else None

        first_title = articles[0]["title"]
        slug = _generate_slug(first_title, event_date)

        with get_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM story_clusters WHERE slug=?", (slug,)
            ).fetchone()
            if existing:
                cluster_id = existing["id"]
            else:
                cursor = conn.execute(
                    """INSERT INTO story_clusters (slug, title, event_date)
                       VALUES (?, ?, ?)""",
                    (slug, first_title, event_date),
                )
                cluster_id = cursor.lastrowid
                saved += 1

            for aid in cluster_ids:
                conn.execute(
                    """INSERT OR IGNORE INTO cluster_articles (cluster_id, article_id)
                       VALUES (?, ?)""",
                    (cluster_id, aid),
                )
            conn.execute(
                "UPDATE articles SET matched=1 WHERE id IN (%s)"
                % ",".join("?" * len(cluster_ids)),
                cluster_ids,
            )

    return saved


def run_matching(recent_hours=72):
    """Run the full matching pipeline on recently collected articles."""
    with get_connection() as conn:
        articles = conn.execute(
            """SELECT a.id, a.title, a.summary, a.keywords, a.published_at,
                      a.source_id, s.name as source_name, s.region, s.country
               FROM articles a
               JOIN sources s ON a.source_id = s.id
               WHERE a.processed = 1
                 AND a.matched = 0
                 AND a.summary IS NOT NULL
               ORDER BY a.published_at DESC
               LIMIT 500"""
        ).fetchall()

    articles = [dict(a) for a in articles]
    articles_by_id = {a["id"]: a for a in articles}

    if len(articles) < 2:
        logger.info("Not enough processed articles to match")
        return {"pairs": 0, "clusters": 0}

    logger.info(f"Starting matching pipeline with {len(articles)} articles")
    pairs = find_matching_pairs(articles)
    clusters = build_clusters_from_pairs(pairs, articles_by_id)
    saved = save_clusters(clusters, articles_by_id)

    logger.info(f"Matching result: {len(pairs)} pairs → {len(clusters)} clusters → {saved} new saved")
    return {"pairs": len(pairs), "clusters": saved}


# Common English stopwords to exclude from keyword matching
STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "has",
    "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
    "how", "man", "new", "now", "old", "see", "two", "way", "who", "its",
    "had", "let", "put", "say", "she", "too", "use", "with", "that", "this",
    "have", "from", "they", "will", "been", "more", "also", "into", "than",
    "then", "when", "over", "said", "were", "what", "your", "some", "time",
    "very", "after", "years", "would", "about", "could", "their", "there",
    "these", "other", "first", "which", "those", "being", "where", "while",
    "before", "during", "people", "state", "world", "government", "official",
}
