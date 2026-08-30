"""Fold non-English keyword spellings onto their English form.

`prompts.extract_keywords` asks for English keywords, and matcher.py's tier-1
overlap check assumes it got them. Measured on the live DB, Italian sources break
that assumption often enough to matter: "Stati Uniti" appears on 136 articles
where no English source ever emitted it, "Ucraina" on 61, "Teheran" on 135 against
only 66 for "Tehran". Those articles cannot share a single keyword token with the
English coverage of the same story, so they fail tier 1 and never reach the
embedding check that would have clustered them.

The prompt is the first line of defence, but a model instruction is a tendency,
not a guarantee. This map is the deterministic backstop, and because matcher.py
applies it at match time it also repairs the ~46k articles already stored.

Entries were taken from the live data — keywords frequent in Italian sources and
absent from English ones — not guessed. Add to it the same way.
"""

import re
import unicodedata

# Italian → English. Lookup keys are folded (lowercase, accent-free); values carry the display
# casing, so a normalized keyword still reads like a keyword. Identity pairs are
# deliberately absent — "Vienna" is already English and mapping it to itself would
# only strip its capital.
EXONYMS = {
    # Countries and regions
    "stati uniti": "United States", "usa": "United States",
    "italia": "Italy", "brasile": "Brazil", "ucraina": "Ukraine",
    "israele": "Israel", "europa": "Europe", "spagna": "Spain",
    "libano": "Lebanon", "francia": "France", "germania": "Germany",
    "marocco": "Morocco", "cina": "China", "messico": "Mexico",
    "arabia saudita": "Saudi Arabia", "regno unito": "United Kingdom",
    "gran bretagna": "United Kingdom", "polonia": "Poland", "cile": "Chile",
    "medio oriente": "Middle East", "unione europea": "European Union",
    "ue": "European Union", "emirati arabi uniti": "United Arab Emirates",
    "eau": "United Arab Emirates", "cisgiordania": "West Bank",
    "cisjordania": "West Bank", "corea del nord": "North Korea",
    "corea del sud": "South Korea", "giappone": "Japan", "egitto": "Egypt",
    "turchia": "Turkey", "siria": "Syria", "grecia": "Greece",
    "svizzera": "Switzerland", "svezia": "Sweden", "norvegia": "Norway",
    "danimarca": "Denmark", "paesi bassi": "Netherlands",
    "olanda": "Netherlands", "belgio": "Belgium", "ungheria": "Hungary",
    "croazia": "Croatia", "libia": "Libya", "giordania": "Jordan",
    "etiopia": "Ethiopia", "sudafrica": "South Africa",
    "nuova zelanda": "New Zealand", "mar rosso": "Red Sea",
    "stretto di hormuz": "Strait of Hormuz",
    # Cities
    "teheran": "Tehran", "mosca": "Moscow", "parigi": "Paris",
    "pechino": "Beijing", "roma": "Rome", "londra": "London",
    "berlino": "Berlin", "gerusalemme": "Jerusalem", "avana": "Havana",
    "san paolo": "Sao Paulo", "il cairo": "Cairo", "damasco": "Damascus",
    "ginevra": "Geneva", "varsavia": "Warsaw", "bruxelles": "Brussels",
    "lisbona": "Lisbon", "atene": "Athens", "copenaghen": "Copenhagen",
    "stoccolma": "Stockholm", "l'aia": "The Hague", "aja": "The Hague",
    "laia": "The Hague", "venezia": "Venice", "firenze": "Florence",
    "milano": "Milan", "napoli": "Naples", "torino": "Turin",
    "genova": "Genoa", "monaco di baviera": "Munich", "colonia": "Cologne",
    "francoforte": "Frankfurt", "praga": "Prague", "nizza": "Nice",
    "marsiglia": "Marseille", "siviglia": "Seville", "barcellona": "Barcelona",
    "lione": "Lyon", "anversa": "Antwerp", "edimburgo": "Edinburgh",
    "dublino": "Dublin", "il cremlino": "Kremlin",
    # Institutions
    "casa bianca": "White House", "cremlino": "Kremlin",
    "studio ovale": "Oval Office", "nazioni unite": "United Nations",
    "onu": "United Nations", "farnesina": "Italian Foreign Ministry",
    "congresso": "Congress", "parlamento": "Parliament",
    "consiglio di sicurezza": "Security Council",
    "pasdaran": "Revolutionary Guards",
    # Recurring common nouns that end up as keywords — lowercase by nature
    "terremoto": "earthquake", "guerra": "war", "sanzioni": "sanctions",
    "narcotraffico": "drug trafficking", "mondiali": "World Cup",
    "cessate il fuoco": "ceasefire", "tregua": "truce",
    "elezioni": "elections", "sciopero": "strike", "incendio": "fire",
    "alluvione": "flood", "attentato": "attack", "ostaggi": "hostages",
    "femminicidio": "femicide", "profughi": "refugees", "migranti": "migrants",
    "dazi": "tariffs", "accordo": "agreement", "vertice": "summit",
    # Name spellings that differ from the English convention
    "benyamin netanyahu": "Benjamin Netanyahu",
    "vladimir zelensky": "Volodymyr Zelensky",
}

# A short, representative sample for the prompt. The full map is too long to send
# on every one of the ~800 extraction calls a night, and the model only needs the
# pattern — that Latin-script foreign names still need translating, not just
# non-Latin ones.
PROMPT_EXAMPLES = [
    ("Stati Uniti", "United States"), ("Ucraina", "Ukraine"),
    ("Mosca", "Moscow"), ("Londra", "London"), ("Teheran", "Tehran"),
    ("Germania", "Germany"), ("Casa Bianca", "White House"),
]


def _fold(text):
    """Lowercase, strip accents and collapse whitespace for lookup."""
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def normalize_keyword(keyword):
    """Return the English form of one keyword, or it unchanged if not an exonym.

    Tries the whole string first so multi-word entries win ("stati uniti" →
    "united states" rather than two useless single-word lookups), then falls back
    to translating individual words.
    """
    folded = _fold(keyword)
    if not folded:
        return keyword
    if folded in EXONYMS:
        return EXONYMS[folded]
    words = folded.split()
    if len(words) > 1:
        swapped = [EXONYMS.get(w, w) for w in words]
        if swapped != words:
            return " ".join(swapped)
    return keyword


def normalize_keywords(keywords):
    """Normalize a list of keywords, dropping duplicates that collapse together."""
    out, seen = [], set()
    for k in keywords or []:
        if not isinstance(k, str) or not k.strip():
            continue
        norm = normalize_keyword(k)
        key = _fold(norm)
        if key and key not in seen:
            seen.add(key)
            out.append(norm)
    return out


def prompt_examples_block():
    """The example pairs, rendered for the extraction prompt."""
    return ", ".join(f'"{src}" -> "{dst}"' for src, dst in PROMPT_EXAMPLES)
