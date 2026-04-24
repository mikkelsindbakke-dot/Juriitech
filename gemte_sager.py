"""
Gemte sager-side: oversigt over brugerens gemte sagsbehandlinger.
Brugeren kan klikke på en sag for at genoptage arbejdet på den.
"""

import base64
import json

import streamlit as st

from database import hent_gemte_sager, hent_gemt_sag, slet_gemt_sag


ER_ADMIN = st.session_state.get("er_admin", False)


if not ER_ADMIN:
    st.markdown(
        """
        <style>
        #MainMenu {visibility: hidden !important;}
        [data-testid="stToolbar"] {visibility: hidden !important;}
        [data-testid="stDeployButton"] {display: none !important;}
        footer {visibility: hidden !important;}
        .viewerBadge_container__1QSob { display: none !important; }
        [data-testid="manage-app-button"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# Styling (matcher øvrige sider)
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap');
    html, body, .stApp, [class*="css"] {
        font-family: 'Inter', -apple-system, sans-serif;
    }
    h1 a, h2 a, h3 a, h4 a,
    [data-testid="stHeaderActionElements"],
    [data-testid="stHeading"] a {
        display: none !important;
    }
    h1, h2, h3, h4 {
        font-family: 'Source Serif 4', Georgia, serif !important;
        font-weight: 600 !important;
    }
    section[data-testid="stSidebar"] {
        background-color: #FAFAFA !important;
        border-right: 1px solid rgba(0, 0, 0, 0.06) !important;
    }
    .stApp, .main {
        background-color: #FFFFFF !important;
    }

    /* ========== NAV-MENU — afrundede pillers, ikon + tekst ========== */
    [data-testid="stSidebarNav"] { padding-top: 0.6rem !important; }
    [data-testid="stSidebarNav"] ul { padding: 0 0.35rem !important; margin: 0 !important; }
    [data-testid="stSidebarNav"] li { margin: 2px 0 !important; list-style: none !important; }
    [data-testid="stSidebarNav"] a {
        display: flex !important; align-items: center !important; gap: 12px !important;
        padding: 9px 14px !important; border-radius: 10px !important;
        font-family: 'Inter', sans-serif !important; font-size: 0.95rem !important;
        font-weight: 500 !important; color: #374151 !important;
        text-decoration: none !important; border: none !important;
        transition: background-color 0.12s ease, color 0.12s ease !important;
    }
    [data-testid="stSidebarNav"] a:hover {
        background-color: rgba(17, 24, 39, 0.05) !important; color: #111827 !important;
    }
    [data-testid="stSidebarNav"] a[aria-current="page"],
    [data-testid="stSidebarNav"] a[data-selected="true"] {
        background-color: rgba(17, 24, 39, 0.08) !important;
        color: #111827 !important; font-weight: 600 !important;
    }
    [data-testid="stSidebarNav"] a [data-testid="stIconMaterial"] {
        font-size: 20px !important; color: #4B5563 !important; font-weight: 400 !important;
    }
    [data-testid="stSidebarNav"] a[aria-current="page"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarNav"] a[data-selected="true"] [data-testid="stIconMaterial"] {
        color: #111827 !important;
    }
    .main .block-container {
        padding-top: 3rem !important;
        max-width: 1000px !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 10px !important;
        padding: 1.25rem !important;
        margin-bottom: 0.75rem !important;
        border: 1px solid rgba(127, 127, 127, 0.14) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _gendan_state_fra_json(state):
    """Gendan session state fra gemt JSON-snapshot."""
    for navn in (
        "sagsakter",
        "auto_vurdering_tekst",
        "relevante_sager",
        "match_info",
        "seneste_svar",
        "seneste_svarbrev",
        "seneste_tjekliste",
        "seneste_anonymisering",
    ):
        if navn in state:
            st.session_state[navn] = state[navn]

    # aktuel_sag — base64-decodede bytes-felter
    if "aktuel_sag" in state and state["aktuel_sag"]:
        sag = state["aktuel_sag"]
        if "filer" in sag:
            for fil in sag["filer"]:
                if fil.get("bytes_b64"):
                    fil["bytes"] = base64.b64decode(fil["bytes_b64"])
                    del fil["bytes_b64"]
        st.session_state.aktuel_sag = sag

    # sagsakter_filer
    if "sagsakter_filer" in state:
        filer = state["sagsakter_filer"]
        for fil in filer:
            if fil.get("bytes_b64"):
                fil["bytes"] = base64.b64decode(fil["bytes_b64"])
                del fil["bytes_b64"]
        st.session_state.sagsakter_filer = filer

    # Nulstil signatur så vurderingen ikke genkøres ved re-open
    st.session_state.auto_vurdering_for_signatur = "gendannet"
    st.session_state.sagsakter_opdaterede_vurdering = False


st.title("Gemte sager")
st.caption(
    "Her finder du alle sagsbehandlinger du har gemt. Klik på en sag for at "
    "genoptage arbejdet præcis hvor du slap."
)


gemte = hent_gemte_sager(user_id=None, begraens=100)

if not gemte:
    st.info(
        "Du har endnu ingen gemte sager. Gå til forsiden, upload en sag, "
        "og tryk **Gem sagen** nederst for at gemme dit arbejde."
    )
else:
    for sag in gemte:
        with st.container(border=True):
            kol_t, kol_k = st.columns([4, 1])
            with kol_t:
                opd = sag.get("opdateret_dato")
                opd_str = (
                    opd.strftime("%d-%m-%Y %H:%M") if opd else "ukendt"
                )
                st.markdown(f"**{sag['titel']}**")
                st.caption(f"Senest opdateret: {opd_str}")
            with kol_k:
                kol_åbn, kol_slet = st.columns(2)
                with kol_åbn:
                    if st.button("Åbn", key=f"aabn_{sag['id']}", type="primary"):
                        detaljer = hent_gemt_sag(sag["id"])
                        if detaljer and detaljer.get("state_json"):
                            try:
                                state = json.loads(detaljer["state_json"])
                            except Exception as e:
                                st.error(f"Kunne ikke læse gemt state: {e}")
                                state = None
                            if state:
                                # Gendan state i session_state
                                _gendan_state_fra_json(state)
                                st.session_state.aktiv_gemt_sag_id = sag["id"]
                                st.success(
                                    f"Sag '{sag['titel']}' indlæst. "
                                    "Gå til Forside for at fortsætte."
                                )
                                st.rerun()
                with kol_slet:
                    if st.button("Slet", key=f"slet_{sag['id']}"):
                        if slet_gemt_sag(sag["id"]):
                            st.success("Sag slettet.")
                            st.rerun()
