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
        "sandsynligheder_dict",
        "sagsresume",
        "seneste_svar",
        "seneste_svarbrev",
        "seneste_tjekliste",
        "seneste_anonymisering",
        "chat_historik",
        "anon_resultater_per_fil",
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

    # ----- Beregn signaturer så førstevurderingen IKKE regenereres -----
    # Forside.py bruger en tuple-baseret signatur til at afgøre om sagen
    # er ændret siden sidst. Hvis 'auto_vurdering_for_signatur' matcher
    # den aktuelle kombinerede signatur, springes regenereringen over.
    sag = st.session_state.get("aktuel_sag") or {}
    sag_filer = sag.get("filer") or []
    sag_sig = tuple(sorted(
        (
            f.get("filnavn", ""),
            len(f.get("bytes") or b"") or len(f.get("tekst") or ""),
        )
        for f in sag_filer
    ))

    sagsakter_tekst = st.session_state.get("sagsakter", "") or ""
    sagsakter_filer = st.session_state.get("sagsakter_filer", []) or []
    sagsakter_sig = tuple(
        (
            f.get("filnavn", ""),
            len(f.get("bytes") or b""),
            len(f.get("tekst") or ""),
        )
        for f in sagsakter_filer
    )
    kombineret_sig = (sag_sig, hash(sagsakter_tekst), sagsakter_sig)

    # Sæt BEGGE signaturer til samme værdi — så når forsiden rendres,
    # ser den at 'auto_vurdering_for_signatur == kombineret_sig' og
    # springer auto-vurderingen over. Den gemte førstevurdering (der
    # allerede ligger i auto_vurdering_tekst) vises som den er.
    st.session_state.sidste_sagsfil_signatur = sag_sig
    st.session_state.auto_vurdering_for_signatur = kombineret_sig
    st.session_state.sagsakter_opdaterede_vurdering = False


def _genaabn_gemt_sag(sag_id, titel):
    """
    Henter den gemte sag fra databasen, gendanner session-state, og
    navigerer bagefter til Forside så brugeren lander lige der hvor
    de slap. Viser et tydeligt loading-panel undervejs.
    """
    # Tydeligt, pænt loading-panel der bliver synligt mens vi arbejder
    loading_placeholder = st.empty()
    loading_placeholder.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #EEEAFF 0%, #F0EEFD 100%);
            padding: 24px 28px;
            border-radius: 16px;
            margin: 20px 0;
            border-left: 4px solid #6366F1;
            display: flex;
            align-items: center;
            gap: 16px;
        ">
            <div style="
                width: 18px; height: 18px; border-radius: 50%;
                background: radial-gradient(circle at 30% 30%,
                    #A5B4FC, #6366F1 60%, #4F46E5);
                box-shadow: 0 0 16px rgba(99, 102, 241, 0.45);
                animation: juri-pulse 1.4s ease-in-out infinite;
                flex-shrink: 0;
            "></div>
            <div>
                <div style="font-weight: 700; color: #111827;
                     font-size: 1rem; margin-bottom: 2px;">
                    Genåbner sagen…
                </div>
                <div style="color: #475569; font-size: 0.88rem;">
                    <strong>{titel}</strong><br/>
                    Indlæser dine uploadede filer, sagsakter og tidligere
                    analyse. Du bliver sendt tilbage til forsiden om et øjeblik.
                </div>
            </div>
        </div>
        <style>
            @keyframes juri-pulse {{
                0%, 100% {{ transform: scale(0.85); opacity: 0.75; }}
                50%      {{ transform: scale(1.15); opacity: 1; }}
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    try:
        detaljer = hent_gemt_sag(sag_id)
        if not detaljer or not detaljer.get("state_json"):
            loading_placeholder.empty()
            st.error("Kunne ikke finde den gemte sag i databasen.")
            return

        try:
            state = json.loads(detaljer["state_json"])
        except Exception as e:
            loading_placeholder.empty()
            st.error(f"Kunne ikke læse gemt state: {e}")
            return

        _gendan_state_fra_json(state)
        st.session_state.aktiv_gemt_sag_id = sag_id

        # Navigér til forsiden — det er dér brugeren skal lande, ikke
        # blive stående på gemte-sager med en lille success-besked.
        try:
            st.switch_page("forside.py")
        except Exception:
            # Fallback hvis switch_page af en eller anden grund fejler
            loading_placeholder.empty()
            st.success(
                f"Sag '{titel}' er indlæst. Klik på **Forside** "
                "i menuen til venstre for at fortsætte."
            )
    except Exception as e:
        loading_placeholder.empty()
        st.error(f"Noget gik galt under genåbning af sagen: {e}")


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
    # Hvis brugeren trykkede 'Åbn' i forrige rerun, håndtér det FØR vi
    # renderer listen — så bliver loading-panelet vist stort og tydeligt
    # øverst på siden, ikke nede ved den specifikke række.
    _aaben_id = st.session_state.pop("_aabn_gemt_sag_id", None)
    _aaben_titel = st.session_state.pop("_aabn_gemt_sag_titel", None)
    if _aaben_id:
        _genaabn_gemt_sag(_aaben_id, _aaben_titel or "sagen")
        # _genaabn_gemt_sag kalder st.switch_page — kun hvis den fejler
        # fortsætter vi her og viser listen nedenunder.

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
                        # Sæt flag i session_state og rerun — så bliver
                        # loading-panelet vist ØVERST på siden i næste
                        # render-cyklus, før noget andet tegnes.
                        st.session_state._aabn_gemt_sag_id = sag["id"]
                        st.session_state._aabn_gemt_sag_titel = sag["titel"]
                        st.rerun()
                with kol_slet:
                    if st.button("Slet", key=f"slet_{sag['id']}"):
                        if slet_gemt_sag(sag["id"]):
                            st.success("Sag slettet.")
                            st.rerun()
