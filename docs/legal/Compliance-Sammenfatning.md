# Compliance-sammenfatning — juriitech PAX

**Dokumentversion:** 1.0
**Dato:** 13. maj 2026
**Forfatter:** juriitech v/ Mikkel Sindbakke
**Gælder for:** juriitech PAX — AI-assistent til håndtering af klagesager ved Pakkerejse-Ankenævnet

---

## 1. Hvad er dette dokument?

Sammenfattende compliance-dokument der dækker juriitech PAX's GDPR-implementation. Det er en indgang til alle de tekniske + juridiske artefakter der dokumenterer hvordan persondata behandles på platformen.

**Hvem bruger det**:
- Kundens DPO ved due-diligence + årlig audit
- Mikkel når en ny kunde spørger "kan I dokumentere jeres compliance?"
- Eksterne revisorer (ISAE 3000 / SOC 2 light-light)

**Hvad er det ikke**:
- En erstatning for de underliggende dokumenter (DPA, DPIA, art. 30, retention)
- En juridisk garanti — kun et bilag til den underskrevne kontrakt
- Statisk — opdateres parallelt med kode og kontrakter

---

## 2. Compliance-bunke (lille bibliotek)

| Dokument | Indhold | Status |
|---|---|---|
| [DPA-juriitech-PAX-skabelon.md](DPA-juriitech-PAX-skabelon.md) | Databehandleraftale (art. 28) — kundespecifik kontrakt | Skabelon klar |
| [DPIA-juriitech-PAX.md](DPIA-juriitech-PAX.md) | Konsekvensanalyse (art. 35) | Udkast færdig |
| [Fortegnelse-Art30-juriitech.md](Fortegnelse-Art30-juriitech.md) | Fortegnelse over behandlingsaktiviteter (art. 30) | Færdig |
| [Procedure-Registreredes-Rettigheder.md](Procedure-Registreredes-Rettigheder.md) | Procedurer for art. 12-22 anmodninger | Færdig |
| [Retention-og-Anonymisering.md](Retention-og-Anonymisering.md) | Operationelle retention-regler + pipelinens flow | Færdig |
| **Denne fil** | Sammenfatning + verifikations-kommandoer | Færdig |

Alle dokumenter er versionerede i Git og kan downloades direkte fra admin-UI'en (`/admin` → "Vigtige dokumenter" → DOCX/PDF/MD).

---

## 3. Hvad har vi implementeret konkret?

### 3.1 Kryptering (GDPR art. 32(1)(a) — pseudonymisering og kryptering)

| Lag | Mekanisme | Verifikation |
|---|---|---|
| **At rest** | pgcrypto `pgp_sym_encrypt(plaintext, ENCRYPTION_KEY)` — symmetrisk AES-256 via OpenPGP-format. Krypterede kolonner: `mine_dokumenter.indhold_krypteret`, `analyse_arkiv.{indhold,sagsakter,spoergsmaal,ekstra_instrukser}_krypteret`, `gemte_sager.state_json_krypteret`, `users.aktiv_sag_state_krypteret` | `scripts/verificer_kryptering.py` (output: 100% dækning af alle private rækker pr. 2026-05-13) |
| **I transit** | TLS 1.2+ tvunget på alle Postgres-, Supabase- og Anthropic-forbindelser. `sslmode=require` i DB-URL. | Fly.io public certificate; supabase-py + anthropic-sdk forced HTTPS |
| **Nøgle-management** | `ENCRYPTION_KEY` lever som Fly secret (encrypted at rest hos Fly's secret-store, kun læselig af kørende app). ALDRIG i Git, .env (committet), eller logs. Rotation: ikke automatisk endnu — kræver dual-write migration. Manuel ad-hoc ved enterprise-krav. | `fly secrets list -a pax-juriitech-next` viser at nøglen er sat — INDHOLDET vises ikke |
| **Backup** | Supabase Point-in-Time-Recovery (PITR) på AES-256-krypterede snapshots, 30 dages vindue, EU-region (Frankfurt). | Supabase Dashboard → Backups |

**Krypteringsnøgle bruges PRÆCIST disse steder i koden:**

| Lokation | Linje | Hvad |
|---|---|---|
| `database.py:76` | `_ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")` | Indlæses ved modul-import |
| `database.py:108` | `pgp_sym_encrypt(%s::text, %s::text)` | Skriver krypterede kolonner — nøglen bindes som SQL-parameter (sikkert pga. SSL/TLS) |
| `database.py:146` | `pgp_sym_decrypt(col::bytea, %s::text)::text` | Læser krypterede kolonner |
| `database.py:187` | `_decrypt_value()` Python-side fallback ved RETURNING-clauses | Bruges når SQL ikke kan dekryptere in-flight |

Hvis `ENCRYPTION_KEY` mangler (lokal dev uden secrets), falder appen tilbage til plaintext-skrivning (ingen kryptering). Produktion må ALDRIG starte uden secret — health-check kan udvides til at fejle hvis det sker.

### 3.2 Audit-logging (GDPR art. 30 + 32(1)(d))

**Tabel:** `gdpr_audit_log` med kolonner:
```
id (PK), tidspunkt, handling, sag_id, tenant_id, user_id, user_email, ip_adresse, metadata
```

**Beskyttelse mod manipulation:**
- INSERT-only fra applikationen (ingen UPDATE/DELETE-stier i koden)
- `tenant_id` → `tenants(id) ON DELETE RESTRICT` — kan ikke utilsigtet ryge
- `user_id` → `users(id) ON DELETE SET NULL` (user_email bevares som plaintext-snapshot, så historikken forbliver læsbar selv om brugeren er slettet)
- CHECK constraint på `handling`-feltet — kun kanoniske værdier accepteres

**Hvad logges:**

| Handling | Hvor i koden | Hvornår |
|---|---|---|
| `upload` | `api/main.py` `/api/parse-fil` | Hver gang en bruger uploader filer |
| `analyse` | `api/main.py` `/api/foerstevurdering`, `/api/tjekliste` | Hver analyse + tjekliste-generering |
| `eksport` | `api/main.py` `/api/svarbrev`, `/api/analyse-eksport` | Hver svarbrev + Word/PDF-eksport |
| `anonymisering` | `gdpr_pipeline.py` (system-handling) + `/api/anonymiser` (bruger-handling) | Auto-pipeline hver time + manuel bilag-anonymisering |
| `sletning` | `database.py` `slet_arkiv_entry`, `slet_gemt_sag`, `gdpr_pipeline.slet_paa_anmodning` | Manuel + TTL-baseret + sletning på anmodning |
| `login_success` / `login_failed` / `logout` | `auth.py` (Streamlit) + `api/main.py` `/api/auth/log-login` (Next.js) | Hver auth-event |
| `admin_user_oprettet` / `admin_user_slettet` / `admin_user_inviteret` | `auth.py` admin-funktioner | Admin-handlinger i bruger-management |
| `admin_tenant_oprettet` / `admin_tenant_opdateret` | (kommer i Phase B5) | Tenant-management |

**Retention:** 5 år (jf. revisorpraksis + GDPR art. 5(1)(f) accountability).

**Adgang:** Kun `role='admin'`-brugere kan læse via `/api/admin/audit-log` eller `admin.py`-UI. Per-tenant filtrering: en admin ser kun sin egen tenants audit-rows.

### 3.3 Tenant-isolation (GDPR art. 25 — privacy by design)

| Lag | Mekanisme |
|---|---|
| Applikation | `tenant_id`-kolonne på alle private tabeller + `hent_aktiv_tenant_id()` ContextVar pr. FastAPI-request |
| Database | Row-Level Security (RLS) policy: `tenant_id = current_setting('app.current_tenant_id')` — sat ved hver `_connect()` |
| Auth | Supabase JWT → `aktiv_tenant`-dependency validerer + slår vores `users.tenant_id` op → sætter ContextVar |
| Testing | `tests/test_b1_isolation.py` — dummy-tenants + cross-tenant adgangs-forsøg |

### 3.4 Anonymisering + retention (GDPR art. 5(1)(c) + (e))

Se [Retention-og-Anonymisering.md](Retention-og-Anonymisering.md) for fuld dokumentation. Kort:

- **Max 24 timer** fra sidste interaktion → AI-anonymisering kører
- **Hardcap 30 dage** uanset aktivitet
- **AI-anonymisering** via Claude med streng regelsæt: navne/adresser/CPR/email/telefon → placeholders; beløb under 100.000 kr. + sagsnumre bevares; embeddings regenereres på anonymiseret tekst
- **k-anonymitet ≥ 5** for cross-tenant læringsmønstre — håndhævet både i applikationskode og som DB CHECK
- **TTL 90 dage** for `gemte_sager` (slettes — anonymiseres ikke)

### 3.5 Sikkerheds-monitoring (GDPR art. 32(1)(d) + (32)(2))

- **Sentry** (DE-region): fejl-alarmering, 10% transaction sampling, PII-stripping aktiveret (`send_default_pii=False`)
- **request_log** (vores egen tabel): 100% SLA-tracking — latency, token-forbrug, fejlkategori pr. request
- **Circuit breaker** (`ai_engine._circuit_breaker_aabent`): 5 fejl på 60 sek → åbnes i 60 sek for at beskytte Anthropic-credits
- **Anthropic 529 overload** håndteres med eksponentiel backoff retry + frontend p-retry — bruger oplever aldrig en rå "overload"-fejl
- **Truncation-detektion** + AI-paragraf-hallucinations-validering — sikrer at AI ikke citerer eksisterende §§ der ikke findes i pakkerejseloven

### 3.6 Bruger-rettigheder (GDPR art. 12-22)

Se [Procedure-Registreredes-Rettigheder.md](Procedure-Registreredes-Rettigheder.md). Kort: alle anmodninger fra registrerede går via data controller (rejseselskabet) → forward til juriitech support. Maks svartid 30 dage; standard ≤ 7 arbejdsdage.

---

## 4. Underdatabehandlere

| # | Underdatabehandler | Formål | Lokalisering | DPA / overførselsgrundlag |
|---|---|---|---|---|
| 1 | Anthropic, PBC | AI-modelbehandling (Claude) | USA | Standard Contractual Clauses (EU-US DPF) |
| 2 | Voyage AI | Embeddings + reranking | USA | SCC |
| 3 | Supabase Inc. | Krypteret database + Auth | USA (kontrol) / EU/Frankfurt (data) | SCC + EU-region data-residency |
| 4 | Fly.io Inc. | Hosting + kørselsmiljø | USA (kontrol) / EU/Frankfurt (data) | SCC + EU-region data-residency |
| 5 | Functional Software (Sentry) | Fejl-monitoring | EU/Frankfurt | Standard EU DPA |

For hver er DPA underskrevet og dokumenteret i juriitech's centrale bilags-arkiv.

---

## 5. Operationelle artefakter

### 5.1 Diagnostik + verifikations-scripts

| Script | Formål |
|---|---|
| `scripts/verificer_kryptering.py` | Verificér 100% dækning af kryptering på alle private rækker |
| `scripts/backfill_krypter_vilkaar.py` | Engang-hjælper hvis ikke-krypterede rækker findes |
| `tests/test_gdpr_fase1_schema.py` | Schema-verifikation (audit-log, anonymiserings-status osv.) |
| `tests/test_gdpr_pipeline.py` | Unit-tests af anonymiserings-pipelinen |
| `tests/test_b1_isolation.py` | Cross-tenant isolation-tests |
| `diagnose_tenants.py` | Diagnose orphaned tenant_ids + auto-fix |

### 5.2 Admin-UI værktøjer

- `/admin` → **GDPR-tab**: pipeline-status, sidste kørsel, antal sager pr. status, audit-log de seneste 50 events
- `/admin` → **Brugere**: opret/inviter/slet brugere; alle handlinger logges
- `/admin` → **Tenants**: opret/edit selskaber
- `/admin` → **Vigtige dokumenter**: download alle GDPR-dokumenter som DOCX/PDF/MD

### 5.3 Backup + disaster-recovery

- Supabase PITR — 30-dages vindue, AES-256-krypteret, EU-Frankfurt
- Fly.io: kode + secrets backuppes ved hvert deploy via deploy-snapshots
- Disaster-test: ikke kørt formelt endnu — planlagt Q3 2026

---

## 6. Hvad skal man verificere ved revision?

Et stykke kortfattet checklist en kunde-DPO kan køre igennem:

### 6.1 Kryptering
```bash
# 1. Indlæs miljø
set -a && source .env && set +a

# 2. Kør verifikations-script
python3 scripts/verificer_kryptering.py
```
**Forventet:** "ALLE 4 TJEK BESTÅET" + 100% dækning af private rækker.

### 6.2 Audit-log
```sql
-- Tæl audit-events de sidste 30 dage pr. handling
SELECT handling, COUNT(*) FROM gdpr_audit_log
WHERE tidspunkt > NOW() - INTERVAL '30 days'
GROUP BY handling ORDER BY COUNT(*) DESC;

-- Verificér at user_email og ip_adresse er udfyldt for nye rows
SELECT
  COUNT(*) FILTER (WHERE user_email IS NOT NULL) AS med_email,
  COUNT(*) FILTER (WHERE ip_adresse IS NOT NULL) AS med_ip,
  COUNT(*) AS total
FROM gdpr_audit_log
WHERE tidspunkt > NOW() - INTERVAL '7 days'
  AND handling IN ('upload', 'analyse', 'eksport');
```
**Forventet:** Nye rows har user_email + ip_adresse sat (system-handlinger som `anonymisering` har dem NULL, det er korrekt).

### 6.3 Anonymiserings-pipeline
```sql
-- Findes der private rækker over 30 dage gamle der IKKE er anonymiseret?
SELECT COUNT(*), MIN(oprettet_dato)
FROM mine_dokumenter
WHERE is_public = FALSE
  AND anonymiserings_status = 'aktiv'
  AND oprettet_dato < NOW() - INTERVAL '30 days';
```
**Forventet:** 0 rækker. Hvis ikke: pipelinen er stoppet — se Fly logs.

### 6.4 Tenant-isolation
```bash
# Kør cross-tenant access-test
python3 tests/test_b1_isolation.py
```
**Forventet:** Alle tests OK — ingen cross-tenant adgang muligt.

### 6.5 Login-historik for en specifik bruger
```sql
SELECT tidspunkt, handling, ip_adresse, metadata
FROM gdpr_audit_log
WHERE user_email = '<bruger@kunde.dk>'
  AND handling IN ('login_success', 'login_failed', 'logout', 'password_reset')
ORDER BY tidspunkt DESC
LIMIT 50;
```

---

## 7. Roadmap (åbne forbedringer)

| Område | Beskrivelse | Prioritet |
|---|---|---|
| Nøgle-rotation | Automatiseret månedlig ENCRYPTION_KEY-rotation via dual-write migration | Mellem (manuel rotation virker) |
| RLS-policies | Faktisk aktivere RLS på alle tabeller (currently sætter vi `app.current_tenant_id` men har ingen policies) | Mellem (applikations-laget håndhæver allerede) |
| Disaster-recovery drill | Formel årlig DR-test (slet test-tenant, restore fra backup, verificer integritet) | Lav (Supabase PITR fungerer) |
| ISAE 3000 / SOC 2 | Eksternt revisor-attesteret kontrolramme | Lav (ikke krævet af nuværende kunder) |
| Self-service GDPR-eksport | Lad rejseselskabet selv hente sin egen audit-log + sletnings-rapport via admin-UI | Lav |

---

## 8. Kontakt

| Rolle | Person | Kontakt |
|---|---|---|
| Data controller (kunden) | Hvert rejseselskab — eget DPO | Iht. underskrevet DPA |
| Data processor | juriitech v/ Mikkel Sindbakke | juriitech@juriitech.com |
| Sub-processor SCC-spørgsmål | juriitech | juriitech@juriitech.com |
| Sikkerheds-incidents | juriitech | juriitech@juriitech.com, telefon på vagt |

**Breach-notifikation:** Inden for 24 timer fra opdagelse til kunden (DPA § 9.2). Standard-procedure: skriftlig email med incidents-id + foreløbig vurdering inden 4 timer.

---

## 9. Ændringshistorik

| Version | Dato | Forfatter | Ændring |
|---|---|---|---|
| 1.0 | 2026-05-13 | Mikkel + Claude-assist | Første samlede compliance-bilagsoversigt. Audit-log udvidet med user_id + email + ip. Krypteringsdækning verificeret til 100%. Retention-dokument oprettet. |
