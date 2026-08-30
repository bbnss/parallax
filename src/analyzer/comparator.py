"""Generate perspective comparison reports for story clusters — 4 factions."""

import json
import logging

from src.analyzer import article_sections, ollama_client, prompts
from src.db import get_connection

logger = logging.getLogger(__name__)

# Region mapping: source region → faction
# Legacy aliases (chinese, indian) are preserved for backward compat with old DB rows
WESTERN_REGIONS     = {"western"}
EASTERN_REGIONS     = {"eastern", "chinese", "indian"}
MIDDLE_EAST_REGIONS = {"middle_east"}
RUSSIA_REGIONS      = {"russia", "russian"}

# Minimum articles required per faction to include it in a comparison
MIN_ARTICLES_PER_SIDE = 2


def _split_by_faction(articles):
    """Split articles into 4 faction groups."""
    western     = [a for a in articles if a["region"] in WESTERN_REGIONS]
    eastern     = [a for a in articles if a["region"] in EASTERN_REGIONS]
    middle_east = [a for a in articles if a["region"] in MIDDLE_EAST_REGIONS]
    russia      = [a for a in articles if a["region"] in RUSSIA_REGIONS]
    return western, eastern, middle_east, russia


def _factions_present(western, eastern, middle_east, russia):
    """Return list of factions that have enough articles."""
    present = []
    if len(western)     >= MIN_ARTICLES_PER_SIDE: present.append("western")
    if len(eastern)     >= MIN_ARTICLES_PER_SIDE: present.append("eastern")
    if len(middle_east) >= MIN_ARTICLES_PER_SIDE: present.append("middle_east")
    # Russia has only 1 source (TASS) → lower threshold to 1
    if len(russia) >= 1: present.append("russia")
    return present


def _is_geopolitical_cluster(cluster_title, articles):
    """LLM gate: drop clusters that are not geopolitical (accidents, celebrity, etc.)."""
    summaries = [a.get("summary") for a in articles[:3] if a.get("summary")]
    prompt = prompts.is_geopolitical_cluster(cluster_title, summaries)
    raw = ollama_client.generate(prompt, temperature=0.0).strip().upper()
    first = raw.split()[0].rstrip(".,:;!?") if raw else ""
    return first == "YES"


def _refine_cluster_title(cluster_id, articles):
    """Ask the LLM to generate a clean neutral title for the cluster."""
    article_list = [{"title": a["title"], "source_name": a["source_name"]} for a in articles]
    prompt = prompts.generate_cluster_title(article_list)
    title = ollama_client.generate(prompt, temperature=0.3).strip().strip('"').strip("'").strip()
    if title:
        with get_connection() as conn:
            conn.execute(
                "UPDATE story_clusters SET title=? WHERE id=?",
                (title, cluster_id),
            )
    return title


def generate_comparison(cluster_id):
    """Generate a 4-faction perspective comparison for one story cluster.

    Returns True if comparison was generated, False otherwise.
    """
    with get_connection() as conn:
        cluster = conn.execute(
            "SELECT * FROM story_clusters WHERE id=?", (cluster_id,)
        ).fetchone()
        if not cluster:
            logger.error(f"Cluster {cluster_id} not found")
            return False

        existing = conn.execute(
            "SELECT id FROM comparisons WHERE cluster_id=?", (cluster_id,)
        ).fetchone()
        if existing:
            return True

        articles = conn.execute(
            """SELECT a.id, a.title, a.summary, a.url,
                      s.name as source_name, s.region, s.country
               FROM articles a
               JOIN cluster_articles ca ON ca.article_id = a.id
               JOIN sources s ON a.source_id = s.id
               WHERE ca.cluster_id = ?""",
            (cluster_id,),
        ).fetchall()

    articles = [dict(a) for a in articles]
    western, eastern, middle_east, russia = _split_by_faction(articles)
    factions = _factions_present(western, eastern, middle_east, russia)

    if len(factions) < 2:
        total = len(western) + len(eastern) + len(middle_east) + len(russia)
        logger.info(
            f"Cluster {cluster_id}: skipping — need ≥2 factions "
            f"(western={len(western)}, eastern={len(eastern)}, "
            f"middle_east={len(middle_east)}, russia={len(russia)}, total={total})"
        )
        return False

    logger.info(
        f"Generating comparison for cluster {cluster_id}: "
        f"western={len(western)}, eastern={len(eastern)}, "
        f"middle_east={len(middle_east)}, russia={len(russia)}"
    )

    cluster_title = _refine_cluster_title(cluster_id, articles)
    if not cluster_title:
        cluster_title = cluster["title"]

    if not _is_geopolitical_cluster(cluster_title, articles):
        logger.info(f"Cluster {cluster_id}: skipping — not geopolitical ('{cluster_title}')")
        return False

    prompt = prompts.compare_perspectives(
        cluster_title=cluster_title,
        event_date=cluster["event_date"] or "recent",
        western_articles=western,
        eastern_articles=eastern,
        middle_east_articles=middle_east,
        russia_articles=russia,
        factions_present=factions,
    )
    # The 180s that fitted e4b leaves 3s of margin on the 12b: the largest real
    # cluster (47 articles, 4528 prompt tokens) measured 177.0s. num_predict caps
    # the work at 4096 tokens, which at ~9 tok/s cannot exceed ~500s.
    comparison_text = ollama_client.generate(prompt, temperature=0.4, timeout=600,
                                             num_predict=4096)

    if not comparison_text:
        logger.error(f"Empty comparison generated for cluster {cluster_id}")
        return False

    sections = _parse_sections(comparison_text)

    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO comparisons
               (cluster_id, comparison_text, key_differences, key_agreements,
                western_frame, nonwestern_frame, omissions)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                cluster_id,
                comparison_text,
                json.dumps(sections.get("key_differences", "")),
                json.dumps(sections.get("factual_agreement", "")),
                sections.get("western_framing", ""),
                # Combine eastern + ME + russian framing in the legacy nonwestern_frame field
                "\n\n".join(filter(None, [
                    sections.get("eastern_framing", ""),
                    sections.get("middle_east_framing", ""),
                    sections.get("russian_framing", ""),
                ])),
                json.dumps(sections.get("notable_omissions", "")),
            ),
        )
        conn.execute("UPDATE story_clusters SET published=0 WHERE id=?", (cluster_id,))

    logger.info(f"  Saved comparison for cluster {cluster_id}: '{cluster_title}'")
    return True


def _parse_sections(text):
    """Extract named sections from the comparison markdown text.

    Delegates to article_sections, which parses by section order and by the bold
    faction labels rather than by literal header names — the prompt asks the model
    to invent its headers, so a name-based map matched only by luck.
    """
    parsed = article_sections.parse(text)
    return {
        "factual_agreement":   parsed.get("facts", ""),
        "key_differences":     parsed.get("divergence", ""),
        "western_framing":     parsed.get("western", ""),
        "eastern_framing":     parsed.get("eastern", ""),
        "middle_east_framing": parsed.get("middle_east", ""),
        "russian_framing":     parsed.get("russia", ""),
        "notable_omissions":   parsed.get("omissions", ""),
        "geopolitical_context": parsed.get("geopolitical", ""),
    }


def process_unpublished_clusters():
    """Generate comparisons for all clusters that don't have one yet."""
    with get_connection() as conn:
        clusters = conn.execute(
            """SELECT sc.id FROM story_clusters sc
               LEFT JOIN comparisons c ON c.cluster_id = sc.id
               WHERE c.id IS NULL
               ORDER BY sc.created_at DESC"""
        ).fetchall()

    cluster_ids = [c["id"] for c in clusters]
    logger.info(f"Generating comparisons for {len(cluster_ids)} clusters...")

    generated = skipped = failed = 0
    for cluster_id in cluster_ids:
        try:
            if generate_comparison(cluster_id):
                generated += 1
            else:
                skipped += 1
        except Exception as e:
            failed += 1
            logger.error(f"Failed for cluster {cluster_id}: {e}")

    logger.info(f"Comparisons: {generated} generated, {skipped} skipped, {failed} failed")
    return {"generated": generated, "skipped": skipped, "failed": failed}
