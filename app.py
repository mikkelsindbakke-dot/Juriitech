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

# Indlæs miljøvariabler (inkl. ADMIN_KEY) før alt andet
load_dotenv()
_ADMIN_KEY = os.getenv("ADMIN_KEY", "")


# ---------- SENTRY ERROR-MONITORING ----------
# Initialiseres FØR alt andet så crashes under app-opstart også fanges.
# DSN læses fra Streamlit secrets eller environment variable. Hvis den
# mangler (fx ved lokal udvikling uden konfiguration), springes
# Sentry-initialiseringen over så appen stadig virker.
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
            # Send PII (klage-tekst, brugerinfo) for rigere fejl-kontekst.
            # Sentry's data-region er Frankfurt (.de.sentry.io) så data
            # forlader aldrig EU.
            send_default_pii=True,
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

# ---------- ADMIN-DETEKTION FRA URL ----------
# Skal ske FØR st.navigation så admin-mode er sat når siderne køres
_query = st.query_params
if "admin" in _query and _ADMIN_KEY and _query.get("admin") == _ADMIN_KEY:
    st.session_state.er_admin = True
if "er_admin" not in st.session_state:
    st.session_state.er_admin = False

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
_pg = st.navigation(_pages)
_pg.run()
