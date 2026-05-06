# Svarbrev — syv ændringer: Implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementér 7 målrettede forbedringer af svarbrevs-funktionaliteten i juriitech PAX, baseret på spec'en i [`2026-05-06-svarbrev-syv-aendringer-design.md`](../specs/2026-05-06-svarbrev-syv-aendringer-design.md).

**Architecture:** Hovedsageligt prompt-justeringer i `byg_svarbrev_opgave` (ai_engine.py) + 1 ny lille modul (`svarbrev_diff.py`) + isolerede UI-rendering-flytninger i `eksport.py`, `forside.py` og `ui.py`. Ingen arkitekturændringer; alle eksisterende funktions-signaturer bevares (nye parametre får default-værdier).

**Tech Stack:** Python 3.11, Streamlit, Anthropic Claude API, python-docx, difflib (stdlib).

**Verifikations-stil:** Projektet bruger ikke pytest — verificering sker via (a) `python3 -c "..."` smoke-tests for pure Python-funktioner og (b) manuel UI-verifikation i Streamlit-appen for prompt- og rendering-ændringer (jf. `CLAUDE.md`).

---

## Filstruktur

| Fil | Ændring | Hvorfor |
|---|---|---|
| `ai_engine.py` | Modify — ny `_beregn_antal_naetter`, opdater `udled_sagsresume_strukturelt`, opdater `byg_svarbrev_opgave`, opdater `generer_svarbrev` + `generer_svarbrev_til_sag` | Antal nætter, sprog-/struktur-regler |
| `svarbrev_diff.py` | Create | Isoleret modul for diff-funktionen — én ansvarlighed |
| `eksport.py` | Modify — `_byg_svarbrev_header` + `svarbrev_til_docx` | Bilag flyttes til bunden |
| `ui.py` | Modify — `render_svarbrev_forside_preview` | Bilag flyttes til bunden i preview |
| `forside.py` | Modify — rejseperiode-chip, kald til `udled_sagsresume_strukturelt`, svarbrev-state-håndtering, diff-rendering, "Gem sagen"-state-dict | Antal nætter i UI, diff-feature, persistering |
| `gemte_sager.py` | Modify — defensiv load af nye felter | Bagudkompatibilitet |

---

## Implementeringsrækkefølge

12 tasks. Rækkefølgen følger spec'ens "lavest risiko først"-princip:

1. **Antal nætter (#1):** Tasks 1-4
2. **Sprogregler (#3 + #4):** Tasks 5-6
3. **Brevstruktur (#2 + #5):** Tasks 7-8
4. **Bilag flyttes (#7):** Task 9
5. **Diff-feature (#6):** Tasks 10-12

Mellem hver task: smoke-test + commit.

---

## Pre-task: Branch-tjek

- [ ] **Step 0: Tjek at vi står på den rigtige branch + ingen ufærdige commits blander sig**

```bash
git status
git log --oneline -5
```

Forventet: står på `refactor/rag-fase-1` (eller en feature-branch deraf), uncommitted changes er ok hvis brugeren har kendt arbejde i gang. Hvis der er ukendte uncommitted changes, stop og spørg.

---

## Task 1: `_beregn_antal_naetter` hjælpefunktion

**Files:**
- Modify: `ai_engine.py` — tilføj ny funktion (foreslået: lige efter `_hent_navn`-funktionen, eller i nærheden af andre `_beregn_*`-helpers hvis de findes)

- [ ] **Step 1: Tilføj `_beregn_antal_naetter` til `ai_engine.py`**

Find et passende sted i ai_engine.py (foreslået: tæt på top, fx omkring linje 200, lige efter de eksisterende top-level helpers). Indsæt:

```python
def _beregn_antal_naetter(rejseperiode_str):
    """
    Parser en rejseperiode-streng og returnerer antal nætter mellem
    udrejse og hjemrejse. Returnerer None hvis parsing fejler eller
    perioden er ugyldig.

    Understøtter danske formater:
      "8.-22. juni 2025"
      "8. juni - 22. juni 2025"
      "8. juni 2025 - 22. juni 2025"
      "08-06-2025 til 22-06-2025"
      "08-06-2025 - 22-06-2025"
      "4. februar - 10. februar"  (uden årstal — antager nuværende år)
    """
    import re as _re
    from datetime import date as _date

    if not rejseperiode_str or not isinstance(rejseperiode_str, str):
        return None

    s = rejseperiode_str.strip().lower()

    DANSKE_MAANEDER = {
        "januar": 1, "februar": 2, "marts": 3, "april": 4,
        "maj": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
        "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
    }

    def _parse_dato(dag, maaned, aar):
        try:
            return _date(int(aar), int(maaned), int(dag))
        except (ValueError, TypeError):
            return None

    # Format A: "8.-22. juni 2025" (fælles måned + årstal)
    m = _re.match(
        r"(\d{1,2})\.\s*[-–—]\s*(\d{1,2})\.\s*(\w+)\s+(\d{4})",
        s,
    )
    if m:
        d1, d2, mn, yr = m.group(1), m.group(2), m.group(3), m.group(4)
        mnum = DANSKE_MAANEDER.get(mn)
        if mnum:
            ud = _parse_dato(d1, mnum, yr)
            hj = _parse_dato(d2, mnum, yr)
            if ud and hj and hj > ud:
                return (hj - ud).days

    # Format B: "8. juni - 22. juni 2025" (samme måned + årstal til sidst)
    m = _re.match(
        r"(\d{1,2})\.\s*(\w+)\s*[-–—]\s*(\d{1,2})\.\s*(\w+)\s+(\d{4})",
        s,
    )
    if m:
        d1, mn1, d2, mn2, yr = (
            m.group(1), m.group(2), m.group(3), m.group(4), m.group(5),
        )
        mnum1 = DANSKE_MAANEDER.get(mn1)
        mnum2 = DANSKE_MAANEDER.get(mn2)
        if mnum1 and mnum2:
            ud = _parse_dato(d1, mnum1, yr)
            hj = _parse_dato(d2, mnum2, yr)
            if ud and hj and hj > ud:
                return (hj - ud).days

    # Format C: "8. juni 2025 - 22. juni 2025" (eget årstal pr. dato)
    m = _re.match(
        r"(\d{1,2})\.\s*(\w+)\s+(\d{4})\s*[-–—]\s*(\d{1,2})\.\s*(\w+)\s+(\d{4})",
        s,
    )
    if m:
        d1, mn1, yr1, d2, mn2, yr2 = (
            m.group(1), m.group(2), m.group(3),
            m.group(4), m.group(5), m.group(6),
        )
        mnum1 = DANSKE_MAANEDER.get(mn1)
        mnum2 = DANSKE_MAANEDER.get(mn2)
        if mnum1 and mnum2:
            ud = _parse_dato(d1, mnum1, yr1)
            hj = _parse_dato(d2, mnum2, yr2)
            if ud and hj and hj > ud:
                return (hj - ud).days

    # Format D: "08-06-2025 til 22-06-2025" eller "08-06-2025 - 22-06-2025"
    m = _re.match(
        r"(\d{1,2})[-./](\d{1,2})[-./](\d{4})\s*(?:til|[-–—])\s*"
        r"(\d{1,2})[-./](\d{1,2})[-./](\d{4})",
        s,
    )
    if m:
        d1, mn1, yr1, d2, mn2, yr2 = (
            m.group(1), m.group(2), m.group(3),
            m.group(4), m.group(5), m.group(6),
        )
        ud = _parse_dato(d1, mn1, yr1)
        hj = _parse_dato(d2, mn2, yr2)
        if ud and hj and hj > ud:
            return (hj - ud).days

    # Format E: "4. februar - 10. februar" (intet årstal — antag nuværende år)
    m = _re.match(
        r"(\d{1,2})\.\s*(\w+)\s*[-–—]\s*(\d{1,2})\.\s*(\w+)\s*$",
        s,
    )
    if m:
        d1, mn1, d2, mn2 = (
            m.group(1), m.group(2), m.group(3), m.group(4),
        )
        mnum1 = DANSKE_MAANEDER.get(mn1)
        mnum2 = DANSKE_MAANEDER.get(mn2)
        if mnum1 and mnum2:
            yr = _date.today().year
            ud = _parse_dato(d1, mnum1, yr)
            hj = _parse_dato(d2, mnum2, yr)
            if ud and hj and hj > ud:
                return (hj - ud).days

    return None
```

- [ ] **Step 2: Smoke-test funktionen**

```bash
cd /Users/mikkelhansen/Desktop/Projekter/juridisk_assistent
python3 -c "
from ai_engine import _beregn_antal_naetter

cases = [
    ('8.-22. juni 2025', 14),
    ('8. juni - 22. juni 2025', 14),
    ('8. juni 2025 - 22. juni 2025', 14),
    ('08-06-2025 til 22-06-2025', 14),
    ('08-06-2025 - 22-06-2025', 14),
    ('4. februar - 10. februar', 6),
    ('04.02.2026 - 25.02.2026', 21),
    ('', None),
    (None, None),
    ('helt ulæseligt', None),
    ('22. juni - 8. juni 2025', None),  # hjemrejse < udrejse
]

for indput, forventet in cases:
    fundet = _beregn_antal_naetter(indput)
    status = 'OK' if fundet == forventet else 'FAIL'
    print(f'{status}: {repr(indput)} -> {fundet} (forventet {forventet})')
"
```

Forventet: alle 11 cases viser `OK`. Hvis nogen viser `FAIL`, fejlret regex'en før du går videre.

- [ ] **Step 3: Commit**

```bash
git add ai_engine.py
git commit -m "feat(svarbrev): tilføj _beregn_antal_naetter helper

Parser danske rejseperiode-strenge og returnerer antal nætter mellem
udrejse og hjemrejse. Bruges som deterministisk fallback før vi sender
data til AI-prompts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Antal nætter i Resumé-pillaren

**Files:**
- Modify: `ai_engine.py` — `udled_sagsresume_strukturelt` (ca. linje 2913)
- Modify: `forside.py` — kald til `udled_sagsresume_strukturelt` (ca. linje 2490)

- [ ] **Step 1: Udvid `udled_sagsresume_strukturelt` med `tidsforhold`-parameter**

I `ai_engine.py`, find `def udled_sagsresume_strukturelt(analyse_tekst, sagsakter_tekst="")` (ca. linje 2913). Ret signaturen og funktionsdocstring til:

```python
def udled_sagsresume_strukturelt(
    analyse_tekst, sagsakter_tekst="", tidsforhold=None
):
    """
    Udtrækker et struktureret resume af sagen baseret på den allerede
    genererede førstevurdering (og evt. sagsakter). Giver brugeren et
    lynhurtigt overblik over hvad sagen handler om, klagepunkter, krav
    og hvordan rejseselskabet har håndteret den indtil videre.

    tidsforhold (valgfri): dict med 'rejseperiode'-felt. Hvis sat og
        nætter kan udledes via _beregn_antal_naetter, beriges 'emne'-
        feltet med en sætning om rejsedatoer + antal nætter.

    Returnerer en dict (samme felter som før).
    """
```

- [ ] **Step 2: Tilføj post-processing der beriger `emne` med antal nætter**

Find i samme funktion stedet hvor `return { "emne": emne, ... }`-blokken er (ca. linje 3020-3026). Lige FØR `return`-statementet, indsæt:

```python
        # Berig emne med antal nætter hvis tidsforhold + parserbar
        # rejseperiode er tilgængelig. Format:
        #   "{eksisterende emne}. Klager rejste den X og kom hjem
        #    den Y, svarende til N nætter."
        if tidsforhold and isinstance(tidsforhold, dict):
            _rp = (tidsforhold.get("rejseperiode") or "").strip()
            _naetter = _beregn_antal_naetter(_rp) if _rp else None
            if _naetter and _naetter >= 1 and _rp:
                # Brug rejseperioden som den står — det er den mest
                # naturlige formulering uden at forsøge at parse
                # datoerne ud separat.
                _emne_basis = emne.rstrip(".").rstrip()
                emne = (
                    f"{_emne_basis}. Rejseperiode: {_rp}, "
                    f"svarende til {_naetter} nætter."
                )
```

- [ ] **Step 3: Opdater kalderen i `forside.py` til at sende `tidsforhold` med**

Find i `forside.py` (ca. linje 2490) blokken der kalder `udled_sagsresume_strukturelt`. Ret den til:

```python
                # Generér struktureret resume af sagen — lynoverblik der vises
                # umiddelbart efter førstevurderingen så juristen hurtigt
                # fanger sagens essens.
                with st.spinner("Sammenfatter sagens essens..."):
                    _resume = udled_sagsresume_strukturelt(
                        analyse_tekst=auto_svar,
                        sagsakter_tekst=st.session_state.get("sagsakter", ""),
                        tidsforhold=st.session_state.get("tidsforhold"),
                    )
                st.session_state.sagsresume = _resume
```

- [ ] **Step 4: Smoke-test i UI**

Start Streamlit-appen lokalt:

```bash
cd /Users/mikkelhansen/Desktop/Projekter/juridisk_assistent
streamlit run app.py
```

Upload en testsag hvor klagen indeholder klare rejsedatoer (fx 8.-22. juni 2025). Generér førstevurdering og verificér visuelt at Resumé-pillaren øverst viser noget som:

> "Klage over poolens tilstand. Rejseperiode: 8.-22. juni 2025, svarende til 14 nætter."

Hvis nætter ikke vises: tjek `st.session_state.tidsforhold`-dict via en midlertidig `st.write(st.session_state.tidsforhold)` for at se om feltet `rejseperiode` faktisk er udfyldt.

- [ ] **Step 5: Commit**

```bash
git add ai_engine.py forside.py
git commit -m "feat(svarbrev): vis antal nætter i Resumé-pillaren

udled_sagsresume_strukturelt accepterer nu tidsforhold-dict og beriger
emne-feltet med 'Rejseperiode: X, svarende til N nætter' når datoerne
kan parses. Graceful fallback: hvis nætter ikke kan udledes, vises
emne uændret.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Antal nætter i Tidslinje-chip

**Files:**
- Modify: `forside.py` — rejseperiode-chip rendering (ca. linje 2950-2966)

- [ ] **Step 1: Tilføj defensiv wrapper øverst i `forside.py`**

Find et passende sted øverst i `forside.py` (efter de eksisterende `from ai_engine import ...`-blokke). Tilføj:

```python
def _beregn_antal_naetter_safe(rejseperiode_str):
    """Defensiv wrapper — fanger evt. ImportError hvis ai_engine ikke
    er fuldt initialiseret. Returnerer None ved enhver fejl."""
    try:
        from ai_engine import _beregn_antal_naetter
        return _beregn_antal_naetter(rejseperiode_str)
    except Exception as e:
        print(f"DEBUG: _beregn_antal_naetter_safe fejlede: {e}")
        return None
```

- [ ] **Step 2: Find og udvid chip-rendering-blokken**

I `forside.py` find blokken der starter med kommentaren "# Lille 'Rejseperiode'-chip øverst" (ca. linje 2950). Den ser sådan her ud lige nu:

```python
        # Lille "Rejseperiode"-chip øverst, så man hurtigt ser hvilke
        # datoer destinationen dækker (gør timing-vurderingen lettere).
        _rejseperiode = (_tf or {}).get("rejseperiode") or ""
        _rejseperiode_html = ""
        if _rejseperiode and _tf_har_observationer:
            _rp_safe = _html_tf.escape(_rejseperiode)
            _rejseperiode_html = (
                '<div style="display: inline-flex; align-items: center; '
                ...
                f'<span>{_rp_safe}</span>'
                '</div>'
            )
```

Erstat hele blokken med:

```python
        # Lille "Rejseperiode"-chip øverst, så man hurtigt ser hvilke
        # datoer destinationen dækker (gør timing-vurderingen lettere).
        # Beriges med antal nætter når datoerne kan parses.
        _rejseperiode = (_tf or {}).get("rejseperiode") or ""
        _rejseperiode_html = ""
        if _rejseperiode and _tf_har_observationer:
            _n_naetter = _beregn_antal_naetter_safe(_rejseperiode)
            _rp_visning = _rejseperiode
            if _n_naetter and _n_naetter >= 1:
                _rp_visning = f"{_rejseperiode} ({_n_naetter} nætter)"
            _rp_safe = _html_tf.escape(_rp_visning)
            _rejseperiode_html = (
                '<div style="display: inline-flex; align-items: center; '
                'gap: 8px; padding: 6px 14px; border-radius: 100px; '
                'background: rgba(255,255,255,0.6); '
                'border: 1px solid rgba(146,64,14,0.18); '
                'font-weight: 600; color: #92400E; font-size: 0.88rem; '
                'margin: 4px 0 12px 0;">'
                '<span style="opacity:0.7;">Rejseperiode:</span>'
                f'<span>{_rp_safe}</span>'
                '</div>'
            )
```

- [ ] **Step 3: Smoke-test i UI**

Genstart Streamlit. Upload en testsag med kendt rejseperiode. Verificér visuelt at chip'en i tidslinje-sektionen viser:

> Rejseperiode: 8.-22. juni 2025 (14 nætter)

- [ ] **Step 4: Commit**

```bash
git add forside.py
git commit -m "feat(svarbrev): vis antal nætter i tidslinje-chip

Rejseperiode-chip i tidslinje-pillaren udvides med '(N nætter)' når
datoerne kan parses. Bruger defensiv wrapper omkring _beregn_antal_naetter.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Antal nætter i svarbrev faktum-afsnit

**Files:**
- Modify: `ai_engine.py` — `byg_svarbrev_opgave` signatur + faktum-afsnit-prompt (ca. linje 1394 + linje 1510-1525)
- Modify: `ai_engine.py` — `generer_svarbrev` (ca. linje 1652) + `generer_svarbrev_til_sag` (ca. linje 4170)

- [ ] **Step 1: Udvid `byg_svarbrev_opgave` med `antal_naetter`-parameter**

Find `def byg_svarbrev_opgave(...)` ca. linje 1394. Ret signaturen til:

```python
def byg_svarbrev_opgave(
    inkluder_kildehenvisninger: bool = False,
    verificerede_klagepunkter: list = None,
    tidsforhold: dict = None,
    antal_naetter: int = None,
) -> str:
```

- [ ] **Step 2: Opdater prompt-teksten i faktum-afsnittet (DEL 2)**

Find blokken (ca. linje 1510-1525):
```
OBLIGATORISK FAKTUM-AFSNIT (kommer LIGE EFTER indledningen):
...
  • Udrejse- og hjemrejse-dato (eller rejseperiode)
  • Antal rejsende
  • Rejsens samlede pris
  • Eventuel allerede udbetalt kompensation (med beløb)
Eksempel-formulering:
  "Klager rejste den X. juni 2025 til [Hotel-navn], [Destination, Land],
  med hjemrejse den Y. juni 2025. Rejsen omfattede [N] rejsende og havde
  en samlet pris på [beløb] kr. {REJSESELSKAB_NAVN} har forud for
  nævnsbehandlingen udbetalt [beløb] kr. i kompensation."
```

Bemærk: bullet'en om kompensation OG kompensationen i eksempel-formuleringen FJERNES helt i Task 7 (faktum-cleanup). Her i Task 4 berører vi KUN datoerne — kompensation lader vi stå indtil Task 7 så vi kan smoke-teste hvert step isoleret.

Byg en ny blok der konditionalt indsætter nætter-instruktionen. Erstat udrejse-bullet'en og eksempel-formuleringen med:

```python
    # Byg den specifikke nætter-instruktion baseret på om vi har tallet
    if antal_naetter and antal_naetter >= 1:
        naetter_bullet = (
            f"  • Udrejse- og hjemrejse-dato (eller rejseperiode), "
            f"OG antal nætter — du SKAL inkludere 'svarende til "
            f"{antal_naetter} nætter' i sætningen om rejsedatoerne. "
            f"Tallet {antal_naetter} er beregnet og verificeret — opfind "
            f"ikke et andet."
        )
        naetter_eksempel = (
            f'  "Klager rejste den X. juni 2025 til [Hotel-navn], '
            f'[Destination, Land], med hjemrejse den Y. juni 2025, '
            f'svarende til {antal_naetter} nætter. Rejsen omfattede '
            f'[N] rejsende og havde en samlet pris på [beløb] kr. '
            f'{REJSESELSKAB_NAVN} har forud for nævnsbehandlingen '
            f'udbetalt [beløb] kr. i kompensation."'
        )
    else:
        naetter_bullet = (
            "  • Udrejse- og hjemrejse-dato (eller rejseperiode)"
        )
        naetter_eksempel = (
            f'  "Klager rejste den X. juni 2025 til [Hotel-navn], '
            f'[Destination, Land], med hjemrejse den Y. juni 2025. '
            f'Rejsen omfattede [N] rejsende og havde en samlet pris på '
            f'[beløb] kr. {REJSESELSKAB_NAVN} har forud for '
            f'nævnsbehandlingen udbetalt [beløb] kr. i kompensation."'
        )
```

Så i den store `return f"""..."""` blok, find DEL 2-sektionen og erstat:
```
  • Udrejse- og hjemrejse-dato (eller rejseperiode)
```
med
```
{naetter_bullet}
```

og erstat `Eksempel-formulering:`-blokkens linjer:
```
  "Klager rejste den X. juni 2025 til [Hotel-navn], [Destination, Land],
  med hjemrejse den Y. juni 2025. Rejsen omfattede [N] rejsende og havde
  en samlet pris på [beløb] kr. {REJSESELSKAB_NAVN} har forud for
  nævnsbehandlingen udbetalt [beløb] kr. i kompensation."
```
med:
```
{naetter_eksempel}
```

- [ ] **Step 3: Opdater `generer_svarbrev_til_sag` til at beregne og sende `antal_naetter`**

I `ai_engine.py` find `def generer_svarbrev_til_sag` (ca. linje 4170). Tilføj `antal_naetter`-parameter til signaturen:

```python
def generer_svarbrev_til_sag(
    sag,
    sagsakter=None,
    ekstra_instrukser=None,
    inkluder_kildehenvisninger=False,
    verificerede_klagepunkter=None,
    tidsforhold=None,
    antal_naetter=None,
):
```

I body, lige FØR `svarbrev_opgave = byg_svarbrev_opgave(...)`-kaldet (ca. linje 4215), tilføj:

```python
        # Beregn antal nætter ud fra rejseperioden i tidsforhold (hvis
        # den findes). Hybrid: Python beregner deterministisk, AI bruger
        # tallet som autoritativt facit i faktum-afsnittet.
        if antal_naetter is None and tidsforhold:
            _rp = (tidsforhold.get("rejseperiode") or "").strip()
            antal_naetter = _beregn_antal_naetter(_rp) if _rp else None
```

Og udvid `byg_svarbrev_opgave`-kaldet til at sende det med:

```python
        svarbrev_opgave = byg_svarbrev_opgave(
            inkluder_kildehenvisninger=inkluder_kildehenvisninger,
            verificerede_klagepunkter=verificerede_klagepunkter,
            tidsforhold=tidsforhold,
            antal_naetter=antal_naetter,
        )
```

- [ ] **Step 4: Opdater også `generer_svarbrev` (single-fil-versionen)**

Find `def generer_svarbrev` (ca. linje 1652). Tilføj `antal_naetter`-parameter med default `None`. I body, send det videre til `byg_svarbrev_opgave`-kaldet (ca. linje 1679):

```python
def generer_svarbrev(
    klage,
    sagsakter=None,
    ekstra_instrukser=None,
    inkluder_kildehenvisninger=False,
    antal_naetter=None,
):
    ...
    try:
        svarbrev_opgave = byg_svarbrev_opgave(
            inkluder_kildehenvisninger=inkluder_kildehenvisninger,
            antal_naetter=antal_naetter,
        )
```

- [ ] **Step 5: Smoke-test i UI**

Genstart Streamlit. Upload testsag med kendt rejseperiode (fx 8.-22. juni 2025). Generér svarbrev. Verificér visuelt at faktum-afsnittet i svarbrevet indeholder en sætning som:

> "Klager rejste den 8. juni 2025 til [Hotel], [Destination], med hjemrejse den 22. juni 2025, svarende til 14 nætter."

Hvis "svarende til X nætter" mangler: tjek terminal-logs for "DEBUG"-output, og verificér at `tidsforhold` faktisk er sat i `st.session_state` på det tidspunkt svarbrevet genereres.

- [ ] **Step 6: Commit**

```bash
git add ai_engine.py
git commit -m "feat(svarbrev): vis antal nætter i svarbrevets faktum-afsnit

byg_svarbrev_opgave accepterer nu antal_naetter-parameter og injicerer
det som autoritativt facit i faktum-afsnits-instruktionen. AI'en bedes
inkludere 'svarende til N nætter' i sætningen om rejsedatoer.

generer_svarbrev_til_sag beregner nætter automatisk fra tidsforhold
hvis det ikke er angivet eksplicit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Sprogregel — neutral tone (#3)

**Files:**
- Modify: `ai_engine.py` — `byg_svarbrev_opgave` (tilføj ny prompt-sektion)

- [ ] **Step 1: Tilføj NEUTRAL TONE-sektion til prompten**

I `byg_svarbrev_opgave` (`ai_engine.py` ca. linje 1394+), find linjen:
```
ABSOLUT ANONYMISERING AF KLAGER (ufravigeligt krav):
```
(ca. linje 1576). Lige FØR den linje, indsæt en ny sektion:

```python
NEUTRAL TONE — UNDGÅ ANERKENDELSER OG UNDSKYLDNINGER:
{REJSESELSKAB_NAVN} udarbejder dette svarbrev fordi selskabet er UENIG
med klagers krav. Brug derfor IKKE formuleringer der lyder som en
indrømmelse — Pakkerejse-Ankenævnet kan tolke dem som anerkendelse
af ansvar og hæve den tilkendte erstatning.

Undgå disse vendinger som default:
  • "anerkender at ..."
  • "beklager at ..."
  • "finder det beklageligt at ..."
  • "erkender at ..."
  • "er enig i at ..."
  • "vi forstår klagers frustration"
  • "vi tager kritikken til efterretning"

Beskriv i stedet faktuelt hvad der er sket — UDEN følelsesladede ord.
Eksempel:
  ❌ "Vi beklager at klager oplevede problemer med poolen."
  ✅ "Klager har anført at poolen ikke var åben i hele perioden."

UNDTAGELSE: Hvis brugerens særlige instrukser ovenfor EKSPLICIT beder
om at anerkende eller beklage et specifikt forhold (fx 'anerkend de
allerede udbetalte 2.000 kr.'), så følg den instruks. Bevidst
anerkendelse er strategisk legitim når juristen aktivt har valgt det.

```

- [ ] **Step 2: Smoke-test i UI**

Genstart Streamlit. Upload en testsag og generér et svarbrev. Læs det igennem og bekræft:
- Brevet undgår "anerkender", "beklager", "finder det beklageligt" osv.
- Faktum beskrives neutralt ("klager har anført at...")

Test også undtagelsen: Tilføj en instruks som "anerkend de allerede udbetalte 2.000 kr." og generér igen. Verificér at brevet nu inkluderer en passende anerkendelse på det specifikke punkt.

- [ ] **Step 3: Commit**

```bash
git add ai_engine.py
git commit -m "feat(svarbrev): undgå 'anerkender/beklager' som default-tone

Tilføjer NEUTRAL TONE-sektion til byg_svarbrev_opgave-prompten med
liste over forbudte vendinger og en eksplicit undtagelse hvis brugeren
beder om anerkendelse via instruks-feltet. Reducerer risiko for at
{REJSESELSKAB} utilsigtet anerkender ansvar og dermed øger tilkendt
erstatning.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Sprogregel — Hr. og Fru. Danmark (#4)

**Files:**
- Modify: `ai_engine.py` — `byg_svarbrev_opgave` (tilføj ny prompt-sektion)

- [ ] **Step 1: Tilføj SIMPELT SPROG-sektion til prompten**

I `byg_svarbrev_opgave`, find sektionen vi lige tilføjede ("NEUTRAL TONE — UNDGÅ ANERKENDELSER..."). Lige EFTER den (men stadig FØR "ABSOLUT ANONYMISERING..."), indsæt:

```python
SIMPELT SPROG — SKRIV SÅ ALLE FORSTÅR DET:
Brevet skal være formelt og juridisk præcist, men IKKE akademisk eller
opstyltet. Pakkerejse-Ankenævnets medlemmer er ikke alle jurister, og
brevet skal kunne forstås af "Hr. og Fru. Danmark".

Undgå akademiske/opstyltede vendinger — brug i stedet hverdagssprog:

  ❌ "de objektivt konstaterbare forhold"
  ✅ "det der faktisk er sket"

  ❌ "i nærværende sag"
  ✅ "i denne sag"

  ❌ "for så vidt angår"
  ✅ "om" / "med hensyn til"

  ❌ "henset til"
  ✅ "fordi" / "set i lyset af"

  ❌ "under hensyntagen til"
  ✅ "ud fra"

  ❌ "uagtet at"
  ✅ "selvom"

  ❌ "det forholder sig således at"
  ✅ "det er sådan at" / (skrives bare direkte)

  ❌ "der er ikke grundlag for at antage"
  ✅ "der er ingen grund til at tro"

  ❌ "påhviler det klager at godtgøre"
  ✅ "det er klagers opgave at vise"

VIGTIGT: Juridiske kerne-termer ("mangel", "rettidig reklamation",
"forholdsmæssigt afslag", "pakkerejselovens § 22" osv.) BEVARES — det
er fagsprog der SKAL være præcist. Reglen rammer kun pyntende,
retoriske formuleringer.

Princippet: Hvis en ven der ikke er jurist kunne stoppe op og tænke
"hvad betyder det?", så skriv det om.

```

- [ ] **Step 2: Smoke-test i UI**

Genstart Streamlit. Upload en testsag og generér et svarbrev. Verificér ved gennemlæsning:
- Brevet undgår "i nærværende sag", "henset til", "for så vidt angår" osv.
- Brevet bevarer juridisk-præcise termer ("mangel", "rettidig reklamation", "§ 22" osv.)
- Sproget føles tilgængeligt uden at være amatøragtigt

- [ ] **Step 3: Commit**

```bash
git add ai_engine.py
git commit -m "feat(svarbrev): kræv tilgængeligt sprog (Hr. og Fru. Danmark)

Tilføjer SIMPELT SPROG-sektion til byg_svarbrev_opgave-prompten med
9 før→efter-eksempler på akademiske vendinger der skal omformuleres,
og eksplicit beskyttelse af juridiske kerne-termer.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Faktum-afsnit cleanup — fjern kompensation-bullet (#2 part 1)

**Files:**
- Modify: `ai_engine.py` — `byg_svarbrev_opgave` (DEL 2 FAKTUM-OVERSIGT)

- [ ] **Step 1: Fjern kompensation fra faktum-bullet-listen og eksempel**

I `byg_svarbrev_opgave`'s prompt-tekst (DEL 2 FAKTUM-OVERSIGT), find blokken (efter Task 4-ændringerne ser den sådan ud):

```
OBLIGATORISK FAKTUM-AFSNIT (kommer LIGE EFTER indledningen):
Direkte efter indledningen skal brevet have et kort, faktuelt
oversigts-afsnit (3-6 sætninger) der præsenterer sagens basale rammer
— uden argumentation. Dette afsnit MÅ IKKE udelades. Inkludér:
  • Klagers booking/rejse: hotel-navn og destination (by, land)
{naetter_bullet}
  • Antal rejsende
  • Rejsens samlede pris
  • Eventuel allerede udbetalt kompensation (med beløb)
Eksempel-formulering:
{naetter_eksempel}
Dette afsnit giver Nævnet en hurtig grundforståelse af sagen, før
argumentationen starter. UDEN det er brevet sværere at læse.
```

Fjern bullet'en `  • Eventuel allerede udbetalt kompensation (med beløb)`.

I Task 4-blokken hvor `naetter_eksempel` defineres (begge grene af if/else), fjern den sidste sætning om kompensation. De to eksempel-formuleringer skal nu se sådan her ud:

```python
    if antal_naetter and antal_naetter >= 1:
        ...
        naetter_eksempel = (
            f'  "Klager rejste den X. juni 2025 til [Hotel-navn], '
            f'[Destination, Land], med hjemrejse den Y. juni 2025, '
            f'svarende til {antal_naetter} nætter. Rejsen omfattede '
            f'[N] rejsende og havde en samlet pris på [beløb] kr."'
        )
    else:
        ...
        naetter_eksempel = (
            f'  "Klager rejste den X. juni 2025 til [Hotel-navn], '
            f'[Destination, Land], med hjemrejse den Y. juni 2025. '
            f'Rejsen omfattede [N] rejsende og havde en samlet pris på '
            f'[beløb] kr."'
        )
```

- [ ] **Step 2: Smoke-test i UI**

Genstart Streamlit. Upload en testsag hvor TUI tidligere har udbetalt kompensation. Generér svarbrev og verificér:
- Faktum-afsnittet (lige efter "TUI vil hermed komme...") indeholder IKKE en sætning om udbetalt kompensation
- Kompensationen vil blive omtalt i Samlet vurdering-afsnittet i Task 8 (vi tester det isoleret)

- [ ] **Step 3: Commit**

```bash
git add ai_engine.py
git commit -m "refactor(svarbrev): fjern kompensations-info fra faktum-afsnit

Forbereder Task 8: kompensations-info flyttes ned i 'Samlet vurdering'-
afsnittet i bunden af brevet. Faktum-afsnittet skal nu kun indeholde
neutrale rejse-grunddata (hotel, destination, datoer, antal, pris).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Samlet vurdering-afsnit (#5 + #2 part 2)

**Files:**
- Modify: `ai_engine.py` — `byg_svarbrev_opgave` (ny DEL 4 + opdater STRENGE KRAV-tjekliste)

- [ ] **Step 1: Tilføj DEL 4 SAMLET VURDERING til prompt-strukturen**

I `byg_svarbrev_opgave`'s prompt, find STRUKTUR-sektionen (ca. linje 1601):

```
STRUKTUR:
Brevet består af tre dele — UDEN nummererede sektion-overskrifter:

DEL 1 — INDLEDNING (én sætning):
  "{REJSESELSKAB_NAVN} vil hermed komme med sine bemærkninger samt bilag til sagen."

DEL 2 — FAKTUM-OVERSIGT (3-6 sætninger):
Kort, neutralt afsnit med rejse-grundoplysninger som beskrevet ovenfor
(hotel, destination, datoer, antal, pris, evt. allerede udbetalt
kompensation).

DEL 3 — JURIDISK VURDERING (brevets hoveddel):
...
```

Ret det til (3 dele bliver til 4 dele, fjern omtale af kompensation i DEL 2-beskrivelsen):

```
STRUKTUR:
Brevet består af FIRE dele — uden nummererede sektion-overskrifter
(undtagen "Samlet vurdering" der SKAL have synlig overskrift):

DEL 1 — INDLEDNING (én sætning):
  "{REJSESELSKAB_NAVN} vil hermed komme med sine bemærkninger samt bilag til sagen."

DEL 2 — FAKTUM-OVERSIGT (3-6 sætninger):
Kort, neutralt afsnit med rejse-grundoplysninger som beskrevet ovenfor
(hotel, destination, datoer, antal, pris). MÅ IKKE indeholde
kompensations-info eller hvad selskabet tidligere har gjort — det
hører hjemme i DEL 4.

DEL 3 — JURIDISK VURDERING (brevets hoveddel):
```

Find afsnittet hvor "Afslut hele brevet med 'Med venlig hilsen'..." står (ca. linje 1627). Lige FØR det afsnit, indsæt DEL 4:

```
DEL 4 — SAMLET VURDERING (afsluttende afsnit, OBLIGATORISK):
Brevet SKAL afsluttes med et afsnit under den synlige overskrift
"Samlet vurdering" (præcis denne overskrift, brug fed eller markdown
header — fx "## Samlet vurdering"). Afsnittet indeholder:

  1. Hvad {REJSESELSKAB_NAVN} har gjort forud for nævnsbehandlingen:
     kontakt med klager, evt. allerede udbetalt kompensation (med
     præcist beløb hvis oplyst), tilbud fremsat, dialogen op til
     ankenævns-klagen. Hold det faktuelt og kort (2-4 sætninger).
  2. {REJSESELSKAB_NAVN}s samlede stilling til klagen: hvad selskabet
     mener Nævnet bør gøre (afvise klagen, fastholde tidligere tilbud,
     osv.) — kort og direkte. Ingen "anmoder Nævnet om..."-formler.

DEL 4 er ALTID det sidste afsnit FØR underskrift. Mangler det,
betragtes brevet som ufuldstændigt.

```

- [ ] **Step 2: Opdater STRENGE KRAV-tjeklisten**

Find den afsluttende STRENGE KRAV-blok (ca. linje 1633-1643). Tilføj nye linjer:

```
STRENGE KRAV:
- Max 1-2 A4-sider samlet. Hvis du er i tvivl, skriv kortere.
- ALLE klagepunkter skal adresseres — tæl dem i klagen og sørg for at
  hvert ét har sin egen behandling i brevet.
- Faktum-oversigten må IKKE udelades.
- Faktum-oversigten må IKKE indeholde kompensation eller forudgående
  håndtering — kun rejse-grunddata.
- "Samlet vurdering"-afsnittet er OBLIGATORISK og skal være sidste
  afsnit før underskrift. Det skal indeholde både forudgående
  håndtering OG selskabets samlede stilling.
- Opfind ALDRIG fakta der ikke står i klagen, sagsakterne eller vidensbanken.
- Skriv på dansk i et formelt, professionelt juridisk sprog.
- Hvis en oplysning mangler der er nødvendig, skriv "[SAGSBEHANDLER UDFYLDER: ...]" som placeholder.
- Brug "{REJSESELSKAB_NAVN}" og "klager" (lille k) konsekvent. Aldrig "rejseselskabet", "K", "Klager 1" eller "Klager 2".
- Underskriftslinjen skal altid være "{REJSESELSKAB_SAGSBEHANDLER}".
- Tjek brevet igennem til sidst: ingen personnavne, ingen sektion-numre, ingen "domstols"-formuleringer, ingen "Til:"-headers, faktum-oversigt med (men UDEN kompensation), "Samlet vurdering"-afsnit til sidst, alle klagepunkter adresseret.
```

- [ ] **Step 3: Smoke-test i UI**

Genstart Streamlit. Upload testsag (helst en hvor TUI tidligere har udbetalt kompensation). Generér svarbrev og verificér:
- Brevet ender med en "Samlet vurdering"-overskrift (synlig som ## eller fed)
- Det indeholder hvad TUI har gjort forud (kontakt, kompensation osv.)
- Det indeholder TUI's samlede stilling
- Faktum-afsnittet IKKE længere indeholder kompensations-info
- "Med venlig hilsen" + signatur kommer EFTER "Samlet vurdering"-afsnittet

- [ ] **Step 4: Commit**

```bash
git add ai_engine.py
git commit -m "feat(svarbrev): tilføj 'Samlet vurdering' som obligatorisk slut-afsnit

Brevstrukturen ændres fra 3 til 4 dele. Det nye DEL 4 'Samlet
vurdering' samler (a) hvad rejseselskabet har gjort forud for
nævnsbehandlingen og (b) selskabets samlede stilling til klagen.
Står som sidste afsnit FØR underskrift.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Bilag flyttes til bunden (#7)

**Files:**
- Modify: `eksport.py` — `_byg_svarbrev_header` (ca. linje 303-394) + `svarbrev_til_docx` (ca. linje 397-460)
- Modify: `ui.py` — `render_svarbrev_forside_preview` (ca. linje 1353-1500)

- [ ] **Step 1: Stop med at rendre bilag i `_byg_svarbrev_header`**

I `eksport.py` find `_byg_svarbrev_header` (ca. linje 303). Find det afsluttende blok (ca. linje 386-394):

```python
    # Lidt ekstra luft før bilag-listen / brødteksten
    doc.add_paragraph()

    # ---------- BILAG-LISTE (lige under Vedr-linjen) ----------
    # Vises KUN hvis bilag_liste indeholder mindst én post. Bilag A er
    # altid svarbrevet selv (det første element); resten er medsendte
    # filer.
    if bilag_liste:
        _byg_bilag_liste(doc, bilag_liste)
```

Erstat med (fjern bilag-listen, behold bare luften):

```python
    # Lidt ekstra luft før brødteksten
    doc.add_paragraph()

    # NOTE: Bilag-listen rendres IKKE længere her. Den er flyttet til
    # bunden af svarbrevet (efter "Med venlig hilsen" + signatur).
    # Se svarbrev_til_docx for placeringen.
```

- [ ] **Step 2: Tilføj bilag-rendering i bunden af `svarbrev_til_docx`**

I `eksport.py` find `def svarbrev_til_docx`. Vi har brug for at se hvor brødteksten slutter — det er typisk efter parsing af markdown og inden funktionen returnerer. Find slutningen af funktionen.

Læs `svarbrev_til_docx` fra linje 397 og find den linje hvor markdown er færdig-parset (typisk lige før `bio = BytesIO(); doc.save(bio); return bio.getvalue()`-blokken).

Tilføj lige FØR den linje (men EFTER markdown-rendering er færdig):

```python
    # ---------- BILAG-LISTE I BUNDEN ----------
    # Bilag-listen rendres som det allersidste i brevet — efter
    # "Med venlig hilsen" og signaturen som AI'en har skrevet i selve
    # brødteksten. Ekstra spacer-paragraph for visuel separation.
    if bilag_liste:
        doc.add_paragraph()  # spacer
        _byg_bilag_liste(doc, bilag_liste)
```

- [ ] **Step 3: Flyt bilag-rendering til bunden i `render_svarbrev_forside_preview`**

I `ui.py` find `render_svarbrev_forside_preview` (ca. linje 1353). Strukturen er pt: header (adresse + logo + by/dato + Vedr-linje) → bilag-liste → slut.

Find blokken `bilag_html = ...` (ca. linje 1425-1449) og blokken hvor `bilag_html` indsættes i HTML'en. Vi skal flytte `bilag_html` til EFTER selve brevhovedet bliver rendret.

Den nemmeste tilgang: behold beregningen af `bilag_html`-string'en (i sig selv ikke et problem), men flyt INDSÆTTELSEN i den endelige HTML.

Find `st.markdown(...)`-kaldet med "Hele forsiden"-kommentaren (ca. linje 1452+). Gennemse strukturen og bestem hvor bilag_html aktuelt indsættes. Flyt det til at være den sidste blok inden slutnings-`</div>`-tags. Konkret betyder det normalt at flytte `{bilag_html}` ned til lige før den ydre `</div>` der wrapper hele preview'en.

- [ ] **Step 4: Smoke-test — Word + UI preview**

Genstart Streamlit. Upload testsag, generér svarbrev, og verificér at preview viser:
- Header (adresse + logo) → by/dato → Vedr-linje (ingen bilag her længere)
- Selve brevteksten → "Samlet vurdering" → "Med venlig hilsen" + signatur
- Bilag-listen NEDERST i preview'en

Tryk "Download svarbrev som Word". Åbn .docx-filen og bekræft samme rækkefølge: header → brev → "Med venlig hilsen" → signatur → bilag-liste.

- [ ] **Step 5: Commit**

```bash
git add eksport.py ui.py
git commit -m "feat(svarbrev): flyt bilag-oversigt til bunden af brevet

Bilag-listen står nu efter 'Med venlig hilsen' og signaturen — både
i Word-eksport og forside-preview. Tidligere stod den lige under
Vedr-linjen øverst. Matcher den foretrukne brevopbygning hvor
bilag fungerer som en form for indholdsfortegnelse til vedhæftninger.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Diff-funktion (`svarbrev_diff.py`)

**Files:**
- Create: `svarbrev_diff.py`

- [ ] **Step 1: Opret `svarbrev_diff.py`**

```python
"""
Diff-beregning for svarbrevs-revisioner.

Sammenligner to versioner af et svarbrev på afsnits-niveau og markerer
hvert afsnit i den nye version som 'uændret', 'ny' eller 'ændret'.
Bruges til UI-rendering der highlight'er ændringer for juristen.

Afsnits-niveau er bevidst valgt over ord/karakter-niveau:
  • Juridisk arbejdsgang fokuserer på 'er det her afsnit ændret?', ikke
    på enkeltord-forskelle.
  • Markdown-rendering pr. afsnit bevares uden at ord-niveau-diff
    spammer hver sætning med spans.
"""

from difflib import SequenceMatcher


def afsnits_diff(gammel: str, ny: str) -> list[dict]:
    """
    Sammenligner to svarbrevs-versioner og returnerer afsnit-listen
    fra den NYE version, hver markeret med status.

    Args:
        gammel: tekst-versionen af det FORRIGE udkast (eller "" / None
                hvis intet forrige udkast findes).
        ny: tekst-versionen af det NYESTE udkast.

    Returns:
        Liste af dicts på formen:
          [{"tekst": str, "status": "uændret" | "ny" | "ændret"}, ...]

        Hvis gammel er tom: alle afsnit markeres som "ny".
        Hvis ny er tom: returnerer tom liste.
    """
    if not ny or not ny.strip():
        return []

    ny_afsnit = _split_afsnit(ny)

    if not gammel or not gammel.strip():
        return [{"tekst": a, "status": "ny"} for a in ny_afsnit]

    gammel_afsnit = _split_afsnit(gammel)

    # For hvert nyt afsnit, find det bedste match i gammel
    resultat = []
    for nyt in ny_afsnit:
        bedste_score = 0.0
        for gam in gammel_afsnit:
            score = SequenceMatcher(None, gam, nyt).ratio()
            if score > bedste_score:
                bedste_score = score

        if bedste_score >= 0.95:
            status = "uændret"
        elif bedste_score >= 0.7:
            status = "ændret"
        else:
            status = "ny"

        resultat.append({"tekst": nyt, "status": status})

    return resultat


def _split_afsnit(tekst: str) -> list[str]:
    """
    Splitter tekst i afsnit på dobbelte newlines. Trimmer whitespace
    pr. afsnit og dropper helt-tomme afsnit.
    """
    raa = (tekst or "").split("\n\n")
    return [a.strip() for a in raa if a and a.strip()]
```

- [ ] **Step 2: Smoke-test funktionen**

```bash
cd /Users/mikkelhansen/Desktop/Projekter/juridisk_assistent
python3 -c "
from svarbrev_diff import afsnits_diff

# Case 1: identiske
result = afsnits_diff('A\n\nB', 'A\n\nB')
print('Case 1 (identisk):', [r['status'] for r in result])
assert all(r['status'] == 'uændret' for r in result), 'forventede alle uændret'

# Case 2: nyt afsnit tilføjet
result = afsnits_diff('A\n\nB', 'A\n\nB\n\nC')
print('Case 2 (tilfoejet):', [r['status'] for r in result])
assert result[0]['status'] == 'uændret'
assert result[1]['status'] == 'uændret'
assert result[2]['status'] == 'ny', f'forventede ny, fik {result[2][\"status\"]}'

# Case 3: afsnit ændret væsentligt
result = afsnits_diff(
    'Dette er det første afsnit.',
    'Dette er det første afsnit, men nu med en helt ny sætning der ændrer betydningen.',
)
print('Case 3 (aendret):', [r['status'] for r in result])
assert result[0]['status'] == 'ændret', f'forventede aendret, fik {result[0][\"status\"]}'

# Case 4: tom gammel
result = afsnits_diff('', 'A\n\nB')
print('Case 4 (tom gammel):', [r['status'] for r in result])
assert all(r['status'] == 'ny' for r in result)

# Case 5: tom ny
result = afsnits_diff('A\n\nB', '')
print('Case 5 (tom ny):', result)
assert result == []

print('Alle cases OK')
"
```

Forventet: alle assertions passerer og "Alle cases OK" printes. Hvis ikke: justér tærsklerne (0.95 / 0.7) eller fix logikken.

- [ ] **Step 3: Commit**

```bash
git add svarbrev_diff.py
git commit -m "feat(svarbrev): tilføj svarbrev_diff.afsnits_diff

Pure Python-modul der sammenligner to svarbrevs-versioner på afsnits-
niveau og markerer hvert afsnit som uændret/ny/ændret. Bruger
difflib.SequenceMatcher med tærsklerne 0.95 (uændret) og 0.7 (ændret).

Forberedelse til diff-visning i UI ved revisioner.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: State-håndtering — gem forrige_svarbrev + udkast_nr

**Files:**
- Modify: `forside.py` — svarbrev-genereringsblok (ca. linje 4396-4414) + "Gem sagen"-state-dict (ca. linje 4607)
- Modify: `gemte_sager.py` — defensiv load af nye felter

- [ ] **Step 1: Opdater state ved svarbrev-generering**

I `forside.py` find blokken hvor `st.session_state.seneste_svarbrev` sættes efter en succesfuld svarbrev-generering (ca. linje 4396-4401):

```python
            st.session_state.seneste_svarbrev = {
                "klage_filnavn": klage_fn,
                "ekstra_instrukser": ekstra_instrukser,
                "svarbrev": svarbrev,
            }
```

Erstat med:

```python
            # Gem forrige udkast hvis det findes — bruges til diff-
            # visning i UI når brugeren genererer en revideret version.
            _eksisterende = st.session_state.seneste_svarbrev or {}
            _forrige_svarbrev = _eksisterende.get("svarbrev")
            _udkast_nr = (_eksisterende.get("udkast_nr") or 0) + 1

            st.session_state.seneste_svarbrev = {
                "klage_filnavn": klage_fn,
                "ekstra_instrukser": ekstra_instrukser,
                "svarbrev": svarbrev,
                "forrige_svarbrev": _forrige_svarbrev,
                "udkast_nr": _udkast_nr,
            }
```

- [ ] **Step 2: Persistér nye felter i "Gem sagen"-state-dict**

I `forside.py` find `state = { ... "seneste_svarbrev": st.session_state.get("seneste_svarbrev"), ... }` (ca. linje 4607). Den linje er allerede korrekt — `seneste_svarbrev` er en dict, og udvidelsen med nye felter persisteres automatisk fordi vi gemmer hele dict'en.

Verificér at `_persist_aktuel_sag_til_db()`-funktionen ligeledes gemmer hele `seneste_svarbrev`-dict'en (ikke kun udvalgte felter). Søg efter den i `forside.py`:

```bash
grep -n "_persist_aktuel_sag_til_db\|def _persist_aktuel_sag_til_db" /Users/mikkelhansen/Desktop/Projekter/juridisk_assistent/forside.py | head -10
```

Læs funktionen og verificér at `seneste_svarbrev` persisteres som hel dict. Hvis funktionen kun persisterer udvalgte sub-felter, udvid den til at inkludere `forrige_svarbrev` + `udkast_nr`.

- [ ] **Step 3: Defensiv load i `gemte_sager.py`**

I `gemte_sager.py` find load-logikken — dvs. den funktion der gendanner `st.session_state` fra en gemt sag. Søg efter `seneste_svarbrev`:

```bash
grep -n "seneste_svarbrev" /Users/mikkelhansen/Desktop/Projekter/juridisk_assistent/gemte_sager.py
```

Hvis den setter `st.session_state.seneste_svarbrev = saved_dict` direkte, så er det allerede defensivt — manglende felter vil simpelthen ikke være i dict'en.

For ekstra robusthed: når `seneste_svarbrev` loades, fyld defaults ind for de nye felter hvis de mangler. Find load-stedet og tilføj umiddelbart efter:

```python
    # Defensiv: fyld defaults ind for nye felter hvis sagen er gemt
    # før diff-feature blev tilføjet
    sb = st.session_state.get("seneste_svarbrev")
    if sb and isinstance(sb, dict):
        sb.setdefault("forrige_svarbrev", None)
        sb.setdefault("udkast_nr", 1)
```

(Tilpas variabelnavnet `sb` hvis der er en mere passende reference allerede i scope.)

- [ ] **Step 4: Smoke-test i UI**

Genstart Streamlit. Upload testsag, generér svarbrev (det er udkast 1). Verificér via en midlertidig debug-print:

```python
# Tilføj midlertidigt et sted i forside.py efter generering
st.write({
    "udkast_nr": st.session_state.seneste_svarbrev.get("udkast_nr"),
    "har_forrige": st.session_state.seneste_svarbrev.get("forrige_svarbrev") is not None,
})
```

Forventet ved første generering: `udkast_nr: 1, har_forrige: False`.

Tilføj en instruks ("læg særlig vægt på X") og generér igen. Forventet: `udkast_nr: 2, har_forrige: True`.

Gem sagen, ryd den, åbn den igen fra Gemte sager. Forventet: state genoprettes med `udkast_nr: 2` og `forrige_svarbrev` intakt.

Fjern den midlertidige `st.write(...)` igen.

- [ ] **Step 5: Commit**

```bash
git add forside.py gemte_sager.py
git commit -m "feat(svarbrev): gem forrige_svarbrev + udkast_nr i session state

Når brugeren genererer et nyt udkast, flyttes det forrige svarbrev til
'forrige_svarbrev'-feltet og udkast_nr inkrementeres. Persisteres
sammen med resten af sagen og loades defensivt fra arkivet (defaults
hvis felterne mangler — bagudkompatibilitet).

Forberedelse til diff-rendering i UI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Diff UI-rendering

**Files:**
- Modify: `forside.py` — svarbrev-display-blok (ca. linje 4416-4514)

- [ ] **Step 1: Erstat brødtekst-rendering med diff-aware rendering**

I `forside.py` find blokken hvor svarbrevet vises (ca. linje 4513-4514):

```python
        # ---------- BRØDTEKST (selve svarbrevet) ----------
        st.markdown(st.session_state.seneste_svarbrev["svarbrev"])
```

Erstat med:

```python
        # ---------- BRØDTEKST (selve svarbrevet) ----------
        _sb = st.session_state.seneste_svarbrev
        _udkast_nr = _sb.get("udkast_nr", 1)
        _forrige = _sb.get("forrige_svarbrev")

        if _udkast_nr > 1 and _forrige:
            # Diff-visning: highlight ændrede/nye afsnit
            from svarbrev_diff import afsnits_diff
            _diff_resultat = afsnits_diff(_forrige, _sb["svarbrev"])

            # Banner + forklaring øverst
            st.markdown(
                f"""
                <div style="background: #EFF6FF; border-left: 3px solid #3B82F6;
                            padding: 10px 14px; border-radius: 8px;
                            margin: 8px 0 4px 0; font-size: 0.92rem;
                            color: #1E3A8A;">
                    <strong>Udkast nr. {_udkast_nr}</strong> — ændringer
                    siden forrige udkast er fremhævet nedenfor.
                </div>
                <div style="font-size: 0.85rem; color: #6B7280;
                            margin: 0 0 12px 0;">
                    🟢 Nyt afsnit · 🟡 Ændret afsnit
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Render hvert afsnit med passende styling
            for _afsnit in _diff_resultat:
                _tekst = _afsnit["tekst"]
                _status = _afsnit["status"]

                if _status == "ny":
                    st.markdown(
                        f"""
                        <div style="background: #E7F5DD;
                                    border-left: 3px solid #76D672;
                                    padding: 10px 14px; border-radius: 8px;
                                    margin: 8px 0;">
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown(_tekst)
                    st.markdown("</div>", unsafe_allow_html=True)
                elif _status == "ændret":
                    st.markdown(
                        f"""
                        <div style="background: #FFF8DC;
                                    border-left: 3px solid #F0C040;
                                    padding: 10px 14px; border-radius: 8px;
                                    margin: 8px 0;">
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown(_tekst)
                    st.markdown("</div>", unsafe_allow_html=True)
                else:
                    # Uændret — render som standard markdown
                    st.markdown(_tekst)
        else:
            # Første udkast — vis som almindelig markdown
            st.markdown(_sb["svarbrev"])
```

- [ ] **Step 2: Verificér at Word-download IKKE påvirkes**

Find umiddelbart efter brødtekst-blokken: `svarbrev_docx = svarbrev_til_docx(...)` (ca. linje 4516). Bekræft at den stadig kalder med `st.session_state.seneste_svarbrev["svarbrev"]` — dvs. den rene tekst uden highlights. Den skal være uændret efter Task 12. Hvis den allerede ser sådan ud, er der intet at ændre her.

- [ ] **Step 3: Smoke-test i UI**

Genstart Streamlit. Upload testsag, generér svarbrev (udkast 1). Verificér: ingen banner, ingen highlights, brevet vises som almindelig markdown.

Tilføj en instruks ("nævn force majeure-forbeholdet eksplicit") og generér igen. Verificér:
- Blå banner øverst: "Udkast nr. 2 — ændringer siden forrige udkast er fremhævet"
- Caption: "🟢 Nyt afsnit · 🟡 Ændret afsnit"
- Mindst ét afsnit har gul (ændret) eller grøn (ny) baggrund med farvet border-left
- Andre afsnit vises uden highlight

Tryk "Download svarbrev som Word". Åbn .docx-filen og verificér at INGEN highlights fremgår — kun den rene tekst.

- [ ] **Step 4: Commit**

```bash
git add forside.py
git commit -m "feat(svarbrev): vis diff-highlights i UI ved revisioner

Når udkast_nr > 1, sammenlignes nuværende svarbrev mod forrige_svarbrev
via svarbrev_diff.afsnits_diff. Nye afsnit får grøn baggrund, ændrede
afsnit får gul baggrund. Banner + caption forklarer hvad farverne
betyder.

Word-download er uændret — den modtager den rene tekst uden
HTML-styling. Diff-feature lever kun i Streamlit-rendering.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Post-implementation: Final verifikation

- [ ] **Step 1: End-to-end smoke-test af alle 7 ændringer**

Genstart Streamlit. Upload en realistisk testsag (helst en hvor der er klar rejseperiode + flere klagepunkter + tidligere udbetalt kompensation). Kør hele flowet:

1. Førstevurdering — tjek Resumé-pillaren viser "Rejseperiode: X, svarende til N nætter"
2. Tidslinje (hvis problematisk) — tjek chip viser "(N nætter)"
3. Generér svarbrev (udkast 1) — tjek alle 4 dele:
   - Faktum-afsnit har "svarende til N nætter" men IKKE kompensation
   - Ingen "anerkender/beklager"-formuleringer
   - Sproget er tilgængeligt (ingen "henset til" osv.)
   - Slutter med "Samlet vurdering"-afsnit der indeholder forudgående handling + samlet stilling
4. Download Word — tjek bilag-listen står NEDERST i .docx
5. Tilføj instruks, generér udkast 2 — tjek diff-highlights vises i UI, men ikke i ny Word-download

- [ ] **Step 2: Tjek branch-status**

```bash
git log --oneline refactor/rag-fase-1..HEAD
git status
```

Forventet: 12 nye commits, intet uncommitted.

- [ ] **Step 3: Push og lav PR (kun hvis brugeren beder om det)**

Spørg brugeren om de vil have en PR oprettet, eller om de selv vil håndtere merge tilbage til main. Lav INTET destruktivt (force-push, merge, etc.) uden eksplicit accept.

---

## Bilag: Kort referenceliste

| Spec-sektion | Tasks | Filer |
|---|---|---|
| #1 Antal nætter | 1, 2, 3, 4 | ai_engine.py, forside.py |
| #2 + #5 Brevstruktur | 7, 8 | ai_engine.py |
| #3 Neutral tone | 5 | ai_engine.py |
| #4 Simpelt sprog | 6 | ai_engine.py |
| #6 Diff-visning | 10, 11, 12 | svarbrev_diff.py, forside.py, gemte_sager.py |
| #7 Bilag i bunden | 9 | eksport.py, ui.py |
