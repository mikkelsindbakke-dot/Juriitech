# Skalering til nye lande — Køreplan

> **Formål:** Trin-for-trin guide til at lancere PAX i et nyt land
> (fx Sverige, Norge, Tyskland, UK). Designet til at kunne læses
> "kold" om 3-12 måneder uden at huske session-konteksten.

## Vision

**Ét PAX-system. Mange lande. Land er data, ikke kode.**

Vi har bevidst valgt **ÉN kodebase, multi-tenant arkitektur** — samme
tilgang som Pleo, Klarna, Vinted, Wolt. Hver gang vi lancerer i et
nyt land, opretter vi en ny tenant-konfiguration med land=`XX` — vi
forker IKKE kodebasen.

Konsekvensen: når du fixer en bug i Danmark, er den også fixet i
Sverige og Norge automatisk. Når du tilføjer en feature, går den live
alle steder samtidig.

## URL- og routing-strategi

### App'en (efter login): ÉT domæne
```
pax.juriitech.com/login    ← samme login overalt
pax.juriitech.com/         ← UI lokaliseret via tenant.sprog
pax.juriitech.com/arkiv    ← samme rute, lokaliseret indhold
pax.juriitech.com/admin    ← samme admin, lokaliseret
```

Når brugeren logger ind, læser systemet `tenant.land` + `tenant.sprog`
og renderer ALT i deres locale. Bruger oplever det som "min PAX" —
ikke som "PAX-DK" eller "PAX-SE".

### Marketing/landing (før login): land-specifikke domæner
```
pax.juriitech.com  → dansk marketing (default)
pax.juriitech.se   → svensk marketing
pax.juriitech.no   → norsk marketing
pax.juriitech.de   → tysk marketing
```

Hvert lands marketing-side har "Log ind"-knap der sender til
`pax.juriitech.com/login`. Det giver:
- Bedre lokal SEO (Google.se rangerer .se-domæner højere)
- Bedre kundetillid (norsk kunde stoler mere på .no)
- Marketing-team kan have helt forskelligt indhold pr. land
- Men ÉN central app at vedligeholde

### Alternativ: alt på subpaths

Hvis du ikke vil købe domæner:
```
pax.juriitech.com         → dansk landing (default)
pax.juriitech.com/se      → svensk landing
pax.juriitech.com/no      → norsk landing
pax.juriitech.com/login   → fælles login
```

Det fungerer fint som start, og du kan altid migrere til separate
domæner senere uden kodeændringer (bare DNS-config).

---

## Fase 0: Forarbejde (gøres ÉN gang, før første nye land)

Dette er det "infrastruktur-arbejde" der gør alle fremtidige
lande-lanceringer hurtige. Gøres ÉN gang. Skøn: **20-30 timers
udvikling.**

### Trin 0.1: Eksternalisér AI-prompts pr. sprog

**Hvad:** Flyt hardcoded danske prompts ud af `ai_engine.py` og ind i
sprog-specifikke filer.

**Hvor:**

```
prompts/
  da/
    system.md                  ← system-prompt på dansk
    foerstevurdering_user.md   ← user-prompt-indledning
    klagepunkter_system.md
    klagepunkter_user.md
    tidsforhold_system.md
    tidsforhold_user.md
    svarbrev_system.md
    svarbrev_user.md
    anonymisering_system.md
  sv/
    system.md                  ← samme indhold, oversat
    ...
  no/
    ...
```

**Kode-ændring i `ai_engine.py`:**

```python
# Tilføj loader-funktion øverst i ai_engine.py
from pathlib import Path
import functools

_PROMPT_ROOT = Path(__file__).parent / "prompts"

@functools.lru_cache(maxsize=64)
def _hent_prompt(navn: str, sprog: str = "da") -> str:
    """Loader prompt fra fil. Cached så vi kun læser disk én gang
    pr. sprog/prompt-kombination."""
    sti = _PROMPT_ROOT / sprog / f"{navn}.md"
    if not sti.exists():
        # Fallback til dansk hvis sproget ikke har den prompt endnu
        sti = _PROMPT_ROOT / "da" / f"{navn}.md"
    return sti.read_text(encoding="utf-8")

def _hent_aktiv_sprog() -> str:
    """Henter sprog fra aktiv tenant. Falder tilbage til 'da'."""
    from database import hent_aktiv_tenant_id
    from selskab_profiler import hent_aktiv_profil
    profil = hent_aktiv_profil() or {}
    return profil.get("sprog", "da")
```

**Refaktorering:** Find hver hardcoded prompt-streng (de starter
typisk med "Du er en præcis juridisk research-assistent..." osv.) og
erstat med:

```python
indled = _hent_prompt("klagepunkter_user", _hent_aktiv_sprog())
```

**Estimat:** 8-12 timer.

### Trin 0.2: i18n i Next.js-frontend

**Hvad:** Brug `next-intl` til at oversætte alle UI-tekster.

**Installation:**

```bash
cd pax-next
npm install next-intl
```

**Mappestruktur:**

```
pax-next/
  messages/
    da.json
    sv.json
    no.json
  src/
    i18n.ts                    ← konfig
    middleware.ts              ← detect locale fra tenant
```

**Eksempel `messages/da.json`:**

```json
{
  "upload": {
    "title": "Upload sagsakter",
    "submit": "Analysér"
  },
  "analyse": {
    "venter": "Analysen kører — det tager 3-7 minutter.",
    "klagepunkter": "Klagens kernepunkter"
  }
}
```

**`messages/sv.json`** (oversat af svensk modersmål):

```json
{
  "upload": {
    "title": "Ladda upp ärenden",
    "submit": "Analysera"
  },
  ...
}
```

**Komponent-brug:**

```tsx
import { useTranslations } from "next-intl";

export function UploadForm() {
  const t = useTranslations("upload");
  return <button>{t("submit")}</button>;
}
```

**Locale-detection:** Læs `tenant.sprog` ved login, gem i cookie,
brug i middleware til at sætte locale.

**Estimat:** 4-8 timer + tid til at finde alle hardcoded danske strings.

### Trin 0.3: Per-land vidensbank

**Hvad:** Adskil public-dokumenter pr. land i samme database.

**Migration:**

```sql
-- Tilføj land-kolonne til mine_dokumenter
ALTER TABLE mine_dokumenter ADD COLUMN land TEXT;

-- Sæt eksisterende public-dokumenter til DK
UPDATE mine_dokumenter
SET land = 'DK'
WHERE is_public = TRUE AND land IS NULL;

-- Sæt private-dokumenter til ejer-tenant's land
UPDATE mine_dokumenter d
SET land = t.land
FROM tenants t
WHERE d.tenant_id = t.id AND d.land IS NULL;

-- Tilføj index for hurtige filter-queries
CREATE INDEX idx_mine_dokumenter_land ON mine_dokumenter(land)
WHERE is_public = TRUE;
```

**Kode-ændring i `database.py`:**

I `find_relevante_chunks()`, `hent_offentlige_dokumenter()` osv. —
tilføj land-filter:

```python
# Eksisterende WHERE-klausul
WHERE is_public = TRUE AND embedding IS NOT NULL

# Nyt:
WHERE is_public = TRUE AND land = %s AND embedding IS NOT NULL
```

Land-parameteret kommer fra `hent_aktiv_tenant_land()`:

```python
def hent_aktiv_tenant_land() -> str:
    """Returnér aktiv tenant's land. Default 'DK' for fallback."""
    profil = hent_aktiv_profil() or {}
    return profil.get("land", "DK")
```

**Estimat:** 4-6 timer.

### Trin 0.4: Admin-UI til at oprette tenants i nye lande

Admin-siden (`pax-next/src/app/admin/`) har allerede formularer til
tenant-oprettelse. Tilføj dropdowns for `land` + `sprog`:

```tsx
<select name="land">
  <option value="DK">Danmark</option>
  <option value="SE">Sverige</option>
  <option value="NO">Norge</option>
  <option value="DE">Tyskland</option>
</select>

<select name="sprog">
  <option value="da">Dansk</option>
  <option value="sv">Svensk</option>
  <option value="no">Norsk</option>
  <option value="de">Tysk</option>
</select>
```

**Estimat:** 1-2 timer.

---

## Fase 1: Lancér første nye land (Sverige som eksempel)

Når Fase 0 er færdig, er hver lancering hurtig. Skøn for Sverige:
**40-60 timer + oversættelses-arbejde.**

### Forarbejde — research (5-10 timer)

- [ ] Find Sveriges pendant til Pakkerejse-Ankenævnet:
      **Allmänna reklamationsnämnden (ARN)** — `arn.se`
- [ ] Find svensk pakkerejselov: **Paketreselagen (2018:1217)**
- [ ] Identificér 3-5 store svenske rejseselskaber (potentielle
      kunder): Ving, Apollo, TUI Nordic, Solresor, Resia
- [ ] Få adgang til ARN's afgørelses-database (er den offentlig?
      kræver det aftale? skraping vs API?)
- [ ] Hent eksempel-afgørelser (5-10) til at validere AI-output
      manuelt FØR du går live

### Oversættelse + selvvalidering (1-2 dage)

Brug **præcis samme tilgang som du gjorde med dansk PAX**: AI laver
hele oversættelsen, du iterér med fiktive testsager indtil output ser
fornuftigt ud.

**Trin 1: AI laver bulk-oversættelsen (~2 timer + $5)**

Kør hvert prompt-fil gennem Claude med følgende instruks (eksempel):

```
Oversæt nedenstående system-prompt fra dansk til svensk. Bevar
JSON-strukturer, eksempler og {variabel}-pladsholdere uændret.
Brug korrekt svensk juridisk terminologi — fx "rättidig reklamation",
"prisavdrag", "hävning av avtal". Returnér KUN oversættelsen, ingen
forklaring.

[indsæt dansk prompt]
```

**Trin 2: UI-strenge oversættes med AI (1 time + $2)**

Tag `pax-next/messages/da.json` til Claude og bed om svensk version.

**Trin 3: Selvvalidering med fiktive testsager (3-5 dage din tid)**

Det her er præcis det du gjorde med dansk PAX:

1. Lav 5-10 fiktive svenske klagesager (du kan bede AI om at generere
   dem baseret på rigtige Pakkerejse-Ankenævn-sager — bare oversat
   til svensk kontekst)
2. Kør dem gennem den oversatte PAX
3. Læs outputtet — selvom det er på svensk, kan du:
   - Lade Claude oversætte tilbage til dansk og kontrollere mening
   - Spot-tjekke specifikke termer i Google Translate
   - Bede Claude kritisere sit eget output: *"Lyder dette som autentisk
     svensk juridisk sprog eller som oversat dansk? Forklar konkret."*
4. Iterér på prompts indtil outputtet ser fornuftigt ud

**Trin 4: Få den første kunde til at finde resten (gratis)**

Når du har en svensk pilot-kunde, finder DERES juridiske medarbejder
de subtile fejl du ikke kunne se selv — og det er gratis fordi de
bruger produktet alligevel.

**Samlede omkostninger Sverige: ~$20 i AI/Voyage-credits + din tid.**

### Oversættelse af UI (2-4 dage)

- [ ] Få alle strenge i `pax-next/messages/da.json` oversat til
      `pax-next/messages/sv.json`
- [ ] Inkludér også: email-skabeloner i Supabase (invite-emails,
      reset-emails)
- [ ] Inkludér også: error-meddelelser i `api-client.ts`

### Scraping af ARN-afgørelser (1-2 uger)

- [ ] Skriv ny scraper i `scrapers/arn_se.py` (analogt til
      `scraper.py` for Pakkerejse-Ankenævnet)
- [ ] Kør initial-scrape af alle tilgængelige afgørelser
- [ ] Embed alle afgørelser via `backfill_embeddings.py` med
      `land='SE'`-flag
- [ ] Tilføj scraper til cron så nye afgørelser hentes løbende

### Svensk lov (1-2 dage)

- [ ] Scrape `Paketreselagen` paragraffer (analogt til
      `pakkerejselov_scraper.py`)
- [ ] Embed paragraffer med `land='SE'`
- [ ] Få loven valideret af modersmål-konsulent — har vi alle relevante
      paragraffer?

### Opret tenants for SE-kunder

- [ ] Via admin-UI eller direkte i DB:

```sql
INSERT INTO tenants (
  slug, navn, land, sprog,
  klageorgan_navn, klageorgan_url, lov_navn,
  sagsbehandler, by
) VALUES (
  'ving-se', 'Ving AB', 'SE', 'sv',
  'Allmänna reklamationsnämnden',
  'https://www.arn.se',
  'Paketreselagen',
  'Test Jurist (Ving)', 'Stockholm'
);
```

### Test før go-live

- [ ] Opret test-bruger med tenant `land='SE'`, `sprog='sv'`
- [ ] Login → verificér UI vises på svensk
- [ ] Upload en fiktiv svensk klagesag
- [ ] Kør analyse → verificér output er på svensk OG henviser til
      svensk lov + ARN-afgørelser (ikke danske)
- [ ] Generer svarbrev → verificér det er affattet som et svensk
      svarbrev (ikke en dansk-oversættelse)
- [ ] Få modersmål-konsulent til at læse output igennem

### Marketing-side (parallelt, 1-2 uger)

- [ ] Køb domæne `pax.juriitech.se` (eller brug `pax.juriitech.com/se`)
- [ ] Opret landing-page med svensk indhold + "Logga in"-knap der
      peger på `pax.juriitech.com/login`
- [ ] Hvis separat domæne: tilføj som custom domain i Fly (`fly certs
      create pax.juriitech.se`)

### Go-live

- [ ] Soft-launch med 1-2 venlige svenske test-kunder
- [ ] Daglig Sentry-tjek i 2 uger
- [ ] Manuel kvalitets-tjek af de første 10-20 analyser
- [ ] Når kvaliteten er valideret: åbn for flere kunder

---

## Fase 2: Lancér Norge

Skøn: **30-40 timer + 1 uge oversættelse + 1-2 uger scraping.**
Hurtigere end Sverige fordi du har lært fra første lancering + norsk
juridisk tradition ligger meget tæt på dansk.

### Forarbejde — research (3-5 timer)

- [ ] Klageorgan: **Pakkereisenemnda** (`reisenemnda.no`) — privat
      branchefinansieret nævn, parallel til Pakkerejse-Ankenævnet i DK
- [ ] Sekundært klageorgan: **Forbrukerklageutvalget** (`forbrukerradet.no`)
      — statslig instans der dækker bredere forbrugersager. Tjek hvor de
      to overlapper og hvad de hver især offentliggør
- [ ] Lov: **Pakkereiseloven** (LOV-2018-06-15-32) — implementerer
      samme EU-direktiv (2015/2302) som dansk pakkerejselov, så
      strukturen er meget lig
- [ ] Identificér 3-5 store norske rejseselskaber: Ving Norge, Apollo
      Norge, TUI Norge, Solfaktor, Star Tour
- [ ] Få adgang til reisenemnda.no's afgørelses-database — typisk fri
      adgang via deres web-portal (verificér scraping-tilladelser)
- [ ] Vurder bokmål vs nynorsk — næsten alle juridiske dokumenter er på
      bokmål (kode: `nb` eller `no`), men officielle myndighedstekster
      eksisterer på begge. Vi anbefaler bokmål som default.

### Oversættelse + selvvalidering (1 dag)

Samme tilgang som Sverige — AI oversætter, du iterér selv med
fiktive testsager. Norge er endnu hurtigere fordi:

- Sprog-lighed gør AI-oversættelser meget pålidelige
- Du kan genbruge mange Sverige-erfaringer (samme EU-direktiv 2015/2302)
- Bokmål ligger så tæt på dansk at du selv kan spot-tjekke output direkte

**Samlede omkostninger Norge: ~$20 i AI/Voyage-credits + din tid.**

### Scraping af Pakkereisenemndas afgørelser (1-2 uger)

- [ ] Skriv `scrapers/reisenemnda_no.py`
- [ ] Backfill alle tilgængelige afgørelser med `land='NO'`
- [ ] Sæt op løbende cron der henter nye afgørelser månedligt
- [ ] Hent også relevante Forbrukerklageutvalget-afgørelser om
      pakkerejser hvis de er offentlige

### Norsk pakkerejselov (1-2 dage)

- [ ] Scrape `Pakkereiseloven` fra `lovdata.no` (officiel norsk
      lov-portal)
- [ ] Embed paragraffer med `land='NO'`

### Tenants for NO-kunder

```sql
INSERT INTO tenants (
  slug, navn, land, sprog,
  klageorgan_navn, klageorgan_url, lov_navn,
  sagsbehandler, by
) VALUES (
  'ving-no', 'Ving Norge AS', 'NO', 'no',
  'Pakkereisenemnda',
  'https://www.reisenemnda.no',
  'Pakkereiseloven',
  'Test Jurist (Ving NO)', 'Oslo'
);
```

### Norske persondata-mønstre (kritisk)

- [ ] Verificér at anonymiserings-pipeline genkender norsk
      **fødselsnummer** (11 cifre, format DDMMYYXXXXX) — IKKE samme
      mønster som dansk CPR
- [ ] Norske adresser bruger gade-format anderledes: "Gateadresse 12B,
      0150 Oslo" — sørg for at adressedele genkendes som persondata
- [ ] Norske bankkontonumre er 11 cifre i format XXXX.XX.XXXXX

### Test før go-live (1-2 dage)

- [ ] Opret test-tenant `land='NO'`, `sprog='no'`
- [ ] Upload fiktiv norsk klagesag
- [ ] Verificér output er på bokmål (ikke direkte dansk-oversættelse)
- [ ] Verificér henvisninger går til Pakkereiseloven, IKKE den danske
- [ ] Verificér RAG finder norske præcedens-sager (ikke danske)
- [ ] Modersmål-konsulent læser 5 outputs igennem

### Marketing-side (parallelt)

- [ ] Køb `pax.juriitech.no` (eller brug `pax.juriitech.com/no`)
- [ ] Landing page på bokmål
- [ ] DNS + SSL via Fly

---

## Fase 3: Lancér Tyskland

Skøn: **60-90 timer + 2-3 uger oversættelse + 2-3 uger scraping.**
Markant større opgave end SE/NO af tre grunde:

1. **Marked og kompleksitet:** Tyskland er Europas største rejsemarked.
   TUI Groups hovedkvarter ligger i Hannover. DER Touristik er Europas
   næststørste rejsekoncern. Forventninger til juridisk kvalitet er
   meget høje
2. **Sprog-familie:** Tysk er IKKE et nordisk sprog. Juridisk tysk har
   omfattende egne traditioner og terminologi der ikke har direkte
   dansk pendant
3. **Lov-struktur:** Tysk pakkerejselov er paragraffer i den civile
   lovbog (BGB), ikke en separat lov. Det kræver omhyggelig
   reference-håndtering

### Forarbejde — research (8-15 timer)

- [ ] Klageorgan landscape (kompliceret — Tyskland har FLERE):
      - **Universalschlichtungsstelle des Bundes** (Kehl) — generel
        forbruger-arbitrage, dækker også rejser når intet branche-
        nævn er ansvarligt
      - **Söp (Schlichtungsstelle für den öffentlichen Personenverkehr)** —
        primært transport (fly, tog), men også relevant for pakkerejser
        med transport-element
      - **Schlichtungsstelle Reise** (private brancheløsninger) —
        afhænger af selskabets medlemskab af DRV (Deutscher Reiseverband)
- [ ] Verificér med jurist hvilket nævn der reelt afgør tyske
      pakkerejse-klager pr. 2026 — landskabet skifter med branche-
      aftaler
- [ ] Lov: **§§ 651a–651y BGB** (Bürgerliches Gesetzbuch — den tyske
      civillov). Pakkerejse-paragrafferne er tilføjet i 2018 ved
      implementering af EU-direktiv 2015/2302
- [ ] Vigtige supplerende love:
      - **BGB-InfoV** (informationspligt-bekendtgørelsen)
      - **EGBGB Art. 250** (overgangsbestemmelser)
- [ ] Identificér 5-8 store tyske rejseselskaber:
      - **TUI Deutschland** (Hannover — koncernens HQ)
      - **DER Touristik** (Köln — REWE Group)
      - **FTI** (München)
      - **Alltours**
      - **Schauinsland-Reisen**
      - **vtours**
      - **ITS** (Tjæreborg Tyskland)
- [ ] Få adgang til afgørelses-databaser. Tyskland har anderledes
      offentlighedstradition end Skandinavien — mange nævn publicerer
      kun udvalg, andre kræver login eller abonnement
- [ ] Hent 10-15 eksempel-afgørelser manuelt til at validere AI-output

### Oversættelse + selvvalidering (2-3 dage)

Samme tilgang som SE/NO. Tyskland kræver lidt mere omhu på prompt-
niveau pga. specifikke BGB-paragraffer, men metoden er stadig 100%
AI + selvvalidering.

**Trin 1: AI-oversættelse med terminologi-ordbog (~3 timer + $10)**

Tilføj en eksplicit terminologi-instruks så AI'en bruger de rigtige
tyske juridiske termer:

```
Brug følgende tyske juridiske terminologi:
- "Mangel" (klar mangel)
- "unverzügliche Anzeige des Mangels" (§ 651h Abs. 2 BGB) for
  "rettidig reklamation"
- "Minderung des Reisepreises" (§ 651m) for "forholdsmæssigt afslag"
- "Rücktritt" (§ 651l) for "hævelse af aftalen"
- "Schadensersatz" for "erstatning"
- Reference altid paragraffer som "§ 651h Abs. 2 BGB"
```

**Trin 2: Selvvalidering med fiktive sager (5-7 dage din tid)**

Tyskland kræver lidt mere fokuseret selvtest fordi du sandsynligvis
ikke kan tjekke tysk juridisk sprog direkte:

1. Bed AI om at generere 10-15 fiktive tyske klagesager med variation
   (hotel-mangel, transport, booking-fejl, sen reklamation)
2. Kør dem gennem PAX og lad Claude **back-translate hele outputtet
   til dansk** så du kan læse det
3. Bed Claude lave en "tysk advokat-kritik" af outputtet:
   *"Du er tysk Reiserecht-advokat. Kritisér nedenstående tyske
   svarbrev: er sproget autentisk? Er §-referencer korrekte? Hvad
   ville en tysk jurist sige er amatøragtigt?"*
4. Iterér på prompts indtil cross-AI-kritikken er overvejende positiv

**Trin 3: Soft-launch med tysk design-partner-kunde (gratis)**

Når du har en tysk pilot-kunde (fx TUI Deutschland — Hannover er
TUI Group's HQ, det er det naturlige sted at starte), bruger DERES
interne jurister produktet og giver feedback gratis.

**Samlede omkostninger Tyskland: ~$30 i AI/Voyage-credits + din tid.**

### Scraping af afgørelser (2-3 uger)

- [ ] Skriv scrapere for HVER relevant kilde:
      - `scrapers/universalschlichtungsstelle_de.py`
      - `scrapers/soep_de.py`
      - `scrapers/drv_schlichtung_de.py` (hvis tilgængelig)
- [ ] Tjek hver kildes "Robots.txt" og publikations-politik —
      tyske myndigheder håndhæver intellectual property strengt
- [ ] Embed alle afgørelser med `land='DE'`
- [ ] Overvej at supplere med **BGH-afgørelser om Reiserecht** (tysk
      højesterets-præcedens — meget vigtigt i tysk jura). Kilder:
      `juris.de` (kommercielt), `dejure.org` (delvis fri)

### BGB-paragraffer (2-3 dage)

- [ ] Scrape §§ 651a–651y BGB fra `gesetze-im-internet.de`
      (officiel forbundsregerings-lovportal — fri adgang)
- [ ] Inkludér også relevante supplerende paragraffer (§ 651w om
      formidlere, § 651u om transport)
- [ ] Embed med `land='DE'`
- [ ] **Vigtigt:** Tysk paragrafstruktur er HIERARKISK (§ → Abs. →
      Satz → Nr.). Sørg for at AI'en kan referere præcist, fx
      "§ 651k Abs. 1 Satz 2 BGB" — ikke bare "§ 651k"

### Tenants for DE-kunder

```sql
INSERT INTO tenants (
  slug, navn, land, sprog,
  klageorgan_navn, klageorgan_url, lov_navn,
  sagsbehandler, by
) VALUES (
  'tui-de', 'TUI Deutschland GmbH', 'DE', 'de',
  'Universalschlichtungsstelle des Bundes',
  'https://www.universalschlichtungsstelle.de',
  '§§ 651a-y BGB',
  'Test Jurist (TUI DE)', 'Hannover'
);
```

### Tyske persondata-mønstre (kompleks)

- [ ] Tysk **Personalausweis-nummer** (10 tegn alfanumerisk) —
      anderledes mønster end CPR
- [ ] **Steuer-Identifikationsnummer** (11 cifre) — eksisterer for
      hver tysk borger, persondata
- [ ] **IBAN** for tyske bankkonti: starter med `DE` + 20 cifre
- [ ] Adresser er hyppigt: "Beispielstraße 12a, 30159 Hannover" —
      verificér at PLZ (postnummer, 5 cifre) genkendes
- [ ] **Datenschutz er kulturelt vigtigt** — tysk GDPR-fortolkning er
      ofte strengere end dansk. Sørg for at anonymiseringen er
      grundig nok til at en tysk advokat ville godkende det

### Test før go-live (3-5 dage)

- [ ] Opret test-tenant `land='DE'`, `sprog='de'`
- [ ] Upload fiktive tyske klagesager (mindst 3 forskellige typer:
      hotel-mangel, transport-aflysning, booking-fejl)
- [ ] Verificér output er **juridisk korrekt tysk** — ikke ord-for-ord
      oversat dansk
- [ ] Verificér §-henvisninger er præcise (Abs/Satz/Nr-niveau)
- [ ] Verificér RAG finder tyske præcedens-sager
- [ ] **Tysk modersmål-konsulent skal læse 10 outputs igennem og
      give skriftlig godkendelse** før go-live. Tysk marked har
      ekstra lav tolerance for fejl
- [ ] Få også tjekket at **Anbieterkennzeichnung/Impressum** (lovpligtig
      tysk informations-pligt på websider) er korrekt sat op på
      marketing-siden

### Marketing-side (parallelt, 2-3 uger)

- [ ] Køb `pax.juriitech.de` (eller subpath)
- [ ] Landing page på tysk — **IKKE bare oversat dansk**. Tyske
      kunder forventer dyb teknisk forklaring, kvalitetsstempler,
      og kontakt-data på første side
- [ ] **Obligatorisk lovkrav:**
      - `Impressum`-side (firmadetaljer, ansvarlig person, kontakt)
      - `Datenschutzerklärung` (GDPR-erklæring — tysk version)
      - `AGB` (forretningsbetingelser)
- [ ] DNS + SSL + Custom Domain i Fly
- [ ] Tysk Google Search Console + Bing Webmaster Tools

### Go-live (særlig forsigtig — markedet er ufodragende)

- [ ] **Soft-launch med ÉN kunde** (ikke 2-3 som SE/NO). Tysk
      marked spreder rygter hurtigt — én dårlig oplevelse kan koste
- [ ] Daglig Sentry + manuel kvalitets-tjek i 4 uger (ikke 2 som SE/NO)
- [ ] Manuel verificering af alle de første 25-30 analyser, ikke 10-20
- [ ] Tysk modersmål-konsulent på retainer de første 3 måneder til
      ad-hoc kvalitetscheck
- [ ] Først åbn bredt når du har bekræftet kvalitet på 50+ analyser

---

## Andre lande (kortere referencer)

### UK
- Klageorgan: **ABTA** (Association of British Travel Agents) +
  **CMA** (Competition and Markets Authority)
- Lov: **Package Travel and Linked Travel Arrangements Regulations
  2018**
- Sprog: `en` (britisk engelsk)
- Forsigtighed: post-Brexit regulering kan ændre sig — verificér
  status før investering. EU-direktiv 2015/2302 er ikke længere
  automatisk gældende

### Finland
- Klageorgan: **Kuluttajariitalautakunta** (Forbrugertvist-nævnet)
- Lov: **Pakettimatkalaki** (901/2017)
- Sprog: `fi` (finsk) + sekundært `sv` (svensk er officielt minoritets-sprog)
- **Bonus:** kunne dele svensk vidensbank for de svensk-talende kunder

### Nederlandene
- Klageorgan: **Stichting Geschillencommissies voor Consumentenzaken**
- Lov: **Wet implementatie richtlijn pakketreizen** (BW boek 7)
- Sprog: `nl` (hollandsk)

---

## Tjekliste pr. nyt land (kopiér til notes når du starter)

```
LAND: ___ (SE / NO / DE / ...)
START-DATO: __________
GO-LIVE MÅLDATO: __________

FORARBEJDE
[ ] Klageorgan identificeret + URL
[ ] Lov identificeret + URL
[ ] 3-5 potentielle kunder mappet
[ ] Modersmål-konsulent (juridisk) fundet
[ ] Eksempel-afgørelser hentet manuelt (5-10 stk.)

OVERSÆTTELSE
[ ] prompts/{LAND}/system.md
[ ] prompts/{LAND}/foerstevurdering_user.md
[ ] prompts/{LAND}/klagepunkter_system.md + user.md
[ ] prompts/{LAND}/tidsforhold_system.md + user.md
[ ] prompts/{LAND}/svarbrev_system.md + user.md
[ ] prompts/{LAND}/anonymisering_system.md
[ ] pax-next/messages/{sprog}.json
[ ] Supabase email-skabeloner (invite + reset)
[ ] Error-meddelelser i api-client.ts

DATA
[ ] Scraper for klageorgan-afgørelser kørt
[ ] Afgørelser embedded med korrekt land-flag
[ ] Lovgivning scraped + embedded
[ ] Rejsevilkår fra mindst 1 lokalt rejseselskab (referencepunkt)

TEST
[ ] Test-tenant oprettet med land + sprog
[ ] Test-bruger oprettet
[ ] Upload + analyse virker
[ ] Output sprog korrekt
[ ] Output henviser til LOKAL lov (ikke dansk)
[ ] Output henviser til LOKALE præcedens-afgørelser
[ ] Svarbrev godkendt af modersmål-konsulent
[ ] Anonymisering virker for lokale CPR/personnummer-mønstre

MARKETING
[ ] Domæne købt (eller subpath besluttet)
[ ] Landing-page lavet på lokalt sprog
[ ] DNS + SSL konfigureret (fly certs create)
[ ] Analytics opsat for lokalt domæne (hvis separat)

GO-LIVE
[ ] 1-2 venlige test-kunder identificeret og kontaktet
[ ] Soft-launch
[ ] Sentry-monitoring 2 uger
[ ] Kvalitetscheck af første 10-20 analyser
[ ] Beslut om åbning for bredere marked
```

---

## Vedligeholdelse efter lancering

### Bugs gælder alle lande
Hvis du opdager en bug i DK, så er den **også til stede i SE/NO**
(samme kodebase). Fix det ÉT sted, alle lande får fixet automatisk
ved næste deploy.

### Features udvikles ÉN gang
En ny feature (fx "auto-generér mødeforberedelse") bygges i kodebasen
én gang, og udrulles til alle lande samtidig. Sproge skal blot
oversættes — kodelogikken er den samme.

### Hver vidensbank skal vedligeholdes separat
- Cron-jobs skraper hvert klageorgan ugentligt
- Lovgivnings-scrapere skal håndteres pr. land
- Manuel kvalitets-check af nye afgørelser før de tilføjes RAG

### Per-land monitoring
- Sentry-tags: `land=DK | SE | NO`
- Filtrér fejl pr. land — så du ved om en bug rammer alle lande
  eller kun ét
- KPI pr. land i admin-dashboard: analyser/dag, fejl-rate, kunde-
  tilfredshed

### Sproglig kvalitet over tid
- Hver 6. måned: få modersmål-konsulent til at læse 10 tilfældige
  analyser og notere kvalitets-problemer
- Hvis AI-output drifter (Anthropic opdaterer model): kør evaluering
  pr. sprog
- Pleje prompt-filer som levende dokumenter — opdatér når du lærer
  hvad der virker bedre

---

## Hvad du IKKE skal gøre

- ❌ **Lave separate Fly-apps pr. land** — én app holder alt enklere.
  Geo-distribution er kun nødvendigt ved 1000+ kunder pr. dag eller
  data-residency-krav (sjældent for B2B juridisk).

- ❌ **Forke kodebasen ("PAX-SE-repo")** — fører garanteret til drift.
  Se rod-dokumentationen om hvorfor.

- ❌ **Bruge maskine-oversættelse uden human terminologi-review.**
  AI er god til bulk-oversættelse (95% korrekt), men forkerte
  juridiske termer kan ødelægge produktet. Brug AI til oversættelsen,
  men lad altid en juridisk modersmål-konsulent verificere
  terminologien én gang.

- ❌ **Skære i kvaliteten af test før go-live** — første dårlige
  analyse til en svensk kunde slår markedet ihjel før det er startet.

- ❌ **Tilføje "land 3 og 4" før "land 2" er stabilt** — modn én ad
  gangen. Ved at lære fra SE-lanceringen får NO-lanceringen halv tid.

---

## Estimat for hele expansion

Vores model er **AI gør alt, du validerer som du gjorde med dansk PAX**.
Du har bygget det hele for ~2.000 DKK — at tilføje nye lande skal
være på samme niveau, ikke pludselig kræve konsulent-budgets.

| Fase | Tid (din) | Eksterne udgifter |
|---|---|---|
| Fase 0 (engang) | 20-30 t udvikling | ~$0 |
| Fase 1 — Sverige | 30-50 t + 1 uge scraping | **~$20 i AI/Voyage-credits** |
| Fase 2 — Norge | 20-30 t + 1 uge scraping | **~$20 i AI/Voyage-credits** |
| Fase 3 — Tyskland | 30-50 t + 1-2 uger scraping | **~$30 i AI/Voyage-credits** |
| **Total for alle 3 lande** | ~100-150 timer din tid | **~$70 (~500 DKK)** |

**Nøgleobservation:**
- Eneste reelle udgift er AI-credits til oversættelse + Voyage-embeddings
- Validering gør du selv via fiktive testsager — præcis som med dansk PAX
- Senere når du har faktiske kunder, finder DE de subtile fejl hurtigere
  end nogen konsulent
- Løbende drift af 3 lande på samme infrastruktur: ~$15-40/mnd baseline
  (samme som dansk alene), plus per-analyse-kost der skalerer med trafik

## Hvad du IKKE skal spare på (selvom alt andet er billigt)

Selvom hele expansionen koster ~500 DKK i AI-credits, er der to ting
hvor du ALDRIG skal spare på din egen tid + opmærksomhed:

❌ **Selvvalidering med fiktive sager før go-live.** Lige som med
dansk PAX skal du tage 20-30 fiktive sager igennem og iterere på
prompts indtil outputtet ser fornuftigt ud. Gør det grundigt —
ellers finder din første kunde fejlene.

❌ **Persondata-anonymisering pr. land.** Tyske persondata-mønstre
(Personalausweis, Steuer-ID) og svenske personnumre er anderledes
end danske CPR. Forkert anonymisering = GDPR-bøde. Test ANONYMI-
SERINGEN specifikt for hvert nyt land med fiktive persondata-mønstre.

## Min anbefaling til rækkefølge

### Stærkt anbefalet rækkefølge (lav risiko, gradvis læring)

1. **Sverige først** — størst nordisk marked, mest lignende juridisk
   system, gode chancer for at finde modersmåls-konsulent. Brug det
   som "lære-mens-du-gør"-marked
2. **Norge** — næste skridt. Sprog- og lov-lighed gør at du genbruger
   meget af det du lærte fra Sverige. Hurtigere lancering
3. **Tyskland** — VENT med dette indtil du har 6+ måneders erfaring
   fra SE/NO i drift. Tyskland er højere indsats og kræver mere
   omhyggelig forberedelse — men også markant større marked

### Alternativ rækkefølge (hvis du har specifikke leads)

Hvis du har en konkret kunde i Tyskland (fx TUI Deutschland — de har
HQ i Hannover), kan det give mening at springe Norge over og gå
direkte til Tyskland efter Sverige. Pengene er ikke længere en
faktor (alle 3 lande koster ~$70 i AI-credits), så det handler kun
om hvor du har faktisk efterspørgsel.

### Hvorfor det stadig giver mening at lære fra Sverige først

Selvom Tyskland teknisk koster det samme at lancere, er det stadig
smart at starte med Sverige:

1. **Sprog-lighed gør selvvalidering nemmere** — du kan spot-tjekke
   svensk output meget bedre end tysk
2. **Du opdager Fase 0-mangler i et "nemt" sprog** — hvis prompt-
   infrastrukturen ikke håndterer det rigtigt, finder du det i SE
   før du investerer tid i DE
3. **Fejl koster mindre i Sverige** — svensk juridisk marked er
   mere tilgivende end tysk i en beta-fase

### Om UK og Finland

- **UK**: Engelsk sprog frister, men post-Brexit-regulering gør det
  juridisk komplekst. EU-direktiv 2015/2302 er ikke længere
  automatisk gældende. Verificér regulatorisk status før investering
- **Finland**: Mindre marked end SE/NO. Kun overvej hvis du har
  specifikke leads. Sproget (finsk) er ekstremt anderledes fra
  skandinavisk — kræver helt separat oversættelse

---

# LÆRING FRA NORSK IMPLEMENTERING (maj 2026)

> Denne sektion er skrevet EFTER vi rent faktisk lancerede Norge.
> Det vi nedenfor beskriver virkede — og hvad der overraskede. Læs
> dette inden næste land (Sverige) for at undgå de samme faldgruber.

## Hvad der gik HURTIGT (uventet velfungerende)

### Multi-tenant B1-skemaet bar 80% af arbejdet

Vi opdagede at `tenants`-tabellen ALLEREDE havde `sprog`, `land`,
`klageorgan_navn`, `lov_navn`, `klageorgan_url`-kolonner fra Phase B1.
Da vi tilføjede FjordTravel-tenanten, var det bare en INSERT med de
norske værdier — ingen skema-ændring nødvendig.

**Vigtigt at huske til næste land:** check at `migration_b1_tenants.py`
har sat alle de relevante kolonner, og at de er populeret rigtigt for
den nye tenant. INSERT'en kan laves direkte via admin-siden eller via
SQL.

### Voyage `voyage-multilingual-2`-modellen håndterede norsk perfekt

Vi bekymrede os om hvorvidt embeddings ville fungere på tværs af sprog
(særligt om norsk og dansk ville "overlappe forkert"). Det gjorde de
IKKE: `find_relevante_sager` med norsk søgespørgsmål returnerede 5/5
norske sager, ingen danske blandet ind (efter land-filteret blev
tilføjet — se nedenfor). Embedding-modellen forstår både sprog uden
at confuse dem.

**Konklusion:** Du behøver IKKE forskellige embeddings-modeller pr.
sprog. `voyage-multilingual-2` er nok.

### i18n med dictionary-fallback var robust

`pax-next/src/lib/i18n/t.ts` har en pattern hvor manglende nøgler i
norsk dict falder tilbage til dansk. Det betød at vi kunne deploye
norske oversættelser delvist UDEN at UI'et crashede. Vi kunne i ro
fylde dictionary-filerne op uden at risikere produktionsstop.

**Vigtigt:** Sæt fallback-strategien op FØRST. Skriv ÉN test der
verificerer den (`expect t("ikke-eksisterende.nøgle") == dansk-værdi`).

## Hvad der OVERRASKEDE (gotchas)

### Fallback-RAG manglede land-filter — KRITISK BUG fundet sent

`find_relevante_sager` og `find_relevante_chunks` (hoved-RAG) havde
land-filter fra dag 1. Men `hent_alle_sager` og `hent_sager_af_type`
(fallback-funktioner) havde det IKKE.

Konsekvens: når chunks-RAG returnerede tomt (rare, men sker for nye
afgørelses-typer), faldt systemet til `hent_alle_sager` der returnerede
ALLE public docs — inkl. norske afgørelser blandet ind i danske
analyser og omvendt.

Test-script: `test_norge_rag_isolation.py` (i projekt-rod) — SQL-oracle-
baseret test der direkte sammenligner "hvad funktionen returnerer" vs
"hvad SQL siger den burde returnere".

**Til næste land:** kør `test_norge_rag_isolation.py` med det nye lands
tenant-ID + landekode FØRST efter migrationen. Hvis testen fejler,
betyder det at land-filteret er regresseret et sted.

### AI-prompts havde 35+ hardcoded "Pakkerejse-Ankenævnet"-refs

Den oprindelige roadmap antog at vi skulle "eksternalisere prompts pr.
sprog" som Fase 0. Det viste sig at være ~30% af det arbejde der
faktisk skulle gøres. De resterende 70% var **mekanisk find-and-replace**
af hardcoded danske institutionsnavne. Mange af dem var i
multiline-strenge eller f-strings hvor det var let at overse en
forekomst.

**Mønster der virkede:**

```python
# I top af funktion der bygger en prompt:
_klageorgan = _hent_klageorgan_navn()

# I selve prompten (f-string):
f"...skrive til {_klageorgan}..."
```

Selskab_profiler returnerer "Pakkerejse-Ankenævnet" for TUI og
"Pakkereisenemnda" for FjordTravel. For DK-tenants er prompten
BYTE-IDENTISK med før fixet — det gjorde det sikkert at rulle ud.

**Til næste land:** GREP først efter ALLE forekomster af den danske
institutions-navn (`grep -n "Pakkerejse-Ankenævn" ai_engine.py`), og
kategoriser dem som:
  - I AI-prompt (f-strings, system-prompts) → SKAL gøres dynamisk
  - I kode-kommentar (// eller #) → kan ignoreres
  - I regex-pattern eller parsing-konstant → SKAL IKKE oversættes
    (matcher mod dansk scrapet tekst)
  - I docstring → kosmetisk, kan ignoreres

**Test-mønster:** monkeypatch Anthropic-klienten til en `PromptCapture`-
klasse, kør de mest brugte funktioner under begge tenant-contexts,
verificer at TUI-prompts indeholder dansk klageorgan og NO-prompts
indeholder norsk klageorgan. Se `test_verifikation_norge_vs_dk.py`.

### `SYSTEM_PROMPT`-konstanten var sværest

Den 98-linjers `SYSTEM_PROMPT`-modul-konstant (omkring linje 313 i
ai_engine.py før fix) er ikke bare hardcoded institutionsnavn — den
er HELE den danske juridiske kontekst:

  - "ALT analyse-output skal være på DANSK"
  - "Brug PRÆCISE DANSKE JURIDISKE TERMER"
  - "den danske pakkerejselov (lov nr. 1666 af 2017)"
  - "Pakkerejsesager i Danmark"

Find-and-replace virker IKKE her. Man skal omdanne konstanten til en
funktion der bygger sprog-specifikke prompts:

```python
def _system_prompt():
    sprog = _hent_sprog()
    if sprog == "no":
        return _SYSTEM_PROMPT_NO
    return _SYSTEM_PROMPT_DA  # default: byte-identisk med før

# I gamle kald-steder, ændr fra:
#   system=SYSTEM_PROMPT
# Til:
#   system=_system_prompt()
```

Til næste land kan man udvide med `elif sprog == "sv": return _SYSTEM_PROMPT_SV`.

**Test:** byte-sammenlign DK-versionen før og efter omdannelsen
(`hashlib.sha256(_system_prompt())` skal være IDENTISK for TUI).

### "Pakkereisenemnda" filtrerer på "land" — ikke "sprog"

Vi var fristet til at filtrere RAG på `tenant.sprog`. Men EU-direktiv
2015/2302 er implementeret OG fortolket forskelligt per land — det er
LAND der er det juridisk relevante filter, ikke sprog. Sverige og
Norge taler scandinavisk, men deres afgørelser har forskellig
juridisk vægt.

**Konkret bevis:** Vi havde 86 lovgivnings-paragrafer i DB efter
norsk-ingest (55 norske + 31 danske). Hvis filteret havde været
sproget, ville en norsk tenant fået alle 86 fordi norsk-talende
"forstår" dansk. Vi vil ALDRIG have at AI'en citerer dansk paragraf-
nummerering i et svar til Pakkereisenemnda.

## Pitfalls for fremtidige lande

### Pagination i afgørelses-scraper

`scripts/scrape_pakkereise_no.py` har et eksplicit TODO: kun side 1 af
reiselivsforum.no's afgørelses-database er scraped. Vi har 311
afgørelser — det er ~10% af deres database. Pagination skal
implementeres for at få fuld dækning.

**Til næste land:** før du roller scraperen, bekræft at den henter
ALLE sider, ikke kun side 1.

### Land-specifikke parsing-patterns mangler

`pax-next/src/components/analyse-resultat.tsx` har en hardcoded liste
af danske sektion-overskrifter (`"Klagens indhold"`, `"Nævnets
bemærkninger og afgørelse"` osv.) der bruges til at parse scrapede
afgørelses-tekster og rendere dem med smukke sektion-overskrifter.

Norske afgørelser bruger andre titler:
  - "Klagens innhold" (i stedet for "Klagens indhold")
  - "Nemndas avgjørelse" (i stedet for "Nævnets afgørelse")

Konsekvensen: norske afgørelser renderer som FLAT TEKST i UI'et i
stedet for med struktureret layout. Fungerer, men er grimt.

**Fix til næste land:** lav listen sproget/land-specifik:

```typescript
const AFG_OVERSKRIFTER_BY_LAND = {
  DK: ["Klagens indhold", "Nævnets bemærkninger og afgørelse", ...],
  NO: ["Klagens innhold", "Nemndas avgjørelse", ...],
  SE: [...],
};
```

### Test-data: lav fiktiv testsag pr. land

For Norge byggede vi `scripts/generer_norsk_test_sag.py` der genererer
en komplet "sag-06-fjordtravel-norge" med klage + bilag + e-mails.
Det viste sig at være essentielt for at teste flow'et end-to-end.

**Til næste land:** kopiér scriptet (`generer_<land>_test_sag.py`),
opdater virksomhedsnavn, hotel-detaljer, lov-referencer.

### `data_imports/` + scrape-state-filer skal i `.gitignore`

Scraperen producerer 322 PDFs + state-fil. Disse hører IKKE i git
(data ligger i DB, ikke i filer). Vi tilføjede mønsteret i .gitignore
efter første commit hvor PDF'er ved en fejl ville være kommet med.

**Til næste land:** verificer at `data_imports/` er gitignored FØR du
kører scraperen.

## Den korte tjekliste til næste land

Antaget at Fase 0 (i den oprindelige roadmap) er gjort, er rækkefølgen
for et nyt land:

1. Identificér officielle kilder (lov + ankenævn). For Norge:
   `lovdata.no` + `reiselivsforum.no`
2. Skriv `<land>_lovgivning_scraper.py` (følg `norsk_pakkereiselov_scraper.py`
   som template)
3. Skriv `scrape_<land>_afgoerelser.py` + `download_<land>_pdfs.py` +
   `ingest_<land>_afgoerelser.py` (følg norsk-trilogien)
4. Kør migrationen `migration_land_kolonne.py` (idempotent — kan køres
   uden risiko hvis den allerede er kørt)
5. Opret tenant i DB med `sprog`, `land`, `klageorgan_navn`,
   `klageorgan_url`, `lov_navn` udfyldt
6. Kør de tre scrapers — verificer rækker i `mine_dokumenter` med
   `WHERE land='<XX>'`
7. Tilføj `pax-next/src/lib/i18n/dictionaries/<sprog>/*.json` (kopiér
   fra `da/` og oversæt). Behold strukturen 1:1 så fallback virker
8. Tilføj sproget til `pax-next/src/lib/i18n/config.ts` (`SUPPORTED_LOCALES`)
9. Verificer at `_hent_klageorgan_navn()` returnerer det rigtige navn
   for den nye tenant
10. Kopiér `test_norge_rag_isolation.py` → `test_<land>_rag_isolation.py`,
    opdater tenant-ID og land-kode, kør den. Skal være GREEN
11. Kopiér `test_verifikation_norge_vs_dk.py` → tilpas til det nye land.
    Verificer at AI-prompts indeholder det rigtige klageorgan
12. Tilføj `<sprog>`-variant af `_SYSTEM_PROMPT` (kopiér DK-versionen
    og oversæt). Test at byte-hash for DK-versionen er uændret
13. Lav `generer_<land>_test_sag.py` så du har en testbar sag
14. Live-test: log ind som test-bruger, upload test-sagen, gennemløb
    analyse + svarbrev. Verificer at sprog er korrekt og at præcedens
    er fra det rigtige land

**Skøn for nyt land (efter at have lavet Norge):** 8-12 timer pr. land,
forudsat at du genbruger scraperne 1:1 og bare oversætter
dictionaries og prompts. Mest tidskrævende: at finde lokalitets-
specifikke parsing-patterns (afgørelses-format) og at få oversat
SYSTEM_PROMPT'et juridisk korrekt af modersmåls-konsulent.

