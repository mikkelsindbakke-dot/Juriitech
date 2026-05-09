# Testing — juriitech PAX

Strategi, kommandoer og hvordan man tilføjer flere tests.

---

## Tre lag, to frameworks

| Lag | Framework | Hvor | Hvad testes |
|---|---|---|---|
| Python (delt business-logic) | **pytest** | `tests/` | Regex-mønstre, ren forretningslogik |
| Next.js TypeScript | **Vitest** + jsdom | `pax-next/tests/` | Lib-funktioner, retry-logik, parsere |
| End-to-end / integration | _ingen pt._ | — | Manuel browser-test indtil videre |

**Hvorfor ikke e2e?** Det kræver kørende FastAPI + Anthropic-credits + ægte test-fixtures. Vi venter til vi har en stabil dev-pipeline. Indtil da: manuel test af kritiske flows.

---

## Kør tests

```bash
# Python
pytest                          # alle tests
pytest tests/test_anonymisering_regex.py  # én fil
pytest -m regex                 # kun regex-tests
pytest -v                       # mere udførligt

# TypeScript (fra pax-next/)
npm test                        # alle tests, én gang
npm run test:watch              # watch-mode
npm run test:ui                 # vitest UI i browseren
```

Begge frameworks rapporterer totaler, fejlede tests, og kører på under 10 sek.

---

## Hvad er dækket

### Python (`tests/` — 69 tests)

- **`test_anonymisering_regex.py`** — CPR/email/telefon-regex i `anonymisering_pdf._patterns_via_regex`. Sikrer at vi IKKE lækker følsomme data til Pakkerejse-Ankenævnet.
- **`test_afvist_detektion.py`** — `ai_engine._check_klagen_afvist`. Sikrer at vi viser "Afvist" i UI'et frem for misvisende "ukendt" når klagen er afvist.
- **`test_fil_rolle.py`** — `processor._gaet_rolle`. Sikrer at høringsbrev detekteres korrekt (ellers virker tjekliste ikke), og at Nævnets vejledninger ikke anonymiseres.
- **`test_beloeb_regex.py`** — `ai_engine._regex_find_beloeb`. Per CLAUDE.md historisk bugged. Tester anonymiserede afgørelses-formuleringer (`[Indklagede] skal betale ... til [Klageren]`) og immunitet mod false positives.

### TypeScript (`pax-next/tests/` — 28 tests)

- **`api-client.test.ts`** — verificerer p-retry-adfærd: retry KUN på 5xx + netværk, INGEN retry på 4xx/schema-fejl. Eksponerer `ApiError` med status + detalje.
- **`text-renderers.test.ts`** — `splitKlagepunkt` (klagepunkt-titel-detektion) og `parseAfgoerelse` (rå afgørelses-tekst → strukturerede AfgBlok[]).

---

## Hvad er IKKE dækket (bevidst)

| Område | Hvorfor skipped | Plan |
|---|---|---|
| FastAPI-endpoints | Kræver real Anthropic-API (dyrt + flaky) | Tilføj med httpx-mock når flow er stabilt |
| PDF-anonymisering (`redact_pdf`) | Kræver fitz/PyMuPDF + ægte PDF-fixtures | Tilføj fixtures fra public Pakkerejse-Ankenævn-afgørelser |
| Supabase-queries | Kræver test-database | Brug Supabase test-project når vi ramper op |
| React-komponenter (rendering) | Lavere ROI end pure logic-tests | Tilføj for kritiske komponenter (UploadForm, AnalyseResultat) ved næste UX-runde |
| E2E user flows | Kræver kørende FastAPI + dev-server | Playwright når Next.js-deploy er klar |

---

## Hvordan tilføjer man flere tests

### Tilføj en Python-test

1. Lav fil: `tests/test_<modul>.py`
2. Importér det du tester:
   ```python
   from ai_engine import min_funktion
   ```
3. Skriv testen:
   ```python
   def test_min_funktion_med_typisk_input():
       # Arrange
       input_tekst = "..."
       # Act
       resultat = min_funktion(input_tekst)
       # Assert
       assert resultat == "forventet"
   ```
4. Marker (valgfrit): `pytestmark = pytest.mark.regex` for at gruppere
5. Kør: `pytest tests/test_<modul>.py -v`

### Tilføj en TypeScript-test

1. Lav fil: `pax-next/tests/<modul>.test.ts` ELLER `src/**/<komponent>.test.tsx`
2. Importér via `@/`-alias:
   ```typescript
   import { minFunktion } from "@/lib/min-modul";
   ```
3. Skriv testen:
   ```typescript
   import { describe, it, expect } from "vitest";

   describe("minFunktion", () => {
     it("returnerer forventet for typisk input", () => {
       expect(minFunktion("input")).toBe("forventet");
     });
   });
   ```
4. Kør: `npm test`

---

## Konventioner

### Hvad skal testes (high-value targets)

1. **Regex-mønstre** — historisk bugkilde, billig at teste
2. **Pure forretningslogik** — afkoblet fra DB/API, hurtige tests
3. **Fejl-håndtering** — retry-logik, fallbacks, edge cases
4. **Datatransformationer** — parser, formatter, mapping-funktioner

### Hvad skal IKKE testes (low-value)

- Trivielle getters/setters
- Eksterne library-kald (vi tester DERES kontrakt, ikke deres impl)
- DOM-rendering hvis logikken er testet separat
- Snapshots der bare reflekterer den seneste kode (giver false confidence)

### Test-format

- **Én ting pr. test.** Hvis testen kræver "and" i navnet, split den.
- **Beskrivende navne på dansk eller engelsk** — vælg én og hold den. Vi bruger blandet pt.
- **AAA-pattern**: Arrange (sæt input op), Act (kald funktionen), Assert (tjek output).
- **Test edge cases**: tom input, None/null, ekstreme værdier, anonymiserede data.
- **Mock eksterne dependencies** — Anthropic, Supabase, fil-systemet, datoer hvis relevant.

---

## Fejl-håndtering i tests

- En **rød test** er en bug, ikke et "fix testen"-problem. Diagnose først, ret koden hvis den er forkert, rette testen hvis den var overforsigtig.
- **Aldrig commit røde tests** uden eksplicit `@pytest.mark.xfail` eller `it.skip()` med kommentar om hvorfor.
- Nye features skal komme med tests **før** commit (TDD i ånden, ikke nødvendigvis bogstavet).

---

## CI integration (TODO)

Når vi sætter CI op (GitHub Actions sandsynligvis):
1. `pytest` kører på Python-changes
2. `npm test` kører på pax-next-changes
3. Begge skal være grønne før merge til main
4. Coverage-rapport (overvej, ikke krav)

Lige nu er CI ikke sat op — tests kører lokalt før commit.
