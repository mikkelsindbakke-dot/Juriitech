# juriitech portal — central login + program-overblik

**Status:** Spec, godkendt 2026-05-02
**Repos berørt:** `juriitech-landing` (Vercel, static HTML) + `juridisk_assistent` (Streamlit, Fly)

## Mål

Etabler `juriitech.com` som **portalen** for hele juriitech-platformen. Brugere logger ind ét sted, ser et overblik over de programmer de har adgang til, og klikker direkte ind i det valgte program uden at logge ind igen.

I dag har juriitech.com en marketing-forside med en "Log ind"-knap der peger direkte på en Streamlit-app. Det er en blindgyde for fremtidig udvidelse: når Program 2 og 3 kommer til, har brugeren brug for et sted at vælge mellem dem. Den side bygger vi nu.

## Stack-konstanter

| Komponent | Stack | Hosting |
|---|---|---|
| `juriitech.com` portal | Vanilla HTML + CSS + JS, Supabase JS SDK via CDN | Vercel |
| `pax.juriitech.com` | Streamlit (eksisterende) | Fly.io |
| Identity provider | Supabase Auth (eksisterende, ét shared projekt) | Supabase |
| Bruger-data | Supabase Postgres `public.users` (eksisterende) | Supabase |

**Bevidst fravalg:** Ingen Next.js / framework-migration. Den nuværende statiske side er 50 linjer HTML + 228 linjer CSS, og det er en feature, ikke en mangel. Vi tilføjer to nye sider og én JS-fil i samme stil.

## End-to-end brugerflow

### Førstegangs login

1. Bruger besøger `juriitech.com` → klikker **"Log ind"** øverst til højre
2. Lander på `juriitech.com/login` — email + password-form
3. JS validerer mod Supabase Auth, gemmer JWT i localStorage på `juriitech.com`
4. Auto-redirect til `juriitech.com/dashboard`

### Dashboard

1. `dashboard.html` checker session-state via JS ved load. Hvis ingen session → redirect til `/login`
2. Viser velkomst + ét eller flere program-kort
3. Hvert kort har titel, beskrivelse og en **"Åbn"**-knap

### Klik fra dashboard ind i et program

1. Bruger klikker "Åbn" på PAX-kortet
2. JS på dashboard'et henter `refresh_token` fra Supabase-sessionen
3. Konstruerer URL: `https://pax.juriitech.com/?sso_token=<refresh_token>`
4. Bruger redirectes; PAX's `auth.py` ser `sso_token`, bytter den til en gyldig session hos Supabase, etablerer `st.session_state.user`, fjerner token fra URL og kører
5. Bruger lander direkte i PAX's forside — **ingen ekstra login**

### Logout

- "Log ud"-knap i dashboard-headeren — kalder `supabase.auth.signOut()`, rydder localStorage, redirecter til `juriitech.com`
- Logout fra inde i PAX (eksisterende sidebar-knap) virker som hidtil — afmelder kun den lokale Streamlit-session, ikke juriitech.com (acceptabelt; bruger-symmetri kan tilføjes senere)

## Komponenter

### `juriitech-landing/` (ny + udvidet)

**Nye filer:**

- `login.html` — Login-form. Felter: email, password. "Glemt password?"-link der kalder `supabase.auth.resetPasswordForEmail()`. Fejl vises inline. Auto-redirect til `/dashboard` ved succes.
- `dashboard.html` — Auth-gated. Hvis ikke session → redirect til `/login`. Viser bruger-email i headeren + "Log ud"-knap. Liste over programmer som hardcoded array i JS (én entry: PAX).
- `auth.js` — Vanilla JS-modul. Eksporterer:
  - `getSupabase()` — initialiserer klient med URL + anon-key fra hardcoded constants
  - `getSession()` — returnerer aktuel session eller null
  - `requireSession()` — redirect til /login hvis ikke authenticated
  - `signIn(email, password)`, `signOut()`, `resetPassword(email)`
  - `buildSsoUrl(programUrl)` — konstruerer `?sso_token=...`-URL til klikbare program-links

**Udvidet fil:**

- `index.html` — `"Log ind"`-knappens `href` ændres fra `https://juriitech.streamlit.app` til `/login`. Også: hvis bruger allerede er logget ind (JS check ved load), skift "Log ind" til "Til dashboard" og peg på `/dashboard`.
- `styles.css` — Tilføj klasser til login-form, dashboard-layout, program-kort. Genbruger eksisterende farvepalette + Inter-font.

### `juridisk_assistent/auth.py` (udvidet)

Tilføj `sso_token`-handler ved siden af eksisterende `token_hash`-handler (linje-niveau bestemmes ved implementering — formodet i `_proces_query_param_token()` eller tilsvarende):

1. Læs `st.query_params.get("sso_token")`
2. Hvis tilstede: validér token mod Supabase via `set_session()` eller `refresh_session()` (præcis API afgøres ved implementation — Python supabase-py SDK har begge)
3. Slå email op i `public.users` via eksisterende `_link_supabase_to_db_user()` (genbruges 1:1)
4. Sæt `st.session_state.user`
5. `st.query_params.clear()` for at fjerne token fra URL'en (sikkerhed + clean look)
6. `st.rerun()` så forsiden vises clean

**Eksisterende `_link_supabase_to_db_user()` genbruges helt** — vi laver kun en ny indgangsvej til samme funktion.

## Sikkerhed

- **Anon-key i JS:** Standard for Supabase JS SDK (anon-key er offentlig efter design — RLS i Supabase håndhæver tilgangskontrol). Ikke en hemmelighed.
- **Token-via-URL:** Vi sender `refresh_token` (ikke `access_token`) i URL'en. Refresh tokens bytter Supabase straks til en ny session ved første brug, så selv hvis URL'en bliver logget i fx en proxy, er token'en kortlivet.
- **Token fjernes fra URL:** PAX's handler kalder `st.query_params.clear()` umiddelbart efter token er konsumeret, så browser-historik ikke beholder tokenen.
- **HTTPS only:** Begge domæner er HTTPS. Vi sætter `Secure` flag på cookies hvis vi senere migrerer til cookie-baseret session.
- **Cross-origin:** `juriitech.com` og `pax.juriitech.com` deler IKKE localStorage eller cookies. Det er bevidst — token-via-URL er den eneste vej. Hvis nogen flytter `pax`-app'en til et helt andet domæne (`pax.example.com`), virker SSO stadig uden config-ændring.

## Adgangskontrol — programmer pr. bruger

**Beslutning:** Hardcoded program-liste i `dashboard.html`'s JS for nu. Hver bruger der er logget ind, ser samme liste (i.e., PAX).

**Begrundelse:** YAGNI. Lige nu er der ét program, og alle brugere af platformen skal have adgang til det. Når Program 2 kommer til OG vi har brugere der kun har adgang til en delmængde, migrerer vi til en `user_program_access`-tabel i Supabase. Det er en isoleret refaktor (kun `dashboard.html` påvirkes) der kan laves uden at røre PAX eller portalen.

**Tabel-skema når den dag kommer (ikke nu):**
```sql
CREATE TABLE user_program_access (
    user_id UUID REFERENCES auth.users(id),
    program_slug TEXT,         -- 'pax', 'program2', ...
    role TEXT DEFAULT 'user',  -- 'user', 'admin'
    PRIMARY KEY (user_id, program_slug)
);
```

## Eksplicit ude af scope

- **Selvbetjent registrering** ("Opret konto") — i dag invitation-only via admin-siden i PAX, og det fortsætter. Login-siden viser INTET "Opret konto"-link.
- **Cross-domain cookies / cookie-baseret SSO** — token-via-URL er enklere og pålidelig nok.
- **Multi-faktor auth** — Supabase understøtter det, men vi aktiverer det ikke nu.
- **Per-program tilgang fra DB** — beskrevet ovenfor; ikke nu.
- **Migration væk fra Streamlit** — PAX bliver på Streamlit/Fly.
- **i18n** — alt er på dansk for now (matcher PAX).
- **Logout fra alle domæner samtidig** — logout fra dashboard logger kun ud af `juriitech.com`. PAX-session hos Streamlit lever videre til timeout. Symmetri kan tilføjes senere via en webhook-baseret invalidering.

## Test-strategi

PAX har historisk kørt uden unit-tests; portal'en arver det. Vi tester manuelt med følgende **smoke-tests** efter implementation:

1. **Anonym besøgende:** `juriitech.com` viser forside, "Log ind"-knap fungerer, fører til `/login`
2. **Login med korrekte credentials:** redirecter til `/dashboard`, viser PAX-kort
3. **Login med forkerte credentials:** viser fejlbesked, ingen redirect
4. **Klik på PAX-kort fra dashboard:** lander direkte i PAX uden ekstra login
5. **Direkte besøg af `pax.juriitech.com` uden session:** viser PAX's egen login (eksisterende adfærd)
6. **Logout fra dashboard:** rydder session, redirect til forside, ny "Log ind"-klik kræver password igen
7. **Direkte besøg af `dashboard.html` uden session:** redirecter til `/login`
8. **"Glemt password":** Supabase sender email, link fører til PAX's eksisterende `set_password.html`-flow (genbruges 1:1; vi bygger ikke en ny reset-password-side på portalen)

Hvis nogen af disse fejler i smoke-test, blokerer det deploy.

## Estimeret arbejde

| Komponent | Estimat |
|---|---|
| `login.html` + auth.js login-flow | 1-1.5 t |
| `dashboard.html` + program-kort + logout | 1 t |
| `styles.css` udvidelse (login + dashboard) | 30 min |
| `auth.py` SSO-handler i PAX | 1-1.5 t |
| Index.html opdatering ("Log ind" → /login + signed-in detection) | 15 min |
| Smoke-test gennem alle 8 scenarier | 30-60 min |
| **Total** | **~4-5 timer** |

## Beslutnings-historie

- **2026-05-02:** Spec godkendt. Tilgang A (portal på juriitech.com) frem for Streamlit-hub eller "alt-i-PAX". Hardcoded program-liste frem for DB-table. Token-via-URL SSO frem for cross-domain cookies. Stack: vanilla HTML + Supabase JS SDK via CDN.
