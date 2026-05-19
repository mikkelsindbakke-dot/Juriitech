# PAX Scaling-plan — hvad gør jeg når kunderne kommer?

Når PAX vokser fra prototype til produktion, skal du opskalere i takt
med belastningen. Denne guide forklarer **præcis hvad du gør, og
hvornår.** Læs den ovenfra og ned: hvert trin antager at de foregående
er på plads.

> **TL;DR — hvor er vi nu (2026-05-13):** Maskinen er `shared-cpu-4x:4gb`
> med worker-concurrency=3 + køsystem. Holder 5-10 samtidige kunder
> uden problemer. Næste skridt afhænger af hvor mange kunder I får.

---

## Indhold

1. [Niveau-oversigt — hvor presset er du?](#niveau-oversigt)
2. [Niveau 1: 1-10 samtidige (nuværende setup)](#niveau-1)
3. [Niveau 2: 10-30 samtidige (vertikal skalering)](#niveau-2)
4. [Niveau 3: 30-100 samtidige (horisontal skalering)](#niveau-3)
5. [Niveau 4: 100+ samtidige (regional + database-skalering)](#niveau-4)
6. [Hvordan ved jeg hvilket niveau jeg er på?](#monitoring)
7. [Hurtig-tjekliste i ord-form (kopiér til pung)](#tjekliste)

---

<a id="niveau-oversigt"></a>
## Niveau-oversigt

| Niveau | Samtidige analyser | Maskine | Worker-concurrency | Månedlig Fly-pris |
|---|---|---|---|---|
| **1** (nuværende) | 1-10 | 1× `shared-cpu-4x:4gb` | 3 | ~$15 |
| **2** | 10-30 | 1× `performance-4x:8gb` | 6 | ~$60 |
| **3** | 30-100 | 2-3× `performance-4x:8gb` | 6 pr. maskine | ~$120-180 |
| **4** | 100+ | Flere regioner + dedicated DB | 6 pr. maskine | $300+ |

**Vigtigt om "samtidige analyser":** Det er IKKE antallet af kunder
totalt. En kunde kan have din side åben i en time og lave EN analyse
hvert 10. minut. "Samtidige" betyder **antallet af analyse-kald der
kører på samme tid**. 100 kunder pr. dag = typisk 3-5 samtidige i peak.

---

<a id="niveau-1"></a>
## Niveau 1: 1-10 samtidige (nuværende setup — gratis så længe det varer)

**Dette er det setup vi har bygget.** Du behøver IKKE gøre noget før
en af disse triggers udløses:

### Triggers der betyder du skal flytte til Niveau 2

- ⚠️ **Kunder klager over ventetid > 10 minutter.** Kø-tid + analyse-tid
  går over 10 min når peak'en holder over længere tid.
- ⚠️ **Sentry-fejl: `fetch failed` eller `OOM`** dukker op igen.
  Det betyder maskinen er presset.
- ⚠️ **`fly logs` viser `Machine d8d441ec562358` reboot uden årsag.**
  Næsten altid OOM-killer i baggrunden.
- ⚠️ **Mere end 5 jobs i pg-boss-kø konstant.** Tjek med:
  ```sql
  SELECT COUNT(*) FROM pgboss.job
  WHERE state IN ('created', 'retry') AND name = 'foerstevurdering';
  ```

### Hvad du IKKE skal røre på Niveau 1

- ❌ Tilføj flere maskiner — overkill
- ❌ Skift database — Supabase Free/Pro klarer dette niveau let
- ❌ Tilføj CDN — Fly's anycast er nok

---

<a id="niveau-2"></a>
## Niveau 2: 10-30 samtidige (vertikal skalering — én maskine, mere muskel)

**Lavet for:** 50-200 kunder pr. dag, peak 10-30 samtidige analyser.

### Kommandoer (i rækkefølge)

**1. Opgradér maskinen:**

```bash
fly scale vm performance-4x --memory 8192 -a pax-juriitech-next
```

Det giver dig 4 dedikerede CPU-kerner (vs delte i `shared-cpu`) +
8GB RAM. Dedikeret CPU er VIGTIGERE end RAM her — AI-prompting og
embedding-beregning er CPU-tung, ikke memory-tung.

**2. Hæv worker-concurrency:**

```bash
fly secrets set PAX_WORKER_CONCURRENCY=6 -a pax-juriitech-next
```

Med 4 CPU og 8GB kan vi bekvemt køre 6 samtidige analyser (~700MB
peak pr. analyse × 6 = 4.2GB, masser luft).

**3. Opdatér `fly.next.toml`** så ændringen overlever fremtidige
deploys:

```toml
[[vm]]
  size = 'performance-4x'
  memory = '8gb'
```

**4. Opgradér Supabase Postgres:**

På [supabase.com/dashboard](https://supabase.com/dashboard) → Database
→ "Compute" → vælg **Small** (2GB RAM, 2 cores) eller **Medium** (4GB RAM,
4 cores). Default Free-tier er for lille til 30 samtidige analyser med
embeddings-tunge queries.

**5. Verificér med load-test:**

```bash
# Lokalt fra projekt-rod
python3 scripts/load_test.py --concurrency 10 --ny-input
```

Forventet: 10/10 success, ~3-5 min pr. analyse.

### Hvad du tjekker dagligt nu

- **Sentry**: nye fejl? Hvis ja, fix før det vokser
- **Fly metrics** (`fly dashboard`): CPU-load skal være < 80% i peak
- **Supabase logs**: ingen "out of memory" eller "connection limit"

---

<a id="niveau-3"></a>
## Niveau 3: 30-100 samtidige (horisontal skalering — flere maskiner)

**Lavet for:** 200-1000 kunder pr. dag, peak 30-100 samtidige analyser.

### Forskel fra Niveau 2

Vertikal skalering har en grænse: Fly's største `performance-16x`
har 16 CPU + 32GB. Når du nærmer dig den grænse, eller hvis du vil
have høj-tilgængelighed (én maskine kan dø uden nedetid), så er
det tid til **horisontal skalering** = flere maskiner.

### Kommandoer

**1. Skaler antal maskiner op:**

```bash
fly scale count 3 -a pax-juriitech-next
```

Fly opretter automatisk 2 ekstra maskiner med samme config. pg-boss
LISTEN/NOTIFY distribuerer jobs automatisk mellem dem — du behøver
ikke konfigurere noget.

**2. Skift fra `shared-cpu`-pool til dedikeret region:**

Hvis trafikken er primært dansk:

```bash
fly scale count 3 --region fra -a pax-juriitech-next
```

Hvis I får tysk/EU-trafik, tilføj `ams` eller `lhr`:

```bash
fly scale count 3 --max-per-region 2 --region fra,ams -a pax-juriitech-next
```

**3. Tilføj Sentry release-tracking:**

På dette niveau skal du KUNNE finde ud af hvilken maskine en fejl kom
fra. Sentry's release-tracking + Fly-tags hjælper:

```bash
# I deploy-script tilføj:
fly deploy --build-arg SENTRY_RELEASE=$(git rev-parse HEAD) ...
```

**4. Konfigurér Postgres connection pooling:**

På Supabase → Settings → Database → Connection Pooler — sikr dig at
**Transaction mode** (port 6543) er aktiveret og at PoolSize er
mindst `antal_maskiner × 10`.

**5. Database — Supabase Pro (eller Team)**

For 30-100 samtidige analyser med embeddings:
- Mindst **Large** compute (8 cores, 16GB RAM)
- ~$45-90/mnd via Supabase
- Aktivér **read replicas** for `mine_dokumenter` og `analyse_arkiv`-
  queries hvis read-load er højere end write-load

### Nye monitoring-krav

- **pg-boss kø-længde alarm**: hvis kø > 50 jobs i 5 min, send notifikation
- **Per-tenant kvota**: implementér rate-limit pr. tenant (fx 10 analyser
  i timen) — én kunde må ikke kunne hamre alles latency op
- **Anthropic-rate-limits**: ved 100 samtidige Claude-kald kan du ramme
  Anthropic's RPM-limit. Bed dem hæve via [billing@anthropic.com](mailto:billing@anthropic.com)

---

<a id="niveau-4"></a>
## Niveau 4: 100+ samtidige (geo-distribution + dedikeret DB)

**Lavet for:** 1000+ kunder pr. dag, eller multi-tenant SaaS med
forskellige selskaber.

På dette niveau er det IKKE længere "tilføj én ting" — det er en
arkitektur-revision. Disse er principperne:

### Database

- Migrér væk fra Supabase (har øvre grænse) til **dedikeret Postgres**
  (AWS RDS, GCP Cloud SQL, eller selvhostet på Fly med volumes)
- Separat database for **embeddings** (pgvector) vs **transactional**
  data — embeddings er læse-tung og kan caches
- Pgvector → overvej dedikeret vector-DB (Pinecone, Qdrant, Milvus)
  hvis embeddings overstiger 1M rows

### Geo-distribution

- Multi-region Fly-deploy: `fra`, `ams`, `lhr` for EU; `iad`, `sjc`
  for US (hvis I går international)
- Hvert region har eget pg-boss-instans (ellers cross-region LISTEN/NOTIFY
  bliver langsom)
- Sticky-routing pr. tenant så samme kunde altid rammer samme region
  (cache-effektivitet)

### AI-cost-optimization

- Cache identiske analyse-resultater (idempotency-cache er allerede
  bygget; udvid TTL fra 1 time til 24 timer for read-heavy patterns)
- Brug **Claude Haiku** til klagepunkt-udledning og indledende kategorisering;
  forbeholdt **Sonnet** til den endelige strukturerede analyse — 5-10x
  billigere uden mærkbar kvalitetstab
- Prompt-caching: bevidst genbrug system-prompts på tværs af kald — Anthropic
  giver 90% rabat på cached input. Vi har allerede infrastruktur til dette
  (`tests/test_prompt_caching.py`).

### Team-skala

- Dedikeret on-call rotation
- Status-side ([status.juriitech.com](https://status.juriitech.com)) med
  uptime-monitoring
- Postmortem-disciplin for hver incident > 5 min nedetid

---

<a id="monitoring"></a>
## Hvordan ved jeg hvilket niveau jeg er på?

Tjek disse tal én gang om ugen (eller bygget ind i admin-dashboardet):

### Daglige målinger

```sql
-- Antal analyser de sidste 7 dage
SELECT date_trunc('day', oprettet) AS dag, COUNT(*)
FROM analyse_jobs
WHERE oprettet > NOW() - INTERVAL '7 days'
GROUP BY dag
ORDER BY dag DESC;

-- Peak samtidige jobs
SELECT date_trunc('hour', oprettet) AS time, COUNT(*) AS samtidige
FROM analyse_jobs
WHERE status IN ('running')
GROUP BY time
ORDER BY samtidige DESC
LIMIT 10;
```

### Tommelfingerregler

| Tal pr. uge | Niveau du er på |
|---|---|
| < 50 analyser | Niveau 1 ✓ |
| 50-300 analyser | Niveau 1, monitorér nøje |
| 300-1500 analyser | Tid til Niveau 2 |
| 1500-5000 analyser | Niveau 3 |
| > 5000 analyser | Niveau 4 |

### Røde flag (uanset niveau)

- **p95-latency > 10 min** = brugere føler det er ødelagt
- **Fejlrate > 2%** = noget systemisk er galt
- **Database CPU > 80% i peak** = upgrade NU
- **Anthropic-credits brugt > 80% af budget** = hæv før Anthropic
  bremser dig automatisk

---

<a id="tjekliste"></a>
## Hurtig-tjekliste i ord-form

**Hvis kunderne klager over ventetid:**

1. Tjek `fly logs -a pax-juriitech-next | grep -E 'FAILED|fetch failed|OOM'`
   — er der fejl?
2. Tjek `fly dashboard` → CPU/RAM-load i peak
3. Tjek pg-boss-kø-længden (SQL ovenfor)
4. Hvis CPU > 80% eller kø > 10: **opgradér til Niveau 2**

**Hvis fly logs viser OOM eller reboot:**

1. Stop ny trafik et øjeblik: `fly scale count 1 -a pax-juriitech-next`
   (sætter på pause)
2. Verificér nuværende RAM via `fly status` → "Memory"
3. Opgradér via `fly scale vm performance-4x --memory 8192`
4. Genstart trafik: `fly scale count 1 -a pax-juriitech-next` (eller højere)

**Hvis Anthropic begynder at returnere `rate_limit_error`:**

1. Logind på [platform.claude.com/settings/limits](https://platform.claude.com/settings/limits)
2. Hæv monthly spend limit
3. Hvis du rammer RPM (requests per minute), kontakt Anthropic for
   tier-upgrade

**Hvis du ikke ved hvad fejlen er:**

1. Tjek Sentry-dashboard (link i `pax-next/.env.local`)
2. Filtrér på "Last 24h"
3. Sortér efter "Most common" — løs den top-fejl først
4. Hvis stadig uklart: kør `python3 scripts/load_test.py --concurrency 5`
   og se hvad der sker

---

## Hvad du IKKE skal gøre, uanset niveau

- ❌ **Skift væk fra pg-boss til Redis/SQS midt under skalering.** pg-boss
  klarer 1000+ jobs/min uden problemer. Skift først hvis du har målbart
  bevis for at det er flaskehalsen.
- ❌ **Optimér prompts uden A/B-test.** Du risikerer at gøre kvaliteten
  værre uden at vide det. Brug `eval`-suite (planlagt i `CLAUDE.md`)
  før du justerer prompts under skalering.
- ❌ **Tilføj nye features under skalerings-fasen.** Stabilitet > nye
  features når kunderne strømmer ind. Gem feature-arbejde til efter
  belastningen er stabil.
- ❌ **Ignorér Sentry-fejl du tror er "ikke kritiske".** Under skalering
  er det ofte de "små" fejl der vokser til store problemer.

---

## Hvor vi er nu (snapshot)

| | Status |
|---|---|
| Maskine | `shared-cpu-4x:4gb` (Fly Frankfurt) |
| Worker-concurrency | 3 |
| Database | Supabase Postgres (Default/Small) |
| Kø | pg-boss SESSION mode, port 5432 |
| Auth | Supabase Auth med dual-mode (cookies + Bearer JWT) |
| Monitoring | Sentry (Python + JavaScript projects), Fly metrics |
| Backup | Supabase automatisk (PITR 7 dage) |
| Verificeret kapacitet | 5-10 samtidige analyser uden problemer |

**Næste milepæl:** Når daglig analyse-volumen overstiger ~300/dag konsistent,
skal vi planlægge skift til Niveau 2.
