"""
Arkiv-side: stikordssøgning gennem alle tidligere klager, afgørelser og vilkår
der ligger i vidensbanken. Med badges, filter og vector-similarity-boost.
"""

import streamlit as st

from database import soeg_i_arkiv, find_relevante_sager
from embeddings import embed_sporgsmaal
from badges import badge, doktype_badge, udfalds_badge_fra_tekst, udled_afgoerelsesdato


# Admin-flag sat af app.py
ER_ADMIN = st.session_state.get("er_admin", False)

# ---------- SKJUL DELINGS-MENU FOR IKKE-ADMINS ----------
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

# Samme styling som hovedappen
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap');
    html, body, .stApp, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        -webkit-font-smoothing: antialiased;
    }
    h1, h2, h3, h4 {
        font-family: 'Source Serif 4', Georgia, serif !important;
        font-weight: 600 !important;
        letter-spacing: -0.015em !important;
    }
    section[data-testid="stSidebar"] {
        backdrop-filter: saturate(180%) blur(24px) !important;
        -webkit-backdrop-filter: saturate(180%) blur(24px) !important;
        background-color: rgba(250, 250, 252, 0.72) !important;
        border-right: 1px solid rgba(0, 0, 0, 0.06) !important;
    }
    @media (prefers-color-scheme: dark) {
        section[data-testid="stSidebar"] {
            background-color: rgba(25, 27, 32, 0.72) !important;
        }
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
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03) !important;
    }
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 100px;
        font-size: 0.75rem;
        font-weight: 500;
        letter-spacing: 0.01em;
        line-height: 1.4;
        margin-right: 6px;
    }
    .badge-green  { background: rgba(34, 197, 94, 0.14);  color: #15803D; }
    .badge-red    { background: rgba(239, 68, 68, 0.14);  color: #B91C1C; }
    .badge-yellow { background: rgba(234, 179, 8, 0.16);  color: #A16207; }
    .badge-blue   { background: rgba(59, 130, 246, 0.14); color: #1D4ED8; }
    .badge-gray   { background: rgba(100, 116, 139, 0.14); color: #475569; }
    .badge-purple { background: rgba(139, 92, 246, 0.14); color: #6D28D9; }
    @media (prefers-color-scheme: dark) {
        .badge-green  { color: #86EFAC; }
        .badge-red    { color: #FCA5A5; }
        .badge-yellow { color: #FDE047; }
        .badge-blue   { color: #93C5FD; }
        .badge-gray   { color: #CBD5E1; }
        .badge-purple { color: #C4B5FD; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- HOVEDINDHOLD ----------
st.title("Søg i arkivet")
st.caption(
    "Søg gennem alle tidligere afgørelser fra Pakkerejse-Ankenævnet, uploadede "
    "klager, og TUI's rejsevilkår. Brug søgning med stikord for en præcis "
    "tekstsøgning, eller skift til semantisk søgning for at finde sager der "
    "handler om det samme tema, selv hvis ordvalget er anderledes."
)


# ---------- SØGE-INPUT ----------
kol_soeg, kol_filter, kol_mode = st.columns([3, 1.2, 1.2])

with kol_soeg:
    stikord = st.text_input(
        "Stikord",
        placeholder="fx 'forsinket fly' eller 'rengøring hotel'",
        label_visibility="collapsed",
    )

with kol_filter:
    filter_type = st.selectbox(
        "Dokumenttype",
        options=["Alle", "Afgørelser", "Klager", "Vilkår"],
        label_visibility="collapsed",
    )

with kol_mode:
    soege_mode = st.selectbox(
        "Søgemetode",
        options=["Stikord", "Semantisk"],
        label_visibility="collapsed",
        help=(
            "Stikord = klassisk tekstsøgning. "
            "Semantisk = find sager der handler om det samme, også hvis "
            "ordvalget er anderledes."
        ),
    )


dokumenttype_map = {
    "Alle": None,
    "Afgørelser": "afgoerelse",
    "Klager": "klage",
    "Vilkår": "vilkaar",
}
doktype = dokumenttype_map.get(filter_type)


# ---------- UDFØR SØGNING ----------
if stikord and stikord.strip():
    if soege_mode == "Semantisk":
        with st.spinner("Søger semantisk i arkivet..."):
            emb = embed_sporgsmaal(stikord)
            if emb is None:
                st.error("Kunne ikke generere embedding — prøv igen eller brug stikord-søgning.")
                resultater = []
            else:
                resultater = find_relevante_sager(
                    sporgsmaal_embedding=emb,
                    top_k=30,
                    dokumenttype=doktype,
                )
    else:
        with st.spinner("Søger i arkivet..."):
            resultater = soeg_i_arkiv(
                stikord=stikord,
                dokumenttype=doktype,
                begraens=50,
            )
else:
    # Ingen søgning — vis alle seneste
    resultater = soeg_i_arkiv(dokumenttype=doktype, begraens=25)


# ---------- RESULTATVISNING ----------
st.markdown(f"**{len(resultater)} resultater**")
st.divider()

if not resultater:
    st.info("Ingen resultater. Prøv et andet stikord eller skift søgemetode.")
else:
    for r in resultater:
        with st.container(border=True):
            # Øverste række: badges og filnavn
            badges_html = []
            badges_html.append(doktype_badge(r.get("dokumenttype") or "afgoerelse"))

            # Udfaldsbadge (kun for afgørelser)
            if r.get("dokumenttype") == "afgoerelse":
                ub = udfalds_badge_fra_tekst(r.get("indhold") or "")
                if ub:
                    badges_html.append(badge(ub[0], ub[1]))

            # Similarity-badge (kun hvis semantisk søgning)
            if r.get("similarity") is not None:
                pct = int(r["similarity"] * 100)
                if pct >= 70:
                    badges_html.append(badge(f"{pct}% match", "green"))
                elif pct >= 55:
                    badges_html.append(badge(f"{pct}% match", "yellow"))
                else:
                    badges_html.append(badge(f"{pct}% match", "gray"))

            st.markdown(" ".join(badges_html), unsafe_allow_html=True)
            st.markdown(f"**{r.get('filnavn', 'ukendt')}**")

            # Afgørelsesdato (udledt fra dokumentets indhold)
            afgoerelses_dato = udled_afgoerelsesdato(
                r.get("indhold"),
                filnavn=r.get("filnavn"),
            )
            dato_str = afgoerelses_dato or "dato ikke angivet"
            meta_linje = f"Afgjort {dato_str}"
            if r.get("kilde_url"):
                meta_linje += f"  ·  [Åbn original]({r['kilde_url']})"
            st.caption(meta_linje)

            # Uddrag af indholdet
            indhold = r.get("indhold") or ""
            uddrag = indhold[:400] + ("..." if len(indhold) > 400 else "")

            with st.expander("Vis uddrag"):
                st.text(uddrag)
                if len(indhold) > 400:
                    with st.expander("Se hele indholdet"):
                        st.text(indhold)
