# Norsk PAX — commit-plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Få det untrackede Norge-arbejde (scrapere, i18n, migration, test-sag generator) commitet i fire logiske bidder på `sikkerhed/fase-1-quick-wins` (nuværende branch), så koden er sikret i git-historik UDEN at risikere at brække dansk PAX-development.

**Architecture:** Commits laves på nuværende branch — IKKE på en separat `feat/norsk-pax`-branch. Begrundelse: 33 filer i pax-next importerer fra `@/lib/i18n/`, hvoraf flere er modificerede (uncommitted M-filer) på denne branch. Hvis i18n flyttes til en separat branch og vi switcher tilbage, ville i18n-mappen forsvinde fra working tree og M-filerne ville importere fra ikke-eksisterende stier — lokal dansk PAX ville være brudt. Sikker isolation er kun mulig hvis M-filerne også committes, hvilket er uden for denne plans scope.

Modificerede filer på sikkerheds-branchen forbliver uncommitted i working tree (de håndteres separat).

**Tech Stack:** git, ingen kode-ændringer — kun fil-organisering og commits.

---

## Inventory

**Norge-specifikke untrackede filer der SKAL commitsi (12 filer + 1 doc):**

```
norsk_pakkereiselov_scraper.py            ← Lovdata.no-scraper
scripts/migration_land_kolonne.py          ← DB ADD COLUMN land
scripts/scrape_norge_saksnummer.py         ← Playwright saksnr-scraper
scripts/scrape_pakkereise_no.py            ← (alternativ HTTP-scraper, v1)
scripts/download_norge_pdfs.py             ← PDF-downloader
scripts/ingest_norge_pakkereise.py         ← PDF→DB ingest
scripts/generer_norsk_test_sag.py          ← FjordTravel test-sag
pax-next/src/lib/i18n/config.ts            ← Locale-typer
pax-next/src/lib/i18n/t.ts                 ← Oversætter
pax-next/src/lib/i18n/client.tsx           ← React Context provider
pax-next/src/lib/i18n/dictionaries/da/*.json (9 filer)
pax-next/src/lib/i18n/dictionaries/no/*.json (9 filer)
docs/SKALERING-NYE-LANDE.md                ← Roadmap
```

**Skal IKKE commits (på denne branch):**
- `data_imports/` — 322 PDFs + state-fil, hører til `.gitignore`
- `scrape_state_no.json` — state-fil, gitignore
- `test-brugere-config.json` — uafhængigt, andet arbejde
- Alle andre `??`-filer fra `git status` — hører til andre features

---

## Task 1: Forbered .gitignore

**Files:**
- Modify: `.gitignore` (tilføj `scrape_state_no.json`, `data_imports/`)

- [ ] **Step 1.1: Verificer at vi er på sikkerhed-branchen**

Run: `git rev-parse --abbrev-ref HEAD`
Expected: `sikkerhed/fase-1-quick-wins`

- [ ] **Step 1.2: Opdater .gitignore for at ekskludere data_imports og state-fil**

Tilføj nederst i `.gitignore`:

```
# Norsk PAX — scrapede data + state-filer (lokal, ikke i git)
data_imports/
scrape_state_no.json
```

- [ ] **Step 1.3: Verificer at filerne nu er ignored**

Run: `git status --short | grep -E "(data_imports|scrape_state_no)"`
Expected: ingen output (filerne er ignored)

---

## Task 2: Commit DB-migration (foundation)

**Files:**
- Add: `scripts/migration_land_kolonne.py`

- [ ] **Step 2.1: Stage migration-scriptet**

Run: `git add scripts/migration_land_kolonne.py .gitignore`

- [ ] **Step 2.2: Verificer staging**

Run: `git status --short`
Expected: `A  scripts/migration_land_kolonne.py` + `M  .gitignore`

- [ ] **Step 2.3: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(norge): tilføj 'land'-kolonne migration på mine_dokumenter

Forbereder PAX til multi-land RAG. Idempotent ADD COLUMN med default
'DK' på eksisterende rækker, backup-flag og verifikation. Eksisterende
queries virker uændret indtil RAG-filteret opdateres til at filtrere
på land.

Allerede kørt mod prod-DB (kolonnen eksisterer, default='DK').

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Commit norske scrapere (officielle kilder)

**Files:**
- Add: `norsk_pakkereiselov_scraper.py`
- Add: `scripts/scrape_norge_saksnummer.py`
- Add: `scripts/scrape_pakkereise_no.py`
- Add: `scripts/download_norge_pdfs.py`
- Add: `scripts/ingest_norge_pakkereise.py`

- [ ] **Step 3.1: Stage scrapere**

```bash
git add norsk_pakkereiselov_scraper.py \
        scripts/scrape_norge_saksnummer.py \
        scripts/scrape_pakkereise_no.py \
        scripts/download_norge_pdfs.py \
        scripts/ingest_norge_pakkereise.py
```

- [ ] **Step 3.2: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(norge): scrapere for pakkereiseloven + Pakkereisenemnda

Henter norsk juridisk vidensbank fra officielle kilder:

  - Lovdata.no (LOV-2018-06-15-32 — Lov om pakkereiser og reisegaranti
    mv.): paragraf-niveau parsing, idempotent, embedder via Voyage
  - Reiselivsforum.no (Pakkereisenemndas afgørelser): Playwright-
    baseret saksnummer-scrape + stabile PDF-URL'er + pypdf-ekstrahering

Alle dokumenter gemmes med land='NO', is_public=TRUE — synlige for
norske tenants, usynlige for danske. Polite scraping: identificerende
User-Agent, 2-4 sek delay, resumable state.

Allerede kørt mod prod-DB: 311 afgørelser + 55 paragrafer ingested.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Commit i18n-system (norsk oversættelse runtime)

**Files:**
- Add: `pax-next/src/lib/i18n/config.ts`
- Add: `pax-next/src/lib/i18n/t.ts`
- Add: `pax-next/src/lib/i18n/client.tsx`
- Add: `pax-next/src/lib/i18n/dictionaries/da/*.json` (9 filer)
- Add: `pax-next/src/lib/i18n/dictionaries/no/*.json` (9 filer)

- [ ] **Step 4.1: Stage hele i18n-mappen**

Run: `git add pax-next/src/lib/i18n/`

- [ ] **Step 4.2: Verificer at alle 21 filer er staged**

Run: `git status --short pax-next/src/lib/i18n/ | wc -l`
Expected: `21` (3 .ts/tsx + 18 .json)

- [ ] **Step 4.3: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(i18n): runtime + ordbøger for norsk PAX (da + no)

Tenant-baseret sprog-overlay: når en bruger logger ind, læses
tenants.sprog ('da' eller 'no') og UI'et renderes på det sprog uden
flere kode-ændringer.

Arkitektur:
  - config.ts: Locale-typer (da | no | sv | de stubs), normalisering
    der mapper 'nb'/'nn' → 'no'
  - t.ts: deep-merge af 9 namespace-JSON-filer pr. locale, fail-safe
    fallback til dansk hvis nøgle mangler i norsk
  - client.tsx: React Context (LocaleProvider) + useT()-hook
  - 18 dictionary-filer (9 namespaces × 2 sprog): _base, upload,
    analyse, svarbrev, sager, arkiv, admin, auth, common

LocaleProvider er wired op på 8 ruter (/, /sager, /sager/[id], /arkiv,
/arkiv/[id], /admin/*, /login, /auth/set-password) i pax-next-appen.

Server-side beregner locale fra tenants.sprog via JOIN i
lib/queries/users.ts og propagerer den til LocaleProvider.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Commit test-sag generator + skalerings-doc

**Files:**
- Add: `scripts/generer_norsk_test_sag.py`
- Add: `docs/SKALERING-NYE-LANDE.md`

- [ ] **Step 5.1: Stage test-sag + roadmap**

```bash
git add scripts/generer_norsk_test_sag.py docs/SKALERING-NYE-LANDE.md
```

- [ ] **Step 5.2: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(norge): FjordTravel test-sag generator + skalerings-roadmap

generer_norsk_test_sag.py bygger sag-06-fjordtravel-norge med komplet
PDF-sæt (klage, FjordTravel.no-bookingbekreftelse, e-mail-tråd) til
test af norsk PAX-flow uden ekte kundedata. Sprog: norsk bokmål.
FjordTravel AS-tenant er oprettet i prod-DB (id=11, sprog=no, land=NO).

docs/SKALERING-NYE-LANDE.md dokumenterer trin-for-trin køreplan for at
lancere PAX i nye lande (Sverige, Norge, Tyskland, UK) — designet til
at kunne læses kold om 3-12 måneder uden session-kontekst.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Verifikation

- [ ] **Step 6.1: Bekræft 4 nye commits øverst**

Run: `git log --oneline -6`
Expected: 4 nye Norge-commits øverst, derefter `c2fc184` SSO-token-handler

- [ ] **Step 6.2: Bekræft at ingen Norge-filer er untracked længere**

Run: `git status --short | grep -iE "(norge|norsk|i18n|land_kolonne|SKALERING-NYE)"`
Expected: ingen output

- [ ] **Step 6.3: Bekræft at M-filerne stadig er uncommitted (urørte)**

Run: `git status --short | grep "^ M" | wc -l`
Expected: samme antal M-filer som før (pax-next-modifikationer og sikkerheds-modifikationer urørte)

- [ ] **Step 6.4: Bekræft at pax-next stadig kan importere fra @/lib/i18n**

Run: `ls pax-next/src/lib/i18n/config.ts pax-next/src/lib/i18n/t.ts pax-next/src/lib/i18n/client.tsx`
Expected: alle tre filer findes (de er nu trackede, men stadig i working tree)

- [ ] **Step 6.5: Rapporter til bruger**

Skriv en kort opsummering med:
- Antal commits + filer pr. commit
- Bekræftelse på at dansk PAX er urørt
- Forslag til næste skridt (push? hvad med M-filerne?)
