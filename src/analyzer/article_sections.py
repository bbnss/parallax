"""Parse the section structure out of a generated comparison article.

`prompts.compare_perspectives` asks the model to invent *evocative* section
headers ("The Architecture of Divergence"), so matching them by literal name is
unreliable: it happened to work on some articles and silently returned nothing on
others. When it returned nothing the teaser prompt went to the model essentially
empty, and the model filled the gap by inventing — one published teaser credited a
"Maduro government" and "Middle Eastern sources" that appear nowhere in the piece.

What the prompt *does* guarantee is:
  1. the order of the sections — facts, divergence, factions, omissions, framing
  2. that each faction is labelled with its own name — though models render that
     as a bold label (**The Western approach**), an h3 (### The Russian Reading)
     or its own h2, depending on the run

So parse on those, and treat header names as a hint rather than a requirement.
"""

import re

# Section keys in the order compare_perspectives emits them.
SECTION_ORDER = ["facts", "divergence", "factions", "omissions", "geopolitical"]

# Header words worth trusting when they happen to be there. Checked before
# falling back to position.
_SECTION_HINTS = {
    "facts":        ("undisputed", "the facts", "factual", "shared", "core", "foundation"),
    "divergence":   ("diverge", "divergence", "differ", "disagree"),
    "factions":     ("views", "perspectives", "lens", "approach", "reading", "narratives"),
    "omissions":    ("omission", "omit", "leaves out", "left out", "unsaid", "silent"),
    "geopolitical": ("geopolitic", "framing", "prism", "context", "stakes"),
}

# Ordered so that "Middle Eastern" is claimed before plain "Eastern" can take it.
_FACTION_PATTERNS = [
    ("middle_east", re.compile(r"middle[\s\-]*east", re.I)),
    ("russia",      re.compile(r"\brussian?\b", re.I)),
    ("western",     re.compile(r"\bwest(ern)?\b", re.I)),
    ("eastern",     re.compile(r"\beastern\b", re.I)),
]

# Strips "**The Eastern lens**, " down to the prose, punctuation included — the
# label is often followed by a comma that would otherwise open the extract.
_BOLD_LABEL = re.compile(r"^\*\*[^*]+\*\*[\s,;:\-—]*")


_HEADING = re.compile(r"^(#{2,6})\s+(.*)$")


def split_sections(text, max_level=2):
    """Return [(heading, body)] in document order.

    max_level=2 keeps only h2 (the top-level structure); a higher value also
    returns the nested headings some runs use for the faction paragraphs.
    """
    sections, heading, body = [], None, []
    for line in (text or "").split("\n"):
        m = _HEADING.match(line)
        if m and len(m.group(1)) <= max_level:
            if heading is not None:
                sections.append((heading, "\n".join(body).strip()))
            heading, body = m.group(2).strip(), []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body).strip()))
    return sections


def _assign_sections(sections):
    """Map each known section key to a body, by header hint then by position."""
    out, claimed = {}, set()

    for key in SECTION_ORDER:
        for i, (heading, body) in enumerate(sections):
            if i in claimed:
                continue
            if any(h in heading.lower() for h in _SECTION_HINTS[key]):
                out[key], _ = body, claimed.add(i)
                break

    # Whatever the hints missed falls back to the position the prompt fixes.
    for pos, key in enumerate(SECTION_ORDER):
        if key not in out and pos < len(sections) and pos not in claimed:
            out[key], _ = sections[pos][1], claimed.add(pos)

    return out


def _first_paragraph(text):
    for block in (text or "").split("\n\n"):
        s = block.strip()
        # Skip the title, the italic subtitle and the '---' rule.
        if s and not s.startswith("#") and not s.startswith("*") and set(s) != {"-"}:
            return s
    return (text or "").strip()


def _extract_factions(text, factions_block):
    """Map faction -> its paragraph, from bold labels or dedicated headers."""
    candidates = []
    for para in (factions_block or "").split("\n\n"):
        p = para.strip()
        if p:
            candidates.append((p.split("\n")[0], p))
    # Some runs never open a faction section at all and just drop the bold-labelled
    # paragraphs into the divergence section. Those labels are the strongest signal
    # available, so scan the whole document for them before falling back to headings.
    for para in (text or "").split("\n\n"):
        p = para.strip()
        if p.startswith("**"):
            candidates.append((p.split("\n")[0], p))
    # Runs differ: some give each faction its own h2, others nest them as h3
    # under the divergence section. Take headings at any level.
    for heading, body in split_sections(text, max_level=6):
        if body:
            candidates.append((heading, body))

    out, claimed = {}, set()
    for name, pattern in _FACTION_PATTERNS:
        for i, (label, body) in enumerate(candidates):
            if i in claimed or not pattern.search(label):
                continue
            out[name] = _BOLD_LABEL.sub("", body).strip()
            claimed.add(i)
            break
    return out


def parse(text):
    """Return the article's sections keyed by role.

    Keys: facts, divergence, omissions, geopolitical, and one per faction present
    (western, eastern, middle_east, russia). Missing sections are absent, never
    guessed — a caller that gets nothing should say so rather than prompt a model
    with a blank template.
    """
    sections = split_sections(text)
    parsed = _assign_sections(sections)
    result = {k: v for k, v in parsed.items() if k != "factions" and v}
    if not result.get("facts"):
        result["facts"] = _first_paragraph(text)
    result.update(_extract_factions(text, parsed.get("factions", "")))
    return result
