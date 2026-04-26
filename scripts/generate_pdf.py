#!/usr/bin/env python3
"""Generate a presentation PDF explaining how Parallax works."""

import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "Parallax_Come_Funziona.pdf"

# Colors
BG = HexColor("#080c14")
BG_CARD = HexColor("#0e1420")
BLUE = HexColor("#60a5fa")
GREEN = HexColor("#10b981")
YELLOW = HexColor("#f59e0b")
RED = HexColor("#ef4444")
PURPLE = HexColor("#8b5cf6")
CYAN = HexColor("#06b6d4")
WHITE = HexColor("#e4e8f0")
GRAY = HexColor("#6b7a94")
DIM = HexColor("#3e4a5e")
DARK = HexColor("#0a0f1a")

W, H = A4  # 595 x 842 pts


def draw_bg(c):
    c.setFillColor(BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)


def draw_rounded_rect(c, x, y, w, h, r=8, fill=None, stroke=None, stroke_w=0.5):
    """Draw a rounded rectangle."""
    p = c.beginPath()
    p.roundRect(x, y, w, h, r)
    if fill:
        c.setFillColor(fill)
    if stroke:
        c.setStrokeColor(stroke)
        c.setLineWidth(stroke_w)
    c.drawPath(p, fill=1 if fill else 0, stroke=1 if stroke else 0)


def draw_arrow(c, x1, y1, x2, y2, color=BLUE, width=1.5):
    """Draw an arrow from (x1,y1) to (x2,y2)."""
    c.setStrokeColor(color)
    c.setLineWidth(width)
    c.line(x1, y1, x2, y2)
    # Arrowhead
    angle = math.atan2(y2 - y1, x2 - x1)
    hl = 8
    c.setFillColor(color)
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - hl * math.cos(angle - 0.4), y2 - hl * math.sin(angle - 0.4))
    p.lineTo(x2 - hl * math.cos(angle + 0.4), y2 - hl * math.sin(angle + 0.4))
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def draw_pipeline_box(c, x, y, w, h, label, sublabel, color, number=None):
    """Draw a pipeline step box."""
    draw_rounded_rect(c, x, y, w, h, r=6, fill=DARK, stroke=color, stroke_w=1.2)
    if number:
        # Circle with number
        cx = x + 18
        cy = y + h / 2
        c.setFillColor(color)
        c.circle(cx, cy, 10, fill=1, stroke=0)
        c.setFillColor(BG)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(cx, cy - 4, str(number))
    # Label
    lx = x + (36 if number else 12)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(lx, y + h / 2 + 4, label)
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 8)
    c.drawString(lx, y + h / 2 - 10, sublabel)


# ── PAGE 1: Cover ──────────────────────────────────────────────

def page_cover(c):
    draw_bg(c)

    # Diamond accent
    c.setFillColor(BLUE)
    c.setFont("Helvetica", 60)
    c.drawCentredString(W / 2, H - 240, "\u25C7")

    # Title
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 42)
    c.drawCentredString(W / 2, H - 300, "PARALLAX")

    # Tagline
    c.setFillColor(BLUE)
    c.setFont("Helvetica-Oblique", 16)
    c.drawCentredString(W / 2, H - 330, "Same event. Different vantage points.")

    # Subtitle
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 13)
    c.drawCentredString(W / 2, H - 380, "Come funziona il sistema che confronta")
    c.drawCentredString(W / 2, H - 398, "le notizie geopolitiche da tutto il mondo")

    # Decorative line
    c.setStrokeColor(HexColor("#1a2235"))
    c.setLineWidth(1)
    c.line(W / 2 - 100, H - 420, W / 2 + 100, H - 420)

    # Stats boxes
    stats = [
        ("21", "fonti attive"),
        ("4", "blocchi geopolitici"),
        ("5", "lingue"),
        ("24/7", "automatico"),
    ]
    box_w = 100
    gap = 15
    total_w = len(stats) * box_w + (len(stats) - 1) * gap
    sx = (W - total_w) / 2
    sy = H - 510

    for i, (val, label) in enumerate(stats):
        bx = sx + i * (box_w + gap)
        draw_rounded_rect(c, bx, sy, box_w, 55, r=6, fill=DARK, stroke=HexColor("#1a2235"))
        c.setFillColor(BLUE)
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(bx + box_w / 2, sy + 28, val)
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 9)
        c.drawCentredString(bx + box_w / 2, sy + 10, label)

    # URL
    c.setFillColor(DIM)
    c.setFont("Helvetica", 10)
    c.drawCentredString(W / 2, 60, "bbnss.github.io/parallax")

    c.showPage()


# ── PAGE 2: Il Problema ──────────────────────────────────────────

def page_problema(c):
    draw_bg(c)

    # Title
    c.setFillColor(BLUE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, H - 50, "01")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(50, H - 80, "Il Problema")

    # Intro text
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 12)
    text_lines = [
        "Ogni giorno accadono eventi importanti nel mondo. Ma la stessa notizia",
        "viene raccontata in modo molto diverso a seconda di chi la racconta.",
        "",
        "Un conflitto militare viene descritto come \"operazione di pace\" da un",
        "giornale e come \"aggressione\" da un altro. Entrambi parlano dello stesso",
        "fatto, ma il lettore che legge una sola fonte vede solo UNA versione.",
    ]
    y = H - 120
    for line in text_lines:
        c.drawString(50, y, line)
        y -= 18

    # Example: 3 newspaper boxes showing different framing
    examples = [
        ("BBC (UK)", "US envoys travel to Pakistan\nfor diplomatic talks", BLUE, "Tono neutro, procedurale"),
        ("Al Jazeera (QA)", "US pressure campaign continues\nas Iran seeks regional peace", PURPLE, "Focus sulla pressione USA"),
        ("TASS (RU)", "Western bloc escalates tension\nin Middle East standoff", RED, "Enfasi sull'aggressione occidentale"),
    ]

    box_w = 155
    gap = 15
    total = len(examples) * box_w + (len(examples) - 1) * gap
    sx = (W - total) / 2
    sy = H - 380

    for i, (source, text, color, note) in enumerate(examples):
        bx = sx + i * (box_w + gap)
        draw_rounded_rect(c, bx, sy, box_w, 120, r=6, fill=DARK, stroke=color, stroke_w=1.5)
        # Source name
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(bx + 10, sy + 100, source)
        # Headline
        c.setFillColor(WHITE)
        c.setFont("Helvetica", 9)
        lines = text.split("\n")
        ty = sy + 80
        for line in lines:
            c.drawString(bx + 10, ty, line)
            ty -= 14
        # Note
        c.setFillColor(GRAY)
        c.setFont("Helvetica-Oblique", 7.5)
        c.drawString(bx + 10, sy + 10, note)

    # Arrow pointing down
    c.setFillColor(YELLOW)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(W / 2, sy - 30, "Stesso evento, 3 narrazioni diverse")

    # Solution box
    draw_rounded_rect(c, 50, 80, W - 100, 100, r=8, fill=DARK, stroke=GREEN, stroke_w=1.5)
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(70, 150, "La Soluzione: Parallax")
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 11)
    c.drawString(70, 128, "Un sistema automatico che ogni giorno raccoglie le stesse notizie")
    c.drawString(70, 110, "da 21 fonti di 4 blocchi geopolitici diversi e le mette a confronto,")
    c.drawString(70, 92, "mostrando dove concordano e dove divergono.")

    c.showPage()


# ── PAGE 3: Le Fonti ──────────────────────────────────────────

def page_fonti(c):
    draw_bg(c)

    c.setFillColor(BLUE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, H - 50, "02")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(50, H - 80, "Le Fonti: 21 Testate, 4 Blocchi")

    c.setFillColor(GRAY)
    c.setFont("Helvetica", 11)
    c.drawString(50, H - 105, "Ogni blocco rappresenta una \"prospettiva geopolitica\" diversa.")

    regions = [
        ("WESTERN", BLUE, "Prospettiva occidentale", [
            ("BBC World", "UK"), ("France 24", "FR"), ("DW News", "DE"),
            ("NPR World", "US"), ("ANSA Mondo", "IT"), ("Il Post", "IT"),
            ("El Pais", "ES"), ("Euronews", "EU"),
        ]),
        ("EASTERN", YELLOW, "Prospettiva orientale", [
            ("CGTN", "CN"), ("Xinhua", "CN"), ("NDTV World", "IN"),
            ("Times of India", "IN"), ("Channel News Asia", "SG"), ("Bangkok Post", "TH"),
        ]),
        ("MIDDLE EAST", PURPLE, "Prospettiva mediorientale", [
            ("Al Jazeera", "QA"), ("Anadolu Agency", "TR"),
            ("Dawn", "PK"), ("Middle East Eye", "UK"),
        ]),
        ("RUSSIA", RED, "Prospettiva russa", [
            ("TASS", "RU"), ("RT", "RU"), ("The Moscow Times", "RU"),
        ]),
    ]

    col_w = 240
    row_h = 155
    margin_x = 55
    start_y = H - 140

    for idx, (name, color, desc, sources) in enumerate(regions):
        col = idx % 2
        row = idx // 2
        bx = margin_x + col * (col_w + 15)
        by = start_y - row * (row_h + 15)

        draw_rounded_rect(c, bx, by - row_h, col_w, row_h, r=6, fill=DARK, stroke=color, stroke_w=1.2)

        # Region title
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(bx + 12, by - 20, name)

        c.setFillColor(GRAY)
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(bx + 12, by - 34, desc)

        # Source list
        c.setFillColor(WHITE)
        c.setFont("Helvetica", 8.5)
        sy = by - 52
        for j, (src_name, country) in enumerate(sources):
            col_offset = 0 if j < 4 else 120
            row_offset = j % 4
            c.setFillColor(DIM)
            c.drawString(bx + 14 + col_offset, sy - row_offset * 14, f"[{country}]")
            c.setFillColor(WHITE)
            c.drawString(bx + 36 + col_offset, sy - row_offset * 14, src_name)

    # Note at bottom
    y_bottom = start_y - 2 * (row_h + 15) - 30
    c.setFillColor(GRAY)
    c.setFont("Helvetica-Oblique", 10)
    c.drawCentredString(W / 2, y_bottom, "Tutte le fonti pubblicano in inglese -- il sistema traduce poi in 5 lingue")

    # Pie/circle infographic
    cy_center = y_bottom - 80
    cx_center = W / 2
    total = 21
    segments = [
        (8, BLUE, "Western (8)"),
        (6, YELLOW, "Eastern (6)"),
        (4, PURPLE, "Middle East (4)"),
        (3, RED, "Russia (3)"),
    ]
    start_angle = 90
    r = 50
    for count, color, label in segments:
        extent = (count / total) * 360
        c.setFillColor(color)
        c.setStrokeColor(BG)
        c.setLineWidth(2)
        c.wedge(cx_center - r, cy_center - r, cx_center + r, cy_center + r,
                start_angle, extent, fill=1, stroke=1)
        start_angle += extent

    # Legend
    lx = cx_center + 80
    ly = cy_center + 30
    for count, color, label in segments:
        c.setFillColor(color)
        c.rect(lx, ly, 10, 10, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica", 9)
        c.drawString(lx + 16, ly + 1, label)
        ly -= 18

    c.showPage()


# ── PAGE 4: La Pipeline (overview) ──────────────────────────────

def page_pipeline(c):
    draw_bg(c)

    c.setFillColor(BLUE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, H - 50, "03")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(50, H - 80, "La Pipeline: Come Funziona")

    c.setFillColor(GRAY)
    c.setFont("Helvetica", 11)
    c.drawString(50, H - 105, "Ogni notte alle 4:30, il Mac Mini esegue automaticamente 5 passaggi.")

    steps = [
        ("Raccolta", "Scarica articoli da 21 fonti RSS", GREEN,
         "Il computer visita ogni giornale e\nscarica i nuovi articoli del giorno."),
        ("Riassunto AI", "Gemma 4 riassume ogni articolo", CYAN,
         "Un modello di intelligenza artificiale\nlegge ogni articolo e ne fa un riassunto."),
        ("Abbinamento", "Trova la stessa notizia in fonti diverse", YELLOW,
         "Confronta i riassunti per trovare quali\narticoli parlano dello stesso evento."),
        ("Confronto AI", "Gemma 4 analizza le differenze", PURPLE,
         "L'AI analizza come la stessa storia\nviene raccontata dai diversi blocchi."),
        ("Traduzione", "5 lingue: EN, IT, ES, DE, FR", RED,
         "Ogni analisi viene tradotta in 5\nlingue da un modello di traduzione AI."),
    ]

    box_w = W - 120
    box_h = 58
    gap = 16
    sx = 60
    sy = H - 150

    for i, (title, subtitle, color, detail) in enumerate(steps):
        by = sy - i * (box_h + gap)
        draw_pipeline_box(c, sx, by, box_w / 2 - 10, box_h, title, subtitle, color, number=i + 1)

        # Detail text on the right
        dx = sx + box_w / 2 + 10
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 9)
        for j, line in enumerate(detail.split("\n")):
            c.drawString(dx, by + box_h / 2 + 4 - j * 13, line)

        # Arrow down
        if i < len(steps) - 1:
            arrow_x = sx + 18
            draw_arrow(c, arrow_x, by, arrow_x, by - gap + 2, color=DIM, width=1)

    # Final output box
    final_y = sy - len(steps) * (box_h + gap)
    draw_rounded_rect(c, sx, final_y, box_w, 50, r=6, fill=DARK, stroke=GREEN, stroke_w=1.5)
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(W / 2, final_y + 28, "Risultato: pagina web aggiornata")
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 9)
    c.drawCentredString(W / 2, final_y + 10, "bbnss.github.io/parallax -- pubblicata automaticamente su GitHub Pages")

    c.showPage()


# ── PAGE 5: Step 1 - Raccolta dettaglio ──────────────────────────

def page_step1(c):
    draw_bg(c)

    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, H - 50, "STEP 1")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(50, H - 80, "Raccolta Articoli")

    c.setFillColor(GRAY)
    c.setFont("Helvetica", 11)
    lines = [
        "Ogni testata giornalistica pubblica un \"feed RSS\" -- un elenco aggiornato",
        "dei propri articoli in formato leggibile dai computer.",
        "",
        "Parallax visita questi 21 feed, scarica i titoli e i link degli articoli",
        "nuovi, poi va su ogni link per leggere il testo completo dell'articolo.",
    ]
    y = H - 115
    for line in lines:
        c.drawString(50, y, line)
        y -= 16

    # Diagram: 3 newspaper icons -> RSS feed -> Database
    diagram_y = H - 320

    # Newspaper boxes (left)
    papers = [
        ("BBC", BLUE), ("Al Jazeera", PURPLE), ("TASS", RED),
        ("NDTV", YELLOW), ("France 24", BLUE), ("...", DIM),
    ]
    for i, (name, color) in enumerate(papers):
        col = i % 2
        row = i // 2
        bx = 50 + col * 85
        by = diagram_y + 100 - row * 38
        draw_rounded_rect(c, bx, by, 78, 30, r=4, fill=DARK, stroke=color, stroke_w=0.8)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if name != "..." else "Helvetica", 8)
        c.drawCentredString(bx + 39, by + 10, name)

    # Arrow
    draw_arrow(c, 225, diagram_y + 65, 280, diagram_y + 65, color=GREEN, width=2)
    c.setFillColor(GREEN)
    c.setFont("Helvetica", 8)
    c.drawCentredString(252, diagram_y + 75, "RSS")

    # Middle: Feed processor
    draw_rounded_rect(c, 285, diagram_y + 35, 100, 60, r=6, fill=DARK, stroke=GREEN, stroke_w=1.5)
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(335, diagram_y + 72, "Feed Parser")
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(335, diagram_y + 55, "feedparser + scraper")
    c.drawCentredString(335, diagram_y + 43, "~50 articoli/giorno")

    # Arrow
    draw_arrow(c, 390, diagram_y + 65, 440, diagram_y + 65, color=GREEN, width=2)

    # Database
    draw_rounded_rect(c, 445, diagram_y + 35, 100, 60, r=6, fill=DARK, stroke=CYAN, stroke_w=1.5)
    c.setFillColor(CYAN)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(495, diagram_y + 72, "Database")
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(495, diagram_y + 55, "SQLite locale")
    c.drawCentredString(495, diagram_y + 43, "~1200+ articoli totali")

    # What gets saved
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, diagram_y - 30, "Cosa viene salvato per ogni articolo:")

    fields = [
        ("Titolo", "Il titolo originale dell'articolo"),
        ("Testo completo", "Il contenuto intero della pagina web"),
        ("Fonte", "Da quale giornale proviene (es. BBC, Al Jazeera)"),
        ("Regione", "A quale blocco geopolitico appartiene"),
        ("Data", "Quando e stato pubblicato"),
    ]

    fy = diagram_y - 55
    for field, desc in fields:
        c.setFillColor(GREEN)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(70, fy, f"  {field}")
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 10)
        c.drawString(200, fy, desc)
        fy -= 20

    c.showPage()


# ── PAGE 6: Step 2 - AI Analysis ──────────────────────────────

def page_step2(c):
    draw_bg(c)

    c.setFillColor(CYAN)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, H - 50, "STEP 2")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(50, H - 80, "Analisi con Intelligenza Artificiale")

    c.setFillColor(GRAY)
    c.setFont("Helvetica", 11)
    lines = [
        "Questo e il cuore di Parallax. Un modello AI chiamato Gemma 4 (di Google),",
        "che gira interamente sul Mac Mini senza inviare dati a nessun server",
        "esterno, esegue tre operazioni in sequenza:",
    ]
    y = H - 115
    for line in lines:
        c.drawString(50, y, line)
        y -= 16

    # 3 sub-steps as big cards
    substeps = [
        ("2a", "Riassunto", CYAN, [
            "L'AI legge ogni articolo e genera:",
            "  - Un riassunto di 3-4 frasi",
            "  - Una lista di parole chiave (es. \"Iran\", \"NATO\", \"sanctions\")",
            "",
            "Esempio: un articolo di 2000 parole su BBC diventa",
            "un riassunto di 50 parole + 5 keyword.",
            "",
            "Tempo: ~1 min per articolo, ~50 articoli al giorno = ~1 ora",
        ]),
        ("2b", "Abbinamento Storie", YELLOW, [
            "Il sistema cerca quali articoli parlano della STESSA notizia.",
            "",
            "Come fa? Due passaggi:",
            "  1. Confronta le keyword (almeno 2 in comune)",
            "  2. Usa un modello matematico (embeddings) per misurare",
            "     quanto due riassunti sono \"simili\" (soglia: 75%)",
            "",
            "Risultato: gruppi (\"cluster\") di articoli sullo stesso evento",
        ]),
        ("2c", "Confronto Prospettive", PURPLE, [
            "Per ogni cluster, l'AI riceve TUTTI gli articoli raggruppati",
            "per blocco (Western, Eastern, Middle East, Russia) e scrive:",
            "",
            "  - I fatti su cui TUTTI concordano",
            "  - Dove le narrazioni DIVERGONO",
            "  - Cosa ciascun blocco OMETTE",
            "",
            "E il confronto finale che appare nella pagina web.",
        ]),
    ]

    card_h = 155
    card_gap = 12
    cy = H - 185

    for step_id, title, color, desc_lines in substeps:
        draw_rounded_rect(c, 50, cy - card_h, W - 100, card_h, r=6, fill=DARK, stroke=color, stroke_w=1.2)

        # Step number circle
        c.setFillColor(color)
        c.circle(78, cy - 22, 14, fill=1, stroke=0)
        c.setFillColor(BG)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(78, cy - 26, step_id)

        # Title
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(100, cy - 25, title)

        # Description
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 9)
        dy = cy - 48
        for line in desc_lines:
            c.drawString(68, dy, line)
            dy -= 13

        cy -= card_h + card_gap

    c.showPage()


# ── PAGE 7: Step 3 - Translation + Output ──────────────────────

def page_step3(c):
    draw_bg(c)

    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, H - 50, "STEP 3")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(50, H - 80, "Traduzione e Pubblicazione")

    c.setFillColor(GRAY)
    c.setFont("Helvetica", 11)
    lines = [
        "L'analisi originale e in inglese. Il sistema la traduce in 4 lingue",
        "aggiuntive usando un altro modello AI specializzato in traduzione.",
    ]
    y = H - 115
    for line in lines:
        c.drawString(50, y, line)
        y -= 16

    # Language circles
    langs = [
        ("EN", "Inglese", BLUE, "Originale"),
        ("IT", "Italiano", GREEN, "Tradotto"),
        ("ES", "Spagnolo", YELLOW, "Tradotto"),
        ("DE", "Tedesco", RED, "Tradotto"),
        ("FR", "Francese", PURPLE, "Tradotto"),
    ]

    cx_start = 70
    cx_gap = 100
    cy_lang = H - 210

    for i, (code, name, color, note) in enumerate(langs):
        cx = cx_start + i * cx_gap
        c.setFillColor(color)
        c.circle(cx, cy_lang, 22, fill=1, stroke=0)
        c.setFillColor(BG if color != YELLOW else BG)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(cx, cy_lang - 5, code)
        c.setFillColor(WHITE)
        c.setFont("Helvetica", 9)
        c.drawCentredString(cx, cy_lang - 35, name)
        c.setFillColor(DIM)
        c.setFont("Helvetica-Oblique", 7)
        c.drawCentredString(cx, cy_lang - 48, note)

    # Arrows from EN to others
    for i in range(1, 5):
        cx_to = cx_start + i * cx_gap
        draw_arrow(c, cx_start + 24, cy_lang, cx_to - 24, cy_lang, color=DIM, width=0.8)

    # Publication flow
    pub_y = H - 340

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, pub_y, "Pubblicazione Automatica")

    c.setFillColor(GRAY)
    c.setFont("Helvetica", 11)
    pub_lines = [
        "Una volta tradotto tutto, il sistema genera una pagina HTML statica",
        "e la pubblica automaticamente su GitHub Pages (hosting gratuito).",
    ]
    py = pub_y - 25
    for line in pub_lines:
        c.drawString(50, py, line)
        py -= 16

    # Flow diagram
    flow_y = pub_y - 100
    boxes = [
        ("15 confronti\n+ traduzioni", PURPLE),
        ("Genera\nHTML", CYAN),
        ("Push su\nGitHub", GREEN),
        ("Online!\ngithub.io", BLUE),
    ]

    bw = 105
    bg = 22
    total_flow = len(boxes) * bw + (len(boxes) - 1) * bg
    fx = (W - total_flow) / 2

    for i, (label, color) in enumerate(boxes):
        bx = fx + i * (bw + bg)
        draw_rounded_rect(c, bx, flow_y, bw, 50, r=6, fill=DARK, stroke=color, stroke_w=1.2)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 9)
        lines = label.split("\n")
        for j, line in enumerate(lines):
            c.drawCentredString(bx + bw / 2, flow_y + 30 - j * 14, line)

        if i < len(boxes) - 1:
            draw_arrow(c, bx + bw + 2, flow_y + 25, bx + bw + bg - 2, flow_y + 25, color=DIM)

    # Timeline
    time_y = flow_y - 80
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, time_y, "Timeline giornaliera tipica")

    timeline = [
        ("04:30", "Inizio pipeline", GREEN),
        ("04:33", "Raccolta completata (~50 articoli)", GREEN),
        ("05:30", "Riassunti AI completati", CYAN),
        ("05:31", "Abbinamento storie (< 1 min)", YELLOW),
        ("05:45", "Confronti prospettive completati", PURPLE),
        ("06:00", "Traduzioni completate", RED),
        ("06:01", "Pagina web online e aggiornata", BLUE),
    ]

    ty = time_y - 25
    # Timeline line
    c.setStrokeColor(DIM)
    c.setLineWidth(1)
    c.line(90, ty + 5, 90, ty - len(timeline) * 20 + 15)

    for time_str, desc, color in timeline:
        c.setFillColor(color)
        c.circle(90, ty, 4, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(78, ty - 4, time_str)
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 9)
        c.drawString(102, ty - 4, desc)
        ty -= 20

    c.showPage()


# ── PAGE 8: Architettura Tecnica ──────────────────────────────

def page_tech(c):
    draw_bg(c)

    c.setFillColor(BLUE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, H - 50, "04")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(50, H - 80, "Sotto il Cofano")

    c.setFillColor(GRAY)
    c.setFont("Helvetica", 11)
    c.drawString(50, H - 105, "Un riepilogo tecnico per i curiosi (ma non serve capirlo per usare il sito!).")

    # Tech stack boxes
    techs = [
        ("Hardware", CYAN, [
            "Mac Mini M2 con 16 GB RAM",
            "L'AI gira tutta in locale",
            "Nessun dato inviato a server esterni",
            "Costo operativo: 0 euro",
        ]),
        ("Software AI", PURPLE, [
            "Gemma 4 (Google) per riassunti e confronti",
            "Translate Gemma per le traduzioni",
            "Ollama come runtime per i modelli",
            "Sentence-Transformers per gli embeddings",
        ]),
        ("Codice", GREEN, [
            "Python 3.9 (~2000 righe di codice)",
            "SQLite per il database locale",
            "HTML/CSS/JS per il sito web",
            "Tutto il codice e open source su GitHub",
        ]),
        ("Infrastruttura", BLUE, [
            "GitHub Pages per l'hosting (gratuito)",
            "launchd (macOS) per lo scheduling",
            "Pipeline automatica ogni notte",
            "Zero dipendenze da servizi a pagamento",
        ]),
    ]

    card_w = (W - 120) / 2
    card_h = 130
    card_gap_x = 20
    card_gap_y = 15
    sx = 50

    for idx, (title, color, items) in enumerate(techs):
        col = idx % 2
        row = idx // 2
        bx = sx + col * (card_w + card_gap_x)
        by = H - 145 - row * (card_h + card_gap_y)

        draw_rounded_rect(c, bx, by - card_h, card_w, card_h, r=6, fill=DARK, stroke=color, stroke_w=1)

        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(bx + 12, by - 20, title)

        c.setFillColor(GRAY)
        c.setFont("Helvetica", 9)
        iy = by - 40
        for item in items:
            c.setFillColor(DIM)
            c.drawString(bx + 14, iy, ">")
            c.setFillColor(GRAY)
            c.drawString(bx + 26, iy, item)
            iy -= 15

    # Key insight box at bottom
    insight_y = H - 145 - 2 * (card_h + card_gap_y) - 30

    draw_rounded_rect(c, 50, insight_y - 120, W - 100, 120, r=8, fill=DARK, stroke=YELLOW, stroke_w=1.5)

    c.setFillColor(YELLOW)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(70, insight_y - 20, "Il Punto Chiave")

    c.setFillColor(WHITE)
    c.setFont("Helvetica", 11)
    key_lines = [
        "Parallax non genera opinioni proprie. Non dice chi ha ragione.",
        "",
        "Mostra solo come la stessa notizia viene raccontata da fonti diverse,",
        "evidenziando fatti condivisi, narrazioni divergenti e omissioni.",
        "",
        "Uscire dalla propria bolla informativa e il primo passo per",
        "capire davvero cosa succede nel mondo.",
    ]
    ky = insight_y - 40
    for line in key_lines:
        c.drawString(70, ky, line)
        ky -= 16

    c.showPage()


# ── PAGE 9: Esempio Concreto ──────────────────────────────────

def page_esempio(c):
    draw_bg(c)

    c.setFillColor(BLUE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, H - 50, "05")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(50, H - 80, "Un Esempio Concreto")

    c.setFillColor(GRAY)
    c.setFont("Helvetica", 11)
    c.drawString(50, H - 108, "Vediamo cosa succede quando scoppia una notizia importante.")

    # Event
    draw_rounded_rect(c, 50, H - 195, W - 100, 65, r=6, fill=DARK, stroke=BLUE, stroke_w=1.5)
    c.setFillColor(BLUE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(70, H - 148, "EVENTO")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(70, H - 168, "Colloqui USA-Iran in Pakistan per negoziati di pace")
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 9)
    c.drawString(70, H - 185, "20 articoli da 12 fonti diverse, 3 blocchi geopolitici")

    # Three perspectives
    perspectives = [
        ("Prospettiva Occidentale", BLUE, [
            "BBC, NPR, France 24:",
            "\"Inviati USA volano in Pakistan",
            "per colloqui diplomatici.\"",
            "",
            "Tono: procedurale, neutro.",
            "Focus: passi diplomatici USA.",
            "Omette: pressioni sul territorio.",
        ]),
        ("Prospettiva Orientale", YELLOW, [
            "NDTV, Times of India:",
            "\"Momento di svolta potenziale",
            "per la pace regionale.\"",
            "",
            "Tono: ottimista, anticipatorio.",
            "Focus: impatto regionale, nucleare.",
            "Omette: dettagli procedurali.",
        ]),
        ("Prospettiva Mediorientale", PURPLE, [
            "Al Jazeera, Middle East Eye:",
            "\"Mediazione complessa con",
            "molti livelli di negoziazione.\"",
            "",
            "Tono: dettagliato, cauto.",
            "Focus: contesto geopolitico.",
            "Omette: esito definitivo.",
        ]),
    ]

    persp_w = (W - 120) / 3
    persp_h = 175
    persp_y = H - 225

    for i, (title, color, lines) in enumerate(perspectives):
        bx = 50 + i * (persp_w + 10)

        # Arrow from event down
        draw_arrow(c, bx + persp_w / 2, persp_y + 12, bx + persp_w / 2, persp_y, color=DIM, width=0.8)

        draw_rounded_rect(c, bx, persp_y - persp_h, persp_w, persp_h, r=6, fill=DARK, stroke=color, stroke_w=1.2)

        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(bx + 10, persp_y - 16, title)

        c.setFillColor(GRAY)
        c.setFont("Helvetica", 8)
        ly = persp_y - 35
        for line in lines:
            if line.startswith("Tono:") or line.startswith("Focus:") or line.startswith("Omette:"):
                c.setFillColor(WHITE)
                c.setFont("Helvetica-Bold", 7.5)
                c.drawString(bx + 10, ly, line.split(":")[0] + ":")
                c.setFillColor(GRAY)
                c.setFont("Helvetica", 7.5)
                c.drawString(bx + 10 + c.stringWidth(line.split(":")[0] + ": ", "Helvetica-Bold", 7.5), ly,
                             line.split(":", 1)[1].strip())
            else:
                c.setFillColor(GRAY)
                c.setFont("Helvetica", 8)
                c.drawString(bx + 10, ly, line)
            ly -= 13

    # Result arrow
    result_y = persp_y - persp_h - 15
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(W / 2, result_y, "Parallax mostra TUTTE e 3 le versioni fianco a fianco")

    # Final output box
    draw_rounded_rect(c, 50, result_y - 130, W - 100, 110, r=6, fill=DARK, stroke=GREEN, stroke_w=1.5)

    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(70, result_y - 30, "Fatti condivisi (su cui tutti concordano):")
    c.setFillColor(WHITE)
    c.setFont("Helvetica", 9)
    c.drawString(70, result_y - 47, "Inviati USA (Witkoff, Kushner) in viaggio per il Pakistan. FM iraniano Araghchi arrivato.")

    c.setFillColor(YELLOW)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(70, result_y - 70, "Dove divergono:")
    c.setFillColor(WHITE)
    c.setFont("Helvetica", 9)
    c.drawString(70, result_y - 87, "L'Occidente enfatizza la procedura. L'Oriente il potenziale di svolta. Il Medio Oriente il contesto.")

    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(70, result_y - 110, "Cosa viene omesso:")
    c.setFillColor(WHITE)
    c.setFont("Helvetica", 9)
    c.drawString(70, result_y - 127, "Ogni blocco tende a omettere i dettagli che non supportano la propria narrativa.")

    c.showPage()


# ── MAIN ──────────────────────────────────────────────────────

def main():
    c = canvas.Canvas(str(OUTPUT), pagesize=A4)
    c.setTitle("Parallax - Come Funziona")
    c.setAuthor("Parallax")

    page_cover(c)
    page_problema(c)
    page_fonti(c)
    page_pipeline(c)
    page_step1(c)
    page_step2(c)
    page_step3(c)
    page_tech(c)
    page_esempio(c)

    c.save()
    print(f"PDF generato: {OUTPUT}")


if __name__ == "__main__":
    main()
