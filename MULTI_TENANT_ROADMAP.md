# Multi-Tenant Roadmap — juriitech PAX

> **Status:** Plan, ikke implementeret. Bygges efter første betalende kunde
> er i hus, og når 1-3 TUI-brugere reelt bruger PAX dagligt.

## Vision

Én URL — `pax.juriitech.com` — som ALLE rejseselskaber tilgår. Brugerens
login-credentials bestemmer hvilken tenant (rejseselskab) de tilhører,
og PAX tilpasser sig automatisk:

- TUI-medarbejder logger ind → ser TUI-branding, TUI-anonymisering,
  TUI's vidensbank og rejsevilkår, signerer med "TUI"
- Apollo-medarbejder logger ind → ser Apollo-branding, Apollo-
  anonymisering, Apollo's vidensbank, signerer med "Apollo"
- Samme arkitektur understøtter Spies, Sunweb, Bravo Tours, osv.

## Hvorfor denne tilgang frem for per-tenant subdomain

| Aspekt | Per-tenant subdomain | Én URL + login (vores valg) |
|---|---|---|
| DNS-administration | 1 record per tenant | 1 record total |
| SSL-certifikater | Wildcard eller én per | Ét fælles |
| Marketing | Forskellige URLs | "pax.juriitech.com" konsekvent |
| Bruger-mobilitet | Skal skifte URL ved jobskifte | Skifter bare email |
| Onboarding ny tenant | DNS + cert + deploy | Bare opret i database |

Branchestandard for B2B SaaS — bruges af Notion, Linear, Stripe, m.fl.

## To dimensioner: Brand × Land

PAX skal forstå tenant som en KOMBINATION af brand og land. Reglerne
er forskellige på BEGGE akser:

- **Brand** (TUI, Apollo, Spies, Sunweb): forskellige rejsevilkår,
  signatur, branding, intern terminologi
- **Land** (DK, SE, NO, FI): forskellig pakkerejselovgivning,
  forskellige ankenævn, forskellige sprog, forskellige offentlige
  afgørelser i vidensbanken

Konkret: TUI Danmark og TUI Sverige er IKKE samme tenant. De har samme
brand men forskellige juridiske rammer:

| Land | Lov | Ankenævn / Klageorgan |
|---|---|---|
| Danmark | Pakkerejseloven | Pakkerejse-Ankenævnet |
| Sverige | Paketreselagen | Allmänna Reklamationsnämnden |
| Norge | Pakkereiseloven | Reklamasjonsnemnda for Pakkereiser |
| Finland | Pakettimatkalaki | Kuluttajariitalautakunta |

Datamodellen håndterer det enklest ved at hver tenant har et eksplicit
`(brand, land)`-par. TUI-DK og TUI-SE er to separate rækker i tabellen.

## Hvad bliver tenant-specifikt

| Konfig | TUI-DK | TUI-SE | Apollo-DK | Spies-DK |
|---|---|---|---|---|
| Brand | TUI | TUI | Apollo | Spies |
| Land | Danmark | Sverige | Danmark | Danmark |
| Sprog | Dansk | Svensk | Dansk | Dansk |
| Lov | Pakkerejseloven | Paketreselagen | Pakkerejseloven | Pakkerejseloven |
| Ankenævn | Pakkerejse-Ankenævnet | ARN | Pakkerejse-Ankenævnet | Pakkerejse-Ankenævnet |
| Selskabsnavn i tekst | TUI | TUI | Apollo | Spies |
| Signatur | TUI | TUI | Apollo | Spies After Sales |
| Anonymisering | "Maria, TUI" | "Maria, TUI" | "Maria, Apollo" | "Maria, Spies" |
| Rejsevilkår | TUI DK's vilkår | TUI SE's vilkår | Apollo DK's | Spies DK's |
| Vidensbank — private | Egne sager | Egne sager | Egne sager | Egne sager |
| Vidensbank — fælles | DK Ankenævn-afgørelser | SE ARN-afgørelser | DK Ankenævn | DK Ankenævn |
| Logo / branding | TUI | TUI | Apollo | Spies |

## Database-skema (når implementeret)

```sql
CREATE TABLE tenants (
    id SERIAL PRIMARY KEY,
    slug VARCHAR UNIQUE,            -- 'tui-dk', 'tui-se', 'apollo-dk'
    brand VARCHAR,                  -- 'TUI', 'Apollo', 'Spies'
    country_code CHAR(2),           -- 'DK', 'SE', 'NO', 'FI'
    display_name VARCHAR,           -- 'TUI Danmark', 'TUI Sverige'
    language CHAR(2),               -- 'da', 'sv', 'no', 'fi'
    signature VARCHAR,              -- 'TUI', 'Apollo Kundeservice'
    anonymization_suffix VARCHAR,   -- 'TUI', 'Apollo'
    primary_email_domain VARCHAR,   -- 'tui.dk', 'tui.se'
    logo_url VARCHAR,
    klageorgan_navn VARCHAR,        -- 'Pakkerejse-Ankenævnet', 'ARN'
    pakkerejselov_doc_id INT,       -- ref til den nationale lov
    rejsevilkaar_doc_id INT,        -- ref til tenant's egne vilkår
    settings_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Eksempel-data:
-- INSERT INTO tenants (slug, brand, country_code, display_name, language,
--                      signature, anonymization_suffix, primary_email_domain,
--                      klageorgan_navn) VALUES
-- ('tui-dk', 'TUI', 'DK', 'TUI Danmark', 'da', 'TUI', 'TUI', 'tui.dk',
--  'Pakkerejse-Ankenævnet'),
-- ('tui-se', 'TUI', 'SE', 'TUI Sverige', 'sv', 'TUI', 'TUI', 'tui.se',
--  'Allmänna Reklamationsnämnden'),
-- ('apollo-dk', 'Apollo', 'DK', 'Apollo Danmark', 'da', 'Apollo Kundeservice',
--  'Apollo', 'apollo.dk', 'Pakkerejse-Ankenævnet');

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    tenant_id INT REFERENCES tenants(id),
    email VARCHAR UNIQUE,
    password_hash VARCHAR,
    role VARCHAR DEFAULT 'jurist',  -- 'admin', 'jurist', 'viewer'
    full_name VARCHAR,
    created_at TIMESTAMP DEFAULT NOW()
);
```

Eksisterende tabeller (`mine_dokumenter`, `analyse_arkiv`, `gemte_sager`)
udvides med `tenant_id INT REFERENCES tenants(id)` og søgning filtreres
altid: `WHERE tenant_id = current_user.tenant_id` for private docs,
plus `OR is_public = true` for offentlige Ankenævn-afgørelser.

## Tenant-detektion via email-domæne

```python
def find_tenant_for_email(email: str) -> Tenant | None:
    domain = email.split('@')[1]   # 'tui.dk' fra 'maria@tui.dk'
    return Tenant.query.filter_by(primary_email_domain=domain).first()
```

Specielle tilfælde (gmail.com, hotmail.com): brugeren får en dropdown
med tenant-valg ved registrering.

## Kode-niveau ændringer

Konstanter der i dag er hardcoded skal blive dynamiske:

- `REJSESELSKAB_NAVN` → `current_tenant.display_name`
- `REJSESELSKAB_SAGSBEHANDLER` → `current_tenant.signature`
- Anonymiseringsregler i `ANONYMISERING_PROMPT` → injicer
  `current_tenant.anonymization_suffix`
- `byg_svarbrev_opgave()` → tager `tenant: Tenant`-parameter
- `_hent_relevante_eller_fald_tilbage()` → filtrerer på
  `tenant_id` for private + `is_public=true` for offentlige

## Implementerings-rækkefølge

### Trin 1: Login-system (Supabase Auth)
- Bruger-konti, password-reset, email-verifikation
- Endnu kun TUI som tenant — alle nye brugere blir TUI-brugere
- **Hvornår:** Når du har 1-3 TUI-brugere klar til at bruge PAX dagligt

### Trin 2: Tenants-tabel + tenant_id-felt
- Database-skema introduceres
- `tenant_id` tilføjes på alle tabeller
- Stadig hardcoded "TUI" overalt i koden, men strukturen er klar
- **Hvornår:** Lige før første ikke-TUI kunde-samtale

### Trin 3: Dynamisk tenant-konfig
- Konstanter erstattes med `current_tenant.X` opslag
- Prompts refaktoreres til at acceptere tenant-parameter
- Test grundigt med TUI før Apollo lukkes ind
- **Hvornår:** Når Apollo (eller anden) har sagt ja til pilot

### Trin 4: Branding + UX
- Per-tenant logo, evt. farver
- Tenant-vælger ved login hvis email-domain er generisk
- Polering af multi-tenant UX
- **Hvornår:** Når 2-5 tenants kører i produktion

## Hvad IKKE skal i denne version

- Per-tenant subdomain (tui.juriitech.com) — kræves ikke
- White-labeling (skjul juriitech-brand) — gem til premium tier
- Tenant-isolation på database-niveau (separate skemaer) — overengineering

## Sikkerhed

- Alle queries SKAL filtrere på `tenant_id` — risiko for cross-tenant
  data-lækage hvis det glemmes
- Audit log: hvem (user_id) gjorde hvad (action) hvornår på hvilken
  tenant (tenant_id)
- Rate limiting per tenant for at forhindre én tenant i at trække
  alle ressourcer

## Hvor PAX-koden allerede er pænt forberedt

Følgende er allerede isoleret som konstanter i én fil (`ai_engine.py`):
- `REJSESELSKAB_NAVN = "TUI"`
- `REJSESELSKAB_SAGSBEHANDLER = "TUI"`

Anonymiseringsreglerne ligger i én funktion (`byg_svarbrev_opgave()`)
og én prompt (`ANONYMISERING_PROMPT`) — relativt overkommelig
refaktorering når tiden er inde.

## Tenant-specifik vidensbank (eksempel: TUI Danmark)

Når TUI-DK-tenanten oprettes, skal den have sin egen vidensbank-segment
udover de fælles offentlige Ankenævn-afgørelser:

**TUI Danmark:**
- Kilde: https://www.tui.dk/rejse-med-tui/ + alle undersider i venstre-menu
- Indhold: TUI's officielle danske rejsevilkår, FAQ, ansvarsregler,
  refusions-politikker, transport-betingelser, mv.
- Scrapes af en dedikeret `tui_dk_scraper.py` (eksisterer allerede
  som `tui_scraper.py` — skal udvides og knyttes til tenant_id)
- Markeres med `dokumenttype='vilkaar'` og `tenant_id=<TUI-DK id>`
- AI'ens prompt henter kun TUI-DK's vilkår når en TUI-DK-bruger laver
  analyse — aldrig TUI-SE's eller Apollo's

**TUI Sverige (når relevant):**
- Kilde: tilsvarende side på tui.se
- Indhold: Svensk version af samme indhold
- Egen scraper eller udvidet version af samme

**Apollo Danmark (når relevant):**
- Kilde: https://www.apollorejser.dk/rejs-med-apollo/ (eller lign.)
- Egen scraper

**VIGTIG REGEL**: Hver tenants vilkår er **isoleret** i vidensbanken.
TUI-DK-brugeren ser ALDRIG Apollo's vilkår eller TUI-SE's vilkår — det
ville være misvisende juridisk grundlag.

## Migration af eksisterende data ved Trin 2

Når `tenant_id` indføres på `mine_dokumenter` og `analyse_arkiv`:

```sql
-- Antagelse: alle eksisterende data tilhører TUI-DK
UPDATE mine_dokumenter SET tenant_id = (SELECT id FROM tenants WHERE slug='tui-dk');
UPDATE analyse_arkiv SET tenant_id = (SELECT id FROM tenants WHERE slug='tui-dk');
UPDATE gemte_sager SET tenant_id = (SELECT id FROM tenants WHERE slug='tui-dk');

-- Marker offentlige afgørelser som ikke-private (delt på tværs af DK-tenants)
UPDATE mine_dokumenter
SET is_public = TRUE, tenant_id = NULL
WHERE dokumenttype = 'afgoerelse';
```

## Beslutnings-historie

- **2026-04-27**: Mikkel og Claude diskuterede arkitekturen. Konklusion:
  én URL + login-baseret tenant-detektion (frem for per-tenant subdomain).
  Implementering udskudt til efter første betalende kunde (TUI) er solidt
  i drift.

- **2026-04-27**: Tilføjet country-dimension. Tenant er ikke kun
  brand, men `(brand × land)` — TUI-DK og TUI-SE er separate tenants.
  Hver har egen lov, eget ankenævn, egne rejsevilkår, eget sprog.

- **2026-04-27**: Bekræftet at tenant-specifik vidensbank-scraping
  (fx TUI-DK fra tui.dk/rejse-med-tui) udskydes til efter login + tenant-
  arkitektur er på plads — for at undgå at scrape og indlæse data der
  bagefter skal flyttes/tagges. Den nuværende `tui_scraper.py` skal
  udvides til at gemme med korrekt `tenant_id`.
