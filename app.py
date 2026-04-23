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

# ---------- ADMIN-DETEKTION FRA URL ----------
# Skal ske FØR st.navigation så admin-mode er sat når siderne køres
_query = st.query_params
if "admin" in _query and _ADMIN_KEY and _query.get("admin") == _ADMIN_KEY:
    st.session_state.er_admin = True
if "er_admin" not in st.session_state:
    st.session_state.er_admin = False

# ---------- MULTI-PAGE NAVIGATION ----------
_pages = [
    st.Page("forside.py", title="Forside", default=True, url_path="forside"),
    st.Page("arkiv.py", title="Søg i arkivet", url_path="arkiv"),
]
_pg = st.navigation(_pages)
_pg.run()
