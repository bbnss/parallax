"""Parallax — HTML preview generator — multi-language, collapsible cards, globe.

Features:
- 5 languages: EN (base) + IT, ES, DE, FR (LLM-translated, cached)
- Full UI localization: all labels switch with language
- Country-aware: selecting a language highlights & prioritises home-country sources
- Collapsible cards: title + summary visible, full analysis on expand
- Small SVG globe rotated to the dominant region perspective
- Source-specific flag icons per badge
- Archives previous preview to data/previews/YYYY-MM-DD_HH-MM.html

Run: python scripts/generate_preview.py [--days 3] [--no-translate]
Opens: data/preview.html
"""

import re
import sys
import os
import json
import shutil
import hashlib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import get_connection
from src.analyzer import ollama_client

# ── Source-specific flag mapping ─────────────────────────────────────────────
SOURCE_FLAGS = {
    "BBC World":         "\U0001f1ec\U0001f1e7",
    "DW News":           "\U0001f1e9\U0001f1ea",
    "France 24":         "\U0001f1eb\U0001f1f7",
    "NPR World":         "\U0001f1fa\U0001f1f8",
    "El Pais English":   "\U0001f1ea\U0001f1f8",
    "Euronews":          "\U0001f1ea\U0001f1fa",
    "Xinhua English":    "\U0001f1e8\U0001f1f3",
    "CGTN":              "\U0001f1e8\U0001f1f3",
    "NDTV World":        "\U0001f1ee\U0001f1f3",
    "Times of India":    "\U0001f1ee\U0001f1f3",
    "Bangkok Post":      "\U0001f1f9\U0001f1ed",
    "Channel News Asia": "\U0001f1f8\U0001f1ec",
    "Al Jazeera":        "\U0001f1f6\U0001f1e6",
    "Middle East Eye":   "\U0001f1f5\U0001f1f8",
    "Anadolu Agency":    "\U0001f1f9\U0001f1f7",
    "Dawn":              "\U0001f1f5\U0001f1f0",
    "TASS":              "\U0001f1f7\U0001f1fa",
    "RT":                "\U0001f1f7\U0001f1fa",
    "The Moscow Times":  "\U0001f1f7\U0001f1fa",
    "ANSA English":      "\U0001f1ee\U0001f1f9",
    "ANSA Mondo":        "\U0001f1ee\U0001f1f9",
    "Il Post":           "\U0001f1ee\U0001f1f9",
    "Repubblica Esteri": "\U0001f1ee\U0001f1f9",
    "Il Sole 24 Ore Mondo": "\U0001f1ee\U0001f1f9",
    "Il Manifesto":      "\U0001f1ee\U0001f1f9",
    "Corriere Esteri":   "\U0001f1ee\U0001f1f9",
    # legacy
    "Rappler":           "\U0001f1f5\U0001f1ed",
    "Al-Ahram":          "\U0001f1ea\U0001f1ec",
    "PressTV":           "\U0001f1ee\U0001f1f7",
}

REGION_COLORS = {
    "western":     "#3b82f6",
    "eastern":     "#ef4444",
    "middle_east": "#8b5cf6",
    "russia":      "#f59e0b",
    "chinese":     "#ef4444",
    "indian":      "#f97316",
    "russian":     "#f59e0b",
}

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PREVIEWS_ARCHIVE_DIR = os.path.join(_DATA_DIR, "previews")
OUT_PATH = os.path.join(_DATA_DIR, "preview.html")

# ── Multi-language configuration ─────────────────────────────────────────────
TRANSLATION_LANGUAGES = ["it", "es", "de", "fr"]   # EN is the base, not translated
ALL_LANGUAGES = ["en"] + TRANSLATION_LANGUAGES

LANG_INFO = {
    "en": {"name": "English",  "country_codes": ["UK", "US"]},
    "it": {"name": "Italian",  "country_codes": ["IT"]},
    "es": {"name": "Spanish",  "country_codes": ["ES"]},
    "de": {"name": "German",   "country_codes": ["DE"]},
    "fr": {"name": "French",   "country_codes": ["FR"]},
}

# UI strings for full site localization (embedded into JS at build time)
UI_STRINGS = {
    "en": {
        "tagline": "Same event. Different vantage points.",
        "comparisons": "comparisons", "sources": "sources", "blocs": "blocs",
        "readMore": "Read full analysis", "close": "Close",
        "articles": "articles", "regions": "regions",
        "tierA": "Confirmed globally", "tierB": "Cross-bloc coverage", "tierC": "Partial coverage",
        "countryCoverage": "Local coverage",
        "source1": "source", "sourceN": "sources",
    },
    "it": {
        "tagline": "Stesso evento. Punti di vista diversi.",
        "comparisons": "confronti", "sources": "fonti", "blocs": "blocchi",
        "readMore": "Leggi analisi completa", "close": "Chiudi",
        "articles": "articoli", "regions": "regioni",
        "tierA": "Confermata globalmente", "tierB": "Copertura cross-bloc", "tierC": "Copertura parziale",
        "countryCoverage": "Copertura italiana",
        "source1": "fonte", "sourceN": "fonti",
    },
    "es": {
        "tagline": "Mismo evento. Diferentes puntos de vista.",
        "comparisons": "comparaciones", "sources": "fuentes", "blocs": "bloques",
        "readMore": "Leer el analisis completo", "close": "Cerrar",
        "articles": "articulos", "regions": "regiones",
        "tierA": "Confirmada globalmente", "tierB": "Cobertura cross-bloc", "tierC": "Cobertura parcial",
        "countryCoverage": "Cobertura espanola",
        "source1": "fuente", "sourceN": "fuentes",
    },
    "de": {
        "tagline": "Gleiches Ereignis. Verschiedene Blickwinkel.",
        "comparisons": "Vergleiche", "sources": "Quellen", "blocs": "Bloecke",
        "readMore": "Vollstaendige Analyse lesen", "close": "Schliessen",
        "articles": "Artikel", "regions": "Regionen",
        "tierA": "Global bestaetigt", "tierB": "Blockuebergreifend", "tierC": "Teilabdeckung",
        "countryCoverage": "Deutsche Abdeckung",
        "source1": "Quelle", "sourceN": "Quellen",
    },
    "fr": {
        "tagline": "Meme evenement. Points de vue differents.",
        "comparisons": "comparaisons", "sources": "sources", "blocs": "blocs",
        "readMore": "Lire l'analyse complete", "close": "Fermer",
        "articles": "articles", "regions": "regions",
        "tierA": "Confirmee mondialement", "tierB": "Couverture inter-blocs", "tierC": "Couverture partielle",
        "countryCoverage": "Couverture francaise",
        "source1": "source", "sourceN": "sources",
    },
}

# ── Dedup / tier thresholds ──────────────────────────────────────────────────
SAME_DAY_THRESHOLD  = 0.78
CROSS_DAY_THRESHOLD = 0.65
PREVIEW_MAX_CARDS   = 25

TIER_LABELS = {"A": "Confirmed globally", "B": "Cross-bloc coverage", "C": "Partial coverage"}
TIER_ICONS  = {"A": "&#9673;", "B": "&#9671;", "C": "&#9723;"}
TIER_COLORS = {"A": "#10b981", "B": "#60a5fa", "C": "#94a3b8"}


def compute_tier(comp):
    regions = comp.get("region_count", 0) or 0
    sources = comp.get("source_count", 0) or 0
    if regions >= 4 or (regions >= 3 and sources >= 5):
        return "A"
    if regions >= 3:
        return "B"
    return "C"


# ── Globe SVG component ─────────────────────────────────────────────────────
GLOBE_CONTINENTS = (
    '<path d="M17,6 L28,4 L33,12 L30,17 L22,15 L18,10 Z" fill="#2d5a47"/>'
    '<path d="M25,19 L32,20 L31,33 L26,36 L23,28 Z" fill="#2d5a47"/>'
    '<path d="M57,5 L65,4 L67,10 L63,14 L57,12 Z" fill="#2d5a47"/>'
    '<path d="M58,15 L67,14 L71,23 L67,34 L61,35 L57,27 Z" fill="#2d5a47"/>'
    '<path d="M69,3 L88,2 L100,7 L98,14 L86,18 L74,15 L69,9 Z" fill="#2d5a47"/>'
    '<path d="M78,17 L84,16 L83,24 L79,25 Z" fill="#2d5a47"/>'
    '<path d="M96,27 L105,26 L108,31 L103,34 L96,32 Z" fill="#2d5a47"/>'
)
GLOBE_OFFSETS   = {"western": -40, "middle_east": -52, "russia": -56, "eastern": -72}
REGION_DOT_POS  = {"western": (62, 10), "eastern": (92, 13), "middle_east": (73, 18), "russia": (80, 7)}

HEADING_REGION_KEYWORDS = {
    "western":     ["western", "west ", "european", "american", "u.s.", "nato",
                    " eu ", "transatlantic", "washington", "brussels", "london"],
    "eastern":     ["eastern", "east ", "chinese", "china", "asian", "asia",
                    "beijing", "indian", "india", "delhi", "pacific"],
    "middle_east": ["middle east", "arab", "turkish", "turkey", "iran",
                    "gulf", "qatar", "israeli", "palestinian", "tehran",
                    "ankara", "riyadh"],
    "russia":      ["russian", "russia", "moscow", "kremlin", "soviet"],
}


def _pick_globe_region(regions):
    for r in ("eastern", "middle_east", "russia", "western"):
        if r in regions:
            return r
    return "western"


def build_globe_svg(regions_seen, card_id):
    offset = GLOBE_OFFSETS.get(_pick_globe_region(regions_seen), -40)
    dots = ""
    for r in regions_seen:
        if r in REGION_DOT_POS:
            x, y = REGION_DOT_POS[r]
            color = REGION_COLORS.get(r, "#6b7280")
            dots += f'<circle cx="{x}" cy="{y}" r="2.5" fill="{color}" opacity="0.9"/>'
            dots += f'<circle cx="{x}" cy="{y}" r="5" fill="{color}" opacity="0.15"/>'
    clip_id = f"gc{card_id}"
    return (
        f'<svg viewBox="0 0 40 40" width="36" height="36" style="flex-shrink:0">'
        f'<defs><clipPath id="{clip_id}"><circle cx="20" cy="20" r="19"/></clipPath></defs>'
        f'<circle cx="20" cy="20" r="19" fill="#0c1929" stroke="#334155" stroke-width="0.7"/>'
        f'<g clip-path="url(#{clip_id})">'
        f'<g transform="translate({offset},0)">{GLOBE_CONTINENTS}{dots}</g></g>'
        f'<circle cx="14" cy="13" r="10" fill="white" opacity="0.04"/></svg>'
    )


def build_inline_globe_svg(region, uid):
    offset = GLOBE_OFFSETS.get(region, -40)
    color = REGION_COLORS.get(region, "#6b7280")
    x, y = REGION_DOT_POS.get(region, (62, 10))
    clip_id = f"ig{uid}"
    return (
        f'<svg viewBox="0 0 40 40" width="22" height="22" style="flex-shrink:0">'
        f'<defs><clipPath id="{clip_id}"><circle cx="20" cy="20" r="19"/></clipPath></defs>'
        f'<circle cx="20" cy="20" r="19" fill="#0c1929" stroke="#334155" stroke-width="0.7"/>'
        f'<g clip-path="url(#{clip_id})">'
        f'<g transform="translate({offset},0)">{GLOBE_CONTINENTS}'
        f'<circle cx="{x}" cy="{y}" r="3" fill="{color}" opacity="0.9"/>'
        f'<circle cx="{x}" cy="{y}" r="6" fill="{color}" opacity="0.15"/>'
        f'</g></g>'
        f'<circle cx="14" cy="13" r="10" fill="white" opacity="0.04"/></svg>'
    )


def detect_region_from_heading(text):
    lower = text.lower()
    for region, keywords in HEADING_REGION_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return region
    return None


# ── Summary / preamble ───────────────────────────────────────────────────────

def extract_summary(text):
    if not text:
        return ""
    for line in text.split("\n")[:10]:
        s = line.strip()
        if s.startswith("*") and s.endswith("*") and not s.startswith("**") and s != "***" and len(s) > 5:
            return s.strip("*").strip()
    for line in text.split("\n"):
        s = line.strip()
        if s and not s.startswith("#") and s not in ("***", "---") and not s.startswith("*") and len(s) > 30:
            return s[:300] + ("..." if len(s) > 300 else "")
    return ""


def strip_preamble(text):
    if not text:
        return ""
    lines = text.strip().split("\n")
    for i, line in enumerate(lines):
        if line.strip().startswith("## "):
            return "\n".join(lines[i:]).strip()
    return text


# ── Deduplication ────────────────────────────────────────────────────────────

def _deduplicate_comparisons(comps):
    if len(comps) < 2:
        return comps
    try:
        from src.analyzer.matcher import _get_embedding, _cosine_similarity
    except ImportError:
        return comps[:PREVIEW_MAX_CARDS]

    embeddings = [_get_embedding(c["title"]) for c in comps]
    parent = list(range(len(comps)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(comps)):
        for j in range(i + 1, len(comps)):
            if embeddings[i] is None or embeddings[j] is None:
                continue
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            same_day = comps[i]["event_date"] == comps[j]["event_date"]
            threshold = SAME_DAY_THRESHOLD if same_day else CROSS_DAY_THRESHOLD
            if sim >= threshold:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    groups = {}
    for i in range(len(comps)):
        groups.setdefault(find(i), []).append(i)

    kept = set()
    for group in groups.values():
        if len(group) == 1:
            kept.add(group[0])
        else:
            same_day_group = len(set(comps[i]["event_date"] for i in group)) == 1
            if same_day_group:
                winner = max(group, key=lambda i: comps[i]["article_count"])
            else:
                winner = max(group, key=lambda i: comps[i]["event_date"])
            kept.add(winner)

    result = [c for i, c in enumerate(comps) if i in kept]
    removed = len(comps) - len(result)
    result.sort(key=lambda c: (c["event_date"], c["article_count"]), reverse=True)
    if len(result) > PREVIEW_MAX_CARDS:
        result = result[:PREVIEW_MAX_CARDS]
        print(f"   Cap applied: showing top {PREVIEW_MAX_CARDS} stories")
    if removed:
        print(f"   Smart dedup: removed {removed} duplicate(s) -> {len(result)} shown")
    return result


# ── Markdown to HTML ─────────────────────────────────────────────────────────

def md_to_html(text, card_id=None):
    if not text:
        return ""
    lines = text.split("\n")
    html = []
    for i, line in enumerate(lines):
        line = line.rstrip()
        if line.startswith("### "):
            heading = line[4:]
            region = detect_region_from_heading(heading) if card_id is not None else None
            if region:
                globe = build_inline_globe_svg(region, f"{card_id}h{i}")
                html.append(f'<h4 class="region-heading">{globe}<span>{heading}</span></h4>')
            else:
                html.append(f'<h4>{heading}</h4>')
        elif line.startswith("## "):
            heading = line[3:]
            region = detect_region_from_heading(heading) if card_id is not None else None
            if region:
                globe = build_inline_globe_svg(region, f"{card_id}h{i}")
                html.append(f'<h3 class="region-heading">{globe}<span>{heading}</span></h3>')
            else:
                html.append(f'<h3>{heading}</h3>')
        elif line.startswith("# "):
            html.append(f'<h2>{line[2:]}</h2>')
        elif line.startswith("- "):
            html.append(f'<li>{line[2:]}</li>')
        elif line == "":
            html.append('<br>')
        else:
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            line = re.sub(r'\*(.*?)\*', r'<em>\1</em>', line)
            html.append(f'<p>{line}</p>')
    return "\n".join(html)


# ── Translation ──────────────────────────────────────────────────────────────

# Domain glossary: per-language preferred renderings for terms the LLM tends to
# mishandle (geographic features, institutions, military/political ranks, severity
# terms, common diplomatic vocabulary). Injected verbatim into the translation
# prompt so the model sees authoritative pairs instead of guessing.
GLOSSARY = {
    "it": {
        "Lebanon": "Libano", "Pentagon": "Pentagono", "White House": "Casa Bianca",
        "Strait of Hormuz": "Stretto di Hormuz", "West Bank": "Cisgiordania",
        "Gaza Strip": "Striscia di Gaza", "United Nations": "Nazioni Unite",
        "European Union": "Unione Europea", "NATO": "NATO",
        "Pope Leo XIV": "Papa Leone XIV", "Vatican": "Vaticano",
        "Secretary of State": "Segretario di Stato",
        "Navy Secretary": "Segretario della Marina",
        "Defense Secretary": "Segretario della Difesa",
        "Foreign Minister": "Ministro degli Esteri",
        "Prime Minister": "Primo Ministro", "envoy": "inviato",
        "ceasefire": "cessate il fuoco", "early-stage": "in stadio iniziale",
        "advanced-stage": "in stadio avanzato", "oil pipeline": "oleodotto",
        "gas pipeline": "gasdotto", "Druzhba pipeline": "oleodotto Druzhba",
        "World Cup": "Coppa del Mondo", "Eastern": "orientale",
        "Western": "occidentale", "Middle Eastern": "del Medio Oriente",
        "Russian": "russo",
    },
    "de": {
        "Lebanon": "Libanon", "Pentagon": "Pentagon", "White House": "Weißes Haus",
        "Strait of Hormuz": "Straße von Hormuz", "West Bank": "Westjordanland",
        "Gaza Strip": "Gazastreifen", "United Nations": "Vereinte Nationen",
        "European Union": "Europäische Union", "NATO": "NATO",
        "Pope Leo XIV": "Papst Leo XIV.", "Vatican": "Vatikan",
        "Secretary of State": "Außenminister",
        "Navy Secretary": "Marineminister",
        "Defense Secretary": "Verteidigungsminister",
        "Foreign Minister": "Außenminister",
        "Prime Minister": "Premierminister", "envoy": "Gesandter",
        "ceasefire": "Waffenstillstand", "early-stage": "im Frühstadium",
        "advanced-stage": "im fortgeschrittenen Stadium",
        "oil pipeline": "Ölpipeline", "gas pipeline": "Gaspipeline",
        "Druzhba pipeline": "Druschba-Pipeline", "World Cup": "Weltmeisterschaft",
        "Eastern": "östlich", "Western": "westlich",
        "Middle Eastern": "nahöstlich", "Russian": "russisch",
    },
    "es": {
        "Lebanon": "Líbano", "Pentagon": "Pentágono", "White House": "Casa Blanca",
        "Strait of Hormuz": "Estrecho de Ormuz", "West Bank": "Cisjordania",
        "Gaza Strip": "Franja de Gaza", "United Nations": "Naciones Unidas",
        "European Union": "Unión Europea", "NATO": "OTAN",
        "Pope Leo XIV": "Papa León XIV", "Vatican": "Vaticano",
        "Secretary of State": "Secretario de Estado",
        "Navy Secretary": "Secretario de la Marina",
        "Defense Secretary": "Secretario de Defensa",
        "Foreign Minister": "Ministro de Asuntos Exteriores",
        "Prime Minister": "Primer Ministro", "envoy": "enviado",
        "ceasefire": "alto el fuego", "early-stage": "en etapa temprana",
        "advanced-stage": "en etapa avanzada", "oil pipeline": "oleoducto",
        "gas pipeline": "gasoducto", "Druzhba pipeline": "oleoducto Druzhba",
        "World Cup": "Mundial", "Eastern": "oriental",
        "Western": "occidental", "Middle Eastern": "del Medio Oriente",
        "Russian": "ruso",
    },
    "fr": {
        "Lebanon": "Liban", "Pentagon": "Pentagone", "White House": "Maison-Blanche",
        "Strait of Hormuz": "détroit d'Ormuz", "West Bank": "Cisjordanie",
        "Gaza Strip": "bande de Gaza", "United Nations": "Nations unies",
        "European Union": "Union européenne", "NATO": "OTAN",
        "Pope Leo XIV": "pape Léon XIV", "Vatican": "Vatican",
        "Secretary of State": "secrétaire d'État",
        "Navy Secretary": "secrétaire à la Marine",
        "Defense Secretary": "secrétaire à la Défense",
        "Foreign Minister": "ministre des Affaires étrangères",
        "Prime Minister": "Premier ministre", "envoy": "envoyé",
        "ceasefire": "cessez-le-feu", "early-stage": "à un stade précoce",
        "advanced-stage": "à un stade avancé", "oil pipeline": "oléoduc",
        "gas pipeline": "gazoduc", "Druzhba pipeline": "oléoduc Droujba",
        "World Cup": "Coupe du monde", "Eastern": "oriental",
        "Western": "occidental", "Middle Eastern": "du Moyen-Orient",
        "Russian": "russe",
    },
}

# Severity / quantitative pairs: when the source text contains the EN key, the
# translation MUST contain at least one of the listed substrings (case-insensitive).
# Catches inversions like "early-stage" → "fortgeschritten" (advanced).
SEVERITY_TERMS = {
    "early-stage": {"it": ["iniziale", "precoce"], "de": ["frühstadium", "präkoz", "früh"],
                    "es": ["temprana", "inicial", "precoz"], "fr": ["précoce", "initial"]},
    "early stage": {"it": ["iniziale", "precoce"], "de": ["frühstadium", "präkoz", "früh"],
                    "es": ["temprana", "inicial", "precoz"], "fr": ["précoce", "initial"]},
    "advanced": {"it": ["avanzat"], "de": ["fortgeschritt"],
                 "es": ["avanzad"], "fr": ["avancé"]},
    "ceasefire": {"it": ["cessate il fuoco", "tregua"], "de": ["waffenstillstand"],
                  "es": ["alto el fuego"], "fr": ["cessez-le-feu"]},
}


def _glossary_for_prompt(lang):
    g = GLOSSARY.get(lang, {})
    if not g:
        return ""
    pairs = "\n".join(f"  - {en} → {tr}" for en, tr in g.items())
    return "Use these exact translations for these terms when they appear:\n" + pairs


def _severity_violations(en_text, tr_text, lang):
    """Return list of (en_keyword, expected_terms) where source contains en_keyword
    but translation lacks any of the expected target-language equivalents."""
    src = (en_text or "").lower()
    dst = (tr_text or "").lower()
    out = []
    for en_kw, by_lang in SEVERITY_TERMS.items():
        if en_kw not in src:
            continue
        expected = by_lang.get(lang, [])
        if not expected:
            continue
        if not any(term in dst for term in expected):
            out.append((en_kw, expected))
    return out


def _translation_cache_dir(lang, model):
    from src import config as _cfg
    base = os.path.join(_DATA_DIR, "translations", lang)
    if model == _cfg.TRANSLATE_MODEL:
        return base
    slug = model.replace(":", "_").replace("/", "_")
    return os.path.join(_DATA_DIR, "translations", f"{lang}_{slug}")


def _parse_translation(result):
    """Parse translated title and body from LLM output — tries multiple label formats."""
    for title_lbl, body_lbl in [
        ("TITLE:", "ANALYSIS:"),
        ("TITOLO:", "ANALISI:"),
        ("TITULO:", "ANALISIS:"),
        ("TITEL:", "ANALYSE:"),
        ("TITRE:", "ANALYSE:"),
    ]:
        if title_lbl in result and body_lbl in result:
            parts = result.split(body_lbl, 1)
            body = parts[1].strip() if len(parts) > 1 else None
            title = None
            for line in parts[0].split("\n"):
                if line.strip().startswith(title_lbl):
                    title = line.strip()[len(title_lbl):].strip()
                    break
            if title and body:
                return title, body
    return None, None


def _source_hash(title, text):
    """Stable fingerprint of the source content used to invalidate stale translations
    when a cluster_id is reused for a different story."""
    h = hashlib.sha256()
    h.update((title or "").encode("utf-8"))
    h.update(b"\x00")
    h.update((text or "")[:12000].encode("utf-8"))
    return h.hexdigest()[:16]


def translate_text(cluster_id, title, text, lang, translate_model=None):
    """Translate title + comparison text to any target language. Cached to disk.

    Cache is keyed by cluster_id but validated against a hash of the source content,
    so stale entries (cluster_id reassigned to a different story) are auto-regenerated.
    """
    from src import config as _cfg
    model = translate_model or _cfg.TRANSLATE_MODEL
    lang_name = LANG_INFO[lang]["name"]

    cache_dir = _translation_cache_dir(lang, model)
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{cluster_id}.json")
    src_hash = _source_hash(title, text)

    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            try:
                cached = json.load(f)
                if (cached.get("title") and cached.get("body")
                        and cached.get("source_hash") == src_hash):
                    return cached["title"], cached["body"]
            except (json.JSONDecodeError, KeyError):
                pass

    glossary_block = _glossary_for_prompt(lang)

    base_prompt = f"""Translate the following news headline and analysis into {lang_name}.

Localization rules:
- Localize country names, institutions, ministries, military ranks, religious titles,
  and well-known geographic features into {lang_name} when a standard local form exists.
- Keep ONLY the following unchanged: personal names of individuals (e.g. Donald Trump,
  Benjamin Netanyahu) and brand/outlet names (BBC, Al Jazeera, TASS).
- Preserve quantitative and severity terms exactly: if the source says "early-stage",
  do not render it as "advanced"; if it says "six months", keep "six months"; etc.
- Translate the ## section headers into {lang_name} too.

{glossary_block}

TITLE: {title}

ANALYSIS:
{text[:12000]}

Reply in this EXACT format:
TITLE: [translated title here]
ANALYSIS:
[translated analysis here]"""

    def _run(prompt_text):
        r = ollama_client.generate(prompt_text, model=model, temperature=0.2, timeout=120)
        if not r or len(r) < 50:
            return None, None, None
        t, b = _parse_translation(r)
        return t, b, r

    tr_title, tr_body, raw = _run(base_prompt)
    if raw is None:
        return None, None

    # Sanity check: severity/quantitative consistency. If violated, retry once with
    # an explicit corrective prefix listing the expected target terms.
    violations = _severity_violations(text, (tr_title or "") + "\n" + (tr_body or ""), lang)
    if violations:
        warn_lines = "\n".join(
            f"- The source contains \"{kw}\". Your translation MUST use one of: "
            f"{', '.join(exp)}." for kw, exp in violations
        )
        retry_prompt = ("PREVIOUS ATTEMPT FAILED a severity/quantitative consistency check:\n"
                        f"{warn_lines}\nRedo the translation respecting these terms exactly.\n\n"
                        + base_prompt)
        t2, b2, raw2 = _run(retry_prompt)
        if raw2 is not None:
            still = _severity_violations(text, (t2 or "") + "\n" + (b2 or ""), lang)
            if len(still) < len(violations):
                tr_title, tr_body, raw = t2, b2, raw2
                violations = still
        if violations:
            print(f"   [WARN] {lang.upper()} cluster {cluster_id}: severity check still failing"
                  f" after retry: {[v[0] for v in violations]}")

    if not tr_title:
        tr_title = title
    if not tr_body:
        tr_body = raw

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"title": tr_title, "body": tr_body, "model": model, "lang": lang,
                   "source_hash": src_hash},
                  f, ensure_ascii=False, indent=2)
    return tr_title, tr_body


def _audit_translations(comps, all_translations, langs):
    """Pre-render sanity audit of generated translations. Logs warnings only —
    does not fail the build. Catches: missing translations, untranslated titles
    (target == EN), suspiciously short bodies, leftover source-language fragments."""
    issues = []
    for comp in comps:
        cid = comp["id"]
        en_title = (comp["title"] or "").strip()
        en_title_norm = re.sub(r'\s+', ' ', en_title.lower())
        for lang in langs:
            tr = all_translations.get(cid, {}).get(lang)
            if not tr or not tr[0] or not tr[1]:
                issues.append((cid, lang, "missing", en_title[:60]))
                continue
            tr_title, tr_body = tr
            tr_title_norm = re.sub(r'\s+', ' ', (tr_title or "").strip().lower())
            if tr_title_norm == en_title_norm and len(en_title_norm) > 20:
                issues.append((cid, lang, "title-untranslated", en_title[:60]))
            if len(tr_body or "") < 200:
                issues.append((cid, lang, "body-too-short", en_title[:60]))
    if issues:
        print(f"   [AUDIT] {len(issues)} translation issue(s):")
        for cid, lang, kind, hint in issues:
            print(f"            cluster {cid} [{lang.upper()}] {kind}: \"{hint}\"")
    else:
        print(f"   [AUDIT] All translations passed basic checks.")


def archive_previous_preview():
    if not os.path.exists(OUT_PATH):
        return
    os.makedirs(PREVIEWS_ARCHIVE_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    dest = os.path.join(PREVIEWS_ARCHIVE_DIR, f"{timestamp}.html")
    shutil.copy2(OUT_PATH, dest)
    print(f"   Archived previous preview -> {dest}")


# ── Card builder ─────────────────────────────────────────────────────────────

def build_card(comp, translations):
    """Build HTML card — collapsed by default, with content in all languages.

    translations: dict {lang: (title, body)} for each TRANSLATION_LANGUAGES entry.
    """
    sources_raw = comp["sources_raw"] or ""
    sources = []
    regions_seen = set()
    countries_count = {}
    for item in sources_raw.split(","):
        parts = item.split("@@")
        if len(parts) >= 3:
            name, region, country = parts[0].strip(), parts[1].strip(), parts[2].strip()
            sources.append((name, region))
            regions_seen.add(region)
            if country:
                countries_count[country] = countries_count.get(country, 0) + 1

    # Source badges
    badges = ""
    for name, region in sources:
        color = REGION_COLORS.get(region, "#6b7280")
        flag = SOURCE_FLAGS.get(name, "")
        badges += (f'<span class="badge" style="background:{color}20;'
                   f'color:{color};border:1px solid {color}40">{flag} {name}</span> ')

    # Region pills
    region_pills = ""
    for r in sorted(regions_seen):
        color = REGION_COLORS.get(r, "#6b7280")
        label = r.replace("_", " ").upper()
        region_pills += f'<span class="region-pill" style="border-color:{color};color:{color}">{label}</span> '

    cid = comp["id"]
    globe = build_globe_svg(regions_seen, cid)

    # Tier
    tier = comp.get("tier", "C")
    tier_color = TIER_COLORS[tier]
    tier_icon = TIER_ICONS[tier]
    region_count = comp.get("region_count", len(regions_seen)) or 0
    source_count = comp.get("source_count", len(sources)) or 0

    convergence_badge = (
        f'<span class="convergence" data-tier="{tier}" data-icon="{tier_icon}" '
        f'data-regions="{region_count}" data-sources="{source_count}" '
        f'style="background:{tier_color}1a;color:{tier_color};border:1px solid {tier_color}50">'
        f'{tier_icon} {TIER_LABELS[tier]} &middot; {region_count} regions &middot; {source_count} sources'
        f'</span>'
    )

    # Country badge placeholder (JS fills in the text based on active language)
    country_badge = (
        f'<span class="country-badge" style="display:none;background:#00924620;'
        f'color:#34d399;border:1px solid #00924650;margin-left:6px;'
        f'font-size:0.68rem;font-weight:600;padding:0.2rem 0.6rem;border-radius:3px">'
        f'</span>'
    )

    countries_json = json.dumps(countries_count, ensure_ascii=False)

    # ── Multi-language content ──
    # Titles
    titles_html = f'<h2 class="card-title lang-en">{comp["title"]}</h2>\n'
    for lang in TRANSLATION_LANGUAGES:
        t = translations.get(lang, (None, None))[0] or comp["title"]
        titles_html += f'        <h2 class="card-title lang-{lang}" style="display:none">{t}</h2>\n'

    # Summaries
    en_summary = extract_summary(comp["comparison_text"])
    summaries_html = f'<p class="card-summary lang-en">{en_summary}</p>\n'
    for lang in TRANSLATION_LANGUAGES:
        t_body = translations.get(lang, (None, None))[1]
        s = extract_summary(t_body) if t_body else en_summary
        summaries_html += f'        <p class="card-summary lang-{lang}" style="display:none">{s}</p>\n'

    # Expand button (label updated by JS on language switch)
    btn_html = (
        f'<button class="expand-btn" id="toggle-{cid}" onclick="toggleCard({cid})">'
        f'<span class="arrow">&#9660;</span> '
        f'<span class="btn-label">Read full analysis</span>'
        f'</button>'
    )

    # Bodies
    en_body = strip_preamble(comp["comparison_text"])
    en_body_html = md_to_html(en_body, card_id=cid)
    bodies_html = f'<div class="comparison lang-en">{en_body_html}</div>\n'
    for lang in TRANSLATION_LANGUAGES:
        t_body = translations.get(lang, (None, None))[1]
        if t_body:
            t_stripped = strip_preamble(t_body)
            t_html = md_to_html(t_stripped, card_id=f"{cid}{lang}")
        else:
            t_html = '<p class="no-translation">Translation not available.</p>'
        bodies_html += f'            <div class="comparison lang-{lang}" style="display:none">{t_html}</div>\n'

    return f"""
    <article class="card tier-{tier.lower()}" style="--tier-color:{tier_color}"
             data-countries='{countries_json}'>
        <div class="card-header">
            <div class="card-meta">
                <span class="date">{comp["event_date"]}</span>
                <span class="sep">&middot;</span>
                <span class="count">{comp["article_count"]} <span data-ui="articles">articles</span></span>
            </div>
            <div class="card-header-right">
                {region_pills}
                {globe}
            </div>
        </div>
        <div class="convergence-row">{convergence_badge}{country_badge}</div>
        {titles_html}
        {summaries_html}
        <div class="sources">{badges}</div>
        {btn_html}
        <div class="card-body" id="body-{cid}">
            {bodies_html}
        </div>
    </article>
    """


# ── Main generator ───────────────────────────────────────────────────────────

def generate(translate=True, days=1, translate_model=None, out_path=None):
    dest = out_path or OUT_PATH
    from src import config as _cfg
    _tmodel = translate_model or _cfg.TRANSLATE_MODEL
    langs = TRANSLATION_LANGUAGES if translate else []

    with get_connection() as conn:
        comps = conn.execute('''
            SELECT sc.id, sc.title, sc.event_date, c.comparison_text,
                   GROUP_CONCAT(DISTINCT s.name || '@@' || s.region || '@@' || COALESCE(s.country,'')) as sources_raw,
                   COUNT(DISTINCT a.id)        as article_count,
                   COUNT(DISTINCT a.source_id) as source_count,
                   COUNT(DISTINCT s.region)    as region_count
            FROM comparisons c
            JOIN story_clusters sc ON sc.id = c.cluster_id
            JOIN cluster_articles ca ON ca.cluster_id = sc.id
            JOIN articles a ON a.id = ca.article_id
            JOIN sources s ON s.id = a.source_id
            WHERE sc.event_date >= date('now', ?)
            GROUP BY c.id
            ORDER BY sc.event_date DESC, sc.id DESC
        ''', (f'-{days} days',)).fetchall()

    comps = [dict(c) for c in comps]
    print(f"   Found {len(comps)} comparisons")
    comps = _deduplicate_comparisons(comps)

    for c in comps:
        c["tier"] = compute_tier(c)
    tier_order = {"A": 0, "B": 1, "C": 2}
    comps.sort(key=lambda c: c["article_count"] or 0, reverse=True)
    comps.sort(key=lambda c: c["event_date"] or "", reverse=True)
    comps.sort(key=lambda c: tier_order[c["tier"]])

    tier_counts = {"A": 0, "B": 0, "C": 0}
    for c in comps:
        tier_counts[c["tier"]] += 1
    print(f"   Tiers: A={tier_counts['A']}  B={tier_counts['B']}  C={tier_counts['C']}")

    archive_previous_preview()

    # ── Translate to all target languages ──
    all_translations = {}
    for comp in comps:
        all_translations[comp["id"]] = {}

    for lang in langs:
        lang_name = LANG_INFO[lang]["name"]
        cached = 0
        generated = 0
        for i, comp in enumerate(comps):
            if comp["comparison_text"]:
                cache_dir = _translation_cache_dir(lang, _tmodel)
                cache_file = os.path.join(cache_dir, f"{comp['id']}.json")
                is_cached = os.path.exists(cache_file)
                print(f"   [{lang.upper()}] {i+1}/{len(comps)}: cluster {comp['id']}"
                      f" {'(cached)' if is_cached else '(translating...)'}     ", end="\r")
                all_translations[comp["id"]][lang] = translate_text(
                    comp["id"], comp["title"], comp["comparison_text"],
                    lang, translate_model=translate_model,
                )
                if is_cached:
                    cached += 1
                else:
                    generated += 1
            else:
                all_translations[comp["id"]][lang] = (None, None)
        print(f"   [{lang.upper()}] Done: {cached} cached, {generated} new translations          ")

    if langs:
        _audit_translations(comps, all_translations, langs)

    # ── Render cards ──
    cards_html = ""
    for tier in ("A", "B", "C"):
        tier_comps = [c for c in comps if c["tier"] == tier]
        if not tier_comps:
            continue
        color = TIER_COLORS[tier]
        icon = TIER_ICONS[tier]
        label = TIER_LABELS[tier]
        cards_html += (
            f'<section class="tier-section">'
            f'<h2 class="section-header" style="color:{color};border-color:{color}50">'
            f'{icon} <span data-tier-label="{tier}">{label}</span>'
            f' <span class="section-count">({len(tier_comps)})</span>'
            f'</h2>'
        )
        for comp in tier_comps:
            cards_html += build_card(comp, all_translations.get(comp["id"], {}))
        cards_html += '</section>'

    source_count = len(SOURCE_FLAGS)
    region_count = 4

    # Language buttons
    lang_btns = ""
    active_langs = ["en"] + langs
    for lang in ALL_LANGUAGES:
        if lang not in active_langs:
            continue
        active = " active" if lang == "en" else ""
        lang_btns += (f'<button class="lang-btn{active}" data-lang="{lang}" '
                      f'onclick="setLang(\'{lang}\')">{lang.upper()}</button>\n      ')

    ui_json = json.dumps(UI_STRINGS, ensure_ascii=False)
    lang_countries_json = json.dumps({l: info["country_codes"] for l, info in LANG_INFO.items()}, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Parallax &mdash; Same event, different vantage points</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #080c14; color: #c0c8d8; line-height: 1.7;
    -webkit-font-smoothing: antialiased;
  }}
  header {{
    background: linear-gradient(180deg, #0e1420 0%, #080c14 100%);
    border-bottom: 1px solid #1a2235; padding: 2.5rem 2rem 2rem; text-align: center;
  }}
  .logo {{
    font-family: 'JetBrains Mono', monospace; font-size: 2rem; font-weight: 700;
    color: #e4e8f0; letter-spacing: 6px; text-transform: uppercase;
  }}
  .logo .accent {{ color: #60a5fa; }}
  .tagline {{ color: #5a6578; margin-top: 0.4rem; font-size: 0.9rem; font-style: italic; }}
  .stats {{
    display: flex; gap: 1rem; justify-content: center; margin-top: 1.2rem; flex-wrap: wrap;
  }}
  .stat {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #4a5568;
    padding: 0.3rem 0.8rem; border: 1px solid #1a2235; border-radius: 4px; background: #0a0f1a;
  }}
  .stat strong {{ color: #60a5fa; }}
  .lang-switcher {{ display: flex; gap: 0.4rem; justify-content: center; margin-top: 1rem; flex-wrap: wrap; }}
  .lang-btn {{
    background: #0a0f1a; border: 1px solid #1a2235; border-radius: 4px;
    color: #4a5568; cursor: pointer; font-size: 0.85rem; padding: 0.3rem 0.8rem;
    font-family: 'Inter', sans-serif; transition: all 0.15s;
  }}
  .lang-btn:hover {{ border-color: #60a5fa; color: #c0c8d8; }}
  .lang-btn.active {{ background: #111827; border-color: #60a5fa; color: #60a5fa; font-weight: 600; }}
  main {{ max-width: 860px; margin: 0 auto; padding: 2rem 1rem; }}
  .tier-section {{ margin-bottom: 2.5rem; }}
  .section-header {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 2px; padding: 0.4rem 0 0.5rem;
    margin-bottom: 1rem; border-bottom: 1px solid; display: flex; align-items: baseline; gap: 0.5rem;
  }}
  .section-count {{ font-size: 0.75rem; font-weight: 400; opacity: 0.5; text-transform: none; letter-spacing: 0; }}
  .card {{
    background: #0e1420; border: 1px solid #1a2235; border-radius: 8px;
    margin-bottom: 1.5rem; overflow: hidden;
    border-left: 3px solid var(--tier-color, #1a2235); transition: border-color 0.2s, box-shadow 0.2s;
  }}
  .card:hover {{ border-color: var(--tier-color); box-shadow: 0 2px 20px rgba(0,0,0,0.3); }}
  .card.tier-a {{ background: linear-gradient(135deg, #0e1420 0%, #0c1a18 100%); border-left-width: 4px; }}
  .card.tier-c {{ opacity: 0.88; }}
  .card-header {{
    padding: 0.7rem 1.2rem; display: flex; justify-content: space-between;
    align-items: center; flex-wrap: wrap; gap: 0.5rem; border-bottom: 1px solid #141c2a;
  }}
  .card-meta {{
    display: flex; gap: 0.5rem; align-items: center;
    font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #3e4a5e;
  }}
  .card-meta .sep {{ opacity: 0.4; }}
  .card-header-right {{ display: flex; gap: 0.5rem; align-items: center; }}
  .convergence-row {{ padding: 0.5rem 1.2rem 0; display: flex; flex-wrap: wrap; align-items: center; }}
  .convergence {{
    display: inline-block; font-size: 0.68rem; font-weight: 600;
    padding: 0.2rem 0.6rem; border-radius: 3px; letter-spacing: 0.3px;
  }}
  .card-title {{
    padding: 0.6rem 1.2rem 0.2rem; font-size: 1.1rem;
    color: #e4e8f0; font-weight: 600; line-height: 1.35;
  }}
  .card.tier-a .card-title {{ font-size: 1.2rem; }}
  .card.tier-c .card-title {{ font-size: 1rem; }}
  .card-summary {{
    padding: 0 1.2rem 0.5rem; color: #6b7a94; font-size: 0.85rem;
    font-style: italic; line-height: 1.55;
  }}
  .sources {{ padding: 0.3rem 1.2rem 0.5rem; display: flex; flex-wrap: wrap; gap: 0.3rem; }}
  .badge {{ display: inline-block; font-size: 0.68rem; padding: 0.15rem 0.5rem; border-radius: 3px; font-weight: 500; }}
  .region-pill {{
    display: inline-block; font-size: 0.6rem; font-weight: 700;
    padding: 0.15rem 0.4rem; border-radius: 3px; border: 1px solid;
    letter-spacing: 0.5px; font-family: 'JetBrains Mono', monospace;
  }}
  .expand-btn {{
    display: block; width: 100%; background: none; border: none;
    border-top: 1px solid #141c2a; color: #4a6fa5; cursor: pointer;
    font-size: 0.78rem; font-family: 'Inter', sans-serif; padding: 0.55rem;
    text-align: center; transition: background 0.15s, color 0.15s; letter-spacing: 0.3px;
  }}
  .expand-btn:hover {{ background: #111827; color: #60a5fa; }}
  .expand-btn .arrow {{ display: inline-block; transition: transform 0.2s; margin-right: 0.3rem; }}
  .expand-btn.active .arrow {{ transform: rotate(180deg); }}
  .card-body {{ display: none; }}
  .card-body.show {{ display: block; }}
  .comparison {{ padding: 0.8rem 1.2rem 1.2rem; border-top: 1px solid #141c2a; }}
  .comparison h2 {{ font-size: 0.95rem; font-weight: 700; color: #e4e8f0; margin: 1rem 0 0.4rem; }}
  .comparison h3 {{
    font-size: 0.82rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1px; color: #60a5fa; margin: 1.2rem 0 0.4rem;
    padding-bottom: 0.25rem; border-bottom: 1px solid #1a2235;
  }}
  .comparison h4 {{ font-size: 0.8rem; font-weight: 600; color: #8896ad; margin: 0.8rem 0 0.3rem; }}
  .region-heading {{ display: flex; align-items: center; gap: 8px; }}
  .region-heading svg {{ margin-top: 1px; }}
  .comparison p {{ color: #a0aec0; font-size: 0.88rem; margin-bottom: 0.3rem; }}
  .comparison li {{ color: #a0aec0; font-size: 0.88rem; margin-left: 1.2rem; }}
  .comparison strong {{ color: #e4e8f0; }}
  .comparison em {{ color: #6b7a94; font-style: italic; }}
  .comparison br {{ display: block; margin: 0.15rem 0; }}
  .no-translation {{ color: #3e4a5e; font-style: italic; }}
  footer {{
    text-align: center; padding: 2rem; color: #2a3244; font-size: 0.72rem;
    font-family: 'JetBrains Mono', monospace; border-top: 1px solid #0e1420;
  }}
  @media (max-width: 600px) {{
    .logo {{ font-size: 1.5rem; letter-spacing: 4px; }}
    main {{ padding: 1rem 0.5rem; }}
    .card-header {{ flex-direction: column; align-items: flex-start; }}
    .card-header-right {{ width: 100%; justify-content: space-between; }}
    .card-title {{ font-size: 1rem; }}
  }}
</style>
</head>
<body>
<header>
  <div class="logo"><span class="accent">&#9671;</span> PARALLAX</div>
  <p class="tagline">Same event. Different vantage points.</p>
  <div class="stats">
    <div class="stat"><strong>{len(comps)}</strong> <span data-ui="comparisons">comparisons</span></div>
    <div class="stat"><strong>{source_count}</strong> <span data-ui="sources">sources</span></div>
    <div class="stat"><strong>{region_count}</strong> <span data-ui="blocs">blocs</span></div>
  </div>
  <div class="lang-switcher">
    {lang_btns}
  </div>
</header>
<main>
{cards_html}
</main>
<footer>
  Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} &middot;
  Parallax &middot; Analysis: Gemma 4 &middot; Translation: {_tmodel} &middot;
  Local LLM, zero cloud cost
</footer>
<script>
var UI = {ui_json};
var LANG_COUNTRIES = {lang_countries_json};

function setLang(lang) {{
  var allLangs = {json.dumps(ALL_LANGUAGES)};
  var s = UI[lang] || UI['en'];

  // 1. Toggle content visibility
  allLangs.forEach(function(l) {{
    document.querySelectorAll('.lang-' + l).forEach(function(el) {{
      el.style.display = l === lang ? '' : 'none';
    }});
  }});

  // 2. Update button active state
  document.querySelectorAll('.lang-btn').forEach(function(btn) {{
    btn.classList.toggle('active', btn.dataset.lang === lang);
  }});

  // 3. Update static UI text
  document.querySelector('.tagline').textContent = s.tagline;
  document.querySelectorAll('[data-ui]').forEach(function(el) {{
    if (s[el.dataset.ui]) el.textContent = s[el.dataset.ui];
  }});

  // 4. Update convergence badges
  document.querySelectorAll('.convergence').forEach(function(el) {{
    var tier = el.dataset.tier;
    var tierLabel = tier === 'A' ? s.tierA : tier === 'B' ? s.tierB : s.tierC;
    el.innerHTML = el.dataset.icon + ' ' + tierLabel +
      ' &middot; ' + el.dataset.regions + ' ' + s.regions +
      ' &middot; ' + el.dataset.sources + ' ' + s.sourceN;
  }});

  // 5. Update tier section headers
  document.querySelectorAll('[data-tier-label]').forEach(function(el) {{
    var tier = el.dataset.tierLabel;
    el.textContent = tier === 'A' ? s.tierA : tier === 'B' ? s.tierB : s.tierC;
  }});

  // 6. Update country badges
  var countries = LANG_COUNTRIES[lang] || [];
  document.querySelectorAll('.country-badge').forEach(function(el) {{
    var card = el.closest('.card');
    var data = JSON.parse(card.dataset.countries || '{{}}');
    var count = 0;
    countries.forEach(function(c) {{ count += (data[c] || 0); }});
    if (count > 0 && lang !== 'en') {{
      el.style.display = '';
      var srcLabel = count === 1 ? s.source1 : s.sourceN;
      el.textContent = s.countryCoverage + ' \\u00B7 ' + count + ' ' + srcLabel;
    }} else {{
      el.style.display = 'none';
    }}
  }});

  // 7. Re-sort cards within each tier section by country relevance
  //    (disabled — default is chronological order for all languages)
  //    Uncomment to enable per-language sorting by local source count:
  // if (countries.length > 0 && lang !== 'en') {{
  //   document.querySelectorAll('.tier-section').forEach(function(section) {{
  //     var cards = Array.from(section.querySelectorAll('.card'));
  //     cards.sort(function(a, b) {{
  //       var ad = JSON.parse(a.dataset.countries || '{{}}');
  //       var bd = JSON.parse(b.dataset.countries || '{{}}');
  //       var asc = 0, bsc = 0;
  //       countries.forEach(function(c) {{ asc += (ad[c] || 0); bsc += (bd[c] || 0); }});
  //       return bsc - asc;
  //     }});
  //     cards.forEach(function(card) {{ section.appendChild(card); }});
  //   }});
  // }}

  // 8. Update expand button labels
  document.querySelectorAll('.expand-btn').forEach(function(btn) {{
    var isExpanded = btn.classList.contains('active');
    btn.querySelector('.btn-label').textContent = isExpanded ? s.close : s.readMore;
  }});

  document.documentElement.lang = lang;
}}

function toggleCard(id) {{
  var body = document.getElementById('body-' + id);
  var btn = document.getElementById('toggle-' + id);
  var expanded = body.classList.toggle('show');
  btn.classList.toggle('active', expanded);
  var lang = document.documentElement.lang || 'en';
  var s = UI[lang] || UI['en'];
  btn.querySelector('.btn-label').textContent = expanded ? s.close : s.readMore;
}}
</script>
</body>
</html>"""

    with open(dest, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   Preview generated: {dest}")
    active = ["en"] + langs
    print(f"   {len(comps)} comparisons, languages: {', '.join(l.upper() for l in active)}, translation: {_tmodel}")
    return dest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-translate", action="store_true", help="Skip translations (EN only)")
    parser.add_argument("--days", type=int, default=1, help="Show comparisons from last N days (default: 1)")
    parser.add_argument("--translate-model", default=None,
                        help="Ollama model for translation (default: TRANSLATE_MODEL from .env)")
    parser.add_argument("--out", default=None,
                        help="Output HTML path (default: data/preview.html)")
    args = parser.parse_args()

    path = generate(
        translate=not args.no_translate,
        days=args.days,
        translate_model=args.translate_model,
        out_path=args.out,
    )
    import subprocess
    subprocess.run(["open", path])
