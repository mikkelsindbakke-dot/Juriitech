# Sådan håndterer juriitech PAX jeres data

**Til:** Indkøbere, jurister og DPO'er hos potentielle kunder
**Version:** 1.0 · **Dato:** 20. maj 2026
**Kontakt:** [hej@juriitech.com](mailto:hej@juriitech.com)

---

PAX behandler følsomme oplysninger fra klagesager — klagernes navne, rejsedetaljer, mailkorrespondance og betalingsoplysninger. Det er ægte persondata under GDPR. Vi har bygget systemet ud fra ét princip: **data lever så kort som muligt, og kun de helt nødvendige systemer rører ved den.**

Denne ét-sider er det korte svar på "hvordan håndterer I vores data?". Den fulde DPIA og databehandleraftale udleveres ved købsforhandling.

---

## Kryptering

Al klage- og analysedata krypteres med **AES-256** allerede inde i databasen (kolonne-niveau kryptering via PostgreSQL `pgcrypto`). Det betyder at selv hvis nogen får direkte adgang til database-filerne, kan de ikke læse indholdet uden vores krypteringsnøgle — som ligger i en isoleret hemmelig opbevaring og aldrig forlader vores produktionsmiljø.

Mellem jeres browser og PAX kører al trafik over **TLS 1.2+ (HTTPS)**. Den samme kryptering gælder mellem PAX og de underleverandører der modtager data til AI-analyse.

Backups krypteres ligeledes (AES-256) og opbevares i EU-Frankfurt med Point-in-Time Recovery i 30 dage.

---

## Anonymisering

PAX anonymiserer automatisk **24 timer efter** at en sag sidst er blevet brugt (med en hård 30-dages-grænse). Anonymiseringen sker via en AI-pipeline der erstatter:

- Klagers navn → `[Klageren]`
- E-mailadresser, telefonnumre, CPR → fjernes
- Adresser og rejsemål → generaliseres
- Datoer → afrundes til kvartal
- Beløb → afrundes til nærmeste 1.000 kr.
- Sundhedsoplysninger og andre Art. 9-data → erstattes med generisk kategori

Det er ikke en valgfri funktion — det kører automatisk i baggrunden hver time som en del af systemets normale drift. Anonymiseringen logges i et auditspor med tidspunkt, sagsidentifikator og hvilke metoder der blev brugt.

For at lære fra historiske sager uden at lække persondata, bruger PAX **k-anonymitet ≥ 5** før et anonymiseret mønster overhovedet får lov til at indgå i den fælles vidensbank. Det betyder at et mønster først kan deles på tværs af kunder hvis det er bekræftet at mindst 5 andre sager allerede har samme karakteristika — så ingen enkelt sag kan identificeres baglæns.

---

## Sletning og opbevaring

| Datatype | Hvor længe ligger den? | Hvad sker der så? |
|---|---|---|
| Klage-dokumenter (PDF, billeder, tekst) | Maks 30 dage; 24 timer efter sidste brug | Anonymiseres (PII erstattes; metadata bevares til revision) |
| AI-analyser og udkast til svarbreve | Maks 30 dage; 24 timer efter sidste brug | Anonymiseres |
| Manuelt gemte sags-kladder | 90 dage fra sidste åbning | Slettes permanent |
| Aktiv browser-session | Indtil næste sag åbnes (typisk samme arbejdsdag) | Overskrives |
| Audit-log (GDPR-spor) | 5 år | Manuel sletning efter revisor-perioden |

Brugere kan til hver en tid manuelt slette egne sager fra arkivet, hvilket logges i audit-sporet. Den registreredes ret til sletning ("right to be forgotten") håndteres via den kontraktuelle data controller (jer som kunde) og efterleves indenfor de lovpligtige 30 dage (typisk 7 arbejdsdage hos os).

---

## Adgangskontrol og auditspor

Hver kunde er sin egen **isolerede tenant** i systemet. Det betyder at en sagsbehandler hos selskab A bogstaveligt talt ikke kan se en eneste række i databasen tilhørende selskab B — adgangs-filtrering håndhæves på hver eneste database-forespørgsel og er dækket af automatiserede integrationstests.

Alle handlinger logges i et **GDPR-auditspor**: hvem uploadede en sag, hvornår blev den analyseret, hvem eksporterede et svarbrev, hvem slettede den, og hvornår blev den anonymiseret. Audit-loggen er append-only — den kan ikke ændres eller slettes manuelt — og holdes i 5 år til opfyldelse af bogføringsloven og GDPR Art. 30.

Login sker via mail + adgangskode (Supabase Auth, MFA på vej). Admin-funktioner kræver eksplicit `admin`-rolle og logges som forhøjet-risiko-handlinger.

---

## Hvor ligger data, og hvem rører ved den?

Al persondata opbevares på servere i **EU (Frankfurt)**. Selvom få af vores underleverandører er amerikanske virksomheder, er deres EU-datacentre dem vi kører i, og der ligger underskrevet databehandleraftale (DPA) + EU-US Data Privacy Framework (eller Standard Contractual Clauses) for samtlige tre:

| Underleverandør | Rolle | Datalokation | Retsgrundlag |
|---|---|---|---|
| **Anthropic** | AI-analyse (Claude API) | USA (kontrol) | DPA + EU-US Data Privacy Framework |
| **Voyage AI** | Indekserings-embeddings | USA (kontrol) | DPA + Standard Contractual Clauses |
| **Supabase** | Database + autentificering | EU/Frankfurt | DPA + EU-region-residency |

Hosting og fejlmonitorering (Fly.io, Sentry) modtager **ikke** dekrypteret klagedata — kun system-metadata uden persondata-eksponering. Sentry har endvidere et PII-filter der scrubber følsomme felter ud af enhver fejlrapport før de forlader vores processer.

---

## Hvad I som kunde kan forvente

- Underskrevet **databehandleraftale (DPA)** med PAX som data processor og jer som data controller, inklusive sub-processor-liste
- **DPIA** (Data Protection Impact Assessment) udleveret til jeres DPO
- **Fortegnelse efter Art. 30** dokumenteret og opdateret
- **Sletteattest** ved kontraktophør — al jeres data (klagesager, analyser, gemte kladder) slettes indenfor 30 dage; audit-loggen bevares de aftalte 5 år i anonymiseret form
- **Årligt compliance-check** med opdatering af DPIA og dokumentation af eventuelle ændringer i sub-processor-listen
- **Sikkerhedsbrud (Art. 33-34):** I informeres skriftligt senest 24 timer efter at bruddet er konstateret, med foreløbig vurdering af berørte datatyper og personer

Har I spørgsmål til konkrete dele af opsætningen, dokumentationen eller en specifik certificering, så er den hurtigste vej en mail til [hej@juriitech.com](mailto:hej@juriitech.com) — vi sender den fulde dokumentationspakke når en NDA er på plads.
