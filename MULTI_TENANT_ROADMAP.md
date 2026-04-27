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

## Hvad bliver tenant-specifikt

| Konfig | TUI | Apollo | Spies |
|---|---|---|---|
| Selskabsnavn | TUI | Apollo | Spies |
| Signatur i svarbrev | TUI | Apollo | Spies After Sales |
| Anonymiseringsmønster | "Maria, TUI" | "Maria, Apollo" | "Maria, Spies" |
| Rejsevilkår | TUI's | Apollo's | Spies' |
| Vidensbank — private | Kun egne sager | Kun egne sager | Kun egne sager |
| Vidensbank — fælles | Alle Ankenævn-afgørelser | Samme | Samme |
| Logo / branding | TUI | Apollo | Spies |

## Database-skema (når implementeret)

```sql
CREATE TABLE tenants (
    id SERIAL PRIMARY KEY,
    slug VARCHAR UNIQUE,            -- 'tui', 'apollo'
    display_name VARCHAR,           -- 'TUI', 'Apollo'
    signature VARCHAR,              -- 'TUI', 'Apollo Kundeservice'
    anonymization_suffix VARCHAR,   -- 'TUI', 'Apollo'
    primary_email_domain VARCHAR,   -- 'tui.dk', 'apollo.dk'
    logo_url VARCHAR,
    rejsevilkaar_doc_id INT,
    settings_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

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

## Beslutnings-historie

- **2026-04-27**: Mikkel og Claude diskuterede arkitekturen. Konklusion:
  én URL + login-baseret tenant-detektion (frem for per-tenant subdomain).
  Implementering udskudt til efter første betalende kunde (TUI) er solidt
  i drift.
