# juriitech PAX — Project Notes & Learnings

> **Til fremtidige Claude-sessions:** Læs denne fil før du foreslår større
> ændringer. Den indeholder den arkitektoniske kontekst + de konkrete
> learnings vi har bygget op gennem trial-and-error. Hvis du ser et
> mønster der kan tilføjes, så skriv det ind nederst — denne fil skal
> vokse løbende.

---

## Hvad projektet er

**juriitech PAX** er en dansk juridisk AI-assistent til rejseselskaber
(primært TUI) der håndterer klagesager ved **Pakkerejse-Ankenævnet**.
Brugeren uploader en klagesag (klageskema + bilag + sagsakter), og PAX
laver en automatisk førstevurdering inkl. præcedens-search i en
vidensbank af 500+ tidligere afgørelser, og kan generere et
færdigformateret svarbrev.

Hovedbrugeren er Mikkel (mikkelsindbakke@gmail.com), der bygger og
maintainer applikationen. Slutbrugerne er jurister/sagsbehandlere
internt hos rejseselskaberne.

---

## Stack

| Komponent | Teknologi |
| --- | --- |
| UI | Streamlit (multi-page) |
| AI | Anthropic Claude (`claude-sonnet-4-6`) via tool-use |
| Embeddings | Voyage AI (`voyage-multilingual-2`, 1024 dim) |
| Reranking | Voyage AI (`rerank-2`) |
| Database | Neon Postgres + pgvector (HNSW indexes) |
| Deploy | Fly.io |
| Fejl-monitoring | Sentry |

---

## Filer og ansvar

| Fil | Rolle |
| --- | --- |
| `app.py` | Streamlit entrypoint |
| `forside.py` | Hovedside — upload, analyse, dashboard |
| `ai_engine.py` | Alle AI-kald, RAG-orchestrering, prompt-bygning |
| `database.py` | Postgres I/O — sager, chunks, arkiv, gemte_sager |
| `embeddings.py` | Voyage wrapper — embed_dokument, embed_sporgsmaal, chunk_tekst, rerank |
| `processor.py` | Fil-upload — PDF/DOCX/billede-parsing |
| `ui.py` | Genbrugte UI-komponenter (thinking_fullpage, badges, kort osv.) |
| `eksport.py` | DOCX/PDF-generering af svarbreve |
| `gemte_sager.py` | Save/load sag-state |
| `arkiv.py` | Arkiv-side — søgning + visning af gemte analyser |
| `selskab_profiler.py` | Per-selskab branding (TUI, Apollo osv.) — læser fra DB |
| `auth.py` | Supabase Auth wrapper — login/logout/session/admin_invite_user |
| `admin.py` | Admin-side: tenants + brugere CRUD + invite-flow (KUN role='admin') |
| `bootstrap_admin.py` | Engangs-script til at oprette første admin-bruger |
| `diagnose_tenants.py` | Tenant-integritet diagnostic + auto-fix orphans |
| `scraper.py` | Pakkerejse-Ankenævn afgørelses-scraper |
| `pakkerejselov_scraper.py` | Lovgivning-scraper |
| `tui_scraper.py` | TUI-vilkår scraper |
| `backfill_embeddings.py` | Engangs-script til hele-dokument-embeddings |
| `backfill_chunks.py` | Engangs-script til chunk-embeddings (køres ved schema-opgradering) |

---

## Sprog-konventioner

- **All user-facing tekst er på dansk.** Det er en dansk juridisk app for danske jurister.
- **Variabler, funktioner, kommentarer er typisk på dansk** (`udled_sagsmetadata`, `find_relevante_chunks`, `vis_brugerfejl`). Følg det mønster — undgå at blande engelsk og dansk i nye funktionsnavne.
- **Filnavne er på dansk** når det giver mening (`forside.py`, `eksport.py`).
- **DEBUG-prints og loggene må gerne være på engelsk** (de læses primært af udvikleren).

---

## Learnings (kategoriseret)

### AI prompt engineering

**JSON-schema låser struktur.** Den enkelt-mest effektive ændring vi
har lavet var at skifte fra "bed AI om at følge markdown-overskrifter"
til "tving JSON-output via tool-use schema" (`udled_foerstevurdering_struktureret`).
Vi gik fra freestyle 14 sektioner til altid præcis 6.

**Force-mapper efter struktureret output.** Selv med JSON-schema kan
modellen emittere valid JSON med "kreative" labels. En post-processor
(`tving_struktur_til_seks_sektioner`) der mapper messy keys til
kanoniske sektion-navne fungerer som belt-and-suspenders.

**`max_tokens` afkorter tavst.** Tjek altid `stop_reason == "max_tokens"`
og lav et continuation-kald (`_faerdiggoer_hvis_afkortet`-mønstret) hvor
det delvise svar sendes tilbage som assistant-turn så modellen fortsætter.
Uden det får du svar der ender midt i en sætning.

**Eksplicitte anti-hallucinations-regler i system-prompten** ("OPFIND
ALDRIG et sagsnummer der ikke står i materialet") forbedrer
ekstraktions-kvalitet mærkbart. Vær specifik om hvad der må og ikke må
findes på.

**AI er ofte for forsigtig på simple ekstraktioner.** Sagsnummer, navne,
datoer, BELØB — selv med eksplicitte instruktioner returnerer modellen
tit tom streng eller "ukendt" "for en sikkerheds skyld". Backup ALTID
med en deterministisk regex-fallback (`_regex_find_sagsnummer`,
`_regex_find_beloeb`-mønstret).

**Når du giver AI'en et FOKUSERET uddrag, så husk at regex-fallback
skal scanne den FULDE tekst.** Vi havde fx beløb der manglede i match-
kortene fordi `udtraek_sagen_angaar` afkortede til 2500 tegn — og
beløbet stod ofte EFTER den grænse. Fallbacken slår det fulde dokument
op via filnavn/dokument_id og scanner hele teksten. Se
`opsummer_matches_til_visning` for mønstret.

**Brug `temperature=0` for ekstraktion og strukturerede opgaver.** Brug
højere temperature kun for kreative opgaver (svarbrev-formuleringer hvor
variation er ønsket). Vi bruger 0 alle steder vi vil have determinisme.

**Tool-use schema garanterer FELT-tilstedeværelse, ikke FELT-kvalitet.**
Selv med required=[felt_x], kan AI'en returnere felt_x med tomme/null/0
værdier. Når et felt SKAL have indholdsfulde værdier (fx
sandsynlighedsvurdering der summer til 100), skal man (a) eksplicit
nævne det i slutningen af user-prompten ("Returnér ALDRIG 0/0/0"),
(b) give et konkret eksempel-fordeling, og (c) tilføje en defensiv
fallback der detekterer den tomme case og kører et second-chance-kald.
Vi havde et tilfælde hvor sandsynlighederne kom som 0/0/0 — schemaet var
opfyldt men værdierne meningsløse. Se `udled_foerstevurdering_struktureret`
+ forside.py's `_alle_nuller`-check.

### RAG-arkitektur

**Én vektor pr. dokument = "find lignende sager". Chunks-pr-paragraf =
"find lignende argumenter".** Chunk altid for dokumenter længere end et
par sider. Dette var den enkeltstående største præcisionsforbedring.

**To-trins retrieval er industristandard.** Stage 1: bredt recall via
embedding + keyword. Stage 2: precision via cross-encoder reranker
(Voyage rerank-2). Hver alene giver okay resultater; begge sammen
giver markant bedre.

**Reciprocal Rank Fusion (k=60) er den simpleste måde at kombinere
heterogene rankings.** Score = sum over kilder af 1/(k + rank). Belønner
chunks der er højt rangeret i mindst én liste, ekstra belønning hvis i
begge. Ingen score-normalisering nødvendig.

**Voyage `input_type='document'` vs `input_type='query'`** — brug dem
korrekt. Embedding for ting der gemmes = `document`. Embedding for
spørgsmål der søger = `query`. Forskellen er ikke kosmetisk.

**Fine-tune ALDRIG for fakta-recall.** RAG vinder altid for memorerbar
viden — du kan citere kilden, ny scraping virker øjeblikkeligt, ingen
risiko for hallucination af ting modellen "har lært".

**HNSW indexes** for pgvector er gratis præcision-til-fart. Tag det
sekund ved tabel-oprettelse. Kør på cosine-distance med
`vector_cosine_ops`.

**Chunk-strategi for Pakkerejse-Ankenævn-afgørelser:** Kanoniske
sektion-overskrifter ("Klagens indhold", "Indklagedes bemærkninger",
"Nævnets bemærkninger og afgørelse", "Konklusion" osv.) er det
naturlige split-punkt. Fallback til paragraf-split for OCR-tekst hvor
formatering er ødelagt. Se `embeddings.chunk_tekst()`.

### Robusthed

**Lazy klient-init for alle eksterne API'er.** Voyage og Anthropic
klienter må ALDRIG initialiseres ved modul-import — manglende eller
ugyldig API-nøgle ville crashe hele appen. Init første gang funktionen
faktisk skal bruges, og returnér None hvis det fejler så kalderne
graceful kan håndtere det.

**Graceful fallback-kæde i hvert lag.** RAG: chunks → hele-dokument →
hent_alle_sager. AI-ekstraktion: AI → regex → tom streng. Embedding:
voyage → keyword-only. Systemet må aldrig gå fuldstændigt mørkt fordi
ét lag er nede.

**Idempotente schema-migrationer.** Brug `CREATE TABLE IF NOT EXISTS`
og `ADD COLUMN IF NOT EXISTS` i `opret_tabeller()` der køres ved hver
app-opstart. Ingen separate migration-scripts at huske — schema er
selvhealende.

**Bagudkompatible dict-former.** Når vi ændrer et data-format (fx fra
hele-dokument-dicts til chunk-dicts), så lad detektoren acceptere begge
former. Det er det der gør at vi kunne deploye chunk-pipelinen FØR
backfill var kørt — systemet faldt tilbage automatisk.

**Detekter via tilstedeværelse af nøgler, ikke via format-versioning.**
Eksempel: `er_chunk = "chunk_index" in sag and sag.get("chunk_index") is not None`
i `_byg_vidensbank_tekst`. Mere robust end at have en `format: "v2"`-felt
der nogle gange mangler.

### Streamlit-specifikt

**`st.rerun()` efter AI-kald hvis UI er skjult under analysen.** Hvis du
skjuler sektioner baseret på state der ændres i samme render som
AI-kaldet kører i, så forbliver de skjult indtil næste user interaction.
Tving en rerun lige efter AI'en er færdig (vi blev bidt af det med
upload-sektionen).

**Initialiser widget-state KUN hvis nøglen ikke findes.** `if key not in
st.session_state: st.session_state[key] = default`. Ellers overskrives
brugerens redigeringer ved hver rerun. Streamlit's widget-state ER
sandhed når widget'en først er oprettet.

**Cache dyre AI-kald i session_state pr. signatur.** Beregn et hash af
inputs (`sag_signatur`), brug det som nøgle. Uden cache kører dyre
AI-kald igen ved hver rerender — det er både langsomt og dyrt.

**`st.components.v1.html` kører i iframe og kan ikke blokere.** Lange
AI-kald hører hjemme i Python-tråden, ikke i iframe-konteksten. Brug
iframes til animation/timer/visualisering, ikke til kald der tager tid.

**Streamlit's segmented_control kan ikke have `index=`** ved
selection_mode="single" — den bruger session_state-værdien som default.

### Regex-faldgruber

**Capturing groups i ANCHOR-patterns flytter downstream group-numre.**
Hvis du har `r"Klagepunkt(er)?\s*:(.*)"` så kan `group(1)` være enten
"er" eller None — og `group(2)` er det du faktisk ville have. Brug
`(?:...)` for ankre og navngivne grupper `(?P<indhold>...)` for det du
faktisk vil have ud. Vi spildte timer på denne i `udtraek_sagen_angaar`.

**Test ALTID regex mod false positives.** En sagsnummer-regex skal IKKE
matche datoen `25-04-2026`. En telefon-regex skal ikke matche en pris.
Skriv en lille test-suite med kendte negative cases.

**Bredere anchor-ord = flere false positives.** I `_regex_find_beloeb`
fjernede vi anchors som "kompensation på" og "godtgørelse på" fordi
de optræder i BÅDE klagers påstand ("klager kræver kompensation på X
kr.") og Nævnets afgørelse ("Nævnet tilkender X kr. som kompensation
på..."). Brug KUN anchors der eksklusivt indikerer den ene side —
"Nævnet tilkender", "Indklagede skal betale", "Klagen tages til følge",
"forholdsmæssigt afslag svarende til" osv.

**Tillad lange ord-gaps i juridiske formuleringer.** Pakkerejse-
Ankenævn skriver typisk "Indklagede skal **inden 30 dage fra dato for
kendelsens forkyndelse** betale klageren X kr." — så 'skal' og
'betale' kan være 8+ ord fra hinanden. Brug `[\s\S]{0,150}?` (eller
tilsvarende char-baseret gap) i stedet for at kræve at ordene er
naboer.

**Pakkerejse-Ankenævn anonymiserer parts-navne.** I scrapede afgørelser
bliver firmanavne og personnavne erstattet med firkantede klammer-
labels: `[Rejsearrangøren]`, `[Klageren]`, `[Indklagede]`,
`[Fuldmagtshaveren]`, `[Arrangøren]`. Når du laver regex for subjekter/
objekter i afgørelserne, så accepter BÅDE klassiske ord ("Indklagede")
OG disse anonymiserede labels med valgfri klammer (`\[?Rejsearrangør(?:en)?\]?`).
Se `_regex_find_beloeb`'s SUBJEKT- og KLAGER_LABEL-konstanter.

**Brug specifikke struktur-mønstre når flere beløb optræder i én
afgørelse.** En typisk afgørelse indeholder fx 3.746 kr. (tilkendt),
2.500 kr. (sagsomkostninger til Ankenævnet) og 275 kr. (klagegebyr) —
plus klagers oprindelige krav. Stærkeste signal for tilkendt er
kombinationen "subjekt skal betale X kr. til [Klageren]" — den fanger
det rigtige beløb selv med flere kandidater i teksten.

**Detekter afvisning eksplicit — vis "Afvist" frem for "ukendt".**
Når en sag er afvist, er der intet tilkendt beløb, men "ukendt" er
misvisende — det får brugeren til at tro at vi ikke kunne udtrække
beløbet. Detekter i stedet kanoniske afvisnings-formuleringer
("Klagerens krav tages ikke til følge", "Klagen afvises", "Indklagede
frifindes" osv.) og sæt feltet til "Afvist". Se `_check_klagen_afvist`
i ai_engine.py.

**ILIKE i Postgres er case-insensitive ud af boksen** — du behøver ikke
selv at lower'e begge sider. Det er hurtigere og mere læseligt.

### Debugging & deploy

**`vis_brugerfejl` sender kun til Sentry, ikke stdout.** Det gør
`fly logs`-debugging frustrerende. Når du diagnosticerer en bug, så
tilføj midlertidigt et `print(traceback.format_exc())` så du kan se
fejlen i logs uden at åbne Sentry-dashboardet.

**Tro på loggene, ikke på tidsmæssig korrelation.** Hvis et nyt feature
shipper og noget andet brækker, så tjek logs FØR du panic-reverter. Vi
spildte fire reverts på et "nyt feature der brød ting" som i
virkeligheden var Anthropic-credits løbet tør + en ikke-relateret regex-
bug. Logs fortæller sandheden, timing er bare korrelation.

**Tag known-good versioner før risikable deploys.** `git tag v1.2.0`.
Så er revert én kommando: `git reset --hard v1.2.0 && fly deploy`.

**`fly logs --no-tail` til diagnose** når du leder efter en specifik
fejl. Tail-mode er til real-time debugging.

**Anthropic-credits løber tør tavst.** Symptom: AI returnerer tomt svar
på sekunder uden fejlmeddelelse i UI. Diagnose: `fly logs` viser
`'Your credit balance is too low to access the Anthropic API'`. Tjek
[https://console.anthropic.com/settings/billing](https://console.anthropic.com/settings/billing).

### Brugeroplevelse

**Lange AI-opgaver = fuld-side loading.** Vis tæller + forventet
varighed + beskrivelse af hvad der sker. Skjul al anden UI så brugeren
ikke scroller eller får tvivl om om noget er ved at ske. Se
`thinking_fullpage()` i `ui.py`.

**"Ryd sag" som rød knap, men diskret placeret.** Destructive actions
skal være visuelt distinkte men ikke fremtrædende — ellers trykkes de
ved et uheld. Bekræftelses-prompt før irreversible operationer.

**Spinners på alle handlinger der tager mere end 1 sekund.** Gem-knap,
slet-knap, AI-kald. Uden spinner tror brugeren appen er frosset.

**Auto-udfyld med graceful manual override.** Sagsnummer og klagers navn
auto-udledes via AI + regex-fallback, men feltet er stadig redigerbart.
Bedre at have noget brugeren kan rette, end intet at starte fra.

### Database / pgvector

**`register_vector(conn)` på hver forbindelse** — pgvector-typer er ikke
auto-registreret. Hvis du springer det over, returnerer Postgres
vektorer som strings.

**`vector(1024)` skal matche embedding-modellens dimension nøjagtigt.**
Hvis du skifter embedding-model, skal du re-embedde alt eller bruge en
ny kolonne. Voyage `voyage-multilingual-2` = 1024.

**`<=>` er cosine-distance i pgvector** (0 = identisk, 2 = modsat).
Sortér ASC for "mest relevante først". Konverter til similarity med
`1 - distance` hvis du vil vise scoren.

**`ON DELETE CASCADE`** for child-tabeller (chunks → mine_dokumenter).
Sletter du et dokument, ryger chunks med — ellers ender du med
forældreløse rækker.

**`ON DELETE RESTRICT`** for tenant_id FK'er. Vi vil ALDRIG accidentielt
slette en tenant og dermed miste alle deres sager — RESTRICT tvinger
admin til først at flytte/slette data manuelt. Kun chunks → dokumenter
bruger CASCADE fordi chunks er afhængige metadata.

**Param-ordering i SQL med flere %s placeholders.** psycopg2 substituerer
positionelt — så `params`-listen SKAL være i samme rækkefølge som
%s-placeholderne i SQL'en. Hvis SQL har en %s i SELECT (fx
`1 - (embedding <=> %s::vector)`), skal det være FØRSTE element i
params. Vi havde en bug i find_relevante_chunks hvor dokumenttype
kom først i params — psycopg2 prøvede at substituere strengen som
vector og funktionen returnerede [] silently (caught af except). Hele
chunk-pipelinen var stille død. Tjek altid at params-rækkefølge matcher
SQL-rækkefølgen, og brug navngivne params (`%(name)s`) for komplekse
queries.

**Tenant-isolation: explicit tenant_id-parameter på ALLE queries.**
Princip: hver query der rør private data SKAL kunne tage tenant_id
eksplicit (default = hent_aktiv_tenant_id()). Det giver ÉT sted at
verificere isolation, og test-scripts kan eksplicit teste cross-tenant
adgang. ALDRIG global state for tenant — det er for nemt at glemme
tilfilteringen. Se test_b1_isolation.py for det fulde testmønster.

---

## Etablerede mønstre i koden

Disse mønstre bruges flere steder; følg dem når du tilføjer ny funktionalitet:

**Lazy AI-klient init**
```python
_client = None
_client_init_fejlet = False

def _get_client():
    global _client, _client_init_fejlet
    if _client is not None: return _client
    if _client_init_fejlet: return None
    try:
        _client = SomeClient(api_key=...)
        return _client
    except Exception as e:
        print(f"DEBUG: ... fejlede: {e}")
        _client_init_fejlet = True
        return None
```

**AI-ekstraktion med regex-fallback**
```python
try:
    data = ai_extract(...)
    if not data.get("vigtigt_felt"):
        data["vigtigt_felt"] = regex_fallback(...)
    return data
except Exception:
    return {"vigtigt_felt": regex_fallback(...)}
```

**Strukturerede AI-svar via tool-use**
```python
schema = {
    "type": "object",
    "properties": {...},
    "required": [...]
}
response = client.messages.create(
    tools=[{"name": "udfyld", "input_schema": schema}],
    tool_choice={"type": "tool", "name": "udfyld"},
    ...
)
data = response.content[0].input
```

**Caching pr. signatur i session_state**
```python
sig = hash((input1, input2))
cache_key = f"resultat_{sig}"
if cache_key not in st.session_state:
    st.session_state[cache_key] = duer_funktion(...)
result = st.session_state[cache_key]
```

---

## Multi-tenant arkitektur (Phase A: gennemført, Phase B+C venter)

**Phase A — kode-refaktor (gennemført, v1.4.0–v1.6.0):**
Alle 152 hardcoded "TUI"-referencer på tværs af ai_engine.py, forside.py,
ui.py, badges.py, arkiv.py og vurdering.py er erstattet med opslag fra
`selskab_profiler.py`. For TUI-brugere er adfærden 100% bit-identisk.
Hvis AKTIV_PROFIL_KEY ændres til "apollo" eller "spies", producerer alle
prompts og UI-labels selskabs-specifik tekst. Se `MULTI_TENANT_ROADMAP.md`.

Mønstret for nye prompt-funktioner:
```python
from selskab_profiler import hent_navn
def min_prompt_funktion(...):
    _navn = hent_navn()
    prompt = f"... {_navn} ..."
```

Bevidst beholdt som STABILE INTERNE STRINGS (omdøb ikke uden koordineret
update i ui.py + forside.py):
  - Enum-værdier i tidsforhold: `positiv_for_tui`, `negativ_for_tui`,
    `tui_reaktion`, `klage_til_tui` — bruges som dict-keys i farve-rendering
  - Field-navn i sagsresumé: `tui_handtering` — bruges i UI-rendering
Suffixet `_tui` er HISTORISK; betydningen er nu generisk.

**Phase B1 — database + tenant-isolation (gennemført, v1.7.0):**
Tenants- og users-tabeller oprettet. tenant_id + is_public kolonner på
mine_dokumenter, analyse_arkiv, gemte_sager. Alle queries refaktoreret
til at filtrere på tenant_id (default = aktiv tenant via
hent_aktiv_tenant_id). Public docs (Pakkerejse-Ankenævn-afgørelser,
lovgivning, anonymiserings-regler) er is_public=TRUE og synlige for
alle tenants. Private docs (klage, vilkår, arkiv, gemte sager) er
isolerede pr. tenant. Cross-tenant slet/læs af andre tenants' data
afvises i database-laget.

selskab_profiler.py læser nu fra DB i stedet for hardcoded dict.
Aktiv tenant fastsættes stadig hardcoded ('tui') indtil B2/B3 (login).

Migration-script: migration_b1_tenants.py opretter TUI/Spies/Apollo
tenants + backfiller alle eksisterende data → TUI-tenant.
Cross-tenant isolation-test: test_b1_isolation.py opretter dummy-
tenants og verificerer alt er isoleret.

OBS bug fixet undervejs: find_relevante_chunks havde param-ordering
bug (passede dokumenttype som første %s i stedet for embedding-vector).
Det betød chunk-pipelinen returnerede [] silently og altid faldt
tilbage til hele-dokument-RAG. Nu fixet — chunks bruges som intended.

**Phase B2 — Supabase Auth integration (gennemført, v1.8.0):**
Login via Supabase Auth (email + password). Custom login-side i auth.py
med "Glemt adgangskode?"-flow. Session-state-baseret session-håndtering
(forsvinder ved tab-luk, brugeren logger ind igen — fint for B2).
Logout-knap i sidebar.

To-system-arkitektur:
  - Supabase Auth (extern): credentials, JWT, password-reset emails
  - Vores users-tabel (Neon): tenant_id, role, business metadata
Bro: supabase_user_id på vores users-row peger på Supabase Auth UUID.

Login-flow:
  1. Bruger taster email+password → auth.login_with_password()
  2. Supabase verificerer credentials, returnerer user+session
  3. _link_supabase_to_db_user() finder vores users-row:
     a) Først via supabase_user_id (returkunde)
     b) Hvis None: via email (første-gangs login efter invitation),
        og opdaterer rækken med UUID for fremtidige logins
     c) Hvis stadig None: brugeren er ikke inviteret → afvises
  4. st.session_state.user sættes med tenant_id + role + email + ...

Bootstrap-script: bootstrap_admin.py opretter mikkels admin-row i
users-tabellen (én gang efter B2 deploy). Mikkels Supabase-konto
oprettes manuelt via Supabase Dashboard (Add User med Auto confirm).

Defensive fallback: hvis SUPABASE_URL/ANON_KEY ikke er sat, springer
auth-gate over så lokal udvikling stadig virker. Produktion må have
secrets sat via 'fly secrets set'.

**Phase B3 — per-request tenant lookup (gennemført, v1.9.0):**
Aktiveringen af multi-tenant routing — det er nu rigtigt at sige at
forskellige brugere ser forskellige tenants. Tre konkrete ting:

  1. `hent_aktiv_tenant_id()` i database.py læser PRIMÆRT fra
     st.session_state.user.tenant_id (sat ved login). TUI-fallback
     bruges KUN i ikke-Streamlit kontekster (scripts, backfills).
  2. `selskab_profiler.hent_aktiv_profil()` følger samme mønster.
  3. Strammet logging: hvis fallback rammes UNDER en Streamlit-
     session, printes en WARNING — det er et tegn på at auth-gate
     er omgået eller session.user er korrupt.

Faktisk var logikken allerede pre-implementeret i B1 (vi byggede
session-aware lookup samtidig med tabellerne). B3 er derfor primært
en aktiverings-milestone + verifikation + diagnostic-værktøj.

Nyt værktøj: diagnose_tenants.py rapporterer tenant-fordeling pr.
tabel og auto-fixer 'orphaned' tenant_ids (rækker der peger på et
tenant_id der ikke længere findes — kan ske hvis migration_b1_tenants.py
køres flere gange og SERIAL-counter genstarter).

**Phase B4 — admin-side til tenant + bruger-management (gennemført, v2.0.0):**
Side kun for role='admin' (dobbelt access-control: skjult i nav for
ikke-admins + auth.is_admin()-check i top af admin.py). Tre tabs:

  1. **Tenants**: liste af eksisterende selskaber + opret/edit-formular
     med alle profil-felter (navn, slug, sagsbehandler, by, logo-upload,
     anonymiserings-suffix, interne team-navne, klageorgan, sprog,
     land, lov-navn). Slug kan IKKE ændres efter oprettelse.

  2. **Brugere**: liste af brugere pr. tenant — viser email, fulde
     navn, role, og om de har linket deres Supabase-konto.

  3. **Inviter ny bruger**: email + tenant + role formular.
     Kalder auth.admin_invite_user() der:
       a) Opretter row i vores users-tabel (uden supabase_user_id)
       b) Sender Supabase magic-link til email'en
       c) Når brugeren klikker linket og sætter password, kobles
          deres Supabase-UUID automatisk til vores users-row
          ved første login (via _link_supabase_to_db_user i auth.py).

Logo-upload: gemmes som static/logos/<slug>.png. OBS: Fly's disk
er ikke persistent på tværs af deploys — uploadede logoer skal
re-uploades efter deploy. Future work: migrer til persistent storage
(Fly volumes eller Supabase Storage).

Service_role-nøgle: bruges i auth._get_admin_client() til Supabase
Admin API. Kun til admin-operationer. Må ALDRIG eksponeres via UI
eller logs.

**Phase C — onboard nye selskaber (planlagt):**
Apollo, Spies osv. som rigtige tenants med egne profiler, scrapere og
vidensbank-segmenter.

## Ting vi IKKE har gjort (endnu) — bevidste fravalg

- **Strukturerede metadata-felter** (udfald, beløb, kategori, indklagede selskab) ekstraheret per afgørelse og lagret som kolonner. Ville muliggøre filtre som "find delvist-medhold-sager om manglende standard hvor TUI var indklagede". Stort men værdifuldt — venter på behov.
- **Unit-tests** — vi har ingen pt. Kører manuel smoke-test via `python3 -c "..."` og live-test i appen. Hvis projektet vokser, bør vi tilføje pytest.
- **Eval-suite for RAG-kvalitet** — vi har talt om at bygge en lille liste af 20-30 kendte sager med rette præcedens, så vi kan måle precision@5 efter ændringer. Gør det før den næste store retrieval-ændring.
- **Fine-tuning af Claude** — bevidst fravalgt. RAG er strukturelt bedre for fakta-recall.

---

## Konventioner for at opdatere denne fil

- **Tilføj nye learnings nederst i den relevante sektion.** Hvis kategorien ikke findes, opret en ny.
- **Beskriv konkret WHAT der virker, ikke bare HVAD der gjorde ondt.** "Brug navngivne grupper i regex" er bedre end "regex er svært".
- **Reference koden hvor det er relevant** — fil + funktionsnavn (`embeddings.chunk_tekst`).
- **Hvis et tidligere learning viser sig forkert, så ret det — ikke tilføj et "men faktisk..." nedenunder.** Filen skal være sand på læsetidspunktet.
- **Hold en lærdom kort — 1-3 sætninger.** Hvis det fylder mere, hører det måske til i en separat docs-fil.
