# juriitech PAX — GDPR-strategi og auto-anonymiserings-pipeline

**Status:** Spec, godkendt 2026-05-02
**Repo berørt:** `juridisk_assistent` (PAX) + `juriitech-landing` (privatlivspolitik + DPIA)

## Mål

Designe en GDPR-position der gør juriitech PAX kommercielt tryg at købe for rejseselskaber. Tre samtidige krav:

1. **Brand-promise:** "Persondata om jeres klagere lever maksimalt 24 timer i juriitech PAX. Efter analyse er færdig, slettes alle personhenførbare oplysninger automatisk."
2. **Læringsevne:** Programmet skal blive klogere over tid via tre kanaler: (i) voksende offentlig vidensbank, (ii) per-tenant historik som RAG-kontekst, (iii) cross-tenant anonymiserede mønstre.
3. **Skalerbarhed:** Nye kunder kan onboardes med ÉN standard processor-DPA uden tilpasninger.

Designet baserer sig på "privacy by design" + "data minimisation" + "storage limitation" — GDPR's egne kerneprincipper.

## Hvad er IKKE i scope: offentlige Pakkerejse-Ankenævn-afgørelser

**Pakkerejse-Ankenævnets afgørelser er allerede offentliggjort på Ankenævnets egen hjemmeside og er pseudonymiseret af Ankenævnet selv før publicering** (parts-navne erstattet med `[Klageren]`, `[Indklagede]` osv. — som beskrevet i CLAUDE.md). Disse afgørelser:

- Markeres med `is_public = TRUE` i `mine_dokumenter`-tabellen
- Tilhører ingen tenant (`tenant_id IS NULL`)
- Skal IKKE igennem auto-anonymiserings-pipelinen
- Bevares uændret i vidensbanken på ubestemt tid
- Bruges som RAG-kontekst af alle tenants (det er hele formålet)

Pipelinen + alle GDPR-foranstaltninger nedenfor gælder **udelukkende kunde-uploadede filer** (klageskema, sagsakter, bilag, klagers korrespondance) — dvs. rækker hvor `is_public = FALSE`. Det er disse filer der indeholder ikke-pseudonymiserede personoplysninger fra konkrete klagere.

Tilsvarende er offentlig lovgivning (`pakkerejselov_scraper.py`) og offentlige anonymiserings-regler (`anonymisering_regler_scraper.py`) `is_public = TRUE` og uden for scope.

## Designet i ét billede

```
┌─────────────────────────────────────────────────────────────────┐
│  T+0:  Kunde uploader sag                                       │
│  T+0:  PAX kører analyse — persondata findes som nødvendigt     │
│  T+0 til T+24h:  Aktiv periode (eksport, re-køring, justering)  │
│  T+24h:  AUTO-ANONYMISERING TRIGGERS                            │
│         ├── AI læser dokumenter og analyse                      │
│         ├── Direkte identifikatorer fjernes 100%                │
│         ├── Quasi-identifikatorer generaliseres                 │
│         ├── Embeddings re-genereres fra anonymiseret tekst      │
│         ├── Originale filer + embeddings slettes permanent      │
│         └── Anonymiseret version deles to steder:               │
│             ├── tenant's egen historik (privat, RAG-kontekst)   │
│             └── shared_patterns (cross-tenant, hvis k≥5)        │
│  T+24h+:  Sagen findes nu KUN som anonymiseret reference        │
└─────────────────────────────────────────────────────────────────┘
```

## Juridisk rolle

### Persondata (klagers navne, adresser, sundhedsoplysninger osv.)

**juriitech er DATA PROCESSOR.** Kunden (rejseselskabet) er data controller.

- Standard processor-DPA underskrives ved onboarding
- Behandling sker udelukkende efter kundens instruks
- Sletteanmodninger fra klagere håndteres af kunden; juriitech videresender hvis modtaget direkte
- Sub-processors (Anthropic, Voyage AI, Supabase, Fly.io, Sentry) listes i DPA-bilag

### Anonymiserede mønstre (efter T+24h)

**juriitech er DATA CONTROLLER for de anonymiserede mønstre.**

Begrundelse: Anonymiserede data er pr. definition ikke længere persondata under GDPR. juriitech har et selvstændigt formål med disse data (forbedring af platformen for alle kunder), hvilket er forskelligt fra den enkelte kundes formål med deres egen sagsbehandling. Cross-tenant brug er kun tilladt på data der ikke længere er persondata.

## Auto-anonymiserings-pipeline

### Trigger

- **Default vindue:** 24 timer efter "Afslut sag"-knap er klikket, ELLER 24 timer efter sidste analyse-aktivitet hvis kunden ikke aktivt lukker sagen.
- **Ingen manuel kontrol:** Vinduet kan ikke forlænges fra UI'en. Det er bevidst — kunden skal ikke have en mekanisme der kan misbruges (eller glemmes) til at holde persondata over 24 timer.
- **Hvis genoptagelse:** Kunden re-uploader filerne (de har originalerne i deres eget sagshåndteringssystem). PAX behandler det som ny sag.
- **Filter:** Pipelinen kører UDELUKKENDE på rækker med `is_public = FALSE` (kunde-uploadede filer). Offentlige Pakkerejse-Ankenævn-afgørelser, lovgivning og anonymiserings-regler (`is_public = TRUE`) er allerede pseudonymiserede af kilden og skal ikke røres.

### Hvad pipelinen gør (i rækkefølge)

1. **AI-læsning:** AI gennemgår alle filer + analysen + svarbrevet og identificerer persondata-typer.
2. **Direkte identifikatorer fjernes 100%:**
   - Klagers fulde navn → `[Klageren]`
   - Adresse, CPR-nr, email, telefon → fjernes helt
   - Fuldmagtshaverens navn → `[Fuldmagtshaveren]`
   - Pakkerejse-Ankenævnets sagsnummer → fjernes helt (kritisk: dette er én-til-én identifikator)
   - Bilags-numre → erstattes med `[Bilag X]`
   - Kontonumre, faktura-numre → fjernes
3. **Quasi-identifikatorer generaliseres:**
   - Datoer → måned/kvartal/sæson (`ferie i højsæson Q3 2025`)
   - Hotel-navne → kategori-niveau (`4-stjernet hotel i Hurghada-området`)
   - Destinationer → region hvis specifikt sted er sjældent
   - Beløb → afrundet til nærmeste 1000 kr; ved beløb >50.000 kr afrundes til 5000 kr
   - Familiekonstellation → `klager med familie` / `klager alene`
4. **Særlige kategorier (GDPR Art. 9) generaliseres maksimalt:**
   - Sundhedsoplysninger → generelt sygdoms-niveau (`klager blev syg under opholdet`), aldrig specifik diagnose hvis ikke essentielt for sagen
   - Religiøse forhold, etnisk oprindelse → generaliseres eller fjernes
   - Børns alder/oplysninger → fjernes/generaliseres ekstra forsigtigt
5. **K-anonymitets-tærskel (k≥5):**
   - Det anonymiserede mønster matches mod eksisterende mønstre i `shared_patterns`-tabellen
   - Kun hvis ≥4 andre lignende sager allerede findes (giver k=5+), gemmes mønsteret i den fælles pulje
   - Ellers gemmes det KUN i tenant's egen historik (ikke i fælles pulje) indtil tærsklen er nået
   - "Lignende" defineres ved struktureret kategori-match (sagstype + udfald + region), ikke fri tekstsammenligning
6. **Embeddings re-genereres:** Nye Voyage-embeddings beregnes fra den anonymiserede tekst. Originale embeddings smides væk (de kunne i teorien lække persondata ved reverse engineering).
7. **Original-sletning:** Originale filer, originale chunks, originale embeddings, original analyse-rapport — slettes permanent fra alle tabeller.
8. **Audit-log skrives:** Per sag dokumenteres hvad der blev anonymiseret, hvornår, hvordan.

### Anonymiserings-rapport per sag

Genereres som del af pipelinen og kan vises til kunden ved revisionsforespørgsel:

```
Sag PA-2026-0142 → anonymiseret 2026-05-03 14:32:15 UTC
- 3 navne fjernet (klager, fuldmagtshaver, ledsager)
- 7 datoer generaliseret til måned-niveau
- 4 beløb afrundet (3.746 → 4000, 12.500 → 13000, ...)
- 2 hotel-navne generaliseret til kategori
- 1 sagsnummer fra Pakkerejse-Ankenævnet fjernet
- 0 sundhedsoplysninger fundet
- Re-embedding gennemført, originaler slettet
- Resultat tilføjet til shared_patterns: NEJ (k=3, ikke nået k≥5 endnu)
- Resultat tilføjet til tenant's historik: JA
```

## Tekniske ændringer i koden

### Nye/ændrede tabeller (database.py)

**Ny: `shared_patterns`** (fælles cross-tenant-pulje)
```sql
CREATE TABLE IF NOT EXISTS shared_patterns (
    id SERIAL PRIMARY KEY,
    tilfojet_dato TIMESTAMPTZ DEFAULT NOW(),
    sag_kategori TEXT NOT NULL,
    udfald_kategori TEXT NOT NULL,
    region TEXT,
    anonymiseret_tekst TEXT NOT NULL,
    embedding vector(1024),
    k_count INTEGER NOT NULL DEFAULT 1,  -- antal lignende sager bag mønstret
    bidragende_tenants INTEGER[]         -- liste af tenant_ids (kun til intern audit)
);

-- INGEN tenant_id på denne tabel = fysisk umulig at lække tenant-info
CREATE INDEX idx_shared_patterns_kategori ON shared_patterns(sag_kategori, udfald_kategori);
```

**Ny: `gdpr_audit_log`** (per-sag anonymiserings-historik)
```sql
CREATE TABLE IF NOT EXISTS gdpr_audit_log (
    id SERIAL PRIMARY KEY,
    sag_id TEXT NOT NULL,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    handling TEXT NOT NULL,  -- 'upload' / 'analyse' / 'anonymisering' / 'sletning' / 'cross_tenant_share'
    tidspunkt TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB
);

CREATE INDEX idx_gdpr_audit_tenant_sag ON gdpr_audit_log(tenant_id, sag_id);
```

**Ny: `mine_dokumenter.anonymiserings_status`** (state-tracking)
```sql
ALTER TABLE mine_dokumenter
ADD COLUMN IF NOT EXISTS anonymiserings_status TEXT DEFAULT 'pending'
    CHECK (anonymiserings_status IN ('pending', 'aktiv', 'anonymiseret', 'slettet'));

ALTER TABLE mine_dokumenter
ADD COLUMN IF NOT EXISTS anonymiseres_efter TIMESTAMPTZ;

CREATE INDEX idx_mine_dokumenter_anonym_pending ON mine_dokumenter(anonymiseres_efter)
    WHERE anonymiserings_status = 'aktiv' AND is_public = FALSE;
```

### Ny modul: `gdpr_pipeline.py`

```python
def trigger_auto_anonymisering():
    """Kører hver time. Finder sager hvor anonymiseres_efter < NOW()
    AND is_public = FALSE og kører pipelinen på dem. Idempotent —
    sager der allerede er anonymiseret skippes. Offentlige
    Ankenævn-afgørelser (is_public=TRUE) er fysisk udelukket fra
    pipelinen via WHERE-clausen."""

def anonymiser_sag(sag_id, tenant_id):
    """Hovedfunktion. Læs original-sag, kør AI-anonymisering,
    generaliser quasi-identifikatorer, re-generer embeddings,
    slet originaler, opdater alle tabeller, skriv audit-log."""

def vurder_k_anonymitet(anonymiseret_mønster):
    """Tæller eksisterende lignende mønstre i shared_patterns.
    Returnerer (k_count, må_dele_bool) — må_dele=True kun hvis k≥5."""

def generer_anonymiserings_rapport(sag_id):
    """Til revisions- og kundeoplysning. Returnerer struktureret
    JSON over hvad der blev anonymiseret."""
```

### Cron-trigger til pipelinen

Fly.io machines schedule (hver time):
```toml
[[scheduled_tasks]]
schedule = '0 * * * *'
command = 'python3 -c "from gdpr_pipeline import trigger_auto_anonymisering; trigger_auto_anonymisering()"'
```

### Row-Level Security (RLS) på Supabase

Aktiveres på alle private tabeller — ekstra forsvarslinje udover tenant_id-WHERE-clauses i applikationskoden:

```sql
ALTER TABLE mine_dokumenter ENABLE ROW LEVEL SECURITY;
ALTER TABLE analyse_arkiv ENABLE ROW LEVEL SECURITY;
ALTER TABLE gemte_sager ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON mine_dokumenter
    USING (
        is_public = TRUE
        OR tenant_id = current_setting('app.current_tenant_id')::INTEGER
    );

-- (Tilsvarende policies på de øvrige tabeller)
```

App-laget skal sætte `app.current_tenant_id` per Supabase-forbindelse efter auth.

### Sub-processor-stack (Tilgang 1: behold current stack med DPAs)

| Provider | Rolle | Region | DPA-link | EU-residency |
| --- | --- | --- | --- | --- |
| Anthropic | AI-prompts | USA + EU | https://www.anthropic.com/legal/dpa | Delvist (US default) |
| Voyage AI | Embeddings | USA | https://www.voyageai.com/dpa | Nej |
| Supabase | Database | EU (eu-west-1) | https://supabase.com/legal/dpa | Ja |
| Fly.io | App-runtime | EU (Frankfurt) | https://fly.io/legal/dpa | Ja |
| Sentry | Fejl-monitoring | EU (Frankfurt) | https://sentry.io/legal/dpa | Ja |

Standard Contractual Clauses (SCCs) inkluderes i kunde-DPAs for de US-baserede sub-processors. Anthropic + Voyage benytter ikke kunde-data til model-træning (verificeret i deres DPAs/T&Cs).

### Privatlivspolitik + DPIA

To nye dokumenter på juriitech.com:

**`/privatlivspolitik`** — for klagere (de fysiske personer i sagerne):
- Kort, læsbar, dansk
- Forklarer: rejseselskabet (TUI/Apollo/Spies) er primær data controller; juriitech er processor
- Forklarer 24-timers-anonymiserings-flowet
- Forklarer at GDPR-anmodninger sendes til rejseselskabet, ikke til juriitech
- Lister sub-processors med EU/non-EU markering

**`/dpia.pdf`** — Data Protection Impact Assessment (krævet under GDPR Art. 35):
- Beskriver behandlings-formål, kategorier af persondata, retention-tider
- Risiko-vurdering + foranstaltninger der mindsker risici
- Dokumenterer 24-timers-anonymiseringen som primær GDPR-foranstaltning
- Kan deles med kunders DPO ved købsforhandlinger

## Eksplicit ude af scope

- **Brugerdrevet anonymiserings-vindue.** Default 24 timer, ikke konfigurerbar (anti-misbrug).
- **Kunde-specifik anonymiserings-grad.** Alle kunder får samme pipeline. Ingen "let anonymisering"-mulighed.
- **Pseudonymisering med re-identifikations-nøgle.** Vi gør ægte anonymisering, ikke pseudonymisering. Ingen mapping-tabel.
- **Manuel godkendelses-step før anonymisering.** Skal være automatisk uden bruger-interaktion.
- **EU-only sub-processors lige nu.** Vurderes igen om 6 måneder hvis det viser sig at være deal-breaker for store kunder.
- **GDPR-rettigheder for kunder selv (juriitech-brugere).** Kunden har sit eget brugerregister i users-tabellen — det er almindelig GDPR (med email + navn) og håndteres separat.

## Test

Testen falder i tre kategorier — alle skal passere før vi sælger til ny kunde:

### Tekniske tests (automatiserbare)

1. **Pipeline-end-to-end:** Upload test-sag med kendte persondata → vent på trigger → bekræft alle 8 originalrækker er slettet, anonymiseret version findes, audit-log er skrevet.
2. **K-anonymitet:** Upload 5 lignende test-sager → første 4 ender ikke i `shared_patterns` (k<5); femte trigger må_dele → alle 5 lægges nu i fælles pulje retroaktivt.
3. **Cross-tenant isolation:** Tenant A's anonymiseringer dukker IKKE op i tenant B's private RAG-resultater (kun via shared_patterns hvor tenant_id er fjernet).
4. **RLS-test:** Direkte SQL-query mod Supabase som tenant A's bruger returnerer 0 rækker fra tenant B's data, selv ved bevidst forkert WHERE-clause.
5. **Embeddings re-generation:** Original-embeddings slettes, nye embeddings findes, ingen reverse-lookup mulig fra ny embedding til original tekst.

### Manuel revision (kvartalsvis)

6. **Anonymiserings-kvalitet:** Stikprøve af 10 anonymiserede sager. Manuel læsning. Tjek for missed direkte identifikatorer (navne der slap igennem AI-filteret).
7. **Re-identifikations-test:** Forsøg at re-identificere en anonymiseret sag uden adgang til kundens originale data. Skal mislykkes.

### Compliance-dokumentation

8. **DPIA-review.** Opdateres når processen ændrer sig væsentligt.
9. **DPA-stack-review.** Tjek alle sub-processors stadig har gyldige DPAs på fil.

## Beslutnings-historie

- **2026-05-02 (i+ii+iii godkendt):** Bruger valgte alle tre lærings-modeller. Cross-tenant værdi er commercial differentiator.
- **2026-05-02 (Model A: anonymiseret data tilhører juriitech):** Bruger valgte processor-rolle for persondata + controller-rolle for anonymiserede mønstre. Skalerbart til mange kunder.
- **2026-05-02 (Flow A: auto-share efter sagslukning):** Bruger valgte default opt-out med transparens — derefter forfinet til "ingen kunde-kontrol over vinduet" da brugeren senere besluttede at det skulle være helt automatisk.
- **2026-05-02 (Tilgang 1: behold sub-processor-stack):** Anthropic + Voyage forbliver USA-baseret. SCCs i DPA. Vurderes igen om 6 måneder.
- **2026-05-02 (24 timer + ingen manuel forlængelse):** Bruger forkortede mit oprindelige forslag (30 dage) til 24 timer og fjernede manuel kontrol — meget stærkere GDPR-position.
- **2026-05-02 (anonymisering ved lagring):** Bruger eskalerede kravet — det skal IKKE bare være cross-tenant der er anonymiseret, men ALT efter analyse. K-anonymitet (k≥5) tilføjet for at sikre ægte anonymitet i fælles pulje.
- **2026-05-02 (offentlige afgørelser eksplicit ude af scope):** Bruger præciserede at Pakkerejse-Ankenævnets afgørelser (samt offentlig lovgivning og anonymiserings-regler) ALLEREDE er pseudonymiseret af Ankenævnet selv før publicering — disse skal IKKE røres af pipelinen. Filtrering på `is_public = FALSE` tilføjet eksplicit i alle pipeline-trin.
