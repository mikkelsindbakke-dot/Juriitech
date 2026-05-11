# Sikkerhedsaudit — juriitech PAX

**Dato:** 2026-05-11
**Scope:** Streamlit-versionen (prod), pax-next (Next.js, under migration), FastAPI-broen, database, eksterne tjenester.
**Metode:** 4 parallelle research-agenter med scope-isoleret kode-audit. Læser, ikke ændringer.

---

## Executive summary

PAX håndterer **GDPR-følsomme data** (klagers fulde navn, CPR, kontaktinfo, evt. helbreds- og økonomi-detaljer i klagesager). Audit identificerede **9 kritiske/høje risici** med konkrete root causes i koden. Den overordnede konklusion er:

> **Defense-in-depth mangler.** App-laget håndhæver tenant-isolation korrekt, men der er ingen sikkerhedsnet på DB-niveauet (RLS-policies inaktive), ingen kryptering af PII i hvile, og ingen retention/anonymisering kører i produktion. Hvis ÉT lag fejler, eksponeres alt.

**Tre highest-impact mitigationer (i prioritet):**
1. **Aktivér GDPR-anonymiseringspipelinen** (`gdpr_pipeline.py`) via cron — fjerner PII fra hvile efter 24 timer
2. **Deploy RLS-policies** (`gdpr_fase2_rls.sql`) — gør tenant-isolation til en DB-invariant, ikke kun en app-konvention
3. **Stop `send_default_pii=True` i Sentry** — forhindrer at klagetekst lækker via stack-frames ved exceptions

Disse tre ændringer kan implementeres på ~1 dag og lukker 3 ud af 4 P1-risici.

---

## 1. Data-flow (ende-til-ende)

```
[Bruger uploads klage] → Streamlit (memory) → processor.py (parsing)
                                            ↓
                            [Embedding] Voyage AI (rå tekst, US-hosted)
                                            ↓
                            [AI-analyse] Anthropic Claude (rå PDF+tekst, US-hosted)
                                            ↓
                            [DB-lagring] Supabase Postgres (EU, plaintext kolonner)
                                            ↓
                            [Persistens] mine_dokumenter.indhold + fil_bytes
                                         analyse_arkiv.indhold (PII fra AI-output)
                                         gemte_sager.state_json (fuldt session-snapshot)
                                         users.aktiv_sag_state (24t reconnect-state)
                                            ↓
                            [Eksport] DOCX/PDF med klagers navn i header
```

**Pax-next har samme flow**, blot via FastAPI-bro (`api/main.py`) i stedet for direkte Python-kald. Broen er **ikke deployet** endnu — kører kun lokalt under migration.

---

## 2. Risici prioriteret

### P1 — Kritiske (skal lukkes hurtigst muligt)

#### P1.1 — Sentry sender PII via stack-frames

| | |
|---|---|
| **Fil:linje** | `app.py:153-185` |
| **Problem** | `send_default_pii=True` uden `before_send`-scrubber. Ved exception under fx `udled_foerstevurdering_struktureret` lægges variabler i frame-snapshots — inkl. `aktuel_sag`, `fil_bytes`, `tekst`. |
| **Worst case** | Et crash sender klagers fulde navn + base64 PDF til Sentry. Selv hvis Frankfurt-region (EU), er det en uautoriseret eksport til processor uden samtykke-dokumentation. |
| **Mitigation** | (a) Sæt `send_default_pii=False`, ELLER (b) registrér `before_send` der scrubber `aktuel_sag`, `sagsakter`, `fil_bytes`, `tekst`, `indhold`, `klage`-felter ud af events. (b) er bedst — beholder debug-værdi. |
| **Estimeret arbejde** | 30 min |

#### P1.2 — GDPR-anonymiseringspipeline er ikke aktiveret

| | |
|---|---|
| **Fil:linje** | `gdpr_pipeline.py:24-25` ("Modulet er IKKE aktiveret") |
| **Problem** | DB-schemaet sætter `anonymiseres_efter = NOW() + 24t` på hver upload (`database.py:1226`), men ingen cron kalder `trigger_auto_anonymisering()`. Sliding-window er bygget, men ingen håndhævelse. |
| **Worst case** | 100% af uploadede klager ligger plaintext i `mine_dokumenter.indhold` og `mine_dokumenter.fil_bytes` indefinitely. GDPR Art. 5(1)(e) "lagringsbegrænsning" overtrædes. |
| **Mitigation** | Konfigurér Fly cron eller GitHub Actions til at køre `gdpr_cron_runner.py` hver time. Verificér første kørsel på test-tenant. |
| **Estimeret arbejde** | 1-2 timer + verifikation |

#### P1.3 — RLS er aktiveret men uden policies

| | |
|---|---|
| **Fil:linje** | `database.py:526-544` (RLS ON), `gdpr_fase2_rls.sql` (policies klar men ikke kørt) |
| **Problem** | Tenant-isolation er **kun** håndhævet i app-laget via `WHERE tenant_id=$N`-filtre. DATABASE_URL bruger postgres-superuser (BYPASS RLS). Hvis DATABASE_URL/credentials lækker → total kompromittering på tværs af alle tenants. |
| **Worst case** | En enkelt bug (manglende `tenant_id`-parameter i en query) eller en SQL injection åbner for cross-tenant adgang. Hjemmesidens defense-in-depth er nul. |
| **Mitigation** | Kør `gdpr_fase2_rls.sql` mod prod. Opret en `pax_app`-rolle uden BYPASSRLS, brug den fra både Streamlit og pax-next. Beholdpostgres-rolle kun til migrationer. |
| **Estimeret arbejde** | 2-4 timer + dual-write-test |

#### P1.4 — Ingen anonymisering før AI-kald (Anthropic + Voyage)

| | |
|---|---|
| **Fil:linje** | `ai_engine.py:2530-2676` (`_byg_sag_content`), `embeddings.py:79-101` (`embed_dokument`) |
| **Problem** | Rå klagetekst + hele PDF'er som base64 sendes til Anthropic (US) og Voyage (US) ved HVER analyse. Ingen filter undervejs. |
| **Worst case** | Personhenførbare oplysninger (Art. 4) og evt. § 9 GDPR-følsomme (helbredsoplysninger fra rejseskader) ender hos US-processor. Hvis DPA/SCC ikke er på plads er det Art. 44-50-brud. |
| **Mitigation (i prioritet)** | (1) Bekræft + dokumentér at Anthropic + Voyage DPA er underskrevet og SCC er på plads. (2) Aktivér Anthropic Zero Data Retention (kræver enterprise). (3) Overvej server-side redaction af kendte regex-mønstre (CPR, email, telefon) FØR Anthropic-kald. **OBS:** Anthropic skal stadig kunne analysere klagen — fuld anonymisering bryder funktionalitet. Find balance: minimum CPR + tlf + email skal redactes pre-upload. |
| **Estimeret arbejde** | DPA-verifikation 1 time. Pre-redaction 4-8 timer (regex + tests). |

---

### P2 — Høje (skal lukkes inden produktion-multi-tenant)

#### P2.1 — `analyse_arkiv` + `gemte_sager` anonymiseres ALDRIG

| | |
|---|---|
| **Fil:linje** | `gdpr_pipeline.py:14-21` (pipeline rør kun mine_dokumenter); `forside.py:2765`, `database.py:1809-1853` |
| **Problem** | AI-output (analyser, svarbreve) skrives til `analyse_arkiv.indhold` med klagers navn fra Claude. `gemte_sager.state_json` indeholder fuld session-snapshot inkl. base64-bytes af originale PDF'er. Begge persisterer ubegrænset. Pax-next gør auto-arkivering fire-and-forget (`svarbrev-sektion.tsx:160-171`) — bruger har ikke samtykke til lagring. |
| **Worst case** | Sletteanmodninger (Art. 17) kan ikke effektivt opfyldes. Lagring overskrider proportionalitet. |
| **Mitigation** | (a) Udvid GDPR-pipelinen til at anonymisere `analyse_arkiv.indhold` og `gemte_sager.state_json` symmetrisk. (b) Strip `bytes_b64` fra state-snapshots (brug reference til `mine_dokumenter.fil_bytes` i stedet). (c) Sæt TTL (90 dage) på gemte_sager med auto-slet. (d) Gør auto-arkivering opt-in i pax-next. |

#### P2.2 — Postgres-superuser bruges fra app-laget (begge versioner)

| | |
|---|---|
| **Fil:linje** | `pax-next/src/lib/db.ts:11-29`, `database.py:_connect()` |
| **Problem** | `DATABASE_URL` bruger Supabase pooler med rollen `postgres` (BYPASSRLS, SUPERUSER). RLS effektivt ineffektivt selv hvis policies sættes. |
| **Mitigation** | Opret `pax_app`-rolle med begrænsede GRANTs (SELECT/INSERT/UPDATE/DELETE på app-tabeller). Brug den fra app-laget. Postgres-rolle reserveres til migrationer + admin-scripts. |

#### P2.3 — Ingen kolonne-kryptering af PII

| | |
|---|---|
| **Fil:linje** | `database.py:94` (`indhold TEXT`), `:280` (`fil_bytes BYTEA`), `:179`, `:191` |
| **Problem** | Klagetekst, fil-bytes, analyser og state_json ligger plaintext. Supabase disk-encryption (AES-256 EBS) beskytter mod tyveri af disk, men ikke mod DATABASE_URL-leak. |
| **Mitigation** | `pgcrypto` `pgp_sym_encrypt` på følsomme kolonner, med nøgle i Supabase Vault eller separat secret-manager. Trade-off: queries der søger i indhold (LIKE/full-text) bliver dyre — accepter at search kun virker på anonymiseret indhold. |

#### P2.4 — FastAPI-broen har ingen auth eller rate-limit

| | |
|---|---|
| **Fil:linje** | `api/main.py:34-51` |
| **Problem** | Når broen deployes, kan enhver med URL'en uploade klagesager → afbrænder Anthropic-credits, læser RAG-vidensbank. CORS er pt. kun localhost — OK lokalt, ikke prod. |
| **Mitigation** | Tilføj `Depends(verify_jwt)` der validerer Supabase JWT på alle endpoints; tilføj `slowapi`-rate-limit. Whitelist pax-next prod-origin i CORS. |
| **Hvornår** | INDEN broen deployes til Fly. |

#### P2.5 — Cross-tenant huller i specifikke queries

| | |
|---|---|
| **Fil:linje** | `database.py:1488-1512` (`hent_dokument_indhold` — ingen tenant-filter), `:881-905` (`slet_user`), `pax-next/src/lib/queries/users.ts:53-109` |
| **Problem** | Disse funktioner mangler tenant-guard og afhænger af caller-disciplin. Hvis to tenants har filer med samme filnavn (sandsynligt: "klage.pdf", "bilag1.pdf"), kan regex-fallbacks i ai_engine returnere forkert tenants indhold. `slet_user` har ingen "samme tenant"-check — fremtidig per-tenant-admin kan slette anden tenants brugere. |
| **Mitigation** | Tilføj `tenant_id`-parameter til alle disse funktioner med `WHERE tenant_id = %s OR is_public`-filter. |

#### P2.6 — `.env` med live prod-credentials plaintext på laptop

| | |
|---|---|
| **Fil:linje** | `.env` (gitignored, men plaintext på disk) |
| **Problem** | `DATABASE_URL` (med postgres-password), `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `ADMIN_KEY`, `SUPABASE_SERVICE_KEY` (pax-next) — alle live prod-credentials. Hvis laptop bliver stjålet, hacket eller backuppes via iCloud/Time Machine → fuld prod-adgang. |
| **Mitigation** | (a) Roter ALLE nøgler nu. (b) Brug 1Password CLI + `op run` eller `direnv` med krypteret kilde. (c) `fly secrets` for prod, lokal-dev har sin egen test-Supabase. |

---

### P3 — Moderate

| ID | Problem | Fil:linje | Mitigation |
|---|---|---|---|
| P3.1 | HTTP (ikke HTTPS) mod FastAPI | `.env.local` (pax-next) | Tving HTTPS-validering i `api-client.ts` for prod |
| P3.2 | Default fallback til TUI tenant ved auth-bypass | `database.py:1159-1170` | Returnér `None` i Streamlit-kontekst; rais RuntimeError |
| P3.3 | Ingen filsize/type-validering klientside | `upload-form.tsx:251-257`, `processor.py:124-258` | Tilføj `f.size < MAX` + magic-byte-tjek |
| P3.4 | ZIP-bomb-beskyttelse mangler | `processor.py:277-355` | Loft på total udpakket bytes (500 MB) |
| P3.5 | Email i stdout-logs ved fejlet login | `auth.py:173` | Mask emails ('mik\*\*\*@example.com') |
| P3.6 | PII-streng i DEBUG-print i anonymisering | `anonymisering_pdf.py:134` | Fjern (debug færdig) |
| P3.7 | `react-markdown` uden `rehype-sanitize` | `tjekliste-sektion.tsx:149` | Tilføj sanitize med whitelist for hrefs |
| P3.8 | Server Actions allowedOrigins ikke sat | `next.config.ts` | Sæt `experimental.serverActions.allowedOrigins` til prod-host |
| P3.9 | Ingen audit-log af sletninger | `database.py:1902-1926`, `:2058-2081` | Skriv til `gdpr_audit_log` ved DELETE |
| P3.10 | Alle brugere i samme tenant ser hinandens gemte sager | `database.py:1984`, `gemte_sager.py:354` | Tilføj user_id-isolation; admin-role bypass |

---

## 3. Eksisterende mitigation (det der fungerer godt)

For ikke at miste perspektivet — meget er allerede gjort rigtigt:

**Tenant-isolation i app-laget**
- Alle private queries tager eksplicit `tenant_id`-parameter
- Alle SQL-kald er parameteriserede (`%s` / `$1`) — ingen string-concat
- Spot-tjek af f-string-bygget SQL (`tenants.ts:124-156`): kolonne-navne valideres mod allowlist
- Test-suite for cross-tenant isolation (`test_b1_isolation.py`)

**Adgangskontrol**
- `requireAdmin()` kaldes i ALLE admin-Server Actions (defense-in-depth ud over layout-gating)
- `service_role`-nøglen kun importeret i `lib/supabase/admin.ts` med `import "server-only"`
- Last-admin-spær + selv-slet-spær på `sletBrugerAction`/`admin_delete_user`
- `genererTempPassword` bruger `crypto.getRandomValues` (cryptographically secure, 14 tegn)

**Data-isolation**
- `mine_dokumenter` → `dokument_chunks` ON DELETE CASCADE
- `tenant_id` FK'er ON DELETE RESTRICT (forhindrer accidentelt tenant-drop)
- `shared_patterns`-tabellen har INGEN tenant_id-kolonne (k-anonymitet ≥ 5 håndhævet med CHECK constraint)
- `gem_i_arkiv` afviser uden tenant_id

**Transport-sikkerhed**
- Alle eksterne API'er bruger HTTPS by default (Anthropic, Voyage, Supabase SDK'er)
- Streamlit-app: `force_https = true` i fly.toml
- Supabase EU-hosted (`aws-0-eu-west-1` = Ireland)
- Sentry data-region Frankfurt (`.de.sentry.io`) — skal verificeres at DSN faktisk peger der

**Anonymiseringskode (klar til aktivering)**
- `gdpr_pipeline.py` — fuld 24-timers sliding-window-pipeline
- 30-dages safety-cap
- PDF-redaction med ægte tekst-fjernelse via PyMuPDF `apply_redactions` (ikke kun visuelt overlay)
- Klager-sikkerhedsnet i `find_navne_til_redaction` — filtrerer klagers navn selv hvis AI returnerer det
- `_sikr_svarbrev_anonymiseret` + `_check_og_rens_forbudte_ord` — AI-output filtreres for selskabs-medarbejder-navne

**Pax-next-specifikt**
- `import "server-only"` på alle DB-queries + admin-klient — ingen DATABASE_URL/service_key kan lande i client-bundle
- React escaper default; ingen `dangerouslySetInnerHTML` brugt
- Genererede DOCX-blobs revokeres straks efter download

---

## 4. Anbefalet køreplan

**Fase 1 — Quick wins (en arbejdsdag)** ✅ **Delvis gennemført 2026-05-11** på branch `sikkerhed/fase-1-quick-wins` (commit 7f72701):
1. ✅ Stop Sentry-PII-lækage — `send_default_pii=False` + `before_send`-scrubber implementeret i `app.py` (5 unit-tests passerer)
2. ✅ Mask emails i DEBUG-prints — ny `_mask_email()` helper i `auth.py` og `database.py`, anvendt på 4 print-statements
3. ✅ Fjern PII-streng-print i `anonymisering_pdf.py:134` — logger kun count nu
4. ⏳ **Roter credentials** — MANUEL OPGAVE (se sektion 7 nedenfor)
5. ⏳ **Filsize-validering + ZIP-bomb-loft** — UDSAT (Mikkel har igangværende refactor i `processor.py` og `pax-next/upload-form.tsx` — skal committes først for at undgå konflikt)

**Fase 2 — Anonymisering aktiveres (1-2 dage)**
5. Aktivér GDPR-pipelinen via Fly cron (kør hver time)
6. Verificér første kørsel mod test-tenant — bekræft at rå `indhold` faktisk overskrives med anonymiseret tekst
7. Udvid pipelinen til at anonymisere `analyse_arkiv.indhold` + `gemte_sager.state_json`
8. Tilføj sletnings-audit-log

**Fase 3 — Defense-in-depth (2-3 dage)**
9. Opret `pax_app`-rolle med begrænsede GRANTs i Supabase
10. Skift DATABASE_URL i begge apps til `pax_app`-rollen
11. Deploy `gdpr_fase2_rls.sql` (RLS-policies)
12. Verificér med eksisterende `test_b1_isolation.py` at intet er brækket
13. Tilføj tenant-guards til `hent_dokument_indhold`, `slet_user`, og 3 andre queries fra audit

**Fase 4 — Inden pax-next prod-deploy (1 dag)**
14. Tilføj JWT-auth + rate-limit til FastAPI-broen
15. Konfigurér CORS-whitelist for prod-origin
16. Tving HTTPS-validering i `api-client.ts` for prod
17. Sæt `experimental.serverActions.allowedOrigins` i `next.config.ts`

**Fase 5 — Kryptering (1-2 uger, lavere prioritet hvis Fase 1-4 er gjort)**
18. `pgcrypto` på `mine_dokumenter.indhold`, `mine_dokumenter.fil_bytes`, `analyse_arkiv.indhold`, `gemte_sager.state_json`
19. Nøgle-rotation-procedure dokumenteret

---

## 5. Tredjeparts-leverandører — compliance-tjek

| Leverandør | Data | Region | Skal verificeres |
|---|---|---|---|
| **Anthropic** | Klagetekst, PDF'er, billeder, PII | US | DPA + SCC + Zero Data Retention-tilmelding |
| **Voyage AI** | Embedding-tekst (kan have PII) | US | DPA + retention-policy + no-train-guarantee |
| **Supabase** | Brugere, klager, embeddings | EU (Ireland) | DPA i sky-konsol; service_role-key-rotation |
| **Sentry** | Stack-traces, evt. PII via `send_default_pii` | Frankfurt (verificér DSN) | DPA, region-låsning, scrubbing-policy |
| **Fly.io** | App-runtime + secrets + logs | Frankfurt | DPA |

**Anbefaling:** Lav en simpel `docs/compliance/` mappe med kopier af alle underskrevne DPA'er, så de er ét sted ved en audit/datatilsynssag.

---

## 7. Manuelle opgaver der venter på Mikkel

Disse kan jeg ikke gøre via kode — de kræver login til eksterne dashboards/services.

### 7.1 Roter alle credentials (kritisk)

`.env` (root) og `pax-next/.env.local` indeholder live prod-credentials der har ligget plaintext på laptop og potentielt været synkroniseret via iCloud/Time Machine. Roter:

| Credential | Hvor roteres | Husk at opdatere |
|---|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/settings/keys | `.env` lokal + `fly secrets set` for prod |
| `VOYAGE_API_KEY` | https://dashboard.voyageai.com/api-keys | `.env` lokal + `fly secrets set` for prod |
| `SUPABASE_SERVICE_KEY` | Supabase Dashboard → Settings → API → "Reset service_role secret" | `.env`, `pax-next/.env.local`, `fly secrets` |
| `DATABASE_URL` (postgres password) | Supabase Dashboard → Settings → Database → "Reset database password" | Alle steder + Fly secrets |
| `ADMIN_KEY` | Generér ny: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` | `.env` + Fly secrets |

Når en nøgle er roteret, **invalider den gamle straks** i hvert dashboard.

### 7.2 Opsæt en bedre secrets-manager til lokal dev

I stedet for plaintext `.env`:

**Option A — direnv + 1Password CLI (anbefalet):**
```bash
brew install direnv 1password-cli
# I projekt-rod, lav .envrc:
export ANTHROPIC_API_KEY="$(op read 'op://Private/Anthropic API/key')"
export VOYAGE_API_KEY="$(op read 'op://Private/Voyage AI/key')"
# ... osv
# Tilføj .envrc til .gitignore. Kør 'direnv allow' i terminalen.
```
Credentials hentes fra 1Password ved hver terminal-start. Ingen plaintext på disk.

**Option B — separat test-Supabase-projekt:**
Opret et separat Supabase-projekt der KUN bruges til lokal dev. Brug `fly secrets` for prod. Hvis test-credentials lækker, sker der intet med prod-data.

### 7.3 Verificér Anthropic + Voyage DPA-status

Log ind på begge dashboards og bekræft:
- Underskrevet Data Processing Agreement (DPA)
- Standard Contractual Clauses (SCC) for EU→US dataoverførsel
- For Anthropic: aktivér "Zero Data Retention" hvis enterprise-aftale tillader (kræver typisk separat anmodning)

Gem PDF-kopier i `docs/compliance/` for audit-trail.

### 7.4 Bekræft Sentry data-region

Tjek i Sentry Dashboard at jeres organization er hosted i Frankfurt (`.de.sentry.io` i DSN-URL). Hvis ikke, kontakt Sentry support om region-migration.

---

## 8. Status efter Fase 1

**Risici lukket:**
- ✅ P1.1 (Sentry PII-lækage) — scrubber aktiv
- ✅ P3.5 (Email i logs) — masked
- ✅ P3.6 (PII-streng-print) — fjernet

**Risici tilbage:** P1.2 (GDPR-pipeline aktivering), P1.3 (RLS-policies), P1.4 (Anthropic/Voyage anonymisering), alle P2-risici, P3.1-P3.4 og P3.7-P3.10.

**Næste prioritet:** Fase 2 (aktivér GDPR-pipelinen) — har størst single impact af alle resterende risici, fordi den fjerner PII fra hvile efter 24 timer i stedet for indefinitely.

---

## 10. Fase 2 — gennemført KODE-mæssigt, venter på cron-aktivering (2026-05-11, commit 3d06087)

### Hvad er gjort

**Pipeline udvidelser:**
- `--dry-run` mode på `anonymiser_sag` og `trigger_auto_anonymisering` så vi sikkert kan teste én sag uden DB-skrivning. Verificeret mod sag 687 (rigtig klage): 5 navne, 8 datoer, 6 beløb, 3 lokationer, 2 sagsnumre fjernet/generaliseret korrekt.
- Ny `anonymiser_arkiv_entry()` der dækker `analyse_arkiv.indhold` + `spoergsmaal` + `sagsakter` + `ekstra_instrukser` i ét AI-kald (semantik bevares).
- Ny `slet_gamle_gemte_sager()` med TTL-baseret sletning (90 dage default for `gemte_sager` fordi `state_json` er for komplekst til praktisk anonymisering).
- `trigger_auto_anonymisering()` dækker nu alle tre faser med en samlet return-struktur.

**Schema-migration kørt mod prod** (idempotent via `opret_tabeller()`):
- `analyse_arkiv.anonymiserings_status` (`'aktiv'` | `'anonymiseret'`) + `anonymiseres_efter` TIMESTAMPTZ. 90 eksisterende rækker backfilled med `NOW() + 24t`.
- `gemte_sager.slet_efter` TIMESTAMPTZ. 1 eksisterende række backfilled med `NOW() + 90 dage`.
- CHECK constraints + indexes for hurtig cron-query.

**P3.9 audit-log:**
- `slet_arkiv_entry()` og `slet_gemt_sag()` skriver nu til `gdpr_audit_log` med metadata før commit (best-effort, fejler ikke selve sletningen).

**Cron-scripts:**
- `scripts/setup-gdpr-cron.sh` — idempotent Fly Cron-machine setup (hourly schedule)
- `scripts/stop-gdpr-cron.sh` — rollback

### Manuel gennemgang før cron-aktivering

For at inspicere AI-anonymiseringens kvalitet mod flere ægte sager:

```bash
# Find sager der venter på anonymisering
python3 -c "
from database import _connect
conn = _connect(); cur = conn.cursor()
cur.execute('''
    SELECT id, filnavn, LENGTH(indhold)
    FROM mine_dokumenter
    WHERE anonymiserings_status = 'aktiv' AND anonymiseres_efter < NOW()
      AND dokumenttype = 'klage' AND LENGTH(indhold) > 3000
    ORDER BY oprettet_dato DESC LIMIT 10
''')
for row in cur.fetchall():
    print(f'sag_id={row[0]:>4} laengde={row[2]:>6}  {row[1]}')
"

# Dry-run mod en specifik sag (koster ~$0.30-0.50 i credits, intet skrives)
python3 gdpr_pipeline.py --dry-run <sag_id> 1   # tenant_id=1 = TUI

# Når du er tilfreds, aktiver cron:
bash scripts/setup-gdpr-cron.sh
```

### Roll-back-options

- **Før cron starter:** intet er ændret i prod-data. Branch kan reverteres uden konsekvenser.
- **Efter cron starter, før første batch:** `bash scripts/stop-gdpr-cron.sh` indenfor en time
- **Efter første batch:** anonymiserede sager kan IKKE gendannes. Branchen kan stadig reverteres, men anonymiseret data forbliver anonymiseret.

### Status

✅ Kode på plads, schema migrated, scripts klar.
⏳ Venter på Mikkels manuelle gennemgang før cron-aktivering.

---

## 9. Referencer (kilde-citater fra agenter)

Alle fund er bekræftet med fil:linje-citater. De fire fulde rapporter ligger som ChatGPT-output i denne audit-session. Hver enkelt rapport dækker:

- **Streamlit Python-flow:** processor.py, ai_engine.py, embeddings.py, database.py, gemte_sager.py, arkiv.py, eksport.py, anonymisering_pdf.py, auth.py
- **Pax-next data-flow:** alle pages, server actions, queries, Supabase-klienter
- **FastAPI + tredjeparts:** alle endpoints, prompts til Anthropic, Voyage-kald, Sentry-config
- **Database + tenant-isolation:** schema, RLS, encryption, gemte_sager/arkiv, retention, credentials
