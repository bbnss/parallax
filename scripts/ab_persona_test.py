#!/usr/bin/env python3
"""AB Persona Test — run the comparison pipeline with a journalist persona.

Instead of the neutral "media analyst" voice, Gemma is instructed to write
as a journalist trained in the style of a specific school of thought.
No real names are mentioned — only the intellectual tradition.

Usage:
  python scripts/ab_persona_test.py --persona A   # populist / anti-establishment
  python scripts/ab_persona_test.py --persona B   # investigative / civil-liberties
  python scripts/ab_persona_test.py --persona C   # policy-analytical / internationalist

Input:  data/ab_base.db  (must exist — run ab_base.py first)
Output: data/test_persona_{A/B/C}.db
        data/preview_persona_{A/B/C}.html
"""
import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── Journalist personas ───────────────────────────────────────────────────────
# Each persona replaces the opening instruction of compare_perspectives().
# The rest of the prompt (sources, format, headers) stays unchanged.

PERSONAS = {

    "A": {
        "label": "Populist / Anti-Establishment",
        "description": """You are a television journalist and political commentator trained \
by a master of populist broadcasting who built a career challenging Washington's foreign \
policy consensus. Your mentor taught you that the most important question is always: \
who in the establishment benefits from this narrative, and who is being silenced? \
You were trained to distrust official government statements, to find the story that \
corporate media refuses to tell, and to speak plainly to the citizens who feel abandoned \
by the political class. You believe international conflicts are frequently engineered by \
elites at the expense of ordinary people who have no voice in the decision.

Your goal is to analyze the following international coverage and expose what each media \
faction chooses to emphasize, what inconvenient facts they bury, and whose interests \
their framing ultimately serves. Ask the questions the powerful would prefer you not ask.""",
    },

    "B": {
        "label": "Investigative / Civil-Liberties",
        "description": """You are an investigative journalist and former constitutional \
attorney trained in the tradition of adversarial accountability journalism. Your mentor \
spent decades at the intersection of national security law and press freedom, exposing \
how governments — regardless of political party or ideology — use secrecy, propaganda, \
and institutional power to pursue elite interests. You apply rigorous documentary \
standards, are equally skeptical of Western liberal media and authoritarian state outlets, \
and believe the most revealing analysis identifies the shared assumptions that ALL media \
factions take for granted — the questions nobody asks, the facts all sides quietly agree \
to ignore.

Your goal is to analyze the following international coverage by dissecting the \
institutional interests each outlet serves, the claims each leaves unquestioned, \
and the structural power dynamics their framing obscures or legitimizes.""",
    },

    "C": {
        "label": "Policy-Analytical / Internationalist",
        "description": """You are an international affairs journalist and foreign policy \
analyst trained in the tradition of long-form geopolitical commentary. Your mentor edited \
a prestigious foreign affairs journal and later anchored a weekly international program, \
teaching you to situate every news event within its historical, structural, and \
institutional context: the balance of power, long-term strategic trends, and the \
international frameworks — legal, economic, diplomatic — that constrain and shape state \
behavior. You write for sophisticated readers who want more than headlines: they want \
to understand why events happen, what historical precedents they echo, and what they \
signal about the evolving international order.

Your goal is to analyze the following international coverage by placing each faction's \
framing within its geopolitical and historical context, identifying how long-term \
strategic interests and institutional positions shape what each outlet emphasizes, \
contextualizes, or omits.""",
    },
}

# ── Argument parsing ──────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--persona", choices=["A", "B", "C"], required=True,
                    help="Journalist persona: A=populist, B=investigative, C=policy-analytical")
args = parser.parse_args()

persona_key = args.persona
persona = PERSONAS[persona_key]

BASE_DB    = PROJECT_ROOT / "data" / "ab_base.db"
TEST_DB_REL = f"data/test_persona_{persona_key}.db"
TEST_DB    = PROJECT_ROOT / TEST_DB_REL
OUT_PATH   = PROJECT_ROOT / f"data/preview_persona_{persona_key}.html"

if not BASE_DB.exists():
    print("ERROR: data/ab_base.db not found. Run ab_base.py first.", file=sys.stderr)
    sys.exit(1)

# ── Isolated DB ──────────────────────────────────────────────────────────────
if TEST_DB.exists():
    TEST_DB.unlink()
shutil.copy2(BASE_DB, TEST_DB)
print(f"Copied ab_base.db → {TEST_DB_REL}")

os.environ["DB_PATH"] = TEST_DB_REL

# Delete existing comparisons so they are regenerated with the persona prompt.
# (ab_base.db is a copy of notizie.db which already has comparisons — we want
# fresh ones written in the journalist's voice, not the neutral analyst's.)
import sqlite3 as _sqlite3
_conn = _sqlite3.connect(str(TEST_DB))
_deleted = _conn.execute("DELETE FROM comparisons").rowcount
_conn.commit()
_conn.close()
print(f"Cleared {_deleted} existing comparisons → will regenerate with persona prompt")

# ── Inject persona into the prompts module ────────────────────────────────────
# We import and monkey-patch BEFORE comparator is imported, so the patched
# version is used throughout the comparison pipeline.

import src.analyzer.prompts as _prompts

_original_compare = _prompts.compare_perspectives
_PERSONA_HEADER   = persona["description"]
_NEUTRAL_HEADER   = (
    "You are a media analyst comparing international news coverage of the same event.\n"
    "Your goal is to objectively identify how different regions frame, emphasize, "
    "and omit information."
)


def _persona_compare(cluster_title, event_date, western_articles, eastern_articles,
                     middle_east_articles, russia_articles=None, factions_present=None):
    """Wrapper: replace neutral opener with journalist persona."""
    original_prompt = _original_compare(
        cluster_title, event_date, western_articles, eastern_articles,
        middle_east_articles, russia_articles, factions_present,
    )
    return original_prompt.replace(_NEUTRAL_HEADER, _PERSONA_HEADER, 1)


_prompts.compare_perspectives = _persona_compare

# ── Pipeline ──────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print(f"PERSONA TEST — {persona_key}: {persona['label']}")
print("=" * 60)

from src.analyzer.matcher import run_matching
from src.analyzer.comparator import process_unpublished_clusters
from src.analyzer.ollama_client import (
    is_available, reset_token_stats, get_token_stats,
)

if not is_available():
    print("ERROR: Ollama not running.", file=sys.stderr)
    sys.exit(1)

print("\nStep 1/2: Matching articles (standard pipeline)...")
match_stats = run_matching()
print(f"  {match_stats['pairs']} pairs → {match_stats['clusters']} new clusters")

reset_token_stats()
print("\nStep 2/2: Generating comparisons with persona prompt...")
comp_stats = process_unpublished_clusters()
tok = get_token_stats()
print(f"  Generated: {comp_stats['generated']} | Skipped: {comp_stats['skipped']} | Failed: {comp_stats['failed']}")
print(f"  LLM: {tok['calls']} calls, {tok['total_tokens']:,} tokens")

# ── Preview ───────────────────────────────────────────────────────────────────
print(f"\nGenerating preview_persona_{persona_key}.html...")

import generate_preview as gp

# Inject persona label into the preview header
_original_build_header = None

def _patched_generate(translate=True, days=3):
    """Generate preview to persona-specific output path, no translation."""
    from src.db import get_connection
    from datetime import datetime

    with get_connection() as conn:
        comps = conn.execute('''
            SELECT sc.id, sc.title, sc.event_date, c.comparison_text,
                   GROUP_CONCAT(DISTINCT s.name || '@@' || s.region) as sources_raw,
                   COUNT(DISTINCT a.id) as article_count
            FROM comparisons c
            JOIN story_clusters sc ON sc.id = c.cluster_id
            JOIN cluster_articles ca ON ca.cluster_id = sc.id
            JOIN articles a ON a.id = ca.article_id
            JOIN sources s ON s.id = a.source_id
            WHERE sc.event_date >= date('now', '-3 days')
            GROUP BY c.id
            ORDER BY sc.event_date DESC, sc.id DESC
        ''').fetchall()

    comps = [dict(c) for c in comps]
    print(f"   Found {len(comps)} comparisons")
    comps = gp._deduplicate_comparisons(comps)

    cards_html = "".join(gp.build_card(c, None, None) for c in comps)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NotizieGeopolitica — Persona {persona_key}: {persona['label']}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0f172a; color: #e2e8f0; line-height: 1.7; }}
  header {{ background: linear-gradient(135deg, #1e293b, #0f172a);
            border-bottom: 1px solid #334155; padding: 2rem; text-align: center; }}
  header h1 {{ font-size: 2rem; color: #f1f5f9; letter-spacing: -0.5px; }}
  header p {{ color: #94a3b8; margin-top: 0.5rem; }}
  .persona-badge {{
    display: inline-block; background: #1e3a5f; color: #93c5fd;
    border: 1px solid #3b82f6; border-radius: 6px;
    font-size: 0.8rem; padding: 0.3rem 0.9rem; margin-top: 0.7rem;
    font-weight: 600; letter-spacing: 0.3px;
  }}
  .stats {{ display: flex; gap: 1.5rem; justify-content: center; margin-top: 1rem; flex-wrap: wrap; }}
  .stat {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px;
           padding: 0.5rem 1rem; font-size: 0.85rem; color: #94a3b8; }}
  .stat strong {{ color: #60a5fa; }}
  main {{ max-width: 900px; margin: 0 auto; padding: 2rem 1rem; }}
  .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px;
           margin-bottom: 2rem; overflow: hidden; }}
  .card-header {{ padding: 1rem 1.5rem 0.5rem; display: flex;
                  justify-content: space-between; align-items: center;
                  flex-wrap: wrap; gap: 0.5rem; border-bottom: 1px solid #334155; }}
  .card-meta {{ display: flex; gap: 1rem; font-size: 0.8rem; color: #64748b; }}
  .card-title {{ padding: 1rem 1.5rem 0.5rem; font-size: 1.2rem;
                 color: #f1f5f9; font-weight: 600; line-height: 1.4; }}
  .sources {{ padding: 0.5rem 1.5rem 1rem; display: flex; flex-wrap: wrap; gap: 0.4rem; }}
  .badge {{ display: inline-block; color: white; font-size: 0.72rem;
            padding: 0.2rem 0.6rem; border-radius: 20px; font-weight: 500; opacity: 0.9; }}
  .region-pill {{ display: inline-block; font-size: 0.65rem; font-weight: 700;
                  padding: 0.2rem 0.5rem; border-radius: 4px; border: 1px solid;
                  letter-spacing: 0.5px; }}
  .comparison {{ padding: 0.5rem 1.5rem 1.5rem; border-top: 1px solid #334155; }}
  .comparison h3 {{ font-size: 0.85rem; font-weight: 700; text-transform: uppercase;
                    letter-spacing: 1px; color: #60a5fa; margin: 1.2rem 0 0.4rem;
                    padding-bottom: 0.3rem; border-bottom: 1px solid #1e3a5f; }}
  .comparison p {{ color: #cbd5e1; font-size: 0.92rem; margin-bottom: 0.3rem; }}
  .comparison li {{ color: #cbd5e1; font-size: 0.92rem; margin-left: 1.2rem; }}
  .comparison strong {{ color: #f1f5f9; }}
  .comparison em {{ color: #94a3b8; font-style: italic; }}
  .comparison br {{ display: block; margin: 0.2rem 0; }}
  footer {{ text-align: center; padding: 2rem; color: #475569;
            font-size: 0.8rem; border-top: 1px solid #1e293b; }}
</style>
</head>
<body>
<header>
  <h1>🌍 NotizieGeopolitica</h1>
  <p>Global News · Multiple Perspectives · Generated by Gemma 4</p>
  <div><span class="persona-badge">🎭 Persona {persona_key} — {persona['label']}</span></div>
  <div class="stats">
    <div class="stat"><strong>{len(comps)}</strong> story comparisons</div>
    <div class="stat"><strong>4</strong> factions</div>
    <div class="stat">Persona {persona_key}</div>
  </div>
</header>
<main>
{cards_html}
</main>
<footer>
  Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} ·
  Persona {persona_key}: {persona['label']} ·
  Powered by Gemma 4 via Ollama · Local LLM, zero cloud cost
</footer>
</body>
</html>"""

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Preview generated: {OUT_PATH}")


_patched_generate()
print(f"\n✅ Persona {persona_key} complete → {OUT_PATH}")
