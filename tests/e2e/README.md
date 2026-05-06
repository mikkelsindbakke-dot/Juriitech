# E2E smoke-test af juriitech PAX

Automatiseret test der driver en headless Chromium-browser via
Playwright og kører gennem hele PAX-flowet step-by-step. Tester:

- Login + auto-restore
- Upload af klage-PDF
- "Scan filer" + loading-cirkel inden for 5s
- Førstevurdering (timeout = 3 min, fanger freezes)
- Sektioner: Klagepunkter, Sandsynligheder, Tidsforhold
- Bilag-checkboxes (catches StreamlitDuplicateElementId-crash)
- Logout

Tester mod **live produktion** — kører i en isoleret Test-tenant så
ingen rigtig kundedata påvirkes.

## Engangs-opsætning

```bash
# 1. Installer dev-deps (kun lokalt — ikke i prod-imaget)
python3 -m pip install -r requirements-dev.txt
python3 -m playwright install chromium

# 2. Hent prod-secrets fra Fly (engangs i din shell)
export DATABASE_URL="$(fly secrets list 2>/dev/null && \
    echo 'kør: fly ssh console -C "printenv DATABASE_URL"')"
export SUPABASE_URL=...
export SUPABASE_ANON_KEY=...
export SUPABASE_SERVICE_KEY=...

# Eller — hurtigt:
# fly ssh console -C "printenv | grep -E 'DATABASE_URL|SUPABASE'"

# 3. Opret Test-tenant + test-bruger (idempotent — kan re-køres)
python3 tests/e2e/setup_test_tenant.py
```

Setup-scriptet skriver `tests/.env.test` med credentials. Filen er
gitignored og har permissions 600.

## Generér fixture-PDF

```bash
python3 tests/e2e/generate_test_klage.py
```

Producerer `tests/e2e/fixtures/test_klage.pdf` — en realistisk fiktiv
klage til Pakkerejse-Ankenævnet. Generes deterministisk hver gang.

## Kør smoke-test

```bash
# Headless (hurtigst, til CI/automatisering)
python3 tests/e2e/run_smoke.py

# Med synligt browser-vindue (til debugging)
python3 tests/e2e/run_smoke.py --headed
```

## Output

Hver kørsel producerer:

- `tests/e2e/screenshots/<timestamp>/` — PNG ved hvert step
- `tests/e2e/reports/<timestamp>.md` — markdown med PASS/WARN/FAIL

Begge mapper er gitignored.

Exit-kode er 0 ved succes, 1 hvis nogen step fejler.

## Hvordan testen ikke påvirker produktion

- Bruger Test-tenant (slug: `test-e2e`) — eksisterende
  tenant-isolation i `database.py` sikrer at data brugeren opretter
  ALDRIG er synlig for TUI/Spies/Apollo-brugere
- Kun READ-operationer mod prod-databasen (læser som test-bruger der
  kun har adgang til Test-tenant)
- Test-brugerens email er `e2e-smoke@juriitech-pax.test` — det
  `.test`-TLD er reserveret af IETF for testing og findes ikke
- Skaber midlertidige sager + svarbreve under test-tenant'en. Ryd
  evt. periodisk via DB-konsol hvis det vokser sig stort.

## Troubleshooting

**`playwright._impl._errors.TimeoutError: Timeout exceeded`**
Streamlit's WebSocket kan være langsom ved første request efter
deploy. Vent 1 minut og kør igen.

**Login fejler med "Forkert email eller adgangskode"**
Test-brugerens password matcher ikke længere det i `.env.test`.
Slet `.env.test` og kør `setup_test_tenant.py` igen.

**`PlaywrightTimeoutError` på "Førstevurdering"**
Anthropic-credits kan være tomme, eller fly-maskinen er overbelastet.
Tjek `fly logs --no-tail | grep -i 'credit\|memory'`.
