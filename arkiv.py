"""
Arkiv-side: avanceret søgning gennem alle tidligere afgørelser, klager
og vilkår i vidensbanken.

Funktioner:
  - Hybrid søgning (kombinerer stikord + semantik for bedst muligt resultat)
  - Filter på dokumenttype, udfald og dato
  - Resultatkort med prominent visning af udfald, dato og match-%
  - "Find lignende"-knap der bruger en sag som søgegrundlag
"""

import re
from datetime import datetime, timedelta

import streamlit as st

from database import soeg_i_arkiv, find_relevante_sager
from embeddings import embed_sporgsmaal
from selskab_profiler import hent_navn as _hent_selskab_navn
from badges import (
    badge,
    doktype_badge,
    udfalds_badge_fra_tekst,
    udled_afgoerelsesdato,
)


# Admin-flag sat af app.py
ER_ADMIN = st.session_state.get("er_admin", False)

# ---------- SKJUL DELINGS-MENU FOR IKKE-ADMINS ----------
if not ER_ADMIN:
    st.markdown(
        """
        <style>
        #MainMenu {visibility: hidden !important;}
        [data-testid="stToolbar"] {visibility: hidden !important;}
        /* MEN: behold sidebar-collapse/expand-knappen synlig saa
           brugeren kan aabne menuen igen efter at have lukket den */
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stSidebarCollapsedControl"],
        button[kind="headerNoPadding"] {
            visibility: visible !important;
            display: flex !important;
            opacity: 1 !important;
        }
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
    h1 a, h2 a, h3 a, h4 a, h5 a, h6 a,
    [data-testid="stHeaderActionElements"],
    [data-testid="stHeading"] a {
        display: none !important;
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
        max-width: 1100px !important;
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
        padding: 4px 11px;
        border-radius: 100px;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.01em;
        line-height: 1.4;
        margin-right: 6px;
    }
    .badge-green  { background: rgba(34, 197, 94, 0.32) !important;  color: #14532D !important; }
    .badge-red    { background: rgba(239, 68, 68, 0.30) !important;  color: #881337 !important; }
    .badge-yellow { background: rgba(234, 179, 8, 0.34) !important;  color: #713F12 !important; }
    .badge-blue   { background: rgba(59, 130, 246, 0.26) !important; color: #172554 !important; }
    .badge-gray   { background: rgba(100, 116, 139, 0.22) !important; color: #1E293B !important; }
    .badge-purple { background: rgba(139, 92, 246, 0.26) !important; color: #3B0764 !important; }
    /* Resultat-kort uddrag — let bagrund så det adskiller sig fra meta */
    .arkiv-uddrag {
        background: rgba(99, 102, 241, 0.04);
        border-left: 3px solid rgba(99, 102, 241, 0.3);
        padding: 10px 14px;
        margin-top: 10px;
        border-radius: 6px;
        font-size: 0.92rem;
        color: #374151;
        line-height: 1.55;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- HJÆLPEFUNKTIONER ----------

def parse_dato(dato_str):
    """Parser en dato-streng som 'd. 12. juni 2024' eller '12-06-2024' til
    datetime-objekt. Returnerer None hvis det fejler."""
    if not dato_str:
        return None
    danske_maaneder = {
        "januar": 1, "februar": 2, "marts": 3, "april": 4,
        "maj": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "december": 12,
    }
    s = dato_str.lower().strip()

    # Format "12. juni 2024" eller "12 juni 2024"
    m = re.search(
        r"(\d{1,2})\.?\s*("
        + "|".join(danske_maaneder.keys())
        + r")\s+(\d{4})",
        s,
    )
    if m:
        dag, maaned_navn, aar = m.groups()
        try:
            return datetime(
                int(aar), danske_maaneder[maaned_navn], int(dag)
            )
        except (ValueError, KeyError):
            pass

    # Format "12-06-2024" eller "12/06/2024"
    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)
    if m:
        dag, maaned, aar = m.groups()
        try:
            return datetime(int(aar), int(maaned), int(dag))
        except ValueError:
            pass

    return None


def overholder_dato_filter(indhold, filnavn, dato_filter):
    """Tjek om afgørelsen falder inden for det valgte dato-interval."""
    if dato_filter == "Alle":
        return True

    dato_str = udled_afgoerelsesdato(indhold, filnavn=filnavn)
    if not dato_str:
        # Hvis vi ikke kan udlede dato, vis sagen (bedre at have for meget end for lidt)
        return True

    dato = parse_dato(dato_str)
    if not dato:
        return True

    nu = datetime.now()
    if dato_filter == "Sidste 6 måneder":
        return dato >= nu - timedelta(days=180)
    if dato_filter == "Sidste år":
        return dato >= nu - timedelta(days=365)
    if dato_filter == "Sidste 2 år":
        return dato >= nu - timedelta(days=730)
    if dato_filter == "Sidste 5 år":
        return dato >= nu - timedelta(days=1825)
    return True


def overholder_udfald_filter(indhold, dokumenttype, udfald_valgt):
    """Tjek om afgørelsen passer på de valgte udfald. Hvis intet er valgt,
    vises alle. Filteret er kun relevant for afgørelser."""
    if not udfald_valgt:
        return True
    # Filteret gælder kun for afgørelser
    if dokumenttype != "afgoerelse":
        return True
    ub = udfalds_badge_fra_tekst(indhold or "")
    if not ub:
        # Kunne ikke udlede — udelad fra resultater når filter er aktivt
        return False
    udfald_navn = ub[0]
    # Map til de menneskelige labels
    if "Fuld medhold" in udfald_navn:
        return "Fuld medhold til klager" in udfald_valgt
    if "Delvist" in udfald_navn:
        return "Delvist medhold" in udfald_valgt
    if "Afvist" in udfald_navn:
        # Sammenligningen er prefix-baseret så den virker for ALLE selskaber
        # (fx 'Afvist (TUI vinder)', 'Afvist (Apollo vinder)' osv.). Det
        # er også bagudkompatibelt med gamle session_state-værdier.
        return any(u.startswith("Afvist") for u in udfald_valgt)
    return False


def hybrid_soeg(stikord, doktype, top_k=40):
    """Kør både stikord-søgning og semantisk søgning, og kombinér
    resultaterne. Sager der findes af BEGGE metoder rangeres højest.

    Returnerer en liste med de samlede resultater, sorteret efter
    kombineret score. Hver sag har et 'kombineret_score'-felt der bruges
    til ranking.
    """
    # 1. Stikord-søgning (præcision)
    stikord_resultater = soeg_i_arkiv(
        stikord=stikord,
        dokumenttype=doktype,
        begraens=top_k,
    )
    # 2. Semantisk søgning (recall — finder synonymer/koncepter)
    semantisk_resultater = []
    emb = embed_sporgsmaal(stikord)
    if emb is not None:
        semantisk_resultater = find_relevante_sager(
            sporgsmaal_embedding=emb,
            top_k=top_k,
            dokumenttype=doktype,
        )

    # Saml i én dict per filnavn med kombineret score
    samlet = {}
    for i, r in enumerate(stikord_resultater):
        fn = r.get("filnavn", f"_{i}")
        # Stikord-score: 0.5 til 1.0 baseret på rang (først = højst)
        stikord_score = 1.0 - (i / max(len(stikord_resultater), 1)) * 0.5
        samlet[fn] = {
            **r,
            "stikord_score": stikord_score,
            "semantisk_score": 0.0,
        }

    for r in semantisk_resultater:
        fn = r.get("filnavn", "")
        sim = r.get("similarity") or 0.0
        if fn in samlet:
            # Sag findes i begge → kombiner
            samlet[fn]["semantisk_score"] = sim
        else:
            # Kun semantisk match
            samlet[fn] = {
                **r,
                "stikord_score": 0.0,
                "semantisk_score": sim,
            }

    # Beregn kombineret score: vægter både stikord (præcision) og
    # semantik (recall). Sager der er stærke på begge får boost.
    for fn, r in samlet.items():
        s = r["stikord_score"]
        sem = r["semantisk_score"]
        # Hvis begge findes → boost ekstra
        boost = 0.15 if (s > 0 and sem > 0) else 0.0
        r["kombineret_score"] = (s * 0.45) + (sem * 0.55) + boost

    # Sortér efter kombineret score
    return sorted(
        samlet.values(),
        key=lambda x: x["kombineret_score"],
        reverse=True,
    )


# ---------- HOVEDINDHOLD ----------
st.title("Søg i arkivet")
st.caption(
    "Find tidligere afgørelser, klager og vilkår der ligner din nuværende sag. "
    "Hybrid søgning kombinerer ord-præcision med semantisk relevans, så du finder "
    "både eksakte ord-matches OG sager der handler om det samme — også med "
    "anderledes ordvalg."
)


# ---------- HÅNDTÉR "FIND LIGNENDE"-KLIK FRA TIDLIGERE SØGNING ----------
# Hvis brugeren klikker "Find lignende" på et resultatkort, sætter vi
# sagens indhold som søgning og kører semantisk for at finde lignende.
if "_find_lignende_query" in st.session_state:
    _query_default = st.session_state.pop("_find_lignende_query")
    _mode_default = "Semantisk"
else:
    _query_default = ""
    _mode_default = "Hybrid (anbefalet)"


# ---------- SØGE-INPUT (række 1) ----------
stikord = st.text_input(
    "Søg",
    value=_query_default,
    placeholder=(
        "fx 'pool ikke ren', 'illusorisk opgradering', "
        "'guide afviste reklamation'"
    ),
    label_visibility="collapsed",
    key="arkiv_soegefelt",
)

# ---------- FILTRE (række 2 — fire kolonner) ----------
kol_type, kol_udfald, kol_dato, kol_mode = st.columns([1.2, 1.6, 1.2, 1.2])

with kol_type:
    filter_type = st.selectbox(
        "Dokumenttype",
        options=["Alle", "Afgørelser", "Klager", "Vilkår"],
        help="Begræns søgning til en bestemt type dokument.",
    )

with kol_udfald:
    _selskab_navn_til_filter = _hent_selskab_navn() or "rejseselskab"
    udfald_valgt = st.multiselect(
        "Udfald",
        options=[
            "Fuld medhold til klager",
            "Delvist medhold",
            f"Afvist ({_selskab_navn_til_filter} vinder)",
        ],
        default=[],
        placeholder="Vælg udfald...",
        help=(
            "Filter på Nævnets udfald (kun for afgørelser). "
            "Tomt = vis alle udfald."
        ),
    )

with kol_dato:
    dato_filter = st.selectbox(
        "Periode",
        options=[
            "Alle",
            "Sidste 6 måneder",
            "Sidste år",
            "Sidste 2 år",
            "Sidste 5 år",
        ],
        help="Begræns til afgørelser inden for tidsrum.",
    )

with kol_mode:
    soege_mode = st.selectbox(
        "Søgemetode",
        options=["Hybrid (anbefalet)", "Stikord", "Semantisk"],
        index=["Hybrid (anbefalet)", "Stikord", "Semantisk"].index(
            _mode_default
        ),
        help=(
            "Hybrid: kombinerer ord-præcision og semantisk relevans (bedst). "
            "Stikord: klassisk eksakt tekst-match. "
            "Semantisk: finder sager om samme tema, også med andre ord."
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
    if soege_mode == "Hybrid (anbefalet)":
        with st.spinner("Søger hybrid (stikord + semantik)..."):
            resultater = hybrid_soeg(stikord, doktype, top_k=40)
    elif soege_mode == "Semantisk":
        with st.spinner("Søger semantisk..."):
            emb = embed_sporgsmaal(stikord)
            if emb is None:
                st.error(
                    "Kunne ikke generere embedding — prøv hybrid eller stikord-søgning."
                )
                resultater = []
            else:
                resultater = find_relevante_sager(
                    sporgsmaal_embedding=emb,
                    top_k=40,
                    dokumenttype=doktype,
                )
    else:  # Stikord
        with st.spinner("Søger med stikord..."):
            resultater = soeg_i_arkiv(
                stikord=stikord,
                dokumenttype=doktype,
                begraens=50,
            )
else:
    # Ingen søgeord — vis seneste
    resultater = soeg_i_arkiv(dokumenttype=doktype, begraens=25)


# ---------- POST-SØGE-FILTRE: udfald + dato ----------
filtreret = []
for r in resultater:
    indhold = r.get("indhold") or ""
    if not overholder_udfald_filter(
        indhold, r.get("dokumenttype"), udfald_valgt
    ):
        continue
    if not overholder_dato_filter(
        indhold, r.get("filnavn"), dato_filter
    ):
        continue
    filtreret.append(r)

resultater = filtreret


# ---------- RESULTATVISNING ----------
antal = len(resultater)
filter_summary = []
if udfald_valgt:
    filter_summary.append(f"udfald: {', '.join(udfald_valgt).lower()}")
if dato_filter != "Alle":
    filter_summary.append(dato_filter.lower())
if doktype:
    filter_summary.append(filter_type.lower())

st.markdown(f"**{antal} resultater**")
if filter_summary:
    st.caption("Filtre: " + " · ".join(filter_summary))
st.divider()

if not resultater:
    st.info(
        "Ingen resultater. Prøv et bredere søgeord, fjern et filter, "
        "eller skift søgemetode."
    )
else:
    for idx, r in enumerate(resultater):
        with st.container(border=True):
            indhold = r.get("indhold") or ""
            filnavn = r.get("filnavn", "ukendt")
            dokumenttype = r.get("dokumenttype") or "afgoerelse"

            # --- Øverste række: badges (doktype + udfald + dato + match) ---
            badges_html = []
            badges_html.append(doktype_badge(dokumenttype))

            # Udfaldsbadge (kun for afgørelser)
            if dokumenttype == "afgoerelse":
                ub = udfalds_badge_fra_tekst(indhold)
                if ub:
                    badges_html.append(badge(ub[0], ub[1]))

            # Dato-badge
            afgoerelses_dato = udled_afgoerelsesdato(
                indhold, filnavn=filnavn
            )
            if afgoerelses_dato:
                badges_html.append(badge(afgoerelses_dato, "blue"))

            # Match-badge — vis enten kombineret score eller semantisk
            match_pct = None
            if r.get("kombineret_score") is not None:
                match_pct = int(r["kombineret_score"] * 100)
            elif r.get("similarity") is not None:
                match_pct = int(r["similarity"] * 100)

            if match_pct is not None:
                if match_pct >= 70:
                    badges_html.append(badge(f"{match_pct}% match", "green"))
                elif match_pct >= 50:
                    badges_html.append(badge(f"{match_pct}% match", "yellow"))
                else:
                    badges_html.append(badge(f"{match_pct}% match", "gray"))

            st.markdown(" ".join(badges_html), unsafe_allow_html=True)

            # --- Filnavn / titel ---
            st.markdown(f"**{filnavn}**")

            # --- Meta-linje: kilde-link ---
            meta_dele = []
            if r.get("kilde_url"):
                meta_dele.append(f"[Åbn original]({r['kilde_url']})")
            if meta_dele:
                st.caption(" · ".join(meta_dele))

            # --- Uddrag (synligt direkte, ikke skjult i expander) ---
            uddrag = indhold[:500].strip()
            if uddrag:
                if len(indhold) > 500:
                    uddrag += "…"
                st.markdown(
                    f'<div class="arkiv-uddrag">{uddrag}</div>',
                    unsafe_allow_html=True,
                )

            # --- Action-række: "Find lignende" + "Vis fuldt indhold" ---
            kol_act1, kol_act2, _ = st.columns([1.3, 1.3, 4])
            with kol_act1:
                if st.button(
                    "🔍 Find lignende",
                    key=f"find_lignende_{idx}_{filnavn}",
                    help=(
                        "Brug denne sag som søgegrundlag — find andre "
                        "sager der semantisk minder om den."
                    ),
                ):
                    # Brug de første 600 tegn af sagen som søgekontekst
                    st.session_state._find_lignende_query = (
                        indhold[:600] or filnavn
                    )
                    st.rerun()
            with kol_act2:
                with st.popover("Vis fuldt indhold"):
                    st.text(indhold)
