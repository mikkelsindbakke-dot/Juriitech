# Anonymisering med sort-bjælke (PDF-redaction) — Design

**Dato:** 2026-05-06
**Status:** Godkendt design
**Forfatter:** Mikkel + Claude (brainstorming-session)

## Mål

Erstat den eksisterende bracket-baserede anonymisering ("[CPR fjernet]", "Maria, [suffix]") med ægte sort-bjælke-redaction der bevarer originalt PDF-layout. Output skal kunne sendes direkte til Pakkerejse-Ankenævnet og ligne professionelt anonymiserede dokumenter (referenceeksempel: `svar fra hotel sag 2026-01994.pdf`).

## Baggrund

Den eksisterende anonymisering parser tekst ud af bilag, bruger AI til at erstatte følsom information med bracket-tags ("[CPR fjernet]"), og rendrer ny Word/PDF i vores eget layout. Det fungerer teknisk men producerer dokumenter der ikke ligner det Nævnet forventer — særligt for email-korrespondancer hvor det originale layout (From:/Sent:/To:/Subject:) signaliserer at der er tale om en email-tråd.

Brugeren har delt et eksempel på korrekt anonymisering hvor PDF-layoutet er bevaret 1:1, og kun følsomme tekst-segmenter er sortmaskeret med sorte rektangler ovenpå originalen.

## Scope

**I scope (første version):**
- PDF'er med tekst-lag — ægte redaction via PyMuPDF
- Detektion af følsomme segmenter via regex (kanoniske mønstre) + Claude AI (navne/adresser)
- Klager-bekræftelses-trin før anonymisering
- Per-fil download + samlet ZIP-download

**Ud af scope (senere udvidelser):**
- Scannede PDF'er (ingen tekst-lag) — får advarsel + bracket-fallback
- DOCX-filer — får eksisterende bracket-fallback
- Billed-uploads — får eksisterende bracket-fallback
- OCR-baseret redaction af scannede dokumenter
- Eval-suite til at måle redaction-kvalitet over tid

## Anonymiserings-regler

| Kategori | Regel | Eksempel |
| --- | --- | --- |
| Klager + medrejsende | Bevares helt | "Wenche Lerang" → "Wenche Lerang" |
| TUI-medarbejdere, hotel-staff, tredjeparter | Fornavn bevares, efternavn(e) sortmaskeres | "Maria Hansen" → "Maria ▇▇▇▇▇▇" |
| Email | Lokaldel sortmaskeres, @ + domæne bevares | "info@hotel.com" → "▇▇▇▇@hotel.com" |
| Telefon | Områdekode bevares, resten sortmaskeres | "928 56 14 14" → "928 ▇▇ ▇▇ ▇▇" |
| CPR | Hele nummeret sortmaskeres | "010199-1234" → "▇▇▇▇▇▇-▇▇▇▇" |
| Adresse | Gade + husnummer sortmaskeres, postnr + by bevares | "Strandvej 14, 2900 Hellerup" → "▇▇▇▇▇▇▇▇▇▇ ▇▇, 2900 Hellerup" |
| Booking-ref, hotelnavn, datoer, beløb, sygdomsbeskrivelser | Bevares helt | — |

## Arkitektur

```
┌─ anonymisering_pdf.py (NY) ────────────────────────┐
│                                                    │
│  Detektor:                                         │
│    udtraek_pdf_tekst(pdf_bytes) → str              │
│    er_pdf_scannet(pdf_bytes) → bool                │
│    find_redaction_targets(tekst, klagere) → list   │
│      ├─ _patterns_via_regex(tekst)                 │
│      │   (CPR, email-lokaldel, tlf-cifre)          │
│      └─ _navne_via_ai(tekst, klagere)              │
│          (returnerer navne + adresser med kategori)│
│                                                    │
│  Redactor:                                         │
│    redact_pdf(pdf_bytes, targets) → bytes          │
│      for hvert target:                             │
│        page.search_for(string) → boxes             │
│        page.add_redact_annot(box)                  │
│      doc.apply_redactions()                        │
│      doc.save() → bytes                            │
│                                                    │
└────────────────────────────────────────────────────┘

┌─ ai_engine.py (UDVIDES) ───────────────────────────┐
│  find_navne_til_redaction(tekst, klagere) →        │
│    {navne: [...], adresser: [...]}                 │
│  (eksisterende _anonymiser_* funktioner uændret)   │
└────────────────────────────────────────────────────┘

┌─ forside.py (UDVIDES) ─────────────────────────────┐
│  Ny anonymiserings-flow:                           │
│    1. Bekræftelses-form for klager + medrejsende   │
│    2. Per-fil routing:                             │
│       - PDF + tekst-lag → ny flow                  │
│       - PDF scannet → advarsel + bracket-fallback  │
│       - DOCX/billede → eksisterende bracket-flow   │
│    3. Resultat-view med per-fil download + ZIP     │
└────────────────────────────────────────────────────┘
```

## Datastrøm pr. PDF

```
pdf_bytes
    ↓
udtraek_pdf_tekst(pdf_bytes) → str
    ↓
parallelt:
    _patterns_via_regex(tekst) → liste af (string, kategori)
    _navne_via_ai(tekst, klagere) → liste af (string, kategori)
    ↓
samlet liste af targets
    ↓
sikkerhedsnet: filtrér alle targets der case-insensitive matcher klagere
    ↓
redact_pdf(pdf_bytes, targets) → ny pdf_bytes
    ↓
gem til download (filename + "_anonymiseret.pdf")
```

## AI tool-use schema

```python
{
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
                        "enum": ["tui_medarbejder", "tredjepart"]
                    },
                    "redact_streng": {
                        "type": "string",
                        "description": "Den præcise streng der skal sortmaskeres — typisk efternavnet"
                    }
                },
                "required": ["fornavn", "efternavn", "kategori", "redact_streng"]
            }
        },
        "adresser": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fuld_adresse": {"type": "string"},
                    "redact_streng": {
                        "type": "string",
                        "description": "Den del af adressen der skal sortmaskeres — gade + husnummer, IKKE postnr/by"
                    }
                },
                "required": ["fuld_adresse", "redact_streng"]
            }
        }
    },
    "required": ["navne", "adresser"]
}
```

System-prompten indeholder:
- Eksplicit liste af klager + medrejsende ("ALDRIG redact disse")
- Reglerne fra tabellen ovenfor
- Konkret eksempel-input/output
- Anti-hallucinations-regel: kun navne der STÅR i teksten, opfind aldrig

## Klager-disambiguation (Model C)

Brugeren ser en bekræftelses-form FØR anonymisering:
- "Klager:" pre-udfyldt fra `sagsmetadata.klagers_navn` (auto-udledt)
- "Medrejsende:" pre-udfyldt hvis tilgængelig, ellers tomt
- Begge felter er redigerbare så brugeren kan tilføje/rette

To-lags beskyttelse mod fejl-redaction af klager:
1. AI'en får klagers navne i system-prompten med eksplicit instruktion om aldrig at returnere dem
2. Efter AI-kald filtrerer vi targets case-insensitive mod klager-navne — sikkerhedsnet hvis AI fejler

## Fejlhåndtering

| Fejl | Detektion | Håndtering |
| --- | --- | --- |
| PDF korrupt/encrypted | PyMuPDF kaster exception | ❌ marker i UI, fortsæt loop, tilbyd bracket-fallback |
| PDF har intet tekst-lag (scannet) | `er_pdf_scannet()` checker selektér-bar tekst | ⚠️ advarsel, brug bracket-fallback |
| AI-kald fejler | Try/except om Claude-kald | 1 retry → ellers regex-only + advarsel "Tjek manuelt før udlevering" |
| AI returnerer tom liste på ikke-tom tekst | Heuristik: tekst > 500 tegn + 0 navne | Vis advarsel, tillad genkør |
| AI inkluderer klager fejlagtigt | Filtrér mod klager_navne før redaction | Stille filtrering, log warning |
| `search_for()` finder ingen boxes | Returnerer tom liste | Log warning, fortsæt |
| `apply_redactions()` fejler | Try/except | ❌ marker, fall back til bracket |
| Klager_navne tomt | Tjek før AI-kald | Hård advarsel, kræver bekræftelse |

### Bruger-kommunikation pr. fil

```
✅  klage_skema.pdf           → klage_skema_anonymiseret.pdf  [Download]
✅  vilkaar.pdf               → vilkaar_anonymiseret.pdf      [Download]
⚠️  hotel_kvittering.pdf       Scannet — bracket-fallback     [Download]
❌  korrupt_bilag.pdf          Kunne ikke åbnes               [Spring over]
```

Plus "Download alle som ZIP".

## Robusthed-principper

Følger eksisterende konventioner i CLAUDE.md:
- **Lazy klient-init** for PyMuPDF
- **Graceful fallback-kæde**: PyMuPDF → bracket-flow → return original
- **Idempotente operationer**: deterministisk output ved gentagne kørsler
- **Per-fil isolation**: én fils fejl stopper ikke loopet

## Test-strategi

Følger projekt-konvention (smoke-tests via `python3 -c "..."` + manuel UI-test):

1. **Regex-tests:** CPR med/uden bindestreg, email-lokaldel, telefon med forskellige områdekoder, dato må IKKE matche som CPR
2. **AI-tests (mock):** Konstrueret tekst med klager + TUI-staff + tredjepart → verificér klager udelades, andre redactes korrekt
3. **Redactor-tests:** Konstrueret PDF → redact kendte targets → verificér output er gyldigt PDF og tekst er fjernet
4. **End-to-end:** Kør pipelinen på brugerens reference-PDF, sammenlign manuelt med forventet output
5. **UI smoke-test:** Upload sag, anonymisér, download, verificér layout og redaction-pattern

## Filstrukturer

**Nye filer:**
- `anonymisering_pdf.py` — kerne-modul (detektor + redactor)

**Modificerede filer:**
- `forside.py` — ny anonymiserings-UI + orchestration
- `ai_engine.py` — tilføj `find_navne_til_redaction()` (ny tool-use schema)
- `requirements.txt` — tilføj `pymupdf`

**Bevares uændret:**
- Eksisterende `_anonymiser_*` funktioner i `ai_engine.py` — bruges som fallback for DOCX/billeder/scannede PDF'er
- `eksport.py` — ingen ændringer

## Bevidste fravalg

- **Vision-baseret detection (Claude vision-API).** Ville håndtere scannede PDF'er, men er dyrere, langsommere, kan hallucinere koordinater. Gemmer til senere udvidelse hvis behov.
- **OCR for scannede PDF'er.** Ud af scope — bracket-fallback dækker indtil videre.
- **DOCX redaction in-place.** Skrøbelig, mange formaterings-edge-cases. Bracket-fallback fortsat.
- **Eval-suite for redaction-kvalitet.** Ud af scope for første version, bør bygges før næste store ændring.
- **Caching af redacted output.** Anonymisering køres typisk én gang pr. sag — caching ville bruge memory uden væsentlig gevinst.

## Succes-kriterier

1. Output-PDF for `svar fra hotel sag 2026-01994.pdf` ligner brugerens referenceeksempel (klager-navn synligt, TUI-staff fornavn synligt + efternavn redacted, email-lokaldel redacted med domæne synligt, tlf med områdekode synlig)
2. Klager-navn redactes ALDRIG (verificeret via two-layer beskyttelse)
3. Original PDF-layout er bevaret 1:1 — samme sider, samme placering, kun tekst er sortmaskeret
4. Anonymisering tager < 30 sekunder pr. PDF (typisk sag har 2-5 PDF'er)
5. Fall-back-paths fungerer (DOCX, scannet PDF, AI-fejl) uden at crashe hele flowet
