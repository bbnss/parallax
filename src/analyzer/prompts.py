"""All LLM prompt templates for NotizieGeopolitica.

All prompts are centralized here for easy iteration and improvement.
Keep everything in English — translation is a Phase 4 feature.
"""


def summarize(title, source_name, country, content):
    """Generate a neutral 2-3 sentence summary of a news article."""
    # Truncate content to avoid excessive token usage
    content_excerpt = content[:3000] if content else "[No content available]"
    return f"""You are a neutral news analyst. Summarize this article in exactly 2-3 sentences.
Focus on: WHO did WHAT, WHERE, WHEN, and WHY.
Do not add opinion or interpretation. Use neutral, factual language.
IMPORTANT: Write the summary in ENGLISH even if the source article is in another language.

Article title: {title}
Source: {source_name} ({country})
Text: {content_excerpt}

Summary in English (2-3 sentences only):"""


def extract_keywords(title, content):
    """Extract specific keywords identifying the event."""
    content_excerpt = content[:1500] if content else ""
    return f"""Extract 5-8 keywords from this news article that identify the specific event, \
people, places, and organizations involved.
Return ONLY a JSON array of strings. No explanation, no markdown, just the JSON array.
Include proper nouns, specific names, countries, organizations. Avoid generic words like "news", "report", "said".
IMPORTANT: Output keywords in ENGLISH even if the source article is in another language. \
For proper nouns, use the common English spelling (e.g. "Putin" not "Путин", "Beijing" not "北京").

Title: {title}
Text: {content_excerpt}

JSON array:"""


def confirm_match(title_a, source_a, date_a, para_a, title_b, source_b, date_b, para_b):
    """Ask the LLM to confirm whether two articles cover the same specific event."""
    return f"""Are these two news articles reporting on the SAME specific event or development?
Not just the same broad topic, but the exact same news event.

Article A: "{title_a}"
Source: {source_a}, Date: {date_a}
Excerpt: {para_a[:400]}

Article B: "{title_b}"
Source: {source_b}, Date: {date_b}
Excerpt: {para_b[:400]}

Answer with exactly one word: YES or NO"""


def is_geopolitical_cluster(cluster_title, sample_summaries):
    """One-shot yes/no classifier: is this cluster a geopolitical story worth comparing?

    Geopolitical = involving international relations, foreign policy, war/conflict between
    states or factions, sanctions, treaties, sovereignty, cross-border crises, global
    economic blocs, alliances, or events with material implications for the international
    order. NOT geopolitical: domestic accidents, celebrity/crime news, individual lawsuits,
    sports, business mergers, religious tours, weather, regional disasters without
    international stakes.
    """
    summaries_block = "\n".join(f"- {s}" for s in sample_summaries[:3] if s)
    return f"""You are filtering a feed of news clusters for a geopolitics-focused publication.

CLUSTER HEADLINE: {cluster_title}

SAMPLE SUMMARIES:
{summaries_block}

Is this cluster about GEOPOLITICS — meaning it involves international relations, foreign \
policy, conflict between states or armed factions, sanctions, treaties, sovereignty, \
cross-border crises, alliances, or events with clear material implications for the \
international order?

NOT geopolitical: domestic accidents/crashes, celebrity or true-crime news, individual \
lawsuits or business probes, sports, religious tours, single-country regulatory matters \
without international fallout, weather/disaster reports without diplomatic angle.

Answer with exactly one word: YES or NO"""


def compare_perspectives(cluster_title, event_date, western_articles, eastern_articles,
                         middle_east_articles, russia_articles=None, factions_present=None):
    """Generate a structured comparison of how 4 factions cover the same event.

    factions_present: list of faction names with enough articles, e.g. ["western", "eastern", "russia"]
    """
    if russia_articles is None:
        russia_articles = []
    if factions_present is None:
        factions_present = []

    def format_articles(articles):
        if not articles:
            return "(no articles)"
        parts = []
        for a in articles:
            parts.append(
                f"- [{a.get('source_name', a.get('source', '?'))} / {a['region'].upper()}] {a['title']}\n"
                f"  Summary: {a['summary'] or 'No summary available'}"
            )
        return "\n".join(parts)

    # Build the sources block, only including factions that are present
    sources_block = ""
    if "western" in factions_present:
        sources_block += f"WESTERN SOURCES (US, UK, Europe):\n{format_articles(western_articles)}\n\n"
    if "eastern" in factions_present:
        sources_block += f"EASTERN SOURCES (China, India, SE Asia):\n{format_articles(eastern_articles)}\n\n"
    if "middle_east" in factions_present:
        sources_block += f"MIDDLE EASTERN SOURCES (Al Jazeera, Middle East Eye, Anadolu, Dawn):\n{format_articles(middle_east_articles)}\n\n"
    if "russia" in factions_present:
        sources_block += f"RUSSIAN SOURCES (TASS):\n{format_articles(russia_articles)}\n\n"

    # Build the comparative section hint: "N views on the same story"
    faction_labels = {
        "western":     "**The Western approach**",
        "eastern":     "**The Eastern lens**",
        "middle_east": "**The Middle Eastern perspective**",
        "russia":      "**The Russian reading**",
    }
    n_factions = len(factions_present)
    factions_hint = "\n".join(
        f"- {faction_labels[f]}: one paragraph on tone, emphasis, narrative choices, citing specific outlets by name."
        for f in ["western", "eastern", "middle_east", "russia"]
        if f in factions_present
    )

    return f"""You are a media analyst and feature writer comparing international news coverage of the same event. \
Produce an engaging, professional long-form article in English — the kind of analysis piece found in a quality newspaper. \
Write in flowing prose, not bullet points or checklists.

EVENT: {cluster_title}
DATE: {event_date}

{sources_block.strip()}

STRUCTURE:

# [Evocative title for the article]
*[Short punchy subtitle in italics framing the comparative angle]*

---

## [Header for the factual core, e.g. "The facts"]
Open with the undisputed facts all sources agree on. Name the outlets analyzed and weave them into the prose. End with a hook pivoting to the divergences.

## [Header introducing divergences, e.g. "Where the accounts diverge"]
One paragraph: the disagreements are about framing and conditions, not facts. Summarize the main axes of divergence.

## [{n_factions} views on the same story]
{factions_hint}

## [Header about omissions, e.g. "What each account leaves out"]
One paragraph: what each faction omits that others include. Be specific.

## [Header about geopolitical framing]
Describe how each faction contextualizes the event within a broader geopolitical narrative. Close with a short, memorable aphoristic final line.

RULES:
- Flowing prose only. No bullets, no lists.
- 3-5 sentences per section; one paragraph per faction in the comparative section.
- Only include factions actually present in the sources.
- Do not invent facts, quotes, or details beyond the source material.
- Be objective. Observations, not judgments.
- Use narrative transitions so the piece reads as unified, not as disconnected blocks.
- End with a memorable closing line."""


def generate_cluster_title(articles):
    """Ask the LLM to generate a neutral title for a story cluster."""
    titles = "\n".join(f"- {a['title']} ({a.get('source_name', a.get('source', '?'))})" for a in articles[:8])
    return f"""These news articles from different international sources all cover the same event.
Write a single, neutral, descriptive headline (10-15 words) that captures the core event.
Do not take any political stance. Just describe what happened.
Return ONLY the headline, no quotes, no explanation.

Article titles:
{titles}

Neutral headline:"""
