# Fortegnelse over behandlingsaktiviteter

**Udarbejdet i medfør af GDPR art. 30, stk. 2 (databehandler-fortegnelse)**

---

**Dokumentversion:** 1.0
**Sidst opdateret:** 2026-05-03
**Ansvarlig:** Mikkel Sindbakke, juriitech

---

> **Formål:** Dette dokument er en intern fortegnelse, som juriitech som databehandler er forpligtet til at føre i medfør af GDPR art. 30, stk. 2. Fortegnelsen kan på anmodning fremvises for tilsynsmyndigheden (Datatilsynet) eller for en dataansvarlig (kunde) i forbindelse med audit eller sikkerhedshændelse.
>
> Fortegnelsen opdateres ved hver ændring i behandlingen, herunder når nye dataansvarlige (kunder) onboardes, eller når underdatabehandlere ændres.

---

## 1. Identifikation af databehandler

| Felt | Oplysning |
| ---- | --------- |
| Navn | juriitech v/Mikkel Sindbakke |
| CVR-nr. | [Indsæt CVR] |
| Adresse | [Indsæt adresse] |
| Kontaktperson | Mikkel Sindbakke |
| Kontakt-e-mail | [Indsæt kontakt-e-mail, fx legal@juriitech.com] |
| Telefon | [Indsæt telefon] |
| DPO | Ikke udnævnt — vurderet ikke obligatorisk efter GDPR art. 37 da behandlingen ikke udgør hovedaktivitet i kerneforretning af det omfang, der udløser kravet. Vurdering revideres årligt eller ved skift i behandlingens omfang. |

---

## 2. Dataansvarlige (kunder), på hvis vegne der behandles

Fortegnelsen opdateres pr. tenant, når en ny dataansvarlig onboardes via Hovedaftalen og en underskrevet databehandleraftale (DPA).

| Tenant-slug | Dataansvarlig (kunde) | DPA-status | Onboarding-dato | Kontakt hos kunden |
| ----------- | --------------------- | ---------- | --------------- | ------------------ |
| tui | TUI Danmark A/S | [Underskrevet / Under forhandling / Ikke startet] | [Dato] | [Indsæt kontaktperson] |
| spies | Spies Rejser A/S | [Status] | — | — |
| apollo | Apollo Rejser A/S | [Status] | — | — |

> **Note:** Tenant-slug refererer til den interne identifikator i juriitech PAX. Hver tenant har isoleret datasæt, jf. de tekniske foranstaltninger i Bilag C til DPA'en.

---

## 3. Kategorier af behandling

For hver dataansvarlig udfører juriitech følgende behandlingsaktiviteter på den dataansvarliges vegne:

### 3.1 Modtagelse og opbevaring

- Modtagelse af klagedokumenter (PDF, Word, billeder, scannede filer) overladt af den dataansvarliges autoriserede brugere via Tjenestens webgrænseflade
- Krypteret opbevaring af dokumenter og udledte data i isoleret tenant-segment
- Strukturering og indeksering af dokumentindhold med henblik på efterfølgende behandling

### 3.2 AI-baseret juridisk analyse

- Ekstraktion af nøgledata (sagsnummer, parter, datoer, beløb, klagepunkter)
- Sammenligning med tidligere offentliggjorte afgørelser fra Pakkerejse-Ankenævnet og pakkerejselovgivning
- Generering af juridisk førstevurdering og udkast til svarbrev
- Levering af resultater til den dataansvarliges autoriserede brugere

### 3.3 Automatiseret anonymisering

- Automatisk anonymisering af personoplysninger inden for 24 timer fra seneste aktive brug, dog højst 30 dage fra første overladelse
- Erstatning af direkte og indirekte identifikatorer med generiske placeholders
- Regenerering af afledte data (embeddings, søgeindeks) på baggrund af anonymiseret tekst
- Logning af anonymiserings-handling i intern audit-log

### 3.4 Sletning på anmodning

- Sletning af specifikke sager eller registrerede efter anmodning fra den dataansvarlige
- Sletning omfatter både primær opbevaring, afledte data og logiske referencer
- Backup-data anonymiseres ved næstkommende backup-rotation, senest inden for 90 dage

### 3.5 Genereret afledte anonyme data

- Udledelse af statistiske mønstre og anonymiserede repræsentationer fra behandlingen, jf. DPA punkt 13
- Anonymiseringen er underlagt k-anonymitet (k ≥ 5) håndhævet både i applikations-laget og som CHECK-constraint på databaseniveau
- Afledte anonyme data er ikke længere personoplysninger og deles ikke med tredjeparter ud over de underdatabehandlere, der er nødvendige for behandlingen

---

## 4. Kategorier af registrerede

- Klagere (fysiske personer, der har indgivet klage til Pakkerejse-Ankenævnet)
- Klagers ledsagere (familie, rejsefæller)
- Fuldmagtshavere (advokater, organisationer)
- Tredjeparter nævnt i sagsmaterialet (hotelpersonale, guides, medrejsende)
- Den dataansvarliges egne medarbejdere (sagsbehandlere, brugere af Tjenesten)

---

## 5. Kategorier af personoplysninger

### 5.1 Almindelige personoplysninger (GDPR art. 6)

- Navn, adresse, kontaktoplysninger
- Bestillingsdetaljer og rejseinformation
- Klagens indhold og dokumentation
- Økonomiske oplysninger (refusionskrav, kompensation, prisreduktioner)
- Korrespondance mellem klager og den dataansvarlige

### 5.2 Særlige kategorier af personoplysninger (GDPR art. 9)

Når disse fremgår af sagsmaterialet:

- Helbredsoplysninger (sygdom under rejsen, allergier, handicap)
- Religiøse forhold (kostkrav, religiøst betingede klager)
- Etnisk oprindelse (sjældent forekommende)
- Mindreåriges forhold

### 5.3 Oplysninger om straffedomme og lovovertrædelser (GDPR art. 10)

Når disse fremgår af sagsmaterialet:

- Påstande om svindel, falske oplysninger eller andre strafbare forhold

> **Bemærkning:** Den dataansvarlige er ansvarlig for, at der foreligger lovligt behandlingsgrundlag for art. 9- og art. 10-oplysninger forud for overladelsen til juriitech, jf. DPA pkt. 4.2.

---

## 6. Opbevaringsperioder

| Datakategori | Opbevaringsperiode |
| ------------ | ------------------ |
| Klagedokumenter og personoplysninger i identificerbar form | Maks. 24 timer fra seneste aktive brug, dog højst 30 dage fra første overladelse |
| Anonymiserede sagsdata (uden personoplysninger) | Indtil aftalens ophør eller den dataansvarliges anmodning om sletning |
| Audit-log for GDPR-handlinger | Mindst 12 måneder |
| Backup-data | Maks. 90 dage rotation |
| Logs ved tredjepart (fejlovervågning) | I overensstemmelse med leverandørens standardpolitik |

---

## 7. Underdatabehandlere

juriitech anvender følgende underdatabehandlere ved leveringen af Tjenesten. Listen er identisk med Bilag B i DPA'en og opdateres med 30 dages varsel ved ændringer.

| Nr. | Underdatabehandler | Behandlingens karakter | Selskabsdomicil | Behandlingsregion | Overførselsgrundlag |
| --- | ------------------ | ---------------------- | --------------- | ----------------- | ------------------- |
| 1 | Anthropic, PBC | AI-baseret sprogmodel-behandling | USA | USA | DPF / SCC |
| 2 | Voyage AI, Inc. | Vektor-embedding og semantisk søgning | USA | USA | SCC |
| 3 | Supabase, Inc. | Krypteret databaseopbevaring og brugerautentificering | USA | EU (Irland) | SCC |
| 4 | Fly.io, Inc. | Applikations-hosting og kørselsmiljø | USA | EU (Tyskland) | SCC |
| 5 | Functional Software, Inc. (Sentry) | Fejl- og driftsovervågning | USA | EU (Tyskland) | SCC |

For hver underdatabehandler er der indgået en databehandleraftale (DPA), der pålægger underdatabehandleren databeskyttelsesforpligtelser svarende til dem, der er fastsat i juriitech's DPA med kunden.

---

## 8. Tredjelandsoverførsler

### 8.1 Overførsler omfattet af fortegnelsen

| Tjeneste | Tredjeland | Overførselsgrundlag |
| -------- | ---------- | ------------------- |
| AI-baseret sprogmodel-behandling (Anthropic) | USA | EU-US Data Privacy Framework (Anthropic er DPF-certificeret) eller alternativt EU-Kommissionens standardkontraktbestemmelser (SCC) |
| Vektor-embedding og semantisk søgning (Voyage AI) | USA | SCC suppleret med Transfer Impact Assessment (TIA) |

### 8.2 Supplerende foranstaltninger

For overførsler til USA på grundlag af SCC (uden DPF-dækning) er følgende foranstaltninger truffet:

- Kryptering af data i transit med TLS 1.2 eller højere
- Begrænsning af de overførte oplysninger til hvad der er nødvendigt for behandlingens formål
- Underdatabehandlerne har kontraktuelt forpligtet sig til ikke at anvende de overførte data til AI-modeltræning eller andre formål
- Transfer Impact Assessment (TIA) vurderer, at de supplerende foranstaltninger giver tilstrækkelig beskyttelse i lyset af USAs nuværende retsstilling

### 8.3 Overførsler til EU/EØS

Tjenester leveret af Supabase, Fly.io og Sentry behandler data i EU (henholdsvis Irland og Tyskland). Selve selskaberne har domicil i USA, og overførselsgrundlaget er derfor SCC for at dække eventuel adgang fra USA til EU-baserede driftsmiljøer.

---

## 9. Tekniske og organisatoriske foranstaltninger

En generel beskrivelse af de tekniske og organisatoriske sikkerhedsforanstaltninger, jf. GDPR art. 32, er specificeret i Bilag C til DPA'en. Hovedpunkterne er:

- **Adgangskontrol:** Autentificering med e-mail og adgangskode (min. 8 tegn + bogstav+tal-validering); logisk isolation pr. tenant; multi-faktor autentificering på leverandør-platforme der understøtter dette
- **Kryptering:** TLS 1.2+ in transit, AES-256 at rest, krypterede secret-stores for hemmeligheder
- **Auto-anonymisering:** 24-timers regel + 30-dages cap, embeddings regenereres på anonymiseret tekst
- **Logning:** GDPR-audit-log med tidspunkt, sag-id, tenant-id, beskyttet mod uautoriseret ændring
- **Overvågning:** Automatiseret fejlovervågning med alarmer til monitoreret kontaktpunkt
- **Backup:** Automatiserede backups med point-in-time recovery i EU-region
- **Software-sikkerhed:** Versionsstyret kodeudvikling, automatiseret testning, afhængigheds-opdateringer
- **Personale:** Tavshedspligt, periodisk gennemgang af adgangsrettigheder

---

## 10. Sikkerhedshændelser

| Procedure | Tidsfrist |
| --------- | --------- |
| Underretning af dataansvarlig ved konstateret brud på persondatasikkerheden | Senest 24 timer |
| Logning af alle hændelser uanset alvorlighed | Straks |
| Bistand til dataansvarliges anmeldelse til Datatilsynet | Inden for 72 timer fra konstatering |
| Bistand til dataansvarliges underretning af registrerede | Hurtigst muligt |

Se også separat dokument: **Procedure for de registreredes rettigheder**.

---

## 11. Versionshistorik

| Version | Dato | Ændring |
| ------- | ---- | ------- |
| 1.0 | 2026-05-03 | Første udgave oprettet i forbindelse med GDPR-compliance-gennemgang. |

---

## 12. Næste planlagte revision

Fortegnelsen revideres mindst én gang årligt og ved enhver væsentlig ændring i:

- Behandlingens karakter eller formål
- Kategorier af registrerede eller personoplysninger
- Underdatabehandlere
- Tekniske eller organisatoriske foranstaltninger
- Anvendelig lovgivning eller praksis fra tilsynsmyndighed

**Næste planlagte revision:** 2027-05-03
