@AGENTS.md

# pax-next — arkitekturnoter

> **Til fremtidige Claude-sessions:** Dette projekt er et Next.js-frontend
> oven på den eksisterende Streamlit-PAX. Frontenden snakker via en
> FastAPI-bro (`api/main.py`) ind i delt Python-business-logic
> (`ai_engine.py`, `processor.py`, `eksport.py` osv.). Læs også rod-projektets
> `CLAUDE.md` og `MULTI_TENANT_ROADMAP.md` før du foreslår større ændringer.

## Mappestruktur

```
src/
  app/             — App-router pages, server-actions
  components/      — Client + server React-komponenter
  lib/
    api-client.ts  — Central FastAPI-klient (p-retry + Zod-validering)
    queries/       — DB-queries (server-side)
    supabase/      — Auth + cookie-mgmt
```

## Konventioner

- **Alt user-facing tekst er på dansk.** Variabel-/funktionsnavne også
  primært på dansk når det giver mening (`håndterAnalyse`, `valgteFiler`).
- **DEBUG-prints og logs gerne på engelsk** (de er for udvikleren).
- **Server Components** er default. Client-only når det kræves
  (formularer, fetch, useState). Marker eksplicit med `"use client"`.

## Lange AI-kald: brug api-client

Alle fetch-kald til FastAPI-broen GÅR igennem `lib/api-client.ts`:

```ts
import { postOgValider, foerstevurderingSchema, ApiError } from "@/lib/api-client";

const data = await postOgValider("/api/foerstevurdering", foerstevurderingSchema, {
  formData,
  retries: 3, // 3 = default for lange kald, 2 for korte
});
```

Det giver dig automatisk:
1. **p-retry med eksponentielt backoff** (1s → 2s → 4s) på 5xx-fejl.
   4xx wraps som AbortError så p-retry stopper med det samme.
2. **Zod-validering** af responsen på fetch-grænsen. Schema-mismatch
   eskaleres som `ApiError` der ikke retry'es (programmer-fejl).
3. **Fælles ApiError-klasse** med `(status, detalje)` så fejl-toasts
   kan skrives ensartet.

Fejl-håndtering pattern:

```ts
try {
  const data = await postOgValider(...);
  // ...
} catch (e) {
  if (e instanceof ApiError) {
    toast.error(e.detalje ? `${e.message}: ${e.detalje.slice(0, 100)}` : e.message);
  } else {
    toast.error(`Uventet fejl: ${e instanceof Error ? e.message : "ukendt"}`);
  }
}
```

## Skemaer i api-client

Bevidst KONSERVATIVE — bruger `.passthrough()` og `.optional()` så små
backend-tilføjelser (nye metadata-felter osv.) ikke breaker frontenden.
Kun KRITISKE felter (svarbrev-string, metadata.tegn osv.) håndhæves
strengt.

Tilføj nye skemaer her, ikke ad hoc i komponenterne. Komponenter skal
kun importere skema + funktion fra api-client.

## Loading states

| Type | Brug | Eksempel |
|---|---|---|
| `useTransition` + button-pending | Korte/medium handlinger (1-30 sek) | Slet-knapper, gem-sag |
| Indeterminate animeret bar | AI-kald uden tids-estimat (60-90 sek+) | `<AnalyseProgress>` i upload-form |
| `loading.tsx` skeleton | Server-componentet henter DB-data | `/sager`, `/arkiv`, `/admin` |
| `<Skeleton>` primitive | Inline-pladsholdere | `components/ui/skeleton.tsx` |

**Vi bruger IKKE tids-baserede progress-bars med procent.** Vi har
ingen real-time feedback fra Anthropic, så enhver procent ville lyve.
Indeterminate animeret bar er det ærlige valg.

## Toast-konventioner

Sonner er valgt (allerede installeret). Mønstre:

```ts
toast.success("Sagen er gemt")              // ✅ kort, præsens
toast.error("Kunne ikke nå API'en")         // ✗ aktiv, brugeren kan handle
```

Undgå:
- Lange toasts (>80 tegn) — de overlever ikke sin egen lifecycle
- Toast for trivielle handlinger (validering på Enter osv.)
- Stack af toasts ved fejl — én tydelig fejl > tre nuancer

## Prefetching

Next.js `<Link>` auto-prefetcher viewport-synlige links. Vi tilføjer
KUN eksplicit `router.prefetch()` for ruter der er forudsigelige men
ikke umiddelbart synlige — fx `router.prefetch("/arkiv")` lige efter
en svarbrev-/tjekliste-success, fordi brugeren typisk navigerer dertil
bagefter.

Brug ALDRIG raw `<a href="/...">` til interne links — det breaker
prefetch og client-side routing.

## Bevidste fravalg (revurdér ved behov)

**`useOptimistic`** — fravalgt i denne fase.

> Begrundelse: Næsten alle vores handlinger er "send fil → vent 60s →
> modtag stort resultat". Det er ikke et optimistisk-UI-mønster.
> Marginale steder (tilføj instruks, gem sag) føles allerede instant
> via lokal state. Risikoen for inkonsistent state ved server-fejl
> opvejer ikke gevinsten lige nu.

Revurdér hvis vi tilføjer realtidssamarbejde, kommentar-tråde, eller
andre handlinger hvor brugeren har brug for instant feedback FØR
serveren har bekræftet.

**Session-persistence til Supabase med debouncing** — venter.

> Kræver schema-design (hvad persistes? kun analyse? hele sagsstaten?)
> + konflikt-håndtering (to faner åbne, samme bruger). For risikabelt
> til natlig autonom kørsel.

Når det skal implementeres: skriv plan først, valider med Mikkel.

## Bekræftet paritet med Streamlit-PAX

`/api/svarbrev` (Next.js-flow) og `forside.py`'s svarbrev-knap (Streamlit-
flow) kalder samme `ai_engine.generer_svarbrev_til_sag` med IDENTISKE
argumenter:

- `sag={"filer": parsed_filer}` med samme `_laes_fra_bytes`-output
- `sagsakter`-streng
- `ekstra_instrukser`-streng formateret som `"- instr1\n- instr2\n..."`
  (begge UI'er joiner samme måde)
- `inkluder_kildehenvisninger` bool
- `verificerede_klagepunkter` list[str] eller None
- `tidsforhold` dict eller None

DOCX-rendering bruger `eksport.svarbrev_til_docx` i begge. Hvis
output drifter fremover, ligger forskellen IKKE i kald-laget — kig i
`ai_engine.generer_svarbrev_til_sag` selv.
