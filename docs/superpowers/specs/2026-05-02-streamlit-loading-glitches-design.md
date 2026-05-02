# Fjern loading-glitches i PAX (sidebar + SSO-flash)

**Status:** Spec, godkendt 2026-05-02
**Repo berørt:** `juridisk_assistent` (PAX)

## Mål

Eliminér to synlige loading-glitches der får appen til at virke uprofessionel:

1. **Sidebar-flash:** Ved cold load (særligt efter SSO fra dashboard) ser brugeren et split-sekund "app" + "Søg i arkivet" i venstre menu, før de bliver erstattet med de proper labels (Forside, Søg i arkivet, Gemte sager, Disclaimer).
2. **SSO-token-flash:** Når man klikker PAX i juriitech.com/dashboard, viser browser-URL'en `?sso_token=eyJhbGc...` (et langt JWT) i ~1 sek., samtidig med at Streamlit's default app-shell glimter, før `try_sso_login()` rydder URL'en og indlæser forsiden.

Begge skal være væk efter dette fix.

## Rod-årsag

Begge glitches har samme rod: app.py kører en kæde af bootstrap-trin (Sentry init, auto-load lov + anonymiseringsregler, auth-gate, SSO-validering) FØR `st.navigation()` og `st.set_page_config()` kalden — og indtil da bygger Streamlit selv en default-UI baseret på filsystemet.

Konkret bidrager to ting:
- `pages/1_Søg_i_arkivet.py` eksisterer som tom stub (efterladt da arkiv blev flyttet til rod). Streamlit auto-detecter `pages/`-mappen og bygger sidebar med filnavne ("app" fra app.py som entry, "Søg i arkivet" fra pages-filen).
- `st.set_page_config(page_title="juriitech PAX")` sættes først i `forside.py` — dvs. efter auth-gate. Indtil da er fanenavnet enten "app" eller URL'en.

## Tekniske ændringer

### Fix 1 — Slet `pages/`-mappen

- Slet `pages/1_Søg_i_arkivet.py` (filen er en tom kommentar — hele indholdet er allerede flyttet til `arkiv.py` på rod-niveau)
- Slet selve `pages/`-mappen så Streamlit's auto-discovery ikke trigger
- `st.navigation()` i app.py overtager helt fra første render

### Fix 2 — Flyt `st.set_page_config()` til app.py øverst

- Tilføj kald til `st.set_page_config(page_title="juriitech PAX", page_icon=None, layout="wide")` ALLERFØRST i app.py — før Sentry, før auto-load, før auth-gate
- Fjern det eksisterende kald i `forside.py:55-59` (Streamlit kaster fejl hvis `set_page_config` kaldes to gange — det skal være ét sted)
- Resultat: browser-fanen viser "juriitech PAX" fra første render

### Fix 3 — Loading-overlay under SSO-login

Når `?sso_token=...` er i URL'en (cold load fra dashboard), inject et fuldskærms-overlay i HEAD'en ALLERFØRST — før Streamlit's egen UI når at rendere. Overlayet dækker hele viewport med:
- juriitech-branding (wordmark "juriitech" i Inter, j i indigo som på landing)
- "Logger ind..." undertekst
- Subtil indigo-orb-animation som matcher landing-siden (visuel kontinuitet)

Når `try_sso_login()` er færdig og `st.rerun()` rydder URL'en, er sso_token væk → overlay vises ikke længere → forsiden er klar.

Implementering: blok øverst i app.py (efter `import streamlit as st` og before alt andet) der tjekker `st.query_params.get("sso_token")` og hvis sat, kalder `st.markdown(...overlay-html..., unsafe_allow_html=True)`. Overlayet er ren HTML+CSS (ingen JS) — fast position, høj z-index, fade-in animation.

CSS svarer til `.bg-orb` + `.wordmark` mønstret fra `juriitech-landing/styles.css` så overgangen fra dashboard føles som ÉN flow.

## Eksplicit ude af scope

- Ydeligere optimering af Streamlit's egen boot-tid (auto-load af lov + regler er allerede cached via `@st.cache_resource` — første cold start tager ~2 sek., subsekvente er instant)
- Cross-domain cookie-baseret SSO (token-i-URL er det vi har valgt; samme begrundelse som i juriitech-portal-spec)
- Browser-history rensning på dashboard FØR navigation (ville kræve to-trins redirect — overkill for det vi vinder)

## Test

Manuel browser-smoke-test efter deploy:
1. **Cold load af pax.juriitech.com** (ny inkognito-tab): sidebar viser "Forside, Søg i arkivet, Gemte sager, Disclaimer" fra første pixel — ingen "app"-flash. Browser-fanen viser "juriitech PAX" fra første render.
2. **Login → forside**: ingen sidebar-flash. Faneblad-titel uændret korrekt.
3. **Klik PAX i dashboard fra juriitech.com**: brugeren ser branded "Logger ind..."-overlay (ikke default Streamlit-shell, ikke URL-token-glimt). Overlay forsvinder cleant når forsiden er klar (~1 sek.).
4. **Cold load med URL-parameter `?sso_token=invalid`**: overlay vises, derefter falder appen tilbage til login-side når token-validering fejler (graceful).

## Beslutnings-historie

- **2026-05-02:** Bruger godkendte alle tre fixes. Bekræftede at der ikke er andre glitches at adressere i samme runde.
