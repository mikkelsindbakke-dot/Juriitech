"""
Word-eksport af analyser og svarbreve.

Konverterer Claudes markdown-output til pænt formaterede .docx-filer med
overskrifter, fed tekst, kursiv og punkttegn. Returnerer bytes som
Streamlit kan tilbyde som download.

Claude returnerer typisk tekst med:
  - # Overskrift eller ## Underoverskrift
  - **fed tekst**
  - *kursiv tekst*
  - - punkttegn
  - Normale afsnit adskilt af tomme linjer
"""

import re
from io import BytesIO
from datetime import datetime

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


# Regex til at finde markdown-formatering i en linje
INLINE_BOLD = re.compile(r"\*\*(.+?)\*\*")
INLINE_ITALIC = re.compile(r"(?<!\*)\*(?!\*)([^*]+?)\*(?!\*)")


def _parse_inline(tekst):
    """
    Splitter en tekstlinje op i segmenter med formatering:
    [("fed", "tekst"), ("normal", " og "), ("kursiv", "kursiv")]
    """
    # Vi finder bold først (gør dem til markører), så italic på resten.
    segmenter = []
    rest = tekst

    # Scan gennem teksten og find matches
    pos = 0
    while pos < len(rest):
        bold_match = INLINE_BOLD.search(rest, pos)
        italic_match = INLINE_ITALIC.search(rest, pos)

        # Find det tidligste match
        kandidater = [m for m in [bold_match, italic_match] if m is not None]
        if not kandidater:
            segmenter.append(("normal", rest[pos:]))
            break

        naeste = min(kandidater, key=lambda m: m.start())
        if naeste.start() > pos:
            segmenter.append(("normal", rest[pos:naeste.start()]))

        if naeste is bold_match:
            segmenter.append(("fed", naeste.group(1)))
        else:
            segmenter.append(("kursiv", naeste.group(1)))
        pos = naeste.end()

    return segmenter


def _tilfoej_formateret_linje(paragraph, tekst):
    """Tilføjer tekst til et Word-afsnit med bold/italic fra markdown."""
    for stil, segment in _parse_inline(tekst):
        if not segment:
            continue
        run = paragraph.add_run(segment)
        if stil == "fed":
            run.bold = True
        elif stil == "kursiv":
            run.italic = True


def _er_overskrift(linje):
    """Returnerer (niveau, ren_tekst) hvis linjen er en overskrift, ellers None."""
    m = re.match(r"^(#{1,3})\s+(.+)", linje)
    if m:
        return len(m.group(1)), m.group(2).strip()
    return None


def _er_fed_overskrift(linje):
    """
    Genkender '**1. Indledning**' og lignende som overskrift.
    Claude bruger ofte dette format frem for # markdown-overskrifter.
    """
    m = re.match(r"^\*\*(.+?)\*\*\s*$", linje.strip())
    if m:
        indhold = m.group(1).strip()
        # Hvis det ligner en overskrift (starter med tal eller er kort), brug det
        if re.match(r"^\d+\.", indhold) or len(indhold) < 70:
            return indhold
    return None


def _er_bullet(linje):
    """Returnerer (niveau, ren_tekst) hvis det er et punkttegn, ellers None."""
    m = re.match(r"^(\s*)[-•*]\s+(.+)", linje)
    if m:
        niveau = len(m.group(1)) // 2
        return niveau, m.group(2).strip()
    return None


def markdown_til_docx_bytes(markdown_tekst, titel="Dokument", undertitel=None):
    """
    Konverterer Claudes markdown-output til en pænt formateret .docx-fil.
    Returnerer bytes.
    """
    doc = Document()

    # Dokumentopsætning — standardfont og margener
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # Sektionsopsætning — rimelige margener
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # Titel
    titel_p = doc.add_heading(titel, level=0)
    titel_p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Undertitel/metadata
    if undertitel:
        meta_p = doc.add_paragraph(undertitel)
        meta_p.runs[0].italic = True
        meta_p.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # Dato
    dato_p = doc.add_paragraph(
        f"Udarbejdet: {datetime.now().strftime('%d-%m-%Y kl. %H:%M')}"
    )
    dato_p.runs[0].italic = True
    dato_p.runs[0].font.size = Pt(9)
    dato_p.runs[0].font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    doc.add_paragraph()  # blank linje

    # Parse markdown linje for linje
    linjer = markdown_tekst.split("\n")
    i = 0
    while i < len(linjer):
        linje = linjer[i].rstrip()

        # Tom linje → blank paragraph
        if not linje.strip():
            # Undgå dobbelte blanke afsnit
            i += 1
            continue

        # Almindelig markdown overskrift (# eller ##)
        overskrift = _er_overskrift(linje)
        if overskrift:
            niveau, tekst = overskrift
            doc.add_heading(tekst, level=min(niveau, 3))
            i += 1
            continue

        # '**1. Indledning**' som overskrift
        fed_overskrift = _er_fed_overskrift(linje)
        if fed_overskrift:
            doc.add_heading(fed_overskrift, level=2)
            i += 1
            continue

        # Punkttegn
        bullet = _er_bullet(linje)
        if bullet:
            _, tekst = bullet
            p = doc.add_paragraph(style="List Bullet")
            _tilfoej_formateret_linje(p, tekst)
            i += 1
            continue

        # Ellers: normalt afsnit. Saml alle sammenhængende ikke-tomme linjer
        # (der ikke er overskrift/bullet) som ét afsnit.
        afsnit_linjer = [linje]
        j = i + 1
        while j < len(linjer):
            n = linjer[j].rstrip()
            if not n.strip():
                break
            if _er_overskrift(n) or _er_fed_overskrift(n) or _er_bullet(n):
                break
            afsnit_linjer.append(n)
            j += 1
        # Join med mellemrum (hårde linjeskift i markdown er normalt soft wraps)
        tekst = " ".join(afsnit_linjer)
        p = doc.add_paragraph()
        _tilfoej_formateret_linje(p, tekst)
        i = j

    # Konvertér til bytes
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


def analyse_til_docx(spoergsmaal, svar, klage_filnavn=None):
    """Konverterer en AI-analyse til en .docx-fil."""
    undertitel_dele = [f"Spørgsmål: {spoergsmaal}"]
    if klage_filnavn:
        undertitel_dele.insert(0, f"Klage: {klage_filnavn}")
    return markdown_til_docx_bytes(
        svar,
        titel="Juridisk analyse",
        undertitel=" — ".join(undertitel_dele),
    )


def svarbrev_til_docx(svarbrev, klage_filnavn=None):
    """Konverterer et svarbrev til en .docx-fil."""
    undertitel = f"Vedr. klage: {klage_filnavn}" if klage_filnavn else None
    return markdown_til_docx_bytes(
        svarbrev,
        titel="Udkast til svarbrev — Pakkerejseankenævnet",
        undertitel=undertitel,
    )


# ---------- PDF-EKSPORT (bruges primært til anonymiserede bilag) ----------

def markdown_til_pdf_bytes(markdown_tekst, titel="Dokument", undertitel=None):
    """
    Konverterer en markdown-tekst til en simpel, læsbar PDF.
    Returnerer bytes. Bruges fx til anonymiserede bilag hvor brugeren
    foretrækker PDF over Word.

    Reportlab importes lokalt så evt. miljøer uden reportlab stadig kan
    importere modulet (eksport til docx bliver ikke påvirket).
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem,
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2.4 * cm,
        bottomMargin=2.4 * cm,
        title=titel,
    )

    styles = getSampleStyleSheet()
    titel_style = ParagraphStyle(
        "DocTitel",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        spaceAfter=6,
    )
    undertitel_style = ParagraphStyle(
        "DocUndertitel",
        parent=styles["Italic"],
        fontSize=10,
        textColor="#64748B",
        spaceAfter=18,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=16,
        spaceAfter=8,
        alignment=TA_LEFT,
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        spaceBefore=12,
        spaceAfter=6,
    )
    h3_style = ParagraphStyle(
        "H3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        spaceBefore=10,
        spaceAfter=4,
    )

    flow = []
    flow.append(Paragraph(_escape_html(titel), titel_style))
    if undertitel:
        flow.append(Paragraph(_escape_html(undertitel), undertitel_style))

    linjer = (markdown_tekst or "").split("\n")
    bullet_buffer = []

    def flush_bullets():
        if not bullet_buffer:
            return
        items = [
            ListItem(Paragraph(_md_inline_til_html(b), body_style))
            for b in bullet_buffer
        ]
        flow.append(ListFlowable(
            items,
            bulletType="bullet",
            start="•",
            leftIndent=18,
            bulletFontName="Helvetica",
            bulletFontSize=10,
        ))
        bullet_buffer.clear()

    for raa in linjer:
        linje = raa.rstrip()
        if not linje.strip():
            flush_bullets()
            flow.append(Spacer(1, 4))
            continue

        if linje.startswith("# "):
            flush_bullets()
            flow.append(Paragraph(_md_inline_til_html(linje[2:]), titel_style))
        elif linje.startswith("## "):
            flush_bullets()
            flow.append(Paragraph(_md_inline_til_html(linje[3:]), h2_style))
        elif linje.startswith("### "):
            flush_bullets()
            flow.append(Paragraph(_md_inline_til_html(linje[4:]), h3_style))
        elif linje.lstrip().startswith(("- ", "* ")):
            content = linje.lstrip()[2:]
            bullet_buffer.append(content)
        else:
            flush_bullets()
            flow.append(Paragraph(_md_inline_til_html(linje), body_style))

    flush_bullets()

    doc.build(flow)
    return buf.getvalue()


def _escape_html(s):
    """Minimal HTML-escape til reportlab Paragraph."""
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _md_inline_til_html(tekst):
    """
    Konverterer markdown inline-formatering til de mini-HTML-tags som
    reportlab's Paragraph forstår. Understøtter **fed** og *kursiv*.
    """
    tekst = _escape_html(tekst)
    tekst = INLINE_BOLD.sub(r"<b>\1</b>", tekst)
    tekst = INLINE_ITALIC.sub(r"<i>\1</i>", tekst)
    return tekst
