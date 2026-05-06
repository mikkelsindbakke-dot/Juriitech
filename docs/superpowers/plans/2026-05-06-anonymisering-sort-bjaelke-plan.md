# Anonymisering med sort-bjælke — Implementerings-plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development for at implementere denne plan task-by-task. Steps bruger checkbox (`- [ ]`) syntax for tracking.

**Goal:** Erstat eksisterende bracket-anonymisering med ægte sort-bjælke-redaction der bevarer originalt PDF-layout, så outputtet kan sendes direkte til Pakkerejse-Ankenævnet.

**Architecture:** Ny modul `anonymisering_pdf.py` med detektor (regex + AI) og redactor (PyMuPDF). Eksisterende bracket-flow bevares som fallback for DOCX, billeder og scannede PDF'er. UI-orchestration i forside.py med klager-bekræftelses-trin.

**Tech Stack:** PyMuPDF (`fitz`) til PDF-manipulation, Anthropic Claude (`claude-sonnet-4-6`) til navne/adresse-detection, eksisterende Streamlit-UI.

---

## File-struktur

**Nye filer:**
- `anonymisering_pdf.py` — kerne-modul med `udtraek_pdf_tekst`, `er_pdf_scannet`, `find_redaction_targets`, `redact_pdf`

**Modificerede filer:**
- `ai_engine.py` — tilføj `find_navne_til_redaction()` (ny tool-use funktion)
- `forside.py` — ny anonymiserings-UI (bekræftelses-form, loading, resultat-view, downloads)
- `requirements.txt` — tilføj `pymupdf`

**Bevares uændret (fallback):**
- Eksisterende `_anonymiser_*` i `ai_engine.py`
- `eksport.py`

---

## Task 1: Tilføj PyMuPDF som dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Tjek om pymupdf allerede er listet**

Run: `grep -i pymupdf requirements.txt`
Expected: ingen output (ikke installeret endnu)

- [ ] **Step 2: Tilføj pymupdf til requirements.txt**

Tilføj linje (alfabetisk placering eller i bunden, følg eksisterende mønster):

```
pymupdf==1.24.10
```

- [ ] **Step 3: Installer lokalt**

Run: `pip install pymupdf==1.24.10`
Expected: "Successfully installed pymupdf-1.24.10" eller "already satisfied"

- [ ] **Step 4: Verificér import virker**

Run: `python3 -c "import fitz; print(fitz.__version__)"`
Expected: `1.24.10` (eller nyere)

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "deps: tilføj pymupdf til PDF-redaction"
```

---

## Task 2: Opret `anonymisering_pdf.py` med tekst-ekstraktion

**Files:**
- Create: `anonymisering_pdf.py`

- [ ] **Step 1: Opret filen med basis-imports og `udtraek_pdf_tekst`**

Skriv `anonymisering_pdf.py`:

```python
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


def udtraek_pdf_tekst(pdf_bytes: bytes) -> str:
    """Returnér al tekst fra PDF'en som én streng. Sider adskilles af '\\n\\n'."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n\n".join(side.get_text() for side in doc)
    finally:
        doc.close()
```

- [ ] **Step 2: Smoke-test med en kendt PDF**

Run:
```bash
python3 -c "
from anonymisering_pdf import udtraek_pdf_tekst
import fitz
# Lav en test-PDF i memory
doc = fitz.open()
side = doc.new_page()
side.insert_text((50, 100), 'Test af tekst-ekstraktion. Maria Hansen.')
pdf_bytes = doc.tobytes()
doc.close()

tekst = udtraek_pdf_tekst(pdf_bytes)
print(repr(tekst))
assert 'Maria Hansen' in tekst, f'Forventede Maria Hansen i: {tekst!r}'
print('OK')
"
```
Expected: `OK` printet sidst.

- [ ] **Step 3: Commit**

```bash
git add anonymisering_pdf.py
git commit -m "feat(anonymisering): nyt modul med PDF-tekst-ekstraktion"
```

---

## Task 3: Tilføj scanned-PDF detektion

**Files:**
- Modify: `anonymisering_pdf.py`

- [ ] **Step 1: Tilføj `er_pdf_scannet`**

Indsæt funktion i `anonymisering_pdf.py` efter `udtraek_pdf_tekst`:

```python
def er_pdf_scannet(pdf_bytes: bytes) -> bool:
    """
    Returnér True hvis PDF'en mangler selektér-bar tekst (kun billed-lag).

    Pragmatisk heuristik: hvis ingen side har > 20 tegn tekst, antager
    vi at det er en scannet PDF. 20 er valgt så små headers/sidetal
    ikke udløser false negatives, men reelle dokumenter altid passerer.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return all(len(side.get_text().strip()) <= 20 for side in doc)
    finally:
        doc.close()
```

- [ ] **Step 2: Smoke-test (positive + negative case)**

Run:
```bash
python3 -c "
from anonymisering_pdf import er_pdf_scannet
import fitz

# Negative: PDF med tekst skal IKKE være scannet
doc = fitz.open()
doc.new_page().insert_text((50, 100), 'En masse rigtig tekst der bør detekteres som ikke-scannet')
pdf_bytes = doc.tobytes()
doc.close()
assert er_pdf_scannet(pdf_bytes) == False, 'PDF med tekst blev fejlagtigt klassificeret som scannet'

# Positive: tom PDF skal være scannet
doc = fitz.open()
doc.new_page()
pdf_bytes = doc.tobytes()
doc.close()
assert er_pdf_scannet(pdf_bytes) == True, 'Tom PDF blev fejlagtigt klassificeret som ikke-scannet'

print('OK')
"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add anonymisering_pdf.py
git commit -m "feat(anonymisering): detektér scannede PDF'er uden tekst-lag"
```

---

## Task 4: Tilføj regex-detektor for kanoniske mønstre

**Files:**
- Modify: `anonymisering_pdf.py`

- [ ] **Step 1: Tilføj regex-detektor**

Indsæt i `anonymisering_pdf.py`:

```python
# CPR: 6 cifre + valgfri bindestreg + 4 cifre
_CPR_RE = re.compile(r"\b\d{6}-?\d{4}\b")

# Email: capture lokaldel før @
_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-]+)@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Telefon: dansk og udenlandsk format. Område-prefiks (+xx eller første gruppe)
# bevares — vi capture KUN cifrene EFTER områdekoden.
# Match: "+45 12 34 56 78" → capture "12 34 56 78"
# Match: "928 56 14 14" → capture "56 14 14" (3-cifret områdekode)
_TLF_INTL_RE = re.compile(r"\+\d{2,3}\s+(\d[\d\s]{6,12}\d)")
_TLF_DK_RE = re.compile(r"\b\d{3}\s+(\d{2}\s+\d{2}\s+\d{2})\b")


def _patterns_via_regex(tekst: str) -> list[dict]:
    """
    Find kanoniske mønstre der altid skal redactes.

    Returnerer liste af dicts: {"streng": <str>, "kategori": <str>}.
    `streng` er den eksakte sub-streng der skal sortmaskeres i PDF'en.

    Vi returnerer KUN den del der skal maskeres — ikke hele matchet.
    Fx for "info@hotel.com" returneres "info" så domænet bevares.
    """
    targets: list[dict] = []

    # CPR: hele matchet redactes
    for m in _CPR_RE.finditer(tekst):
        targets.append({"streng": m.group(0), "kategori": "cpr"})

    # Email: kun lokaldel
    for m in _EMAIL_RE.finditer(tekst):
        targets.append({"streng": m.group(1), "kategori": "email_lokaldel"})

    # Telefon (intl): cifre efter +xx
    for m in _TLF_INTL_RE.finditer(tekst):
        targets.append({"streng": m.group(1).strip(), "kategori": "telefon"})

    # Telefon (DK 3-cifret områdekode): cifre efter områdekode
    for m in _TLF_DK_RE.finditer(tekst):
        targets.append({"streng": m.group(1).strip(), "kategori": "telefon"})

    return targets
```

- [ ] **Step 2: Smoke-test med positive cases**

Run:
```bash
python3 -c "
from anonymisering_pdf import _patterns_via_regex

tekst = '''
CPR: 010199-1234 og 0101991234
Email: info@hotel.com og support@apartamentosmiami.com
Telefon: +45 12 34 56 78 og 928 56 14 14
'''
targets = _patterns_via_regex(tekst)
print(targets)

strenge = [t['streng'] for t in targets]
assert '010199-1234' in strenge, f'CPR mangler: {strenge}'
assert '0101991234' in strenge, f'CPR uden bindestreg mangler: {strenge}'
assert 'info' in strenge, f'Email-lokaldel info mangler: {strenge}'
assert 'support' in strenge, f'Email-lokaldel support mangler: {strenge}'
assert '12 34 56 78' in strenge, f'Tlf intl mangler: {strenge}'
assert '56 14 14' in strenge, f'Tlf DK mangler: {strenge}'
print('OK positive cases')
"
```
Expected: `OK positive cases`

- [ ] **Step 3: Smoke-test med negative cases (false-positive guards)**

Run:
```bash
python3 -c "
from anonymisering_pdf import _patterns_via_regex

# Dato må IKKE matche som CPR — kun 8 cifre + bindestreg er forskelligt fra CPR-format
tekst = 'Sagen sluttede 25-04-2026. Datoer er ikke CPR.'
targets = _patterns_via_regex(tekst)
strenge = [t['streng'] for t in targets if t['kategori'] == 'cpr']
assert strenge == [], f'Dato matchede fejlagtigt som CPR: {strenge}'

# Booking-ref må ikke matche som telefon (8 cifre uden mellemrum)
tekst = 'Booking 29984552 er aktiv.'
targets = _patterns_via_regex(tekst)
strenge = [t['streng'] for t in targets if t['kategori'] == 'telefon']
assert strenge == [], f'Booking-ref matchede fejlagtigt som telefon: {strenge}'

print('OK negative cases')
"
```
Expected: `OK negative cases`

- [ ] **Step 4: Commit**

```bash
git add anonymisering_pdf.py
git commit -m "feat(anonymisering): regex-detektor for CPR/email/telefon"
```

---

## Task 5: Tilføj AI-baseret navne/adresse-detektion

**Files:**
- Modify: `ai_engine.py`

- [ ] **Step 1: Tilføj `find_navne_til_redaction` i ai_engine.py**

Find slutningen af de eksisterende `_anonymiser_*` funktioner i `ai_engine.py` og indsæt EFTER dem:

```python
_REDACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "navne": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fornavn": {"type": "string"},
                    "efternavn": {"type": "string"},
                    "kategori": {
                        "type": "string",
                        "enum": ["tui_medarbejder", "tredjepart"],
                    },
                    "redact_streng": {
                        "type": "string",
                        "description": (
                            "Den præcise streng der skal sortmaskeres "
                            "— typisk efternavnet"
                        ),
                    },
                },
                "required": ["fornavn", "efternavn", "kategori", "redact_streng"],
            },
        },
        "adresser": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fuld_adresse": {"type": "string"},
                    "redact_streng": {
                        "type": "string",
                        "description": (
                            "Den del af adressen der skal sortmaskeres "
                            "— gade + husnummer, IKKE postnr/by"
                        ),
                    },
                },
                "required": ["fuld_adresse", "redact_streng"],
            },
        },
    },
    "required": ["navne", "adresser"],
}


def find_navne_til_redaction(tekst: str, klager_navne: list[str]) -> dict:
    """
    Bed AI om at finde alle navne og adresser i teksten der skal redactes.

    Klagers navne (og medrejsende) udelades fra resultatet — de skal
    ALDRIG redactes. AI'en får dem eksplicit i prompten.

    Returnerer dict med 'navne' og 'adresser' lister. Tom liste hvis
    intet fundet, eller hvis AI-kaldet fejler (fall-back graceful).
    """
    klient = _get_client()
    if klient is None:
        print("DEBUG: anonymisering AI-klient ikke tilgængelig — returnerer tom")
        return {"navne": [], "adresser": []}

    klager_liste_str = ", ".join(klager_navne) if klager_navne else "(ingen angivet)"

    system_prompt = f"""Du anonymiserer juridiske dokumenter for et dansk rejseselskab.

KLAGERE I DENNE SAG (må ALDRIG redactes — de skal forblive synlige): {klager_liste_str}

Find ALLE navne og adresser i teksten der SKAL redactes efter disse regler:

NAVNE:
- TUI-medarbejdere og tredjeparter (hotel-staff, læger, vidner osv.):
  fornavn BEVARES, efternavn(e) sortmaskeres
- Kategori: 'tui_medarbejder' for ansatte hos TUI/rejseselskabet,
  'tredjepart' for alle andre (hotel, eksterne osv.)
- redact_streng: den PRÆCISE streng (typisk efternavnet) som det står i teksten

ADRESSER:
- Privatadresser: gade + husnummer sortmaskeres, postnr + by bevares
- redact_streng: den del der skal redactes (fx 'Strandvej 14')
- Hotel-adresser, virksomhedsadresser i signaturer og lignende
  publikke adresser SKAL OGSÅ redactes (gade+nr)

VIGTIGE REGLER:
- Opfind ALDRIG navne der ikke står i teksten
- Inkludér ALDRIG klagernes navne i listen
- Hvis et navn er flertydig (kan være klager eller tredjepart),
  så lad være med at inkludere det
- Returnér tom liste hvis intet skal redactes
"""

    try:
        response = klient.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            temperature=0,
            system=system_prompt,
            tools=[{
                "name": "rapporter_redaction_targets",
                "description": "Rapportér alle navne og adresser der skal redactes",
                "input_schema": _REDACTION_SCHEMA,
            }],
            tool_choice={"type": "tool", "name": "rapporter_redaction_targets"},
            messages=[{
                "role": "user",
                "content": f"Find alle redaction-targets i denne tekst:\n\n{tekst}",
            }],
        )
        for blok in response.content:
            if blok.type == "tool_use":
                return blok.input
    except Exception as e:
        print(f"DEBUG: find_navne_til_redaction AI-kald fejlede: {e}")

    return {"navne": [], "adresser": []}
```

- [ ] **Step 2: Smoke-test (kun hvis API-credits er tilgængelige)**

Run:
```bash
python3 -c "
from ai_engine import find_navne_til_redaction

tekst = '''
Mrs. Wenche Lerang har klaget over opholdet.
TUI-medarbejderen Maria Hansen behandlede sagen.
Hotelreceptionisten Arantza Piñero kontaktede os.
'''
result = find_navne_til_redaction(tekst, klager_navne=['Wenche Lerang'])
print(result)

# Verificér struktur
assert 'navne' in result
assert 'adresser' in result

# Klager må ALDRIG være i listen
strenge = [n.get('redact_streng', '') for n in result['navne']]
assert 'Lerang' not in strenge, f'Klager Lerang fejlagtigt i listen: {strenge}'
assert 'Wenche' not in strenge, f'Klagers fornavn fejlagtigt i listen: {strenge}'

print('OK — AI-detektor virker')
"
```
Expected: `OK — AI-detektor virker`. Hvis credits er tomme, returneres tom liste graceful (test fortsætter).

- [ ] **Step 3: Commit**

```bash
git add ai_engine.py
git commit -m "feat(anonymisering): AI-detektor for navne og adresser"
```

---

## Task 6: Kombinér detektorer med sikkerhedsnet-filter

**Files:**
- Modify: `anonymisering_pdf.py`

- [ ] **Step 1: Tilføj `find_redaction_targets`**

Indsæt i `anonymisering_pdf.py` (importér ai_engine øverst):

```python
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

    # Lag 1: regex-mønstre
    targets.extend(_patterns_via_regex(tekst))

    # Lag 2: AI-detektion af navne og adresser
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

    # Sikkerhedsnet: fjern alt der case-insensitive matcher klager_navne
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
```

- [ ] **Step 2: Smoke-test sikkerhedsnet**

Run:
```bash
python3 -c "
# Test sikkerhedsnet uden AI-kald — mock find_navne_til_redaction
import sys, types
fake_ai = types.ModuleType('ai_engine')
fake_ai.find_navne_til_redaction = lambda t, k: {
    'navne': [
        {'fornavn': 'Wenche', 'efternavn': 'Lerang', 'kategori': 'tredjepart', 'redact_streng': 'Lerang'},
        {'fornavn': 'Maria', 'efternavn': 'Hansen', 'kategori': 'tui_medarbejder', 'redact_streng': 'Hansen'},
    ],
    'adresser': [],
}
sys.modules['ai_engine'] = fake_ai

from anonymisering_pdf import find_redaction_targets
targets = find_redaction_targets('dummy tekst', klager_navne=['Wenche Lerang'])
strenge = [t['streng'] for t in targets]
print(strenge)
assert 'Lerang' not in strenge, f'Sikkerhedsnet fejlede — Lerang er i: {strenge}'
assert 'Hansen' in strenge, f'Hansen mangler — sikkerhedsnet for aggressivt: {strenge}'
print('OK')
"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add anonymisering_pdf.py
git commit -m "feat(anonymisering): kombinér detektorer med klager-sikkerhedsnet"
```

---

## Task 7: Tilføj PDF-redactor (PyMuPDF apply_redactions)

**Files:**
- Modify: `anonymisering_pdf.py`

- [ ] **Step 1: Tilføj `redact_pdf`**

Indsæt i `anonymisering_pdf.py`:

```python
def redact_pdf(pdf_bytes: bytes, targets: Iterable[dict]) -> bytes:
    """
    Anvend redactions på PDF'en og returnér ny PDF som bytes.

    For hvert target finder vi alle forekomster via PyMuPDF's
    `search_for` og tilføjer en redact-annotation. `apply_redactions`
    fjerner derefter den underliggende tekst og tegner sort rektangel
    — det er ÆGTE redaction (tekst kan ikke længere kopieres ud).

    Hvis et target ikke findes i PDF'en, ignoreres det stille (kan
    ske ved usædvanlig glyph-spacing). Andre targets fortsætter.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for side in doc:
            for target in targets:
                streng = target["streng"]
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
```

- [ ] **Step 2: Smoke-test redaction**

Run:
```bash
python3 -c "
from anonymisering_pdf import redact_pdf, udtraek_pdf_tekst
import fitz

# Lav test-PDF med kendt indhold
doc = fitz.open()
side = doc.new_page()
side.insert_text((50, 100), 'Maria Hansen ringede til 928 56 14 14.')
pdf_bytes = doc.tobytes()
doc.close()

# Redact 'Hansen' og '56 14 14'
targets = [
    {'streng': 'Hansen', 'kategori': 'navn'},
    {'streng': '56 14 14', 'kategori': 'telefon'},
]
ny_pdf = redact_pdf(pdf_bytes, targets)

# Verificér at den nye PDF er gyldig og at teksten er fjernet
ny_tekst = udtraek_pdf_tekst(ny_pdf)
print(repr(ny_tekst))
assert 'Hansen' not in ny_tekst, f'Hansen ikke redactet: {ny_tekst!r}'
assert '56 14 14' not in ny_tekst, f'Telefon ikke redactet: {ny_tekst!r}'
assert 'Maria' in ny_tekst, f'Maria fejlagtigt redactet: {ny_tekst!r}'
assert '928' in ny_tekst, f'Områdekode fejlagtigt redactet: {ny_tekst!r}'
print('OK — redaction virker')
"
```
Expected: `OK — redaction virker`

- [ ] **Step 3: Commit**

```bash
git add anonymisering_pdf.py
git commit -m "feat(anonymisering): PDF-redactor med ægte apply_redactions"
```

---

## Task 8: Tilføj orchestrator-funktion

**Files:**
- Modify: `anonymisering_pdf.py`

- [ ] **Step 1: Tilføj `anonymiser_pdf_fil` orchestrator**

Indsæt i `anonymisering_pdf.py`:

```python
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
      - "fejl_redaction"   — apply_redactions fejlede på alle sider, output er None

    Kalderen i forside.py skal selv vise advarsler og evt. tilbyde
    bracket-fallback baseret på status.
    """
    # 1. Tjek for scannet PDF
    try:
        if er_pdf_scannet(pdf_bytes):
            return (None, "scannet")
    except Exception as e:
        print(f"DEBUG: kunne ikke åbne PDF til scan-detektion: {e}")
        return (None, "fejl_aaben")

    # 2. Udtræk tekst og find targets
    try:
        tekst = udtraek_pdf_tekst(pdf_bytes)
    except Exception as e:
        print(f"DEBUG: tekst-ekstraktion fejlede: {e}")
        return (None, "fejl_aaben")

    targets = find_redaction_targets(tekst, klager_navne)

    # 3. Anvend redactions
    try:
        output_bytes = redact_pdf(pdf_bytes, targets)
        return (output_bytes, "ok")
    except Exception as e:
        print(f"DEBUG: redact_pdf fejlede: {e}")
        return (None, "fejl_redaction")
```

- [ ] **Step 2: Smoke-test orchestrator**

Run:
```bash
python3 -c "
from anonymisering_pdf import anonymiser_pdf_fil
import fitz

# Lav test-PDF
doc = fitz.open()
doc.new_page().insert_text((50, 100), 'Maria Hansen ringede.')
pdf_bytes = doc.tobytes()
doc.close()

# Bemærk: dette kalder ai_engine.find_navne_til_redaction.
# Hvis API-credits er tomme, returneres tom AI-liste graceful.
output, status = anonymiser_pdf_fil(pdf_bytes, klager_navne=['Wenche Lerang'])
print(f'Status: {status}')
assert status == 'ok', f'Forventede ok, fik {status}'
assert output is not None
assert len(output) > 0
print('OK')
"
```
Expected: `Status: ok` og `OK`

- [ ] **Step 3: Commit**

```bash
git add anonymisering_pdf.py
git commit -m "feat(anonymisering): orchestrator-funktion med fejlstatus"
```

---

## Task 9: Bekræftelses-form for klager-navne

**Files:**
- Modify: `forside.py`

- [ ] **Step 1: Find eksisterende anonymiseringsknap-blok**

Run: `grep -n "anonymis" forside.py | head -20`

Identificér linjenummeret hvor anonymiseringsknappen findes, og noter den eksisterende flow (typisk: knap → `_anonymiser_*` kald → download Word/PDF).

- [ ] **Step 2: Tilføj klager-bekræftelses-form FØR anonymiseringskaldet**

Lige før den eksisterende anonymiseringsknap, indsæt en ny form (eksakt placering afhænger af eksisterende kode-struktur). Generel struktur:

```python
# Hent klagers navn fra sagsmetadata (auto-udledt under analyse)
_metadata = st.session_state.get("sagsmetadata", {}) or {}
_default_klager = _metadata.get("klagers_navn", "") or ""
_default_medrejsende = _metadata.get("medrejsende_navn", "") or ""

with st.expander("Anonymisér bilag", expanded=False):
    st.markdown(
        "Bekræft hvem der er klager — disse navne **bevares** i de "
        "anonymiserede bilag. Alle andre navne får sortmaskeret efternavn."
    )
    klager_input = st.text_input(
        "Klager(e)",
        value=_default_klager,
        key="anon_klager",
        help="Komma-separeret hvis flere",
    )
    medrejsende_input = st.text_input(
        "Medrejsende (valgfrit)",
        value=_default_medrejsende,
        key="anon_medrejsende",
        help="Komma-separeret hvis flere",
    )

    if st.button("🖍️ Anonymisér bilag", type="primary", key="anon_start"):
        klager_navne = [
            n.strip() for n in (klager_input + "," + medrejsende_input).split(",")
            if n.strip()
        ]
        if not klager_navne:
            st.error(
                "⚠️ Du har ikke angivet nogen klager. ALLE navne i "
                "dokumenterne vil blive sortmaskeret. Tilføj klagers navn "
                "først, eller bekræft eksplicit i næste trin."
            )
        else:
            st.session_state["_anon_klager_navne"] = klager_navne
            st.session_state["_anon_pending"] = True
            st.rerun()
```

- [ ] **Step 3: Smoke-test UI manuelt**

```bash
streamlit run app.py
```

Naviger til en sag, åbn "Anonymisér bilag"-expander, verificér at:
- Klager er pre-udfyldt fra sagsmetadata
- Felter er redigerbare
- Knappen sætter session-state og kører rerun

- [ ] **Step 4: Commit**

```bash
git add forside.py
git commit -m "feat(anonymisering): klager-bekræftelses-form før redaction"
```

---

## Task 10: Anonymiseringsloop med per-fil routing

**Files:**
- Modify: `forside.py`

- [ ] **Step 1: Tilføj loop-handler der kører ved `_anon_pending`-flag**

Tilføj efter bekræftelses-formen (eller på et logisk sted i renderingen):

```python
if st.session_state.get("_anon_pending"):
    from ui import thinking_fullpage
    from anonymisering_pdf import anonymiser_pdf_fil

    klager_navne = st.session_state.get("_anon_klager_navne", [])
    sag = st.session_state.get("aktuel_sag", {}) or {}
    filer = sag.get("filer", []) or []

    if not filer:
        st.warning("Ingen bilag at anonymisere.")
        st.session_state["_anon_pending"] = False
        st.stop()

    resultater: list[dict] = []
    placeholder = thinking_fullpage("Forbereder anonymisering...")
    placeholder.empty()

    for idx, fil in enumerate(filer, start=1):
        navn = fil.get("filnavn", f"bilag_{idx}.pdf")
        type_ = (fil.get("filtype") or "").lower()
        bytes_ = fil.get("indhold")

        placeholder = thinking_fullpage(
            f"Anonymiserer bilag {idx} af {len(filer)}: {navn}"
        )

        if type_.endswith("pdf") and bytes_:
            output, status = anonymiser_pdf_fil(bytes_, klager_navne)
            resultater.append({
                "navn": navn,
                "status": status,
                "output_pdf": output,
                "type": "pdf",
            })
        else:
            # DOCX, billeder, ukendt → fallback til eksisterende bracket-flow
            from ai_engine import _anonymiser_enkeltfil
            try:
                bracket_text = _anonymiser_enkeltfil(fil)
                resultater.append({
                    "navn": navn,
                    "status": "bracket_fallback",
                    "output_text": bracket_text,
                    "type": type_,
                })
            except Exception as e:
                print(f"DEBUG: bracket-fallback fejlede for {navn}: {e}")
                resultater.append({
                    "navn": navn,
                    "status": "fejl_aaben",
                    "type": type_,
                })

        placeholder.empty()

    st.session_state["_anon_resultater"] = resultater
    st.session_state["_anon_pending"] = False
    st.rerun()
```

- [ ] **Step 2: Smoke-test loop manuelt**

Upload 1-2 PDF'er + 1 DOCX i en sag, kør anonymisering. Verificér i `fly logs` (eller terminal) at:
- DEBUG-linjer vises for hver fil
- Flow ender uden exceptions
- `_anon_resultater` er sat i session_state

- [ ] **Step 3: Commit**

```bash
git add forside.py
git commit -m "feat(anonymisering): per-fil loop med routing til ny eller fallback"
```

---

## Task 11: Resultat-view med per-fil download + ZIP

**Files:**
- Modify: `forside.py`

- [ ] **Step 1: Tilføj resultat-rendering**

Tilføj efter loop-handleren:

```python
if st.session_state.get("_anon_resultater"):
    import io
    import zipfile

    resultater = st.session_state["_anon_resultater"]
    st.markdown("### Anonymiserings-resultat")

    # Per-fil status
    for res in resultater:
        navn = res["navn"]
        status = res["status"]

        if status == "ok" and res.get("output_pdf"):
            ny_navn = navn.rsplit(".", 1)[0] + "_anonymiseret.pdf"
            cols = st.columns([0.7, 0.3])
            cols[0].markdown(f"✅ `{navn}` → `{ny_navn}`")
            cols[1].download_button(
                "Download",
                data=res["output_pdf"],
                file_name=ny_navn,
                mime="application/pdf",
                key=f"dl_{navn}",
            )
        elif status == "scannet":
            st.markdown(
                f"⚠️ `{navn}` — scannet PDF, kan ikke sort-bjælke-anonymiseres. "
                f"Brug bracket-fallback eller skip."
            )
        elif status == "bracket_fallback" and res.get("output_text"):
            st.markdown(f"⚠️ `{navn}` — anonymiseret som tekst (bracket-form)")
            st.text_area(
                f"Anonymiseret tekst for {navn}",
                value=res["output_text"],
                key=f"bracket_{navn}",
                height=200,
            )
        else:
            st.markdown(f"❌ `{navn}` — kunne ikke behandles ({status})")

    # ZIP-download for alle PDF-resultater
    pdf_resultater = [r for r in resultater if r.get("output_pdf")]
    if pdf_resultater:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for res in pdf_resultater:
                ny_navn = res["navn"].rsplit(".", 1)[0] + "_anonymiseret.pdf"
                zf.writestr(ny_navn, res["output_pdf"])
        st.download_button(
            "📦 Download alle som ZIP",
            data=zip_buffer.getvalue(),
            file_name="anonymiserede_bilag.zip",
            mime="application/zip",
            key="dl_zip",
        )

    if st.button("Ryd anonymiserings-resultat", key="anon_clear"):
        st.session_state.pop("_anon_resultater", None)
        st.rerun()
```

- [ ] **Step 2: Smoke-test UI manuelt**

Verificér at:
- ✅/⚠️/❌ statuser vises korrekt
- Per-fil download virker
- ZIP indeholder kun ✅-PDF'er
- "Ryd resultat" nulstiller view

- [ ] **Step 3: Commit**

```bash
git add forside.py
git commit -m "feat(anonymisering): resultat-view med per-fil download + ZIP"
```

---

## Task 12: End-to-end smoke-test på reference-PDF

**Files:**
- Ingen kode-ændringer — kun verifikation

- [ ] **Step 1: Find eller upload reference-PDF**

Brug `svar fra hotel sag 2026-01994.pdf` (referenceeksempel brugeren delte under brainstorming).

- [ ] **Step 2: Kør hele flowet**

```bash
streamlit run app.py
```

1. Login, vælg sag eller opret ny
2. Upload reference-PDF
3. Kør analyse (sagsmetadata udfyldes)
4. Åbn "Anonymisér bilag", bekræft klager-navn
5. Klik "Anonymisér"
6. Download resultatet
7. Åbn i PDF-viewer

- [ ] **Step 3: Visuel verifikation**

Sammenlign output med brugerens referenceeksempel og verificér:

- [ ] Klager-navn (Wenche Lerang) er **synligt**, ikke redactet
- [ ] TUI-staff og hotel-staff: **fornavn synligt**, efternavn sortmaskeret
- [ ] Email-lokaldele: sortmaskeret, **domæne synligt** (`@apartamentosmiami.com`)
- [ ] Telefon: **områdekode synlig** (`928`), resten sortmaskeret
- [ ] Layout: sider, marginer, fonts, indrykninger **uændret**
- [ ] Booking-ref `29984552`: **synlig**, ikke redactet
- [ ] Hotel-navn `Apartamentos Miami`: **synligt**, ikke redactet

- [ ] **Step 4: Hvis alle checks består — commit final-marker**

```bash
git commit --allow-empty -m "test: end-to-end smoke-test bestået for anonymisering"
```

---

## Self-Review

Efter at have skrevet planen — quick spec coverage check:

| Spec-krav | Task |
| --- | --- |
| Erstat bracket med sort-bjælke for PDF | Task 7 + 8 |
| Klager bevares (Model C) | Task 9 + 6 (sikkerhedsnet) |
| Fornavn bevaret, efternavn redactet | Task 5 (AI-prompt) |
| Email-lokaldel redacted, domæne synligt | Task 4 (regex) |
| Telefon med områdekode synlig | Task 4 (regex) |
| CPR redactes helt | Task 4 (regex) |
| Adresse: gade+nr redacted, postnr+by synligt | Task 5 (AI) |
| Scannet PDF → fallback | Task 8 (orchestrator) + Task 10 (routing) |
| DOCX → fallback | Task 10 (routing) |
| Per-fil download + ZIP | Task 11 |
| Original layout bevaret | Task 7 (PyMuPDF apply_redactions) |
| End-to-end test på reference | Task 12 |

Alle spec-krav har en tilhørende task. Ingen placeholders. Type-konsistens: `targets` er overalt en `list[dict]` med `{"streng": str, "kategori": str}`.

Plan klar til eksekvering via subagent-driven-development.
