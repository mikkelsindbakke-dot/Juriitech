# Streamlit loading-glitches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fjern de to synlige loading-glitches i PAX (sidebar-flash + SSO-token-flash) så app'en virker professionel fra første pixel.

**Architecture:** Tre uafhængige fixes i app.py + forside.py: (1) slet ubrugt `pages/`-mappe der trigger Streamlit's auto-discovery, (2) flyt `st.set_page_config()` til allerførste app.py-linje så page_title sættes før alt andet, (3) inject et juriitech-brandet fuldskærms-overlay når `?sso_token=...` er i URL'en så brugeren ikke ser default Streamlit-shell mens SSO behandles.

**Tech Stack:** Python 3.11+, Streamlit, Supabase Auth (refresh_token-via-URL), Fly.io deploy.

**Test-strategi:** Projektet har ingen pytest-suite (jf. CLAUDE.md "Vi har ingen pt — kører manuel smoke-test"). Tasks bruger manuel browser-verifikation efter hver ændring.

---

## File Structure

- **Modify:** `/Users/mikkelhansen/Desktop/juridisk_assistent/app.py` — flyt `st.set_page_config()` til top, tilføj SSO-loading-overlay
- **Modify:** `/Users/mikkelhansen/Desktop/juridisk_assistent/forside.py:55-59` — fjern duplikeret `st.set_page_config()`
- **Delete:** `/Users/mikkelhansen/Desktop/juridisk_assistent/pages/1_Søg_i_arkivet.py` (tom stub)
- **Delete:** `/Users/mikkelhansen/Desktop/juridisk_assistent/pages/` (tom mappe efter sletning ovenfor)

---

### Task 1: Slet ubrugt pages/-mappe

**Why:** Mens `pages/`-mappen eksisterer, auto-genererer Streamlit en default sidebar med "app" + "Søg i arkivet" baseret på filnavne. Den vises i ~0.5–2 sek. ved cold load FØR `st.navigation()` overtager. Hele indholdet er for længst flyttet til `arkiv.py` på rod-niveau.

**Files:**
- Delete: `/Users/mikkelhansen/Desktop/juridisk_assistent/pages/1_Søg_i_arkivet.py`
- Delete: `/Users/mikkelhansen/Desktop/juridisk_assistent/pages/`

- [ ] **Step 1: Verificér at filen er tom-stub**

Run: `cat /Users/mikkelhansen/Desktop/juridisk_assistent/pages/1_Søg_i_arkivet.py`

Expected: Kun en kommentar — "Denne fil er flyttet til rod-niveau som 'arkiv.py'…". Ingen kode at flytte.

- [ ] **Step 2: Verificér at intet andet refererer til pages/-mappen**

Run:
```bash
grep -rn "pages/1_Søg\|pages/\|from pages" /Users/mikkelhansen/Desktop/juridisk_assistent/*.py 2>/dev/null
```

Expected: Ingen matches (intet kode referer til pages-mappen).

- [ ] **Step 3: Slet filen og mappen**

Run:
```bash
rm /Users/mikkelhansen/Desktop/juridisk_assistent/pages/1_Søg_i_arkivet.py
rmdir /Users/mikkelhansen/Desktop/juridisk_assistent/pages
```

- [ ] **Step 4: Verificér slettelse**

Run: `ls /Users/mikkelhansen/Desktop/juridisk_assistent/pages 2>&1`

Expected: `ls: pages: No such file or directory`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
Fjern ubrugt pages/-mappe der trigger Streamlit auto-sidebar

pages/1_Søg_i_arkivet.py var en tom stub efterladt da arkiv-siden blev
flyttet til rod-niveau. Mappen fik Streamlit til at auto-generere
default-sidebar med "app" + "Søg i arkivet" ved cold load — synlig
i ~0.5-2 sek. før st.navigation() overtog.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Flyt st.set_page_config til app.py top

**Why:** Lige nu sættes `page_title="juriitech PAX"` først i `forside.py:55` — efter Sentry init, auto-load lov, auth-gate, SSO-validering. Browser-fanen viser derfor "app" eller URL'en indtil hele kæden er kørt. At flytte kaldet til allerførste linje i app.py betyder fane-titlen er korrekt fra første render. Streamlit kaster fejl ved dobbeltkald — derfor SKAL kaldet i forside.py fjernes samtidig.

**Files:**
- Modify: `/Users/mikkelhansen/Desktop/juridisk_assistent/app.py` (top — efter `import streamlit as st`)
- Modify: `/Users/mikkelhansen/Desktop/juridisk_assistent/forside.py:54-59`

- [ ] **Step 1: Tilføj st.set_page_config øverst i app.py**

Find blokken efter `from dotenv import load_dotenv` og før `load_dotenv()`-kaldet. Edit i app.py:

**Old (app.py:14-20):**
```python
import os
import streamlit as st
from dotenv import load_dotenv

# Indlæs miljøvariabler (inkl. ADMIN_KEY) før alt andet
load_dotenv()
_ADMIN_KEY = os.getenv("ADMIN_KEY", "")
```

**New (app.py:14-26):**
```python
import os
import streamlit as st
from dotenv import load_dotenv

# Sæt page-config ALLERFØRST. Skal ske før alt andet st.*-kald, ellers
# kaster Streamlit en fejl. Dette sikrer at browser-fanen viser
# "juriitech PAX" fra første render — ikke "app" eller URL'en mens
# resten af bootstrap kører (Sentry, auto-load, auth-gate).
st.set_page_config(
    page_title="juriitech PAX",
    page_icon=None,
    layout="wide",
)

# Indlæs miljøvariabler (inkl. ADMIN_KEY) før alt andet
load_dotenv()
_ADMIN_KEY = os.getenv("ADMIN_KEY", "")
```

- [ ] **Step 2: Fjern duplikeret st.set_page_config fra forside.py**

Edit `/Users/mikkelhansen/Desktop/juridisk_assistent/forside.py`:

**Old (forside.py:53-59):**
```python


# ---------- OPSÆTNING ----------
st.set_page_config(
    page_title="juriitech PAX",
    page_icon=None,
    layout="wide",
)
```

**New (forside.py:53-55):**
```python


# ---------- OPSÆTNING ----------
# st.set_page_config sættes nu i app.py øverst, så page_title er korrekt
# fra første render — ikke først efter auth-gate.
```

- [ ] **Step 3: Smoke-test lokalt at appen stadig starter**

Run:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python -c "
import ast
with open('app.py') as f: ast.parse(f.read())
with open('forside.py') as f: ast.parse(f.read())
print('SYNTAX OK')
"
```

Expected: `SYNTAX OK`

- [ ] **Step 4: Commit**

```bash
git add app.py forside.py
git commit -m "$(cat <<'EOF'
Flyt st.set_page_config til app.py øverst

Page_title var sat først i forside.py — efter Sentry, auto-load og
auth-gate. Browser-fanen viste derfor "app" indtil hele kæden var
kørt. At sætte det allerførst i app.py giver korrekt fane-titel fra
første render.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: SSO loading-overlay

**Why:** Når brugeren klikker PAX i juriitech.com/dashboard, navigerer browseren til `https://pax.juriitech.com/?sso_token=<lang JWT>`. Indtil `try_sso_login()` har behandlet tokenet og kørt `st.query_params.clear()` + `st.rerun()` (~1-2 sek.), ser brugeren default Streamlit-shell + URL-tokenet i adresse-linjen. Et fuldskærms-overlay der inject'es ALLERFØRST når `?sso_token=` er i URL skjuler hele Streamlit-shell'en mens SSO behandles, og falder væk automatisk når tokenet er ryddet og siden re-renderes.

**Files:**
- Modify: `/Users/mikkelhansen/Desktop/juridisk_assistent/app.py` (lige efter `st.set_page_config`-blokken fra Task 2)

- [ ] **Step 1: Tilføj overlay-blok i app.py**

Edit app.py — tilføj BLOK lige efter `st.set_page_config(...)` fra Task 2 og før `load_dotenv()`:

**Insert after st.set_page_config(...) closing paren and before "# Indlæs miljøvariabler":**

```python

# ---------- SSO LOADING-OVERLAY ----------
# Når brugeren klikker PAX i juriitech.com/dashboard, lander de her med
# ?sso_token=<refresh_token> i URL'en. Mellem at browseren parser HTML
# og at try_sso_login() har valideret tokenet + redirected, ser brugeren
# default Streamlit-shell + JWT-tokenet i URL'en. Vi inject'er et
# juriitech-brandet fuldskærms-overlay der dækker hele viewport indtil
# SSO er færdig (st.rerun() rydder URL'en → overlay vises ikke længere).
# Ren CSS, ingen JS — virker uanset om Streamlit-frontenden er færdig.
if st.query_params.get("sso_token"):
    st.markdown(
        """
        <style>
        @keyframes jt-fade-in { from { opacity: 0; } to { opacity: 1; } }
        @keyframes jt-orb-drift {
            0%, 100% { transform: translate(-50%, -50%) scale(1); }
            50%      { transform: translate(-50%, -52%) scale(1.04); }
        }
        @keyframes jt-spin {
            to { transform: rotate(360deg); }
        }
        #jt-sso-overlay {
            position: fixed;
            inset: 0;
            z-index: 999999;
            background: #FAF8F4;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont,
                         'Segoe UI', sans-serif;
            animation: jt-fade-in 0.2s ease;
            overflow: hidden;
        }
        #jt-sso-overlay .jt-orb {
            position: absolute;
            width: 62vw;
            height: 62vw;
            max-width: 880px; max-height: 880px;
            min-width: 420px; min-height: 420px;
            border-radius: 50%;
            background: radial-gradient(
                circle at 50% 50%,
                rgba(99, 102, 241, 0.20) 0%,
                rgba(99, 102, 241, 0.08) 35%,
                transparent 70%
            );
            filter: blur(40px);
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            pointer-events: none;
            animation: jt-orb-drift 18s ease-in-out infinite;
        }
        #jt-sso-overlay .jt-wordmark {
            position: relative;
            z-index: 1;
            font-size: clamp(3rem, 9vw, 6rem);
            font-weight: 800;
            letter-spacing: -0.055em;
            line-height: 0.95;
            color: #0A0B0F;
        }
        #jt-sso-overlay .jt-wordmark .j {
            color: #6366F1;
        }
        #jt-sso-overlay .jt-status {
            position: relative;
            z-index: 1;
            margin-top: 1.4rem;
            display: flex;
            align-items: center;
            gap: 0.7rem;
            color: #64748B;
            font-size: 1rem;
            font-weight: 400;
            letter-spacing: 0.01em;
        }
        #jt-sso-overlay .jt-spinner {
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 2px solid rgba(99, 102, 241, 0.25);
            border-top-color: #6366F1;
            animation: jt-spin 0.9s linear infinite;
        }
        /* Skjul Streamlit's default loading-spinner og evt. shell-elementer
           der måtte ligge bagved — overlay skal være ALENE på skærmen */
        [data-testid="stAppViewContainer"],
        [data-testid="stHeader"],
        [data-testid="stSidebar"] {
            visibility: hidden !important;
        }
        </style>
        <div id="jt-sso-overlay">
            <div class="jt-orb"></div>
            <div class="jt-wordmark"><span class="j">j</span>uriitech</div>
            <div class="jt-status">
                <span class="jt-spinner"></span>
                <span>Logger ind…</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

```

**Resulterende rækkefølge i app.py top:**
1. `import os, streamlit as st, dotenv`
2. `st.set_page_config(...)` (Task 2)
3. SSO loading-overlay (denne task)
4. `load_dotenv()` + `_ADMIN_KEY = ...`
5. Sentry init
6. Auto-load lov + regler
7. Auth-gate (incl. `try_sso_login()`)
8. `st.navigation(...)`

- [ ] **Step 2: Verificér syntaks**

Run:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python -c "
import ast
with open('app.py') as f: ast.parse(f.read())
print('SYNTAX OK')
"
```

Expected: `SYNTAX OK`

- [ ] **Step 3: Smoke-test lokalt — starter app'en?**

Run:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && timeout 10 python -c "
import sys
sys.path.insert(0, '.')
# Bare import-test — ikke kør Streamlit
import app
" 2>&1 | head -30
```

Expected: Ingen Python-traceback. (Streamlit-runtime kaster ikke fejl ved kun-import.)

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "$(cat <<'EOF'
Tilføj SSO loading-overlay så token-flash skjules

Når brugeren klikker PAX i juriitech.com/dashboard, navigerer
browseren til pax.juriitech.com/?sso_token=<JWT>. Indtil
try_sso_login() har valideret + ryddet URL'en (~1-2 sek.) så brugeren
default Streamlit-shell + JWT i adresse-linjen.

Inject'er et fuldskærms-overlay (juriitech-wordmark + indigo-orb +
"Logger ind…" + spinner) når ?sso_token er i URL. Skjuler Streamlit's
egen UI bag overlayet. Falder automatisk væk når SSO er færdig og
st.rerun() har ryddet URL.

Ren CSS/HTML — ingen JS. Visuel kontinuitet med juriitech.com/dashboard.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Manuel browser-smoke-test lokalt

**Why:** Disse glitches kan kun verificeres visuelt. Tjek alle tre fixes virker FØR vi deployer til prod.

**Files:** Ingen ændringer — kun verifikation.

- [ ] **Step 1: Start Streamlit lokalt**

Run i én terminal:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && streamlit run app.py
```

Lad den køre. Åbn `http://localhost:8501` i en INKOGNITO-fane (ingen cached session).

- [ ] **Step 2: Verificér Fix 1+2 (sidebar + page_title)**

Tjek i browseren:
- Browser-fanen viser "juriitech PAX" fra første render (ikke "app", ikke URL).
- Sidebar viser INTET med teksten "app" eller filnavne. Login-skærm vises uden sidebar-glitch.
- Efter login: sidebar viser "Forside, Søg i arkivet, Gemte sager, Disclaimer" med ikoner — ingen flash af andre labels.

**Hvis "app" stadig vises et øjeblik:** Tjek om `pages/`-mappen er væk: `ls /Users/mikkelhansen/Desktop/juridisk_assistent/pages 2>&1` skal sige "No such file".

- [ ] **Step 3: Verificér Fix 3 (SSO overlay)**

Login først via login-formen. Tag refresh-tokenet ud af localStorage og konstruer test-URL:

```javascript
// Kør i browser-console på localhost:8501 efter login
const sess = JSON.parse(localStorage.getItem(
  Object.keys(localStorage).find(k => k.includes('auth-token'))
) || '{}');
console.log('Test-URL:', `http://localhost:8501/?sso_token=${sess.refresh_token}`);
```

Åbn den URL i en NY inkognito-fane. Forventet:
- Du ser et "juriitech" wordmark + "Logger ind…" overlay (indigo-orb baggrund, matcher landing-stil) — IKKE default Streamlit-shell.
- Efter ~1-2 sek. forsvinder overlayet og forsiden vises som logget-ind bruger.
- URL'en er ryddet (ingen `?sso_token=` længere).

**Hvis overlayet ikke vises:** Tjek browser-console for CSS-fejl. Tjek at `?sso_token=` faktisk er i URL'en før page-load.

- [ ] **Step 4: Verificér graceful fallback ved invalid token**

Åbn `http://localhost:8501/?sso_token=invalid_garbage` i ny inkognito-fane. Forventet:
- Overlay vises kortvarigt
- Falder tilbage til normal login-side når `try_sso_login()` afviser tokenet
- Ingen Python-fejl i terminal-loggen — kun en `DEBUG: try_sso_login — refresh_session fejlede:`-print

- [ ] **Step 5: Stop lokal Streamlit-server**

Tryk Ctrl+C i terminalen hvor streamlit kørte.

---

### Task 5: Deploy til prod og verificér live

**Why:** Lokal test bekræfter koden virker, men SSO-flowet fra juriitech.com går mod produktions-Supabase + produktions-PAX. Live-test er sidste check.

**Files:** Ingen ændringer — kun deploy + verifikation.

- [ ] **Step 1: Push til remote**

Run:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && git push
```

Expected: Push succeeds. (`auto-push.sh`-hook gør dette muligvis allerede automatisk efter hver commit.)

- [ ] **Step 2: Deploy til Fly.io**

Run:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && fly deploy
```

Expected: Deploy succeeds with exit code 0. Tager ~2-4 min.

- [ ] **Step 3: Smoke-test live SSO-flow**

I en INKOGNITO-fane:
1. Gå til `https://juriitech.com/login.html` → log ind med din admin-bruger
2. Du lander på `https://juriitech.com/dashboard.html` — verificér: ingen sidebar-flash i header (det er PAX-kontekst — n/a her), velkomst-titel viser "Velkommen, Mikkel"
3. Klik PAX-kortet
4. Browseren navigerer til `https://pax.juriitech.com/?sso_token=...`
5. Forventet visuel oplevelse:
   - Du ser et juriitech-brandet "Logger ind…" overlay (indigo-orb + wordmark)
   - INGEN flash af "app" eller "Søg i arkivet" i sidebar
   - INGEN synligt JWT-token-blink i adresse-linjen (eller kun meget kortvarigt — det er OK fordi overlayet skjuler resten)
   - Efter ~1-2 sek. forsvinder overlay → PAX-forsiden vises som logget-ind
   - URL'en er ren `https://pax.juriitech.com/forside`
   - Browser-fanen viser "juriitech PAX"
   - Sidebar viser "Forside, Søg i arkivet, Gemte sager, Disclaimer" + Admin (du er admin)

- [ ] **Step 4: Smoke-test direkte cold load af PAX**

I en NY inkognito-fane:
1. Gå direkte til `https://pax.juriitech.com/`
2. Forventet:
   - Browser-fane: "juriitech PAX" fra start
   - Login-skærm vises uden sidebar-flash (fordi `_auth.is_logged_in()` er False)
   - INGEN "app" / "Søg i arkivet" synligt nogetsteds

- [ ] **Step 5: Tjek Fly-logs for uforudsete fejl**

Run:
```bash
fly logs --no-tail | tail -50
```

Expected: Ingen tracebacks. Eventuelle `DEBUG: try_sso_login`-prints er fine.

- [ ] **Step 6: Færdig — ingen separat commit nødvendigt**

Alle ændringer er allerede committet i Task 1+2+3.

---

## Done når

- Cold load af pax.juriitech.com viser ingen "app"-flash i sidebar
- Browser-fane viser "juriitech PAX" fra første pixel
- SSO fra dashboard viser branded overlay i stedet for default Streamlit-shell + URL-token
- Live-test bekræfter alle tre fixes virker i prod
