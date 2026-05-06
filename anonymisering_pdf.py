"""
PDF-anonymisering med sort-bjælke-redaction.

Bevarer original PDF-layout 1:1 og lægger sorte rektangler oven på
følsomme tekst-segmenter. Brugeren får et output der ligner det
Pakkerejse-Ankenævnet forventer (fx anonymiserede mail-tråde).

Tre lag:
- Detektor: udtræk tekst, find redaction-targets (regex + AI)
- Redactor: anvend redactions via PyMuPDF
- Orchestrator: kaldes fra forside.py med fil-loop og fejlhåndtering
"""
from __future__ import annotations

import re
from typing import Iterable

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Tekst-ekstraktion + scan-detektion
# ---------------------------------------------------------------------------

def udtraek_pdf_tekst(pdf_bytes: bytes) -> str:
    """Returnér al tekst fra PDF'en som én streng. Sider adskilles af '\\n\\n'."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n\n".join(side.get_text() for side in doc)
    finally:
        doc.close()


def er_pdf_scannet(pdf_bytes: bytes) -> bool:
    """
    True hvis PDF'en mangler selektér-bar tekst (kun billed-lag).

    Heuristik: hvis ingen side har > 20 tegn tekst, antager vi at det
    er en scannet PDF. Tærsklen er valgt så små headers ikke udløser
    false negatives, men reelle dokumenter altid passerer.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return all(len(side.get_text().strip()) <= 20 for side in doc)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Regex-detektor for kanoniske mønstre
# ---------------------------------------------------------------------------

# CPR: 6 cifre + valgfri bindestreg + 4 cifre
_CPR_RE = re.compile(r"\b\d{6}-?\d{4}\b")

# Email: capture lokaldel før @
_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-]+)@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Telefon med internationalt prefix: "+45 12 34 56 78" → capture "12 34 56 78"
_TLF_INTL_RE = re.compile(r"\+\d{2,3}\s+(\d[\d\s]{6,12}\d)")

# Telefon i lokalt format med 3-cifret område: "928 56 14 14" → capture "56 14 14"
_TLF_DK_RE = re.compile(r"\b\d{3}\s+(\d{2}\s+\d{2}\s+\d{2})\b")


def _patterns_via_regex(tekst: str) -> list[dict]:
    """
    Find kanoniske mønstre der altid skal redactes.

    Returnerer liste af {"streng": str, "kategori": str}. `streng` er
    den eksakte sub-streng der skal sortmaskeres i PDF'en — fx for
    "info@hotel.com" returneres "info" så domænet bevares.
    """
    targets: list[dict] = []

    for m in _CPR_RE.finditer(tekst):
        targets.append({"streng": m.group(0), "kategori": "cpr"})

    for m in _EMAIL_RE.finditer(tekst):
        targets.append({"streng": m.group(1), "kategori": "email_lokaldel"})

    for m in _TLF_INTL_RE.finditer(tekst):
        targets.append({"streng": m.group(1).strip(), "kategori": "telefon"})

    for m in _TLF_DK_RE.finditer(tekst):
        targets.append({"streng": m.group(1).strip(), "kategori": "telefon"})

    return targets


# ---------------------------------------------------------------------------
# Kombineret detektor med klager-sikkerhedsnet
# ---------------------------------------------------------------------------

def find_redaction_targets(
    tekst: str,
    klager_navne: list[str],
) -> list[dict]:
    """
    Find alle strenge der skal sortmaskeres i PDF'en.

    Kombinerer regex (CPR/email/tlf) med AI (navne/adresser) og
    filtrerer derefter mod klager_navne som sikkerhedsnet — selv hvis
    AI'en uheldigvis returnerer klagers navn, fjernes det her.

    Returnerer liste af {"streng": str, "kategori": str}.
    """
    from ai_engine import find_navne_til_redaction

    targets: list[dict] = []

    targets.extend(_patterns_via_regex(tekst))

    ai_result = find_navne_til_redaction(tekst, klager_navne)
    for navn in ai_result.get("navne", []):
        streng = (navn.get("redact_streng") or "").strip()
        if streng:
            targets.append({
                "streng": streng,
                "kategori": f"navn_{navn.get('kategori', 'ukendt')}",
            })
    for adresse in ai_result.get("adresser", []):
        streng = (adresse.get("redact_streng") or "").strip()
        if streng:
            targets.append({"streng": streng, "kategori": "adresse"})

    klager_lower = [n.lower() for n in klager_navne if n]
    filtreret: list[dict] = []
    for t in targets:
        streng_lower = t["streng"].lower()
        skip = False
        for klager in klager_lower:
            if streng_lower in klager or klager in streng_lower:
                print(
                    f"DEBUG: filtrerer redaction-target '{t['streng']}' "
                    f"— matcher klager '{klager}'"
                )
                skip = True
                break
        if not skip:
            filtreret.append(t)

    return filtreret


# ---------------------------------------------------------------------------
# Redactor (PyMuPDF apply_redactions)
# ---------------------------------------------------------------------------

def redact_pdf(pdf_bytes: bytes, targets: Iterable[dict]) -> bytes:
    """
    Anvend redactions på PDF'en og returnér ny PDF som bytes.

    For hvert target finder vi alle forekomster via PyMuPDF's
    `search_for` og tilføjer en redact-annotation. `apply_redactions`
    fjerner derefter den underliggende tekst og tegner sort rektangel
    — det er ÆGTE redaction (tekst kan ikke længere kopieres ud).

    Hvis et target ikke findes, ignoreres det stille (kan ske ved
    usædvanlig glyph-spacing). Andre targets fortsætter.
    """
    targets = list(targets)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for side in doc:
            for target in targets:
                streng = target.get("streng", "")
                if not streng:
                    continue
                try:
                    boxes = side.search_for(streng)
                except Exception as e:
                    print(f"DEBUG: search_for fejlede for {streng!r}: {e}")
                    continue
                for box in boxes:
                    side.add_redact_annot(box, fill=(0, 0, 0))
            try:
                side.apply_redactions()
            except Exception as e:
                print(f"DEBUG: apply_redactions fejlede på side: {e}")

        return doc.tobytes()
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Orchestrator (kaldes fra forside.py)
# ---------------------------------------------------------------------------

def anonymiser_pdf_fil(
    pdf_bytes: bytes,
    klager_navne: list[str],
) -> tuple[bytes | None, str]:
    """
    Komplet anonymiseringsflow for én PDF.

    Returnerer (output_bytes, status_streng). Status er én af:
      - "ok"               — successful redaction
      - "scannet"          — PDF har intet tekst-lag, output er None
      - "fejl_aaben"       — PDF kunne ikke åbnes, output er None
      - "fejl_redaction"   — apply_redactions fejlede, output er None

    Kalderen i forside.py viser advarsler og evt. bracket-fallback
    baseret på status.
    """
    try:
        if er_pdf_scannet(pdf_bytes):
            return (None, "scannet")
    except Exception as e:
        print(f"DEBUG: kunne ikke åbne PDF til scan-detektion: {e}")
        return (None, "fejl_aaben")

    try:
        tekst = udtraek_pdf_tekst(pdf_bytes)
    except Exception as e:
        print(f"DEBUG: tekst-ekstraktion fejlede: {e}")
        return (None, "fejl_aaben")

    targets = find_redaction_targets(tekst, klager_navne)

    try:
        output_bytes = redact_pdf(pdf_bytes, targets)
        return (output_bytes, "ok")
    except Exception as e:
        print(f"DEBUG: redact_pdf fejlede: {e}")
        return (None, "fejl_redaction")
