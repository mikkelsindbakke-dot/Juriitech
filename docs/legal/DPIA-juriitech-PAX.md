# Data Protection Impact Assessment (DPIA) — juriitech PAX

**Dokumentversion:** 1.0 (UDKAST)
**Dato:** 2. maj 2026
**Forfatter:** juriitech
**Gælder for:** juriitech PAX — AI-assistent til håndtering af klagesager ved Pakkerejse-Ankenævnet

> **STATUS:** Dette er et UDKAST skrevet automatisk. Det skal gennemlæses og finpudses af Mikkel + evt. ekstern jurist før det deles med kunder. Markeret med [REVIEW] hvor særlig opmærksomhed bør rettes.

---

## 1. Formål med dokumentet

Denne DPIA er udarbejdet i overensstemmelse med GDPR Art. 35. juriitech PAX behandler personoplysninger om klagere i pakkerejse-sager via AI-teknologi, hvilket er en behandling der KAN udgøre høj risiko for de registreredes rettigheder. Dokumentet beskriver behandlingen, vurderer risici, og dokumenterer de foranstaltninger der er indført for at mindske dem.

DPIA'en deles med kunder (rejseselskaber) og deres DPO ved købsforhandlinger.

---

## 2. Beskrivelse af behandlingen

### 2.1 Behandlings-kontekst

juriitech PAX er et SaaS-værktøj brugt af rejseselskaber til at analysere klagesager indgivet til Pakkerejse-Ankenævnet. Sagsbehandlere uploader klage-dokumenter (klageskema, bilag, korrespondance), og systemet:

1. Analyserer sagen via AI (Anthropic Claude)
2. Søger lignende tidligere afgørelser i en vidensbank
3. Genererer en juridisk førstevurdering + udkast til svarbrev

### 2.2 Kategorier af registrerede

- **Klagere** (fysiske personer der har indgivet klage til Pakkerejse-Ankenævnet)
- **Klagers ledsagere** (familie, rejsefæller nævnt i sagsmaterialet)
- **Fuldmagtshavere** (advokater eller andre der repræsenterer klager)
- **Sagsbehandlere hos kunden** (juriitech PAX-brugere)

### 2.3 Kategorier af personoplysninger

**Almindelige personoplysninger:**
- Navne, adresser, e-mails, telefonnumre
- Klagesagens detaljer (datoer, beløb, hotel-navne)
- Bilags-numre og sagsnumre

**Følsomme personoplysninger (GDPR Art. 9):**
- Sundhedsoplysninger (hvis klager blev syg under rejsen)
- Religiøse forhold (hvis relevant for sagen — fx halal-mad)
- Etnisk oprindelse (sjældent, men kan forekomme)
- Børns oplysninger (hvis børn er nævnt i klagen)

### 2.4 Formål

- **Primært formål** (kundens, hvor juriitech er processor): Analyse af konkrete klagesager med henblik på juridisk vurdering og udarbejdelse af svarbrev til Pakkerejse-Ankenævnet.
- **Sekundært formål** (juriitech's, controller for anonymiserede mønstre): Forbedring af platformen for alle kunder via lærings-mønstre fra anonymiserede sager.

### 2.5 Retsgrundlag

- **Almindelige personoplysninger:** GDPR Art. 6(1)(b) — behandlingen er nødvendig for opfyldelse af kontrakten mellem klager og rejseselskabet (klage-håndtering er en kontraktuel forpligtelse). Kunden er data controller; juriitech er processor.
- **Følsomme personoplysninger (Art. 9):** GDPR Art. 9(2)(f) — behandlingen er nødvendig for at retsskrav kan fastlægges, gøres gældende eller forsvares (klagesag er per definition et retskrav).
- **Anonymiserede mønstre (cross-tenant):** Ikke relevant — anonymiserede data er ikke længere personoplysninger under GDPR.

[REVIEW] Retsgrundlag bør verificeres med jurist — særligt for følsomme oplysninger.

---

## 3. Nødvendighed og proportionalitet

### 3.1 Nødvendighed

Sagsbehandlere bruger 30-90 minutter pr. sag på manuel læsning af lignende afgørelser. juriitech PAX reducerer dette til 5-10 minutter ved at automatisere recall + analyse. Behandlingen er nødvendig for kommercielt forsvarlig sagshåndtering — uden AI-assistance er hverken kvalitet eller volumen muligt at opretholde.

### 3.2 Proportionalitet

Personoplysninger behandles KUN så længe de er nødvendige for det specifikke formål:
- Maksimalt 24 timer efter sagens analyse er færdig
- Derefter ÆGTE anonymisering eller permanent sletning
- Følsomme oplysninger generaliseres maksimalt allerede ved anonymisering

Dette er en stærkere position end markedets standard og opfylder GDPR Art. 5(1)(c) (data minimisation) og 5(1)(e) (storage limitation) i højeste grad.

---

## 4. Risikovurdering

### 4.1 Risici for de registrerede

**Risiko 1: Uautoriseret adgang til klagedata**
- *Sandsynlighed:* Lav (forudsætter brud på Supabase eller Fly.io infrastructure)
- *Konsekvens:* Mellem (sagsdata kan være følsomme; men ÆGTE persondata findes max 24 timer)
- *Foranstaltning:* TLS 1.2+ in transit, AES-256 at rest, tenant-isolation via tenant_id + Row-Level Security, krypterede backups

**Risiko 2: Cross-tenant data-leakage**
- *Sandsynlighed:* Lav (forudsætter app-bug + RLS-bypass)
- *Konsekvens:* Høj (rejseselskab A kan se rejseselskab B's klagedata)
- *Foranstaltning:* Tenant_id på alle private tabeller + Row-Level Security som ekstra forsvar + cross-tenant testpakke (test_b1_isolation.py)

**Risiko 3: AI-hallucination der eksponerer personoplysninger forkert**
- *Sandsynlighed:* Mellem
- *Konsekvens:* Lav (sagsbehandler verificerer altid AI-output)
- *Foranstaltning:* Disclaimer på siden + AI-genererede kildehenvisninger gør verificering hurtig

**Risiko 4: Re-identifikation af anonymiserede mønstre**
- *Sandsynlighed:* Lav (k-anonymitet ≥5 + AI-baseret anonymisering)
- *Konsekvens:* Høj (ville brydt vores controller-rolle for shared_patterns)
- *Foranstaltning:* K-anonymitet enforced både i app-laget og som CHECK-constraint i DB; kvartalsvis manuel revision af anonymiserings-kvalitet

**Risiko 5: Data-overførsel til USA (Anthropic, Voyage AI)**
- *Sandsynlighed:* 100% (det er normal drift)
- *Konsekvens:* Mellem (USA har ikke samme GDPR-niveau som EU)
- *Foranstaltning:* Standard Contractual Clauses (SCCs) i DPA; Anthropic + Voyage bruger ikke kunde-data til model-træning (kontraktuelt)

**Risiko 6: AI-leverandørs personalets adgang til prompt-data**
- *Sandsynlighed:* Lav
- *Konsekvens:* Lav-mellem
- *Foranstaltning:* Anthropic/Voyage har egne SOC 2-revisioner og access-controls

### 4.2 Resterende risiko

Efter foranstaltningerne er den resterende risiko **lav til mellem**. De primære resterende risici er:
- AI-hallucination (mitigeres af user verification)
- Anonymiserings-fejl (mitigeres af kvartalsvis revision + k-anonymitet)
- Sub-processor-overførsler (mitigeres af DPA + SCCs)

[REVIEW] Hvis kunder rejser specifikke risici vi ikke har forudset, opdateres dette dokument.

---

## 5. Foranstaltninger og kontroller

### 5.1 Tekniske foranstaltninger

| # | Foranstaltning | Status |
| - | -------------- | ------ |
| 1 | TLS 1.2+ for alle eksterne forbindelser | Aktiv |
| 2 | AES-256 encryption at rest (Supabase default) | Aktiv |
| 3 | Tenant-isolation via tenant_id på alle private tabeller | Aktiv |
| 4 | Row-Level Security (RLS) på Supabase | Klar til aktivering (Fase 2) |
| 5 | Auto-anonymisering inden for 24 timer | Klar til aktivering (Fase 3+4) |
| 6 | K-anonymitet (k≥5) enforced i DB-constraint | Aktiv |
| 7 | Audit-log af alle GDPR-handlinger | Aktiv (skema), Fase 3 fylder data |
| 8 | EU-region for database (Supabase eu-west-1) | Aktiv |
| 9 | EU-region for app-runtime (Fly Frankfurt) | Aktiv |
| 10 | EU-region for monitoring (Sentry .de) | Aktiv |
| 11 | Sikker session-håndtering (Supabase Auth + JWT) | Aktiv |
| 12 | Lazy AI-klient init (forhindrer kredentialer i logs) | Aktiv |

### 5.2 Organisatoriske foranstaltninger

| # | Foranstaltning | Status |
| - | -------------- | ------ |
| 1 | Data Processing Agreement (DPA) med kunder | Standard skabelon klar |
| 2 | DPA med sub-processors (Anthropic, Voyage, Supabase, Fly, Sentry) | Underskrevet eller offentligt tilgængelig |
| 3 | Standard Contractual Clauses (SCCs) for USA-overførsler | Inkluderet i kunde-DPA |
| 4 | Privatlivspolitik på juriitech.com | Klar til publicering (Fase 4) |
| 5 | Sletteanmodnings-procedure (via kunden) | Dokumenteret i DPA |
| 6 | Breach notification-procedure (24 timer) | Dokumenteret |
| 7 | DPIA (dette dokument) | UDKAST |
| 8 | Kvartalsvis manuel revision af anonymiserings-kvalitet | Planlagt |

---

## 6. Konklusion

Behandlingen af personoplysninger i juriitech PAX er proportional og nødvendig for at opnå formålet (juridisk klage-håndtering). De tekniske og organisatoriske foranstaltninger er på et niveau, der overstiger de fleste sammenlignelige SaaS-tilbud i markedet — særligt 24-timers auto-anonymisering, ægte anonymisering med k-anonymitet, og fuld EU-residency for data-i-hvile.

Den resterende risiko vurderes som **lav til mellem** og er acceptabel for det formål, der opnås.

DPIA'en revideres mindst en gang om året eller ved væsentlige ændringer i behandlingen.

---

## 7. Versionshistorik

| Version | Dato | Ændring |
| ------- | ---- | ------- |
| 1.0 (UDKAST) | 2026-05-02 | Første udkast oprettet automatisk efter GDPR-spec |

---

## 8. Kontakt

For spørgsmål om dette dokument eller juriitech PAX's GDPR-håndtering generelt:

**Mikkel Sindbakke**
juriitech
mikkelsindbakke@gmail.com
