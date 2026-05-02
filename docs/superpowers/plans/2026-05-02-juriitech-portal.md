# juriitech portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tilføj central login + program-overblik på `juriitech.com` med token-via-URL SSO til `pax.juriitech.com`.

**Architecture:** Vanilla HTML/CSS/JS på Vercel (eksisterende statisk side), Supabase JS SDK via CDN, refresh_token i URL-query når bruger klikker fra dashboard ind i program. PAX's `app.py` udvides med en `sso_token`-handler ved siden af eksisterende `token_hash`-flow.

**Tech Stack:** Vanilla HTML/CSS/JS, Supabase JS SDK v2 (via esm.sh CDN), Streamlit + supabase-py (eksisterende).

**Spec:** [docs/superpowers/specs/2026-05-02-juriitech-portal-design.md](../specs/2026-05-02-juriitech-portal-design.md)

**Codebases:**
- Portal: `/Users/mikkelhansen/juriitech-landing` (GitHub: `mikkelsindbakke-dot/juriitech-landing`, deployer auto til Vercel)
- PAX: `/Users/mikkelhansen/Desktop/juridisk_assistent` (GitHub repo, deployer til Fly.io)

**Test-strategi:** PAX bruger ikke unit-tests. Hver task ender med manuel browser-smoke-test + commit. Final task kører gennem alle 8 spec-test-scenarier.

---

## Task 1: Foundation — auth.js + Supabase config

**Files:**
- Create: `/Users/mikkelhansen/juriitech-landing/auth.js`

**Mål:** Opret kerne-modulet der håndterer Supabase-klient, session-state, login, logout, og buildSsoUrl. Alle senere tasks importerer fra denne fil.

- [ ] **Step 1: Hent SUPABASE_URL og SUPABASE_ANON_KEY**

```bash
grep -E "^SUPABASE_(URL|ANON_KEY)=" /Users/mikkelhansen/Desktop/juridisk_assistent/.env
```

Forventet output: to linjer med URL og anon-key.

ANON_KEY er offentlig efter design (Supabase RLS håndhæver tilgangskontrol, ikke key-secrecy). Sikker at hardcode i JS.

- [ ] **Step 2: Opret auth.js med fuld implementering**

Skriv filen `/Users/mikkelhansen/juriitech-landing/auth.js`:

```javascript
/**
 * juriitech portal — auth-modul.
 *
 * Wrapper omkring Supabase JS SDK med de operationer portalen har brug for:
 * login, logout, session-check, password-reset, og SSO-URL-builder.
 *
 * Anon-key er offentlig efter Supabase's design — RLS i databasen håndhæver
 * adgangskontrol, ikke at key'en er hemmelig. Det er sikkert at hardcode.
 */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const SUPABASE_URL = 'https://sebsjjsfxlegspqturxl.supabase.co';
const SUPABASE_ANON_KEY = 'PASTE_FROM_ENV_FILE';  // ← engineer fylder ind fra step 1

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
        persistSession: true,
        autoRefreshToken: true,
        storage: window.localStorage,
    }
});

/**
 * Returnerer aktuel session eller null. Baseret på localStorage —
 * kalder Supabase for at refreshe access_token hvis den er ved at udløbe.
 */
export async function getSession() {
    const { data, error } = await supabase.auth.getSession();
    if (error) {
        console.error('getSession fejlede:', error);
        return null;
    }
    return data?.session ?? null;
}

/**
 * Hvis bruger ikke er logget ind: redirect til /login.html.
 * Brug øverst i dashboard.html før noget andet kører.
 */
export async function requireSession() {
    const session = await getSession();
    if (!session) {
        window.location.href = '/login.html';
        return null;
    }
    return session;
}

/**
 * Login med email + password. Returnerer session ved succes,
 * kaster Error med Supabase-besked ved fejl (caller fanger og viser).
 */
export async function signIn(email, password) {
    const { data, error } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
    });
    if (error) throw error;
    return data;
}

/**
 * Log ud lokalt. Rydder localStorage. Påvirker IKKE PAX's egen
 * Streamlit-session (asymmetri accepteret per spec).
 */
export async function signOut() {
    const { error } = await supabase.auth.signOut();
    if (error) console.error('signOut fejlede:', error);
}

/**
 * Send password-reset-email. Bruger får link der peger på
 * pax.juriitech.com's eksisterende set_password-flow (genbrug).
 */
export async function resetPassword(email) {
    const { error } = await supabase.auth.resetPasswordForEmail(
        email.trim(),
        { redirectTo: 'https://pax.juriitech.com/' }
    );
    if (error) throw error;
}

/**
 * Konstruér SSO-URL til et program. Bruger refresh_token (ikke access_token)
 * fordi refresh_tokens er kortlivede — Supabase bytter dem til access_token
 * straks ved første brug og roterer.
 */
export async function buildSsoUrl(programUrl) {
    const session = await getSession();
    if (!session) throw new Error('Ikke logget ind — kan ikke bygge SSO-URL');
    const url = new URL(programUrl);
    url.searchParams.set('sso_token', session.refresh_token);
    return url.toString();
}
```

ENGINEER-NOTE: Erstat `PASTE_FROM_ENV_FILE` med faktisk anon-key-værdi fra step 1.

- [ ] **Step 3: Smoke-test at filen indlæses**

Opret en midlertidig test-side `/tmp/auth-test.html`:

```html
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body>
<h1>auth.js smoke test</h1>
<pre id="output"></pre>
<script type="module">
import { getSession, supabase } from '/Users/mikkelhansen/juriitech-landing/auth.js';
const out = document.getElementById('output');
out.textContent = 'supabase klient: ' + (supabase ? 'OK' : 'FEJL') + '\n';
const s = await getSession();
out.textContent += 'session: ' + (s ? JSON.stringify(s.user.email) : 'ingen (forventet)');
</script>
</body>
</html>
```

Åbn filen i browser. Forventet: vis "supabase klient: OK" + "session: ingen (forventet)". Ingen fejl i console.

Slet `/tmp/auth-test.html` efter test.

- [ ] **Step 4: Commit**

```bash
cd /Users/mikkelhansen/juriitech-landing
git add auth.js
git commit -m "Tilføj auth.js — Supabase-wrapper for portal

Foundation for login, dashboard og SSO. Eksporterer:
- getSession() / requireSession() — session-check + redirect-gating
- signIn() / signOut() / resetPassword() — Supabase Auth-wrappere
- buildSsoUrl(programUrl) — konstruerer SSO-URL med refresh_token

Ingen build-step — importeres direkte via type=module + esm.sh CDN."
```

---

## Task 2: login.html — login-form + flow

**Files:**
- Create: `/Users/mikkelhansen/juriitech-landing/login.html`
- Modify: `/Users/mikkelhansen/juriitech-landing/styles.css`

**Mål:** Fungerende login-side. Form med email + password. Ved succes: redirect til /dashboard.html. Ved fejl: vis fejlbesked inline. "Glemt password?"-link sender Supabase reset-email.

- [ ] **Step 1: Opret login.html**

```html
<!DOCTYPE html>
<html lang="da">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Log ind — juriitech</title>
    <link rel="icon" href="favicon.svg" type="image/svg+xml">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="styles.css">
</head>
<body class="auth-page">
    <main class="auth-container">
        <a href="/" class="auth-logo">
            <span class="j">j</span>uriitech
        </a>

        <form id="login-form" class="auth-form" novalidate>
            <h2>Log ind</h2>
            <p class="auth-subtitle">Adgang til dine juriitech-værktøjer</p>

            <label for="email">Email</label>
            <input type="email" id="email" name="email" required autocomplete="email" autofocus>

            <label for="password">Password</label>
            <input type="password" id="password" name="password" required autocomplete="current-password">

            <button type="submit" id="submit-btn">Log ind</button>

            <p id="error-msg" class="auth-error" hidden></p>

            <a href="#" id="forgot-link" class="auth-link">Glemt password?</a>
        </form>
    </main>

    <script type="module">
        import { signIn, resetPassword, getSession } from './auth.js';

        // Hvis allerede logget ind, redirect til dashboard
        const existing = await getSession();
        if (existing) {
            window.location.href = '/dashboard.html';
        }

        const form = document.getElementById('login-form');
        const btn = document.getElementById('submit-btn');
        const errorMsg = document.getElementById('error-msg');
        const forgotLink = document.getElementById('forgot-link');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            errorMsg.hidden = true;
            btn.disabled = true;
            btn.textContent = 'Logger ind...';

            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;

            try {
                await signIn(email, password);
                window.location.href = '/dashboard.html';
            } catch (err) {
                errorMsg.textContent = err.message || 'Login fejlede. Tjek email og password.';
                errorMsg.hidden = false;
                btn.disabled = false;
                btn.textContent = 'Log ind';
            }
        });

        forgotLink.addEventListener('click', async (e) => {
            e.preventDefault();
            const email = document.getElementById('email').value.trim();
            if (!email) {
                errorMsg.textContent = 'Indtast din email i feltet ovenfor først.';
                errorMsg.hidden = false;
                return;
            }
            try {
                await resetPassword(email);
                errorMsg.textContent = 'Reset-email sendt. Tjek din indbakke.';
                errorMsg.hidden = false;
                errorMsg.style.color = 'var(--text-success, #1f7a3e)';
            } catch (err) {
                errorMsg.textContent = err.message || 'Kunne ikke sende reset-email.';
                errorMsg.hidden = false;
            }
        });
    </script>
</body>
</html>
```

- [ ] **Step 2: Tilføj styles til styles.css**

Append til `/Users/mikkelhansen/juriitech-landing/styles.css`:

```css
/* ───────────────────────────────────
   AUTH-SIDER (login + dashboard)
   ─────────────────────────────────── */

.auth-page {
    background-color: #FAF8F4;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
}

.auth-container {
    width: 100%;
    max-width: 400px;
    padding: 2rem;
    text-align: center;
}

.auth-logo {
    display: inline-block;
    font-family: 'Inter', sans-serif;
    font-weight: 900;
    font-size: 2rem;
    color: #000;
    text-decoration: none;
    margin-bottom: 2rem;
}

.auth-logo .j {
    color: #6366f1;
}

.auth-form {
    background-color: #fff;
    padding: 2rem;
    border-radius: 12px;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
    text-align: left;
}

.auth-form h2 {
    margin: 0 0 0.5rem 0;
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 1.5rem;
}

.auth-subtitle {
    color: #666;
    font-size: 0.9rem;
    margin: 0 0 1.5rem 0;
}

.auth-form label {
    display: block;
    font-size: 0.85rem;
    font-weight: 500;
    margin-top: 1rem;
    margin-bottom: 0.4rem;
    color: #333;
}

.auth-form input {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid #ddd;
    border-radius: 8px;
    font-size: 1rem;
    font-family: 'Inter', sans-serif;
    box-sizing: border-box;
}

.auth-form input:focus {
    outline: none;
    border-color: #6366f1;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.auth-form button {
    width: 100%;
    margin-top: 1.5rem;
    padding: 0.85rem;
    background-color: #6366f1;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
}

.auth-form button:hover:not(:disabled) {
    background-color: #4f46e5;
}

.auth-form button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}

.auth-error {
    margin-top: 1rem;
    padding: 0.6rem 0.8rem;
    background-color: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 6px;
    color: #b91c1c;
    font-size: 0.875rem;
}

.auth-link {
    display: block;
    margin-top: 1rem;
    text-align: center;
    color: #6366f1;
    text-decoration: none;
    font-size: 0.875rem;
}

.auth-link:hover {
    text-decoration: underline;
}
```

- [ ] **Step 3: Smoke-test login-flowet**

Open Vercel preview lokalt med `npx serve /Users/mikkelhansen/juriitech-landing` (eller direkte i Finder hvis browser tillader file:// med ES modules — prøv først; hvis ikke, brug `npx serve`).

I browseren:
1. Gå til `/login.html`
2. Forventet: login-form vises med juriitech-logo, email + password-felter
3. Indtast forkert email + password → klik "Log ind" → forventet: rød fejl-besked vises
4. Indtast korrekt email + password → klik "Log ind" → forventet: redirect til `/dashboard.html` (siden eksisterer endnu ikke, så 404 eller blank — det er OK på dette trin)
5. Indtast email → klik "Glemt password?" → forventet: grøn besked "Reset-email sendt"

- [ ] **Step 4: Commit**

```bash
cd /Users/mikkelhansen/juriitech-landing
git add login.html styles.css
git commit -m "Tilføj login.html + auth-styles

Login-form med email + password, forgot-password-link, og redirect
til /dashboard.html ved succes. Bruger auth.js (signIn, resetPassword).

Ved password-reset peger redirect på pax.juriitech.com's
eksisterende set_password-flow (genbrug, ingen ny kode på portal)."
```

---

## Task 3: dashboard.html — auth-gated program-overblik

**Files:**
- Create: `/Users/mikkelhansen/juriitech-landing/dashboard.html`
- Modify: `/Users/mikkelhansen/juriitech-landing/styles.css`

**Mål:** Dashboard vises kun for logged-in brugere. Header med bruger-email + Log ud-knap. Ét program-kort (PAX) med Åbn-knap. Klik på Åbn fører til `pax.juriitech.com` (rå URL — SSO kommer i Task 6).

- [ ] **Step 1: Opret dashboard.html**

```html
<!DOCTYPE html>
<html lang="da">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard — juriitech</title>
    <link rel="icon" href="favicon.svg" type="image/svg+xml">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="styles.css">
</head>
<body class="dashboard-page" style="visibility: hidden">
    <!-- Hidden indtil session-check for at undgå flash af content for ikke-loggede brugere -->
    <header class="dashboard-header">
        <a href="/" class="dashboard-logo">
            <span class="j">j</span>uriitech
        </a>
        <div class="dashboard-user">
            <span id="user-email"></span>
            <button id="logout-btn" class="logout-btn">Log ud</button>
        </div>
    </header>

    <main class="dashboard-main">
        <h1 id="welcome-heading">Velkommen</h1>
        <p class="dashboard-subtitle">Vælg et program at åbne</p>

        <div id="program-grid" class="program-grid">
            <!-- Programmer indsættes af JS -->
        </div>
    </main>

    <script type="module">
        import { requireSession, signOut } from './auth.js';

        const session = await requireSession();
        if (!session) {
            // requireSession har redirected — stop kørsel
        } else {
            // Hardcoded program-liste. Når Program 2 kommer: tilføj entry her.
            // (Spec siger: migrér til DB-tabel når der er flere programmer + brugere
            //  med forskellig adgang. YAGNI nu.)
            const PROGRAMMER = [
                {
                    slug: 'pax',
                    navn: 'juriitech PAX',
                    beskrivelse: 'AI-førstevurdering af klagesager ved Pakkerejse-Ankenævnet',
                    url: 'https://pax.juriitech.com',
                    farve: '#6366f1',
                }
            ];

            // Vis bruger-email og velkomst
            const email = session.user.email;
            document.getElementById('user-email').textContent = email;

            // Hent fulde_navn fra session metadata hvis tilstede
            const navn = session.user.user_metadata?.full_name
                || session.user.user_metadata?.fulde_navn
                || email.split('@')[0];
            document.getElementById('welcome-heading').textContent = `Velkommen, ${navn}`;

            // Render program-kort
            const grid = document.getElementById('program-grid');
            for (const p of PROGRAMMER) {
                const kort = document.createElement('article');
                kort.className = 'program-card';
                kort.innerHTML = `
                    <div class="program-icon" style="background-color: ${p.farve}"></div>
                    <h2>${p.navn}</h2>
                    <p>${p.beskrivelse}</p>
                    <a href="${p.url}" class="program-open-btn" data-program-url="${p.url}">
                        Åbn
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
                            <path d="M5 12h14M13 5l7 7-7 7"/>
                        </svg>
                    </a>
                `;
                grid.appendChild(kort);
            }

            // Logout
            document.getElementById('logout-btn').addEventListener('click', async () => {
                await signOut();
                window.location.href = '/';
            });

            // Vis siden
            document.body.style.visibility = 'visible';
        }
    </script>
</body>
</html>
```

- [ ] **Step 2: Tilføj dashboard-styles**

Append til `/Users/mikkelhansen/juriitech-landing/styles.css`:

```css
/* ───────────────────────────────────
   DASHBOARD
   ─────────────────────────────────── */

.dashboard-page {
    background-color: #FAF8F4;
    min-height: 100vh;
    margin: 0;
}

.dashboard-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem 2rem;
    border-bottom: 1px solid #ebe8e0;
    background-color: #fff;
}

.dashboard-logo {
    font-family: 'Inter', sans-serif;
    font-weight: 900;
    font-size: 1.5rem;
    color: #000;
    text-decoration: none;
}

.dashboard-logo .j {
    color: #6366f1;
}

.dashboard-user {
    display: flex;
    align-items: center;
    gap: 1rem;
    font-size: 0.9rem;
    color: #555;
}

.logout-btn {
    background: none;
    border: 1px solid #ddd;
    padding: 0.45rem 1rem;
    border-radius: 20px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    font-size: 0.875rem;
    color: #555;
}

.logout-btn:hover {
    background-color: #f5f5f5;
}

.dashboard-main {
    max-width: 1000px;
    margin: 0 auto;
    padding: 3rem 2rem;
}

.dashboard-main h1 {
    font-family: 'Inter', sans-serif;
    font-weight: 800;
    font-size: 2rem;
    margin: 0 0 0.5rem 0;
}

.dashboard-subtitle {
    color: #666;
    margin: 0 0 2.5rem 0;
}

.program-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 1.5rem;
}

.program-card {
    background-color: #fff;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
    border: 1px solid #ebe8e0;
    display: flex;
    flex-direction: column;
}

.program-card:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
    border-color: #d8d4ca;
}

.program-icon {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    margin-bottom: 1rem;
}

.program-card h2 {
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 1.15rem;
    margin: 0 0 0.5rem 0;
}

.program-card p {
    color: #666;
    font-size: 0.9rem;
    line-height: 1.5;
    margin: 0 0 1.5rem 0;
    flex-grow: 1;
}

.program-open-btn {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.6rem 1.25rem;
    background-color: #000;
    color: #fff;
    text-decoration: none;
    border-radius: 24px;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    font-size: 0.9rem;
}

.program-open-btn:hover {
    background-color: #333;
}
```

- [ ] **Step 3: Smoke-test dashboard**

1. Direkte besøg af `/dashboard.html` UDEN session → forventet: redirect til `/login.html`
2. Login → redirect til `/dashboard.html` → forventet: PAX-kort vises, bruger-email i header, "Velkommen, [navn]"
3. Klik "Åbn" på PAX-kortet → forventet: går til `https://pax.juriitech.com` (PAX viser sin egen login fordi vi endnu ikke har SSO)
4. Klik "Log ud" → forventet: redirect til `/`
5. Genbesøg `/dashboard.html` → forventet: redirect til `/login.html` (session er ryddet)

- [ ] **Step 4: Commit**

```bash
cd /Users/mikkelhansen/juriitech-landing
git add dashboard.html styles.css
git commit -m "Tilføj dashboard.html — program-overblik

Auth-gated dashboard med:
- Header (juriitech-logo, bruger-email, Log ud-knap)
- Velkomst med fulde_navn fra session-metadata
- Hardcoded liste af programmer som kort (kun PAX nu)
- Klik på 'Åbn' fører til programmets URL (rå — SSO tilføjes i senere task)

Bruger 'visibility: hidden' indtil session-check er færdig for at
undgå flash af content for ikke-loggede brugere.

Når Program 2 kommer: tilføj entry i PROGRAMMER-arrayet.
Når brugere skal have differentieret adgang: migrér til DB-tabel."
```

---

## Task 4: Opdater index.html — login-knap target + signed-in detection

**Files:**
- Modify: `/Users/mikkelhansen/juriitech-landing/index.html`

**Mål:** Forsiden's "Log ind"-knap peger nu på `/login.html` (i stedet for streamlit.app). Hvis bruger allerede er logget ind ved load, skift knappen til "Til dashboard" og peg på `/dashboard.html`.

- [ ] **Step 1: Opdater index.html**

Erstat hele `<header>`-blokken og tilføj script-tag før `</body>`:

```html
<header class="top-nav">
    <a href="/login.html" id="auth-btn" class="login-btn">
        Log ind
        <svg class="arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12h14M13 5l7 7-7 7"/>
        </svg>
    </a>
</header>
```

Og lige før `</body>`, tilføj:

```html
<script type="module">
    // Hvis bruger er logget ind: skift "Log ind"-knappen til "Til dashboard"
    import { getSession } from './auth.js';
    const session = await getSession();
    if (session) {
        const btn = document.getElementById('auth-btn');
        btn.href = '/dashboard.html';
        // Behold pile-ikonet, ændre kun teksten
        btn.firstChild.textContent = '\n            Til dashboard\n            ';
    }
</script>
```

- [ ] **Step 2: Smoke-test index.html**

1. Anonym (ikke logget ind) → besøg `/` → forventet: "Log ind"-knap vises, klik → `/login.html`
2. Logget ind (kør Task 2 først) → besøg `/` → forventet: knap viser "Til dashboard", klik → `/dashboard.html`
3. Log ud fra dashboard → besøg `/` → forventet: knap er tilbage til "Log ind"

- [ ] **Step 3: Commit**

```bash
cd /Users/mikkelhansen/juriitech-landing
git add index.html
git commit -m "Opdater Log ind-knap til at pege på portal

- href ændret fra https://juriitech.streamlit.app til /login.html
- Hvis bruger er logget ind: skift knap-tekst til 'Til dashboard'
  og href til /dashboard.html"
```

---

## Task 5: PAX SSO-handler — accept sso_token i URL

**Files:**
- Modify: `/Users/mikkelhansen/Desktop/juridisk_assistent/auth.py` (tilføj funktion)
- Modify: `/Users/mikkelhansen/Desktop/juridisk_assistent/app.py:130-141` (kald handleren)

**Mål:** Når PAX modtager en URL med `?sso_token=...`, validér tokenet hos Supabase, etablér session_state.user via eksisterende `_link_supabase_to_db_user`, fjern token fra URL, og lad brugeren lande i forsiden uden ekstra login.

- [ ] **Step 1: Tilføj `try_sso_login` til auth.py**

Find slutningen af `login_with_password()`-funktionen i auth.py (formodet omkring linje 245). Tilføj DIREKTE EFTER den, før `def send_password_reset`:

```python
def try_sso_login():
    """
    Engangs-login via refresh_token i URL'ens query-params (sso_token).

    Bruges når brugeren klikker fra juriitech.com/dashboard ind i PAX.
    Dashboard-siden konstruerer URL'en med session.refresh_token, og denne
    handler bytter den til en lokal Streamlit-session.

    Returnerer:
        True hvis SSO-login lykkedes (caller bør kalde st.rerun())
        False hvis ingen sso_token i URL eller validering fejlede
    """
    sso_token = st.query_params.get("sso_token")
    if not sso_token:
        return False

    client = _get_supabase_client()
    if client is None:
        print("DEBUG: try_sso_login — Supabase-klient utilgængelig")
        return False

    try:
        # Refresh-tokens validerer ved at få ny session ud af dem
        result = client.auth.refresh_session(sso_token)
        supabase_user = result.user if hasattr(result, "user") else None
        if not supabase_user:
            print("DEBUG: try_sso_login — refresh_session returnerede ingen user")
            return False
    except Exception as e:
        print(f"DEBUG: try_sso_login — refresh_session fejlede: {e}")
        return False

    # Genbrug eksisterende DB-link-logik
    db_user = _link_supabase_to_db_user(supabase_user)
    if db_user is None:
        print(
            f"DEBUG: try_sso_login — bruger {supabase_user.email} er ikke "
            "i users-tabellen. SSO afvist."
        )
        return False

    # Set session_state — samme struktur som login_with_password
    st.session_state.user = {
        "id": db_user["id"],
        "supabase_user_id": str(supabase_user.id),
        "email": supabase_user.email,
        "tenant_id": db_user["tenant_id"],
        "role": db_user["role"],
        "fulde_navn": db_user["fulde_navn"] or "",
    }

    # Fjern token fra URL af sikkerhedshensyn (browser-historik) + ren UX
    st.query_params.clear()
    return True
```

- [ ] **Step 2: Kald `try_sso_login` i app.py FØR token_hash-handler og login-side**

Find blokken i app.py omkring linje 130-141 der starter med `if _auth_konfigureret and not _auth.is_logged_in():`. Erstat den med:

```python
if _auth_konfigureret and not _auth.is_logged_in():
    # Specialcase 1: SSO-token i URL fra juriitech.com/dashboard.
    # Hvis SSO lykkes, kører appen videre som logget ind.
    if _auth.try_sso_login():
        st.rerun()

    # Specialcase 2: hvis URL har ?token_hash=... så er brugeren her via
    # invite-link eller password-reset-link fra deres email. Vi sender
    # dem til set_password-siden i stedet for login-siden.
    _qp_check = st.query_params
    if _qp_check.get("token_hash"):
        import set_password as _set_password
        _set_password.render()
        st.stop()

    # Almindeligt tilfælde: vis login-siden
    _auth.render_login_page()
    st.stop()
```

- [ ] **Step 3: Smoke-test SSO-handler — manuel URL-konstruktion**

Få et refresh_token først. Åbn browser-console på `juriitech.com` (når Task 1-2 er deployet og du er logget ind):

```javascript
const { data } = await window.supabase?.auth.getSession() ||
    (await import('/auth.js')).supabase.auth.getSession();
console.log(data.session.refresh_token);
```

Eller fra terminal med Python (hurtigere):

```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_ANON_KEY'])
r = c.auth.sign_in_with_password({'email': 'juriitech@juriitech.com', 'password': 'DIT_PASSWORD'})
print('refresh_token:', r.session.refresh_token)
"
```

Start PAX lokalt:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent
streamlit run app.py
```

Åbn URL: `http://localhost:8501/?sso_token=<TOKENVÆRDIEN>`

Forventet:
- PAX lander direkte i forsiden uden login-formular
- URL'en bliver renset (ingen `?sso_token=` synlig efter load)
- Bruger-email vises i sidebar (eller hvor som helst auth.is_logged_in() bruges)

Hvis det fejler — tjek terminal-output for `DEBUG: try_sso_login`-linjer for diagnose.

- [ ] **Step 4: Commit**

```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent
git add auth.py app.py
git commit -m "Tilføj SSO-handler — accept sso_token via URL fra portal

Når bruger klikker PAX-kortet på juriitech.com/dashboard, sendes
de til pax.juriitech.com/?sso_token=<refresh_token>. Handleren:

1. Læser sso_token fra st.query_params
2. Kalder supabase.auth.refresh_session() for at validere + få user
3. Genbruger _link_supabase_to_db_user() til at finde users-row
4. Sætter st.session_state.user (samme struktur som login_with_password)
5. Renser URL med st.query_params.clear()
6. Caller kører st.rerun()

Token fjernes fra URL straks for at undgå at den ligger i browser-
historik. Refresh_tokens er kortlivede og roterer ved første brug
hos Supabase, så selv hvis URL'en lækker, er token'en ubrugelig
inden for kort tid."
```

---

## Task 6: Wire up dashboard PAX-kort til SSO

**Files:**
- Modify: `/Users/mikkelhansen/juriitech-landing/dashboard.html`

**Mål:** Når bruger klikker "Åbn" på et program-kort, skal browseren navigere til SSO-URL'en (med `?sso_token=`-parameter) i stedet for raw URL'en. Det giver det egentlige SSO-flow.

- [ ] **Step 1: Erstat klik-handler i dashboard.html**

I `dashboard.html` find scriptet hvor program-kortene rendres. Lige efter `grid.appendChild(kort);`-linjen (inde i for-løkken), tilføj klik-handler. Erstat:

```javascript
            for (const p of PROGRAMMER) {
                const kort = document.createElement('article');
                kort.className = 'program-card';
                kort.innerHTML = `
                    <div class="program-icon" style="background-color: ${p.farve}"></div>
                    <h2>${p.navn}</h2>
                    <p>${p.beskrivelse}</p>
                    <a href="${p.url}" class="program-open-btn" data-program-url="${p.url}">
                        Åbn
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
                            <path d="M5 12h14M13 5l7 7-7 7"/>
                        </svg>
                    </a>
                `;
                grid.appendChild(kort);
            }
```

med:

```javascript
            for (const p of PROGRAMMER) {
                const kort = document.createElement('article');
                kort.className = 'program-card';
                kort.innerHTML = `
                    <div class="program-icon" style="background-color: ${p.farve}"></div>
                    <h2>${p.navn}</h2>
                    <p>${p.beskrivelse}</p>
                    <a href="${p.url}" class="program-open-btn" data-program-url="${p.url}">
                        Åbn
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
                            <path d="M5 12h14M13 5l7 7-7 7"/>
                        </svg>
                    </a>
                `;
                grid.appendChild(kort);

                // Klik-handler: byg SSO-URL og naviger
                const openBtn = kort.querySelector('.program-open-btn');
                openBtn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    openBtn.textContent = 'Åbner...';
                    try {
                        const ssoUrl = await buildSsoUrl(p.url);
                        window.location.href = ssoUrl;
                    } catch (err) {
                        console.error('SSO-URL fejlede:', err);
                        alert('Kunne ikke åbne programmet. Prøv at logge ind igen.');
                        openBtn.textContent = 'Åbn';
                    }
                });
            }
```

Sørg også for at importere `buildSsoUrl` i toppen — find import-linjen og tilføj:

```javascript
        import { requireSession, signOut, buildSsoUrl } from './auth.js';
```

- [ ] **Step 2: Smoke-test end-to-end SSO**

Forudsætning: Task 5 er deployet til Fly så `pax.juriitech.com` har den nye handler. Eller test lokalt:
- Kør PAX lokalt på `http://localhost:8501`
- I dashboard.html, ÆNDRE `url: 'https://pax.juriitech.com'` til `url: 'http://localhost:8501'` MIDLERTIDIGT for testing (ROLL TILBAGE INDEN COMMIT)

Test:
1. Login på portal → `/dashboard.html`
2. Klik "Åbn" på PAX-kort
3. Forventet: knap viser "Åbner..." kortvarigt, så redirect til PAX
4. PAX-siden lander direkte uden login-form
5. URL'en på PAX-siden viser ingen `?sso_token=` (renset af handler)

Husk: roll tilbage `url` til `https://pax.juriitech.com` før commit hvis du midlertidigt pegede på localhost.

- [ ] **Step 3: Commit**

```bash
cd /Users/mikkelhansen/juriitech-landing
git add dashboard.html
git commit -m "Wire up SSO: dashboard PAX-kort bruger buildSsoUrl

Når bruger klikker 'Åbn' på et program-kort, kalder vi
buildSsoUrl(programUrl) der konstruerer URL med ?sso_token=<refresh_token>
og navigerer dertil. PAX's handler bytter token til session.

e.preventDefault() forhindrer browseren i at navigere til den raw URL
før vi har bygget SSO-URL'en. 'Åbner...'-tekst giver feedback hvis
buildSsoUrl er langsom (typisk <50ms)."
```

---

## Task 7: Final smoke-test — alle 8 spec-scenarier

**Files:** Ingen — kun test.

**Mål:** Bekræft at alle 8 test-scenarier fra spec'ens "Test-strategi"-sektion fungerer ende-til-ende.

- [ ] **Step 1: Anonym besøgende**

Åbn nyt privat browser-vindue. Besøg `https://juriitech.com/`.

Forventet:
- Forsiden vises som hidtil
- "Log ind"-knap øverst til højre fører til `/login.html`

- [ ] **Step 2: Login med korrekte credentials**

På `/login.html`: indtast korrekt email + password → klik "Log ind".

Forventet:
- Knappen viser "Logger ind..."
- Redirect til `/dashboard.html`
- Velkomst med navn + PAX-kort

- [ ] **Step 3: Login med forkerte credentials**

Log ud først. På `/login.html`: indtast forkert password → klik "Log ind".

Forventet:
- Rød fejl-besked vises (fx "Invalid login credentials")
- Knappen genaktiveres til "Log ind"
- INGEN redirect

- [ ] **Step 4: Klik på PAX-kort**

Login på portal, fra `/dashboard.html`: klik "Åbn" på PAX-kortet.

Forventet:
- "Åbner..."-tekst på knap
- Redirect til `pax.juriitech.com`
- Lander direkte i PAX-forside, ingen login-form
- URL'en har INGEN `?sso_token=` (renset)

- [ ] **Step 5: Direkte besøg af PAX uden session**

Åbn nyt privat vindue. Besøg `https://pax.juriitech.com` direkte.

Forventet: PAX's egen login-side vises (eksisterende adfærd).

- [ ] **Step 6: Logout fra dashboard**

På `/dashboard.html`: klik "Log ud".

Forventet:
- Redirect til `/`
- Knappen "Log ind" vises (ikke "Til dashboard")
- Genbesøg `/dashboard.html` → redirect til `/login.html`

- [ ] **Step 7: Direkte besøg af dashboard uden session**

Privat vindue. Besøg `https://juriitech.com/dashboard.html` direkte.

Forventet: redirect til `/login.html`.

- [ ] **Step 8: Glemt password**

På `/login.html`: indtast email → klik "Glemt password?".

Forventet:
- Grøn besked "Reset-email sendt"
- Tjek email-indbakken — Supabase-mail med "Reset password"-link
- Klik linket → fører til `pax.juriitech.com/?token_hash=...&type=recovery`
- PAX viser eksisterende set_password-flow

- [ ] **Step 9: Log resultaterne**

Hvis alle 8 scenarier passerer:

```bash
cd /Users/mikkelhansen/juriitech-landing
git tag portal-v1.0.0
echo "Portal v1.0.0 fuldt smoke-tested 2026-05-02 — alle 8 scenarier OK"
```

Hvis et scenario fejler — diagnoser i denne rækkefølge:
1. Browser DevTools console — JS-fejl?
2. Network tab — Supabase-request returnerer 4xx/5xx?
3. Streamlit terminal — Python-traceback?
4. Fly logs hvis production — `fly logs --no-tail | tail -100`

---

## Self-review

✅ **Spec coverage**:
- "End-to-end brugerflow" → Task 2 (login), 3 (dashboard), 6 (SSO-klik), 7 (logout)
- "Auth-flow (SSO)" → Task 5 (PAX-side) + Task 6 (portal-side)
- "Dashboard data + UI" → Task 3
- "PAX-side ændringer" → Task 5
- "Sikkerhed" → Task 5 (token clear), Task 1 (anon-key dokumenteret som offentlig)
- "Adgangskontrol" → Task 3 (hardcoded liste)
- "Test-strategi" alle 8 scenarier → Task 7

✅ **Placeholder scan**: Ingen TBD/TODO. Alle code-blocks er komplette.

✅ **Type-konsistens**: `auth.js` exports matcher hvad `login.html`/`dashboard.html`/`index.html` importerer. `try_sso_login()` i auth.py kaldes med samme navn i app.py.

⚠️ **Note til engineer:** I Task 1 step 2 skal `PASTE_FROM_ENV_FILE` erstattes med faktisk anon-key. I Task 6 step 2 hvis du tester lokalt med `localhost:8501`, husk at rollback dashboard.html's PAX-URL inden commit.
