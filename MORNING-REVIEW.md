# MORNING REVIEW — 2026-05-03

> Det her er hvad jeg har lavet i nat mens du sov. Læs igennem over kaffe inden du gør noget i prod.

## TL;DR

GDPR Fase 2, 3 og 4 er **skrevet og committet i grenen** `refactor/rag-fase-1` — men **INTET er aktiveret i produktion**. Du har 7 nye commits at reviewe, ingen overraskelser i prod-app, og en konkret tjekliste at gennemgå når du vil aktivere pipelinen.

## Hvad der er klart

### Fase 2 — Row-Level Security (RLS)
- **Plan:** [docs/superpowers/plans/2026-05-02-gdpr-fase2-rls.md](docs/superpowers/plans/2026-05-02-gdpr-fase2-rls.md)
- **SQL-script:** [gdpr_fase2_rls.sql](gdpr_fase2_rls.sql) (klar til kørsel mod Supabase, med ROLLBACK-script)
- **Database-patch dokumenteret:** [docs/superpowers/gdpr_fase2_database_patch.md](docs/superpowers/gdpr_fase2_database_patch.md) — beskriver konkret edit i `_connect()` der skal følge med SQL'en
- **Status:** IKKE kørt. Kan blokere alle queries hvis aktiveret uden patch.

### Fase 3 — Anonymiserings-pipeline
- **Plan:** [docs/superpowers/plans/2026-05-02-gdpr-fase3-pipeline.md](docs/superpowers/plans/2026-05-02-gdpr-fase3-pipeline.md)
- **Modul:** [gdpr_pipeline.py](gdpr_pipeline.py) — fire entry points (`trigger_auto_anonymisering`, `anonymiser_sag`, `vurder_k_anonymitet`, `generer_anonymiserings_rapport`)
- **Tests:** [test_gdpr_pipeline.py](test_gdpr_pipeline.py) — **alle 7 tests bestået** mod produktions-DB:
  * Konstanter (K_TAERSKEL=5)
  * K-anonymitet på tom pulje (k=1, ikke OK at dele)
  * K-anonymitet med 4 kunstige mønstre (k=5, OK at dele)
  * `skriv_audit` indsætter korrekt række
  * `trigger_auto_anonymisering` finder 0 sager (korrekt — ingen har `anonymiseres_efter` sat endnu)
- **Status:** Modulet er IKKE koblet til appen. Det importeres ingen steder. Sikker at have liggende.

### Fase 4 — Cron-aktivering + UI
- **Plan:** [docs/superpowers/plans/2026-05-02-gdpr-fase4-cron-aktivering.md](docs/superpowers/plans/2026-05-02-gdpr-fase4-cron-aktivering.md)
- Indeholder konkrete kode-snippets til "Afslut sag"-knap, migration-script, fly.toml cron, admin-UI tab
- **Status:** Plan kun. Implementeres når Fase 2+3 er aktiveret.

### DPIA-dokument
- **Fil:** [docs/legal/DPIA-juriitech-PAX.md](docs/legal/DPIA-juriitech-PAX.md)
- Komplet udkast efter GDPR Art. 35-strukturen
- Markeret med `[REVIEW]` hvor jurist bør tjekke (fx retsgrundlag for Art. 9, CVR-nummer)
- **Status:** Udkast. Skal finpudses før det deles med kunder.

### Privatlivspolitik
- **Fil:** [/Users/mikkelhansen/juriitech-landing/privatlivspolitik.html](/Users/mikkelhansen/juriitech-landing/privatlivspolitik.html)
- Linket fra footer på [juriitech.com](https://juriitech.com)
- Designet matcher landing-stilen (Space Grotesk, indigo-orb, samme farve-palette)
- Indeholder: hvem er ansvarlig, hvilke data, hvor længe gemmes, sub-processors, sikkerhed, klagers rettigheder, klage til Datatilsynet, kontakt
- **Status:** Klar til at gå live. Pushed til main → Vercel auto-deployer.

## Hvad jeg IKKE har gjort (bevidst)

- **Aktiveret RLS på Supabase** — for risikofyldt uden dit review
- **Patchet `database._connect()`** — skal ske SAMTIDIG med RLS
- **Tilføjet cron-trigger** — ville begynde at anonymisere rigtige sager
- **Skrevet GDPR-tekst på disclaimer-siden** — først når pipelinen virker
- **Mergede `refactor/rag-fase-1` → `main`** — venter på dit OK
- **Ikke aktiveret Anthropic/Voyage AI DPAs** — du skal selv klikke gennem dashboards og bekræfte de er underskrevet

## Commits i nat

```
docs/superpowers/plans/2026-05-02-gdpr-fase2-rls.md
gdpr_fase2_rls.sql
docs/superpowers/gdpr_fase2_database_patch.md          → "Fase 2: RLS plan + SQL"
docs/superpowers/plans/2026-05-02-gdpr-fase3-pipeline.md
gdpr_pipeline.py
test_gdpr_pipeline.py                                   → "Fase 3: pipeline-modul + tests"
docs/legal/DPIA-juriitech-PAX.md
docs/superpowers/plans/2026-05-02-gdpr-fase4-cron-aktivering.md
juriitech-landing/privatlivspolitik.html
juriitech-landing/index.html (footer-link)
juriitech-landing/styles.css (footer-link styling)      → "Fase 4 plan + DPIA + privatlivspolitik"
MORNING-REVIEW.md (denne fil)
```

## Hvad du skal gøre i morgen tidlig

1. **Læs DPIA-udkastet** ([docs/legal/DPIA-juriitech-PAX.md](docs/legal/DPIA-juriitech-PAX.md)) og finpudsen `[REVIEW]`-markeringer
2. **Læs privatlivspolitikken** (åbn `https://juriitech.com/privatlivspolitik.html` efter Vercel har deployet) og bekræft at indholdet er korrekt
3. **Beslut om du vil aktivere Fase 2 (RLS)** — det kræver:
   - Backup af Supabase-DB
   - Manuel patch af `_connect()` i database.py
   - Kørsel af `gdpr_fase2_rls.sql`
   - Ny test for at verificere appen stadig virker
4. **Verificér Anthropic + Voyage DPAs** — gå til deres dashboards og bekræft underskrivelse
5. **Beslut om du vil aktivere Fase 3+4 (pipeline + cron)** — først hvis Fase 2 er stabil

## Forventet næste session

Hvis du godkender alt, kan vi i næste session:
- Aktivere Fase 2 forsigtigt (med backup + grundig test)
- Aktivere Fase 3 manuelt på én test-sag (ikke cron — manuel kald)
- Tilføje "Afslut sag"-knap (Fase 4.1)
- Først DEREFTER aktivere cron + GDPR-disclaimer-tekst

## Hvis noget er gået galt mens jeg sov

Hvis app-tjekket fejler eller noget ikke virker — det burde IKKE ske, fordi jeg ikke har deployet noget til prod i nat — men hvis det gør:

```bash
# Tilbageruk til før nat-arbejde
git log --oneline | head -10  # find sidste commit FØR nat
git reset --hard <hash>
fly deploy
```

Sidste committet til prod var `f01dd24` (GDPR Fase 1 verifikations-script). Alt efter det er kun branch-arbejde og ikke deployet.

---

God morgen ☕
