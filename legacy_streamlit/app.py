"""
Juriitech — entry point.

Denne fil definerer den overordnede multi-page navigation og er det
Streamlit Cloud starter. Selve sidernes indhold ligger i:
  - forside.py (Analysér en sag)
  - arkiv.py (Søg i arkivet)

Hvis brugeren har admin-flaget i URL'en (?admin=<KEY>), gives adgang til
scraper-knapper, statistik og andre administrative værktøjer inde i
forside.py og arkiv.py.
"""

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

# ---------- SSO LOADING-OVERLAY ----------
# Når brugeren klikker PAX i juriitech.com/dashboard, lander de her med
# ?sso_token=<refresh_token> i URL'en. Mellem at browseren parser HTML
# og at try_sso_login() har valideret tokenet + redirected, ser brugeren
# default Streamlit-shell + JWT-tokenet i URL'en. Vi inject'er et
# juriitech-brandet fuldskærms-overlay der dækker hele viewport indtil
# SSO er færdig (try_sso_login rydder URL'en → overlay vises ikke
# længere). Ren CSS, ingen JS — virker uanset om Streamlit-frontenden
# er færdig.
#
# Vises KUN hvis vi faktisk er ved at processere SSO-token — ikke hvis
# brugeren allerede er logget ind, og ikke hvis et tidligere SSO-forsøg
# fejlede (i så fald har try_sso_login allerede ryddet URL'en og sat
# _sso_fejl_besked, og brugeren skal se login-form'en, ikke overlay'et).
if (
    st.query_params.get("sso_token")
    and "user" not in st.session_state
    and not st.session_state.get("_sso_fejl_besked")
):
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
            font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont,
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
            font-weight: 700;
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

# Indlæs miljøvariabler (inkl. ADMIN_KEY) før alt andet
load_dotenv()
_ADMIN_KEY = os.getenv("ADMIN_KEY", "")


# ---------- SENTRY ERROR-MONITORING ----------
# Initialiseres FØR alt andet så crashes under app-opstart også fanges.
# DSN læses fra Streamlit secrets eller environment variable. Hvis den
# mangler (fx ved lokal udvikling uden konfiguration), springes
# Sentry-initialiseringen over så appen stadig virker.

# Felt-navne der KAN indeholde klagers PII eller fil-bytes. Hvis Sentry
# fanger en exception med disse i frame-vars/extras, redactes værdien
# før eventet sendes. Listen er udvidet ved hvert nyt sted vi gemmer PII.
_PII_FELT_NAVNE = frozenset({
    "aktuel_sag", "sagsakter", "sagsakter_filer", "filer",
    "fil_bytes", "bytes", "raw_bytes", "pdf_bytes",
    "tekst", "indhold", "klage", "klage_tekst", "sag_tekst",
    "klager_navn", "klagers_navn", "email", "fulde_navn",
    "auto_vurdering_tekst", "seneste_svarbrev", "seneste_anonymisering",
    "seneste_tjekliste", "sagsresume", "chat_historik",
    "state_json", "aktiv_sag_state", "snapshot",
    "spoergsmaal", "ekstra_instrukser",
    "password", "access_token", "refresh_token", "api_key",
})


def _scrub_pii(node, _depth=0):
    """
    Rekursiv PII-scrubber til Sentry-events. Erstatter værdier af
    følsomme felter med "[REDACTED]" og trunkerer lange strenge.
    Max-dybde 8 så vi ikke rammer rekursions-grænse på cykliske
    referencer eller meget dybe pydantic-modeller.
    """
    if _depth > 8:
        return "[REDACTED:max-depth]"
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            # Felt-navn matcher kendt PII → erstat værdien
            if isinstance(k, str) and k.lower() in _PII_FELT_NAVNE:
                out[k] = "[REDACTED]"
            else:
                out[k] = _scrub_pii(v, _depth + 1)
        return out
    if isinstance(node, (list, tuple)):
        scrubbed = [_scrub_pii(item, _depth + 1) for item in node]
        return type(node)(scrubbed) if not isinstance(node, tuple) else tuple(scrubbed)
    if isinstance(node, bytes):
        return f"[REDACTED:bytes len={len(node)}]"
    if isinstance(node, str) and len(node) > 500:
        # Lange strenge i extras/messages er sandsynligvis tekst-dumps
        # (klage, AI-svar). Trunkér til 200 tegn + længde-indikator.
        return node[:200] + f"...[TRUNCATED len={len(node)}]"
    return node


def _sentry_before_send(event, hint):
    """
    Renser Sentry-event for PII før det forlader processen. Følger
    Sentry's officielle before_send-API: returnér modificeret event
    (eller None for at droppe det helt).

    Beskytter mod 3 lækage-vektorer:
      1. Stack-frame local vars (`event["exception"]["values"][N]["stacktrace"]["frames"][N]["vars"]`)
      2. Extra context sat via sentry_sdk.set_context / capture med extras
      3. Request body hvis Sentry's integration har samlet det op
    """
    try:
        # 1) Stack-frame vars
        for exc in (event.get("exception") or {}).get("values") or []:
            for frame in (exc.get("stacktrace") or {}).get("frames") or []:
                if frame.get("vars"):
                    frame["vars"] = _scrub_pii(frame["vars"])

        # 2) Extra context og tags
        if event.get("extra"):
            event["extra"] = _scrub_pii(event["extra"])
        if event.get("contexts"):
            event["contexts"] = _scrub_pii(event["contexts"])

        # 3) Request body (hvis Sentry-integration har samlet form-data op)
        req = event.get("request") or {}
        if req.get("data"):
            req["data"] = _scrub_pii(req["data"])
    except Exception as e:
        # Fail-open: hvis scrubberen kaster, vil vi hellere sende et
        # event uden scrubbing end at miste fejlen helt. Print kort.
        print(f"DEBUG: Sentry PII-scrubber fejlede: {e}")
    return event


def _init_sentry():
    try:
        # Forsøg først Streamlit secrets (production), falder tilbage til
        # environment variable (lokal udvikling)
        sentry_dsn = ""
        try:
            sentry_dsn = st.secrets.get("SENTRY_DSN", "") or ""
        except Exception:
            pass
        if not sentry_dsn:
            sentry_dsn = os.getenv("SENTRY_DSN", "")

        if not sentry_dsn:
            return False

        import sentry_sdk
        sentry_sdk.init(
            dsn=sentry_dsn,
            # PII slået FRA. Tidligere var dette True hvilket sendte
            # brugerens IP og frame-vars (potentielt klage-tekst og
            # fil-bytes) til Sentry. Den eksplicitte scrubber nedenfor
            # er belt-and-suspenders.
            send_default_pii=False,
            # before_send fanger alle events før de forlader processen
            # og redacter kendte PII-felter (aktuel_sag, fil_bytes,
            # klager_navn, email, m.fl.). Se _sentry_before_send.
            before_send=_sentry_before_send,
            # Saml 10% af requests til performance-monitoring
            traces_sample_rate=0.1,
            # Tag environment så vi kan skelne prod fra evt. staging
            environment=os.getenv("SENTRY_ENV", "production"),
            # Release-version så vi kan se hvilken kodeversion en bug kom fra
            release=os.getenv("SENTRY_RELEASE", "juriitech-pax@dev"),
        )
        return True
    except Exception as e:
        print(f"DEBUG: Sentry init fejlede (ikke kritisk): {e}")
        return False


_SENTRY_AKTIV = _init_sentry()


# ---------- AUTO-LOAD PAKKEREJSELOVEN ----------
# Sikrer at lovens paragraffer er i vidensbanken. Kører kun én gang pr.
# server-instans takket være @st.cache_resource — første gang appen
# starter scrapes loven stille; derefter gør funktionen ingenting.
@st.cache_resource
def _sikr_pakkerejseloven_i_db():
    """Indlæs pakkerejseloven hvis den ikke allerede er der. Fejler
    stille, så appen aldrig blokeres hvis scraping fejler."""
    try:
        from database import opret_tabeller, antal_af_type
        opret_tabeller()
        antal = antal_af_type("lovgivning")
        if antal == 0:
            from pakkerejselov_scraper import scrape_og_gem_pakkerejseloven
            scrape_og_gem_pakkerejseloven()
    except Exception as e:
        print(f"DEBUG: Auto-load af pakkerejselov fejlede (ikke kritisk): {e}")
    return True

_sikr_pakkerejseloven_i_db()


# ---------- AUTO-LOAD ANONYMISERINGSREGLER ----------
# Sikrer at de fire autoritative kilder om anonymisering/pseudonymisering
# ligger i vidensbanken som 'anonymisering_regler'. Disse bliver
# automatisk en del af modellens forståelse når anonymisering udføres —
# brugeren skal ikke selv scrape eller uploade. Fejler stille.
@st.cache_resource
def _sikr_anonymiseringsregler_i_db():
    try:
        from database import opret_tabeller, antal_af_type
        opret_tabeller()
        antal = antal_af_type("anonymisering_regler")
        if antal == 0:
            from anonymisering_regler_scraper import (
                scrape_og_gem_anonymiseringsregler,
            )
            scrape_og_gem_anonymiseringsregler()
    except Exception as e:
        print(
            "DEBUG: Auto-load af anonymiseringsregler fejlede "
            f"(ikke kritisk): {e}"
        )
    return True

_sikr_anonymiseringsregler_i_db()

# ═══════════════════════════════════════════════════════════════
# AUTH-GATE (Phase B2)
# ═══════════════════════════════════════════════════════════════
# FØRSTE ting vi gør efter bootstrap-funktionerne er at tjekke om
# brugeren er logget ind. Hvis ikke, viser vi login-siden og stopper —
# resten af app'en (forside, arkiv, gemte sager, navigation) renderes
# slet ikke. Det er den enkleste form for "alt bag login".
#
# Backward compat: Hvis SUPABASE_URL/ANON_KEY ikke er sat (lokal dev,
# eller før secrets er rullet ud), springer vi auth-gate over så vi
# ikke crasher app'en. Det er bevidst lempeligt for udvikler-flowet.
import auth as _auth

_auth_konfigureret = bool(
    os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_ANON_KEY")
)

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

# ---------- ADMIN-DETEKTION ----------
# Phase B2+: er_admin styres nu af brugerens role i users-tabellen.
# URL-parameter ?admin=KEY bevares som backup for lokale tests
# (når _auth_konfigureret er False).
_query = st.query_params
if _auth_konfigureret:
    # Logged-in user: rolle fra users-tabellen styrer admin-status
    st.session_state.er_admin = _auth.is_admin()
else:
    # Lokal dev uden auth: behold gammel URL-baseret detektion
    if "admin" in _query and _ADMIN_KEY and _query.get("admin") == _ADMIN_KEY:
        st.session_state.er_admin = True
    if "er_admin" not in st.session_state:
        st.session_state.er_admin = False

# ---------- LOGOUT-KNAP I SIDEBAR ----------
# Vises kun når auth er aktiv (skjules i lokal dev). Kommer nederst
# i sidebaren via _auth.render_logout_button(); selve st.navigation
# placerer side-vælgeren ovenfor.
if _auth_konfigureret:
    _auth.render_logout_button(placement="sidebar")

# ---------- MULTI-PAGE NAVIGATION ----------
_pages = [
    st.Page(
        "forside.py",
        title="Forside",
        default=True,
        url_path="forside",
        icon=":material/home:",
    ),
    st.Page(
        "arkiv.py",
        title="Søg i arkivet",
        url_path="arkiv",
        icon=":material/search:",
    ),
    st.Page(
        "gemte_sager.py",
        title="Gemte sager",
        url_path="gemte-sager",
        icon=":material/folder:",
    ),
    st.Page(
        "disclaimer.py",
        title="Disclaimer",
        url_path="disclaimer",
        icon=":material/info:",
    ),
]

# Admin-side vises KUN for brugere med role='admin'. Den selv har
# desuden adgangskontrol i top af filen (auth.is_admin()) så ingen
# kan komme ind via direkte URL-tilgang selvom de gætter URL'en.
if _auth_konfigureret and _auth.is_admin():
    _pages.append(
        st.Page(
            "admin.py",
            title="Admin",
            url_path="admin",
            icon=":material/admin_panel_settings:",
        )
    )

_pg = st.navigation(_pages)

# ---------- TOP-LEVEL SAFETY NET ----------
# Wrap _pg.run() i en try/except så ALLE crashes — også uforudsete
# import-fejl eller database-fejl — vises som en venlig fejlboks i
# stedet for Streamlits rå røde traceback. Brugeren får besked om at
# prøve igen, og fejlen sendes automatisk til Sentry så vi ser den.
try:
    _pg.run()
except Exception as _kritisk_fejl:
    # Print fuld traceback til stdout så fly logs viser fejlen direkte
    # — vi har ikke altid Sentry-adgang under feltdebugging.
    import traceback as _traceback
    print("KRITISK FEJL i _pg.run():", flush=True)
    print(_traceback.format_exc(), flush=True)

    # Send til Sentry hvis muligt (ikke-blokkerende)
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as _scope:
            _scope.set_tag("brugerhandling", "side-opstart")
            _scope.set_level("fatal")
            sentry_sdk.capture_exception(_kritisk_fejl)
    except Exception:
        pass

    # Vis venlig fejlboks — undgår at brugeren ser en rå Python-traceback
    st.markdown(
        """
        <div style="
            margin: 40px auto; max-width: 640px;
            padding: 32px; border-radius: 16px;
            background: #FEF2F2; border: 1px solid #FCA5A5;
            font-family: 'Space Grotesk', -apple-system, sans-serif;
        ">
          <div style="font-size: 1.4rem; font-weight: 700;
            color: #991B1B; margin-bottom: 8px;">
            Hov — noget gik galt under opstart
          </div>
          <div style="color: #7F1D1D; font-size: 1rem; line-height: 1.55;">
            juriitech PAX kunne ikke starte korrekt lige nu. Vores system
            er allerede blevet underrettet, og fejlen bliver udbedret.
            <br><br>
            <b>Prøv venligst at:</b>
            <ul style="margin: 8px 0 0 0; padding-left: 22px;">
              <li>Genindlæse siden (Cmd+R eller Ctrl+R) om et øjeblik</li>
              <li>Skrive til support@juriitech.com hvis problemet
                  fortsætter</li>
            </ul>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
