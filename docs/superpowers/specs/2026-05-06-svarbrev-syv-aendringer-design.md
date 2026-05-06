# Svarbrev — syv ændringer

**Dato:** 2026-05-06
**Status:** Design godkendt — afventer implementeringsplan
**Berørte filer:** `ai_engine.py`, `eksport.py`, `forside.py`, `ui.py`, `gemte_sager.py`, ny `svarbrev_diff.py`

---

## Formål

Syv målrettede forbedringer af svarbrevs-funktionaliteten i juriitech PAX, baseret på feedback fra daglig brug. Ingen af ændringerne kræver arkitektoniske refaktoreringer — alle er enten prompt-justeringer, små rendering-flytninger eller én enkelt ny UI-feature (diff-visning).

Ledende princip: **Bryd ikke noget der virker.** Eksisterende kald-signaturer bevares; nye parametre får default-værdier; LEGACY-stabile nøgler omdøbes ikke.

---

## De syv ændringer

### #1 — Antal nætter i resumé og svarbrev

**Hvor (tre steder):**
1. **Resumé-pillaren** (øverst på analyse-siden, vises altid) — `emne`-feltet i `udled_sagsresume_strukturelt` udvides med en sætning der inkluderer rejsedatoer + antal nætter. Eksempel: "Klage over poolens tilstand på Hotel X i februar 2026. Klager rejste den 4. februar og kom hjem den 10. februar, svarende til 6 nætter."
2. **Tidslinje-chip'en** (`Rejseperiode`-chip, rendres i `forside.py` omkring linje 2950) — udvides til "Rejseperiode: 8.-22. juni 2025 (6 nætter)".
3. **Svarbrevets faktum-afsnit** (DEL 2 i `byg_svarbrev_opgave`) — sætningen om udrejse + hjemrejse-dato udvides med "svarende til X nætter".

**Adfærd:** Når både udrejse- og hjemrejse-dato kan udledes, beriges teksten med "(svarende til X nætter)" eller "svarende til X nætter".

**Implementering — hybrid (Python + AI):**

Ny hjælpefunktion i `ai_engine.py`:
```python
def _beregn_antal_naetter(rejseperiode_str: str) -> int | None:
    """
    Parser strenge som '8.-22. juni 2025', '8. juni - 22. juni 2025',
    '08-06-2025 til 22-06-2025', '4. februar - 10. februar'.
    Returnerer (hjemrejse - udrejse).days, eller None hvis parsing fejler.
    """
```

- I `udled_sagsresume_strukturelt` (`ai_engine.py`): efter AI har returneret JSON, beregn nætter ud fra `tidsforhold.rejseperiode` (når tilgængeligt). Hvis tallet kan udledes, suppler `emne`-strengen med en sætning der inkluderer rejsedatoer + antal nætter. Format: "{eksisterende emne}. Klager rejste den {udrejse} og kom hjem den {hjemrejse}, svarende til {N} nætter." Funktionen får ny optional parameter `tidsforhold: dict | None` så den har adgang til datoerne. Kaldsteder i `forside.py` (omkring linje 2490) skal opdateres til at sende `tidsforhold` med.
- I `forside.py` ved rejseperiode-chip-rendering (omkring linje 2952): før chip'en bygges, beregn nætter ud fra `_rejseperiode`-strengen via `_beregn_antal_naetter`. Hvis tallet kan udledes, append "({N} nætter)" til chip-teksten.
- I `byg_svarbrev_opgave`: ny parameter `antal_naetter: int | None`. Når sat, injiceres det som autoritativt facit i faktum-afsnits-instruktionen, og AI'en bedes inkludere "(svarende til {N} nætter)" i den relevante sætning.
- `generer_svarbrev` og `generer_svarbrev_til_sag` udvides med samme parameter — beregnes lige før kald ud fra `tidsforhold.rejseperiode`.

**Edge cases:**
- Ikke parserbar dato → ingen "svarende til..."-tilføjelse, intet ændres.
- Hjemrejse < udrejse → returnér None (sjusk i kildedata; bedre at undlade end at vise "-3 nætter").
- < 1 nat → undlades (sjældent for pakkerejser; "0 nætter" lyder underligt).

---

### #2 + #5 — Brevstruktur: faktum-afsnit + Samlet vurdering

**Beslutning:** Det forudgående hånderingsafsnit (hvad TUI/rejseselskabet har gjort før nævnsbehandlingen) flyttes fra faktum-afsnittet ned i et nyt afsluttende afsnit kaldet **"Samlet vurdering"**.

**Ny brev-struktur fra top til bund:**
```
1. Indledning (én sætning, uændret)
2. Faktum-oversigt (3-6 sætninger)
   — fjern bullet om "allerede udbetalt kompensation"
   — fjern eksempel-formuleringen "...har forud for nævnsbehandlingen udbetalt..."
3. Juridisk vurdering (klagepunkterne, uændret struktur)
4. Samlet vurdering (NY — eksplicit overskrift)
   — Hvad rejseselskabet har gjort forud for nævnsbehandlingen
     (kontakt, evt. udbetalt kompensation, fremsatte tilbud osv.)
   — Selskabets samlede stilling til klagen
5. Med venlig hilsen
   [Sagsbehandler-navn]
6. Bilag-liste (flyttet — se #7)
```

**Implementering:** Kun prompt-ændringer i `byg_svarbrev_opgave`:
- DEL 2 FAKTUM-OVERSIGT-instruktionen renses.
- Ny DEL 4 "SAMLET VURDERING"-instruktion tilføjes — eksplicit krav om både overskrift og indhold.
- Strenge krav-listen og final tjekliste opdateres tilsvarende.

---

### #3 — Neutral tone (undgå "anerkender / beklager" som default)

**Beslutning:** Forbud som default; undtagelse hvis juristen aktivt beder om det via instruks-feltet.

**Implementering:** Ny sektion i `byg_svarbrev_opgave`-prompten:
```
NEUTRAL TONE — UNDGÅ ANERKENDELSER OG UNDSKYLDNINGER:
{REJSESELSKAB_NAVN} udarbejder dette svarbrev fordi selskabet er UENIG
med klagers krav. Brug derfor IKKE formuleringer der lyder som en
indrømmelse — Pakkerejse-Ankenævnet kan tolke dem som anerkendelse
af ansvar og hæve den tilkendte erstatning.

Undgå disse vendinger som default:
  • "anerkender at ..."
  • "beklager at ..."
  • "finder det beklageligt at ..."
  • "erkender at ..."
  • "er enig i at ..."
  • "vi forstår klagers frustration"
  • "vi tager kritikken til efterretning"

Beskriv i stedet faktuelt hvad der er sket — UDEN følelsesladede ord.
Eksempel:
  ❌ "Vi beklager at klager oplevede problemer med poolen."
  ✅ "Klager har anført at poolen ikke var åben i hele perioden."

UNDTAGELSE: Hvis brugerens særlige instrukser ovenfor EKSPLICIT beder
om at anerkende eller beklage et specifikt forhold (fx 'anerkend de
allerede udbetalte 2.000 kr.'), så følg den instruks. Bevidst
anerkendelse er strategisk legitim når juristen aktivt har valgt det.
```

---

### #4 — Hr. og Fru. Danmark-sprog

**Implementering:** Ny sektion i `byg_svarbrev_opgave`-prompten med 9 før→efter-eksempler:

```
SIMPELT SPROG — SKRIV SÅ ALLE FORSTÅR DET:
Brevet skal være formelt og juridisk præcist, men IKKE akademisk eller
opstyltet. Pakkerejse-Ankenævnets medlemmer er ikke alle jurister, og
brevet skal kunne forstås af "Hr. og Fru. Danmark".

Undgå akademiske/opstyltede vendinger — brug i stedet hverdagssprog:

  ❌ "de objektivt konstaterbare forhold"
  ✅ "det der faktisk er sket"

  ❌ "i nærværende sag"
  ✅ "i denne sag"

  ❌ "for så vidt angår"
  ✅ "om" / "med hensyn til"

  ❌ "henset til"
  ✅ "fordi" / "set i lyset af"

  ❌ "under hensyntagen til"
  ✅ "ud fra"

  ❌ "uagtet at"
  ✅ "selvom"

  ❌ "det forholder sig således at"
  ✅ "det er sådan at" / (skrives bare direkte)

  ❌ "der er ikke grundlag for at antage"
  ✅ "der er ingen grund til at tro"

  ❌ "påhviler det klager at godtgøre"
  ✅ "det er klagers opgave at vise"

Princippet: Hvis en ven der ikke er jurist kunne stoppe op og tænke
"hvad betyder det?", så skriv det om.
```

**Vigtigt:** Juridiske kerne-termer ("mangel", "rettidig reklamation", "forholdsmæssigt afslag", "pakkerejselovens § 22" osv.) bevares — det er fagsprog der SKAL være præcist. Reglen rammer kun pyntende, retoriske formuleringer.

---

### #6 — Diff-visning ved revisioner

**Beslutning:** Afsnits-niveau diff, sammenlignet mod forrige udkast (rullende vindue), beregnet i Python via `difflib`. Highlights vises kun i Streamlit-UI; Word/PDF-download er uændret.

**Datamodel** — `st.session_state.seneste_svarbrev` udvides:
```python
{
    "klage_filnavn": str,
    "ekstra_instrukser": str,
    "svarbrev": str,                    # nuværende udkast
    "forrige_svarbrev": str | None,     # NYT — det udkast der lige er blevet erstattet
    "udkast_nr": int,                   # NYT — 1 for første udkast, 2 efter første rev., osv.
}
```

**Genereringsflow** (i `forside.py`'s "Generer udkast"-knap):
- Hvis `seneste_svarbrev` er tom → første udkast: `forrige_svarbrev = None`, `udkast_nr = 1`.
- Hvis `seneste_svarbrev` allerede findes → flyt nuværende `svarbrev` til `forrige_svarbrev` før vi skriver det nye, og `udkast_nr += 1`.

**Diff-funktion** (ny `svarbrev_diff.py`):
```python
def afsnits_diff(gammel: str, ny: str) -> list[dict]:
    """
    Returnerer en liste af afsnit fra det NYE udkast, hver med:
      - tekst: str (afsnittet)
      - status: 'uændret' | 'ny' | 'ændret'

    Bruger difflib.SequenceMatcher på afsnits-niveau (split på \\n\\n).
    'Ændret' = afsnit der er væsentligt forskelligt fra et tilsvarende
    afsnit i gammel (similarity < 0.7).
    'Ny' = afsnit der ikke har en tilsvarende parring i gammel.
    """
```

**UI-rendering** (kun når `udkast_nr > 1`):
- Banner øverst: *"Udkast nr. {N} — ændringer siden forrige udkast er fremhævet."*
- Caption: "🟢 Nyt afsnit · 🟡 Ændret afsnit"
- Brevet rendres afsnit-for-afsnit:
  - Uændret → standard markdown
  - Ny → grøn baggrund (`background: #E7F5DD; border-left: 3px solid #76D672; padding: 8px 12px;`)
  - Ændret → gul baggrund (`background: #FFF8DC; border-left: 3px solid #F0C040; padding: 8px 12px;`)

**Word/PDF download — uændret.** `svarbrev_til_docx` kaldes med `seneste_svarbrev["svarbrev"]` (ren markdown). Diff lever kun i Streamlit-rendering.

**Persistering:** `_persist_aktuel_sag_til_db` og gem-/load-logik i `gemte_sager.py` skal også gemme + læse `forrige_svarbrev` og `udkast_nr`. Defaults ved load: `forrige_svarbrev = None`, `udkast_nr = 1`.

**Edge cases:**
- Genererer udkast 3 efter udkast 2 → diff vises mod udkast 2, ikke mod udkast 1 (rullende vindue).
- "Ryd sag" → nulstil `seneste_svarbrev` helt, inkl. nye felter.
- Sag genoptaget fra arkiv uden nye felter → defaults; ingen diff vises (`udkast_nr == 1`).
- Helt identisk udkast (intetsigende instruks) → alle afsnit som "uændret"; banner vises stadig.

---

### #7 — Bilagsoversigt flyttes til allersidst

**Beslutning:** Bilagsoversigten flyttes fra brevhovedet (lige under "Vedr."-linjen) til brevets allerbageste position — efter "Med venlig hilsen" og signaturen. Gælder både Word-eksport og forside-preview.

**Implementering:**
- `eksport.py`/`_byg_svarbrev_header`: stop med at rendre bilag-liste i headeren (parameter `bilag_liste` ignoreres her, eller fjernes).
- `eksport.py`/`svarbrev_til_docx`: efter brødteksten (efter "Med venlig hilsen" + signatur fra AI'ens output) tilføj spacer-paragraph + bilag-blokken via `_byg_bilag_liste`.
- `ui.py`/`render_svarbrev_forside_preview`: bilag-liste flyttes fra header-sektionen til bunden af preview, så preview matcher Word-output.

---

## Implementeringsrækkefølge (foreslået)

Fra lavest risiko + mest uafhængig til højere risiko + afhængig:

1. **#1 antal nætter** — isoleret prompt + Python-funktion, let at smoke-teste
2. **#3 + #4 sprogregler** — kun prompt-tilføjelser i én funktion
3. **#2 + #5 brevstruktur** — også prompt, men ændrer eksisterende struktur
4. **#7 bilag flyttes til bunden** — Word + preview-rendering, isoleret
5. **#6 diff-visning** — størst (ny feature, state, UI), bygges sidst når resten er stabilt

Mellem hvert trin: smoke-test ved at uploade en testsag og generere svarbrev manuelt.

---

## Bevarede aftaler (bagudkompatibilitet)

- Alle eksisterende parametre på funktioner bevares; nye parametre får default-værdier.
- LEGACY-stabile nøgler bevares uændret: `tui_handtering` i sagsresumé-dict.
- `seneste_svarbrev`-dict udvides kun (eksisterende felter er uændret).
- Graceful fallbacks:
  - Nætter ikke parserbare → ingen tilføjelse, brevet ser ud som i dag.
  - `udkast_nr == 1` → diff-rendering aktiveres ikke.

---

## Bevidste fravalg

- Ingen oprydning eller refactoring "mens vi er i gang" — fokus 100% på de 7 ændringer.
- Ingen ny abstraktion rundt om diff-rendering — rå funktion + lille CSS.
- Ingen unit-tests (matcher projektets nuværende stil).
- Ingen ord- eller karakter-niveau diff (afsnits-niveau matcher juridisk arbejdsgang bedre).
- Ingen historik over alle tidligere udkast — kun N vs. N-1 (rullende vindue).

---

## Risici

| Risiko | Mitigering |
|---|---|
| Prompt-ændring i `byg_svarbrev_opgave` påvirker utilsigtet andre dele af brevet | Smoke-test efter hvert prompt-trin på en testsag |
| Dato-parsing fejler på nye formater vi ikke har set | Graceful fallback til None — brevet generer fint uden tilføjelse |
| Diff-rendering bryder ved særlige markdown-konstruktioner (tabeller osv.) | Afsnits-split på `\n\n` er konservativt; markdown rendres pr. afsnit som i dag |
| `forrige_svarbrev` mangler efter sag-genoptagelse fra arkiv | Defensiv load med default `None`; så ingen diff vises (acceptabelt) |
| Bilag-liste i bunden ser klemt ud uden spacer | Tilføj eksplicit spacer-paragraph før bilag-blokken |
