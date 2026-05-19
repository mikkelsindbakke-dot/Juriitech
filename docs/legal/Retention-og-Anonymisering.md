# Retention Policy og Anonymiseringsmetode — juriitech PAX

**Dokumentversion:** 1.0
**Dato:** 13. maj 2026
**Gælder for:** juriitech PAX (SaaS-platform til håndtering af klagesager ved Pakkerejse-Ankenævnet)
**Retsgrundlag:** GDPR art. 5(1)(c) (dataminimering), art. 5(1)(e) (opbevaringsbegrænsning), art. 25 (privacy by design)

---

## 1. Formål

Dette dokument beskriver de retention-perioder, anonymiserings-mekanismer og slette-procedurer som juriitech PAX håndhæver automatisk for at opfylde GDPR-kravet om opbevaringsbegrænsning og dataminimering.

Det er det operationelle bilag til DPIA-dokumentet og Fortegnelsen efter art. 30. Det bør deles med kunden (data controller) og kundens DPO som dokumentation for, hvordan persondata håndteres efter behandlingen.

---

## 2. Retention-matrix

| Datakategori | Tabel(ler) | Aktiv periode | Anonymiserings-trigger | Slette-trigger | Backup-rotation |
|---|---|---|---|---|---|
| Klage-dokumenter (PDF/DOCX/billede + udtrukket tekst) | `mine_dokumenter` (private) | Indtil sagen er afsluttet, max 24 timer fra seneste aktive brug | `anonymiseres_efter < NOW()` | Direkte anonymisering — rækken bevares men PII erstattes | Erstattes ved næste backup-rotation (≤ 30 dage) |
| AI-genererede analyser + svarbreve | `analyse_arkiv` | Som ovenfor | Som ovenfor | Som ovenfor | Som ovenfor |
| Manuelt gemt arbejds-tilstand (klade/draft) | `gemte_sager` | 90 dage fra oprettelse / seneste åbning | — (sletning frem for anonymisering) | `slet_efter < NOW()` | Som ovenfor |
| Aktiv sag (browser-session state) | `users.aktiv_sag_state_krypteret` | Indtil ny sag åbnes eller 24 timer | — | Overskrives ved næste sag | Som ovenfor |
| Audit-log (GDPR) | `gdpr_audit_log` | 5 år (revisorkrav + ISAE 3000 / GDPR art. 30) | Aldrig — auditspor må ikke ændres | Manuel sletning efter 5 år | Som ovenfor |
| Request-log (SLA + drift) | `request_log` | 365 dage | — | Manuel sletning efter 365 dage | Som ovenfor |
| Offentlige afgørelser fra Pakkerejse-Ankenævnet | `mine_dokumenter` (public) | Permanent | Aldrig — public data | — | Som ovenfor |
| Anonymiserede mønstre (cross-tenant pulje) | `shared_patterns` | Permanent (ikke personoplysninger) | k-anonymitet ≥ 5 håndhæves ved CHECK-constraint | — | Som ovenfor |

**Maksimalt opbevarings-vindue for PII**: 24 timer fra sidste interaktion, kontraktlig hardcap 30 dage fra første overladelse.

---

## 3. Den automatiske anonymiserings-pipeline

### 3.1 Trigger og kadence

Pipelinen kører som en `APScheduler.BackgroundScheduler` i FastAPI-processen. Standard-kadence: **én kørsel hver time** (`0 * * * *`).

Implementation: `gdpr_pipeline.trigger_auto_anonymisering()` kaldes fra `api/main.py:_koer_gdpr_pipeline()`. Kører `inkluder_arkiv=True` og `inkluder_gemte_sager=True`, så alle tre faser dækkes i samme kørsel.

Maks pr. kørsel: 20 sager pr. tabel (kan justeres via env-variabel). Det begrænser kørselstid + Anthropic-credit-forbrug pr. cyklus og forhindrer at en stor kø blokerer scheduleren.

### 3.2 Hvornår markeres en sag til anonymisering?

Ved upload (`gem_sag_i_db`) sættes to felter:
```sql
anonymiserings_status = 'aktiv'
anonymiseres_efter   = NOW() + INTERVAL '24 hours'
```

`anonymiseres_efter` opdateres ved hver "åben sag igen"-handling, så aktivt arbejde forlænger vinduet. Sager der ikke røres i 24 timer ryger ind i næste pipeline-cyklus.

Hardcap: hvis en sag er over 30 dage gammel (`oprettet_dato < NOW() - 30 days`), tvinges anonymisering uanset om brugeren stadig "rører" den. Det opfylder DPA-clausulen om "max 30 dage fra første overladelse".

### 3.3 Trin i pipelinen pr. sag

For hver sag der opfylder kriterierne:

1. **Hent indhold via SQL (dekrypterer in-flight)**:
   ```sql
   SELECT COALESCE(
     CASE WHEN er_krypteret THEN pgp_sym_decrypt(indhold_krypteret, $KEY)::text END,
     indhold
   ) FROM mine_dokumenter WHERE id = %s AND tenant_id = %s
   ```
   COALESCE-pattern sikrer at både plaintext-rækker (legacy) og krypterede rækker håndteres.

2. **AI-anonymisering** (`_ai_anonymiser_tekst`):
   Anthropic Claude (`claude-sonnet-4-6`) får sagen + et streng anonymiserings-regelsæt og returnerer:
   - `anonymiseret_tekst`: hele dokumentet med PII erstattet
   - `kategori`: kanonisk sagstype (fx "manglende_standard", "flyforsinkelse")
   - `udfald_kategori`: forventet udfald
   - `region`: region eller "ukendt"

   Erstatninger:
   - Navne → `[Klageren]`, `[Klagers ledsager]`, `[Sagsbehandleren]`, `[Fuldmagtshaveren]`
   - Adresser → `[adresse]`
   - Email → `[email]`
   - Telefon → `[telefon]`
   - CPR → `[cpr]`
   - Specifikke beløb → bevares hvis under 100.000 kr. (juridisk relevante); over → `[beløb]`
   - Sagsnumre fra Pakkerejse-Ankenævnet → bevares (offentlig reference)
   - Datoer → bevares men generaliseres til måned hvis specifik dag er identificerende

3. **Skriv anonymiseret tekst tilbage (transaktionelt)**:
   ```sql
   UPDATE mine_dokumenter
     SET indhold = NULL,
         indhold_krypteret = pgp_sym_encrypt($anonym, $KEY),
         er_krypteret = TRUE,
         anonymiserings_status = 'anonymiseret',
         anonymiseret_dato = NOW()
   WHERE id = %s AND tenant_id = %s
   ```
   Plaintext fjernes (sættes til NULL); kun krypteret anonymiseret version forbliver.

4. **Genberegn embedding** på anonymiseret tekst (`embeddings.embed_dokument`).
   Det er kritisk — embeddings indeholder semantisk fingeraftryk og kunne i teorien identificere klagen igen. Ny embedding sikrer at også RAG-/søge-laget kun bygger på anonyme data.

5. **Vurdér k-anonymitet for cross-tenant deling**:
   Hvis (`kategori`, `udfald_kategori`, `region`) allerede har ≥ 4 lignende kandidater på tværs af tenants → tilføj til `shared_patterns` med `k_count = ny værdi`. Ellers gem ikke (læringsmønstre der står alene = re-identification-risiko).

   `shared_patterns` har CHECK `k_count >= 5` på databaseniveau som defense-in-depth.

6. **Audit-log** (`skriv_gdpr_audit`):
   ```
   handling: anonymisering
   sag_id: doc_id
   tenant_id: …
   metadata: {step: 'ai_call_start', indhold_laengde: 12345}
   metadata: {step: 'committed', kategori: 'manglende_standard'}
   ```
   To rækker pr. sag — start + committed — for at give et tidsstempel-spor af handlingens varighed.

7. **Transaktionel kommit** — hvis et trin fejler, rollback'es ALLE ændringer. Sagen forbliver `anonymiserings_status = 'aktiv'` og prøves igen næste cron-cyklus.

### 3.4 Anonymisering af `analyse_arkiv`

Samme principper, men:
- Anonymiseres fire kolonner: `indhold`, `sagsakter`, `spoergsmaal`, `ekstra_instrukser` (alle krypteret-varianter).
- Kører efter `mine_dokumenter` så analysen er anonymiseret før dens kilde-data.

### 3.5 Sletning af `gemte_sager` (TTL)

Manuelt gemt arbejds-tilstand sletes — anonymiseres ikke — fordi state-objektet indeholder base64-encoded filbytes + nested AI-output. For komplekst at meningsfuldt anonymisere.

TTL = 90 dage fra `oprettet_dato`. Brugeren forlænger ved at åbne sagen igen (`slet_efter` opdateres). Manuel sletning fra arkiv-UI = direkte DELETE + audit-row med `handling='sletning'`.

---

## 4. Begrundelse for retention-tider

### 4.1 Hvorfor 24 timer for klage-data

- Pakkerejse-Ankenævnets svarfrist for indklagede er typisk 4 uger. Sagsbehandleren analyserer typisk inden for 1-3 dage og udarbejder svarbrev. Når svarbrevet er sendt, er klage-dokumenterne ikke længere nødvendige i deres oprindelige form.
- 24 timer giver buffer til evt. genåbninger samme dag (fx flere reviews af samme svarbrev) uden at akkumulere.
- Brugeren kan EKSPLICIT gemme sagen som en "gemt sag" hvis den skal beholdes længere (op til 90 dage TTL).

### 4.2 Hvorfor 30 dage hardcap

DPA § 6.3 forpligter juriitech til at slette eller anonymisere personoplysninger "uden ugrundet ophold". 30 dage er den øvre grænse vi har skrevet ind i kontrakten med vores kunder. Ingen sag — uanset om brugeren stadig rører den — overstiger 30 dage uden anonymisering.

### 4.3 Hvorfor 5 år for audit-log

Erhvervsstyrelsens bogføringslov + ISAE 3000-revisor-praksis kræver typisk 5 år. Audit-log kategoriseres som "transaktionsbilag" i den forstand at hver row dokumenterer en behandlings-handling. Kortere tid ville hindre kunder i at gennemføre årlig DPO-audit retrospektivt.

### 4.4 Hvorfor 365 dage for request-log

Tilstrækkeligt til:
- Kvartalsvis SLA-rapport (oppetid, latency-percentiler) overfor enterprise-kunder
- Year-over-year sammenligning af volumen ved kontraktforhandling
- Diagnose af "rare" fejl der kun forekommer få gange om året

`request_log` indeholder INGEN persondata (kun `tenant_id`, endpoint, latency, token-tællere, sanitized error-kategori). Derfor er der ikke nogen GDPR-begrundelse for kortere retention.

---

## 5. Hvad sker der ved manuel sletnings-anmodning fra registreret?

GDPR art. 17 (ret til at blive glemt) håndteres via følgende procedure:

1. Klager kontakter rejseselskabet (data controller).
2. Rejseselskabet sender sletnings-anmodning til juriitech med klagers identifikation (typisk Pakkerejse-Ankenævnet-sagsnummer + navn).
3. Admin i juriitech-staben kører `gdpr_pipeline.slet_paa_anmodning(sag_id, tenant_id, grund)` der:
   - Sletter alle rækker i `mine_dokumenter`, `analyse_arkiv`, `gemte_sager` der matcher sag-id + tenant
   - Sletter relaterede `chunks`
   - Sletter request_log-rækker der refererer det specifikke sagsnummer (forsigtigt — vi bevarer aggregerede metrics)
   - **Bevarer** audit-log-rækker (sletning skal kunne bevises)
   - Skriver en `handling = 'sletning'` audit-row med grund i metadata

4. Bekræftelse sendes til rejseselskabet inden for 30 dage (lovkrav).

Hvis data allerede er anonymiseret (dvs. ikke længere personoplysninger), informeres rejseselskabet om at sletning ikke er nødvendig — anonyme data falder uden for GDPR.

---

## 6. Hvad sker der ved kontrakt-ophør med en kunde?

DPA § 14 (terminering): inden 30 dage efter kontraktens ophør:

1. **Eksport** — kunden modtager alt deres data som anonymiserede DOCX/PDF (samme format som svarbreve) hvis ønsket.
2. **Sletning** — alle rækker hvor `tenant_id = <kunde>` slettes i:
   - `mine_dokumenter` (alle private)
   - `analyse_arkiv`
   - `gemte_sager`
   - `users`
   - `request_log` (anonymiseret aggregat bevares for SLA-statistik på platforms-niveau)
3. **Audit-log bevares** i 5 år men er kun tilgængelig for retslige formål.
4. **`shared_patterns`** røres ikke — anonymiserede k-anonymitet ≥ 5 mønstre er ikke personoplysninger.
5. **Backup-rotation** sikrer at data også fjernes fra Supabase Point-in-Time-Recovery inden for 30 dage.

Bekræftelses-brev sendes til kunden + slet-rapport.

---

## 7. Hvordan verificeres pipelinen virker?

### 7.1 Verifikations-scripts

- `scripts/verificer_kryptering.py` — verificerer at private rækker er krypteret at-rest. Output indeholder dækningsprocent.
- `tests/test_gdpr_pipeline.py` — unit-tests af pipelinens delkomponenter (mock'et Anthropic).
- `gdpr_pipeline.kør_diagnostik(tenant_id)` — admin-tool der lister alle rækker pr. tenant med deres `anonymiserings_status` og hvor længe de har været i hver status.

### 7.2 Admin-UI-dashboard

Admin → GDPR-tab i `admin.py` viser:
- Antal sager pr. status (`aktiv`, `anonymiseret`, `slettet`) pr. tenant
- Sidste pipeline-kørsel + antal sager behandlet
- Audit-log-events for de seneste 50 handlinger med tidspunkt, bruger, IP, handling-type

### 7.3 Pipeline-fejl-håndtering

Hvis pipelinen fejler 5 gange i træk (Anthropic credits, DB-down, scheduler crash):
- Sentry alarmerer (`sentry_sdk.capture_exception` ved hver fejl)
- Scheduler genstarter automatisk ved næste FastAPI-process-start
- Pipeline-tabellen ophobes ikke — næste vellykkede kørsel processerer alle de manglende sager (op til `maks_per_kørsel`)

---

## 8. Verifikations-kommando-liste

Disse kommandoer kan køres ved kunde-revision:

```bash
# 1. Verificér at alle private data er krypteret
ENCRYPTION_KEY=$(fly secrets list -a pax-juriitech-next | grep ENCRYPTION_KEY) \
python3 scripts/verificer_kryptering.py

# 2. Verificér at pipeline er aktiv
fly logs -a pax-juriitech-next --grep "trigger_auto_anonymisering" --no-tail

# 3. Hent audit-log som CSV for revisor
psql $DATABASE_URL -c "\COPY (
  SELECT tidspunkt, user_email, ip_adresse, handling, sag_id, metadata
  FROM gdpr_audit_log
  WHERE tenant_id = <kunde_tenant_id>
  ORDER BY tidspunkt DESC
) TO 'audit-export.csv' CSV HEADER"

# 4. Tæl sager pr. status pr. tenant
psql $DATABASE_URL -c "
  SELECT
    t.navn AS tenant,
    m.anonymiserings_status,
    COUNT(*) AS antal,
    MIN(m.oprettet_dato) AS aeldste,
    MAX(m.oprettet_dato) AS nyeste
  FROM mine_dokumenter m
  JOIN tenants t ON m.tenant_id = t.id
  WHERE m.is_public = FALSE
  GROUP BY t.navn, m.anonymiserings_status
  ORDER BY t.navn, m.anonymiserings_status
"
```

---

## 9. Ændringshistorik

| Version | Dato | Ændring |
|---|---|---|
| 1.0 | 2026-05-13 | Første samlede dokument (sammenfletter retention-regler fra DPIA + Art30-fortegnelse + audit-log-system med user_id/ip-adresse) |
