import os
import streamlit as st
from dotenv import load_dotenv

from processor import extracer_tekst, laes_klage, laes_sag_fra_filer

# Indlæs admin-nøgle fra .env
load_dotenv()
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
from database import (
    opret_tabeller,
    gem_sag_i_db,
    hent_antal_sager,
    hent_alle_sager,
    sag_findes,
    opdater_embedding,
    gem_i_arkiv,
    hent_arkiv,
    slet_arkiv_entry,
)
from ai_engine import (
    spoerg_ai,
    spoerg_ai_med_klage,
    generer_svarbrev,
    spoerg_ai_med_sag,
    generer_svarbrev_til_sag,
    generer_tjekliste,
    anonymiser_sag,
)
from embeddings import embed_dokument
from eksport import analyse_til_docx, svarbrev_til_docx
from vurdering import vis_dashboard as vis_udfalds_dashboard
from ui import thinking


# ---------- OPSÆTNING ----------
st.set_page_config(
    page_title="Juriitech",
    page_icon=None,
    layout="wide",
)

# ---------- STYLING (Stripe/Notion-inspireret, minimal og professionel) ----------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600;8..60,700&display=swap');

    /* ========== TYPOGRAFI ========== */
    html, body, .stApp, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    h1, h2, h3, h4, h5, h6,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
        font-family: 'Source Serif 4', Georgia, serif !important;
        font-weight: 600 !important;
        letter-spacing: -0.015em !important;
    }

    h1 {
        font-size: 2.4rem !important;
        line-height: 1.15 !important;
        margin-bottom: 0.5rem !important;
    }
    h2 {
        font-size: 1.65rem !important;
        margin-top: 3rem !important;
        margin-bottom: 1.25rem !important;
        letter-spacing: -0.02em !important;
    }
    h3 {
        font-size: 1.2rem !important;
        margin-top: 1.75rem !important;
        margin-bottom: 0.75rem !important;
    }

    .stMarkdown p, .stMarkdown li, p, li {
        line-height: 1.7 !important;
        font-weight: 400 !important;
    }

    /* ========== GENNEMSIGTIG SIDEBAR MED BLUR (iOS/macOS-look) ========== */
    section[data-testid="stSidebar"] {
        backdrop-filter: saturate(180%) blur(24px) !important;
        -webkit-backdrop-filter: saturate(180%) blur(24px) !important;
        background-color: rgba(250, 250, 252, 0.72) !important;
        border-right: 1px solid rgba(0, 0, 0, 0.06) !important;
    }

    @media (prefers-color-scheme: dark) {
        section[data-testid="stSidebar"] {
            background-color: rgba(25, 27, 32, 0.72) !important;
            border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
        }
    }

    /* Sidebarens titel — lidt mindre og mere elegant */
    [data-testid="stSidebar"] h1 {
        font-size: 1.55rem !important;
        margin-bottom: 0.25rem !important;
    }

    /* ========== HVIDT RUM OG LAYOUT (Stripe-inspireret) ========== */
    .main .block-container {
        padding-top: 3rem !important;
        padding-bottom: 4rem !important;
        max-width: 1000px !important;
    }

    /* Divider — meget subtil */
    hr {
        margin: 2.5rem 0 !important;
        border: none !important;
        border-top: 1px solid rgba(127, 127, 127, 0.15) !important;
    }

    /* ========== KORT/CONTAINERS — meget subtile borders ========== */
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 10px !important;
        padding: 1.5rem !important;
        margin-bottom: 1rem !important;
        border: 1px solid rgba(127, 127, 127, 0.14) !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03) !important;
    }

    /* ========== KNAPPER — tynde, Stripe-agtige ========== */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 500 !important;
        font-size: 0.9rem !important;
        padding: 0.5rem 1.1rem !important;
        border: 1px solid rgba(127, 127, 127, 0.3) !important;
        transition: all 0.15s ease !important;
    }
    .stButton > button:hover {
        border-color: rgba(99, 102, 241, 0.5) !important;
        transform: translateY(-1px) !important;
    }

    /* Primary knapper — fyldte, men moderat */
    .stButton > button[kind="primary"] {
        background-color: #0F172A !important;
        color: #FFFFFF !important;
        border: 1px solid #0F172A !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #1E293B !important;
        border-color: #1E293B !important;
    }

    /* ========== CAPTIONS — mere subtile ========== */
    .stCaption, [data-testid="stCaptionContainer"] {
        color: rgba(100, 116, 139, 0.85) !important;
        font-size: 0.85rem !important;
        font-weight: 400 !important;
    }

    /* ========== INLINE KILDEHENVISNINGER ========== */
    .stMarkdown code {
        background: rgba(127, 127, 127, 0.12) !important;
        padding: 1px 6px !important;
        border-radius: 4px !important;
        font-size: 0.82em !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
        color: rgba(100, 116, 139, 1) !important;
    }

    /* ========== BADGES (Notion/Apple-style tags) ========== */
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

    /* ========== EXPANDER HEADERS — subtile ========== */
    .streamlit-expanderHeader {
        font-weight: 500 !important;
        font-size: 0.95rem !important;
    }

    /* ========== CUSTOM "THINKING"-ANIMATION (Claude-inspireret) ========== */
    .thinking-wrapper {
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 20px 24px;
        border-radius: 12px;
        background: rgba(99, 102, 241, 0.05);
        border: 1px solid rgba(99, 102, 241, 0.12);
        margin: 1rem 0;
    }

    .thinking-dot {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: radial-gradient(circle at 30% 30%, #A5B4FC, #6366F1 60%, #4F46E5);
        box-shadow:
            0 0 16px rgba(99, 102, 241, 0.45),
            inset -2px -2px 6px rgba(0, 0, 0, 0.12);
        animation: thinking-pulse 1.4s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        flex-shrink: 0;
    }

    .thinking-text {
        color: rgba(71, 85, 105, 0.95);
        font-size: 0.95rem;
        font-weight: 500;
        letter-spacing: 0.01em;
        animation: thinking-text-fade 2.8s ease-in-out infinite;
    }

    @media (prefers-color-scheme: dark) {
        .thinking-wrapper {
            background: rgba(99, 102, 241, 0.1);
            border-color: rgba(99, 102, 241, 0.2);
        }
        .thinking-text {
            color: rgba(203, 213, 225, 0.9);
        }
    }

    @keyframes thinking-pulse {
        0%, 100% {
            transform: scale(0.85);
            opacity: 0.75;
            box-shadow:
                0 0 10px rgba(99, 102, 241, 0.3),
                inset -2px -2px 6px rgba(0, 0, 0, 0.12);
        }
        50% {
            transform: scale(1.15);
            opacity: 1;
            box-shadow:
                0 0 22px rgba(99, 102, 241, 0.6),
                inset -2px -2px 6px rgba(0, 0, 0, 0.12);
        }
    }

    @keyframes thinking-text-fade {
        0%, 100% { opacity: 0.75; }
        50% { opacity: 1; }
    }

    </style>
    """,
    unsafe_allow_html=True,
)

opret_tabeller()

# ---------- ADMIN-MODE ----------
# Admin-adgang gives via URL-parameter: ?admin=<ADMIN_KEY>
# Almindelige brugere ser kun bruger-interfacet (upload, analyse, svarbrev).
# Admin (dig) ser også scraper-knapper, statistik og tekniske værktøjer.
query_params = st.query_params
if "admin" in query_params and ADMIN_KEY and query_params.get("admin") == ADMIN_KEY:
    st.session_state.er_admin = True
if "er_admin" not in st.session_state:
    st.session_state.er_admin = False

ER_ADMIN = st.session_state.er_admin

# Session state til den aktuelle sag (så den overlever reruns)
if "aktuel_sag" not in st.session_state:
    st.session_state.aktuel_sag = None
if "sidste_sagsfil_signatur" not in st.session_state:
    st.session_state.sidste_sagsfil_signatur = None
# Legacy state — bevares for bagudkompatibilitet hvis nogen bruger gammel flow
if "aktuel_klage" not in st.session_state:
    st.session_state.aktuel_klage = None
if "sidste_klage_filnavn" not in st.session_state:
    st.session_state.sidste_klage_filnavn = None
if "sagsakter" not in st.session_state:
    st.session_state.sagsakter = ""
if "seneste_svar" not in st.session_state:
    st.session_state.seneste_svar = None
if "seneste_svarbrev" not in st.session_state:
    st.session_state.seneste_svarbrev = None
if "seneste_tjekliste" not in st.session_state:
    st.session_state.seneste_tjekliste = None
if "seneste_anonymisering" not in st.session_state:
    st.session_state.seneste_anonymisering = None
if "auto_vurdering_tekst" not in st.session_state:
    st.session_state.auto_vurdering_tekst = None
if "auto_vurdering_for_signatur" not in st.session_state:
    st.session_state.auto_vurdering_for_signatur = None
if "relevante_sager" not in st.session_state:
    st.session_state.relevante_sager = []


def _auto_gem_klage_i_db(klage_dict):
    """
    Gemmer en uploadet klage i databasen med dokumenttype='klage', hvis den
    ikke allerede findes. Returnerer en statusstreng til brug i UI'en.
    """
    filnavn = klage_dict.get("filnavn")
    if not filnavn:
        return None

    if sag_findes(filnavn):
        return f"{filnavn} findes allerede i vidensbanken — ikke gemt igen."

    if klage_dict["type"] == "tekst":
        indhold = klage_dict.get("tekst") or ""
    else:
        # Scannet PDF — vi har ikke udtrukket tekst lokalt. Gem et tydeligt placeholder,
        # så vidensbanken ved at filen findes. Selve analysen sker via Juriitechs vision
        # på den fil der ligger i session state.
        indhold = (
            f"[Scannet klage — tekst ikke udtrukket lokalt. "
            f"Analyseres ved upload via Juriitechs vision. Filnavn: {filnavn}]"
        )

    # Generer embedding hvis vi har rigtig tekst. For scannede PDF'er gør
    # vi det ikke — placeholderen giver et ubrugeligt vektor-match.
    emb = None
    if klage_dict["type"] == "tekst" and indhold.strip():
        emb = embed_dokument(indhold)

    gem_sag_i_db(filnavn, indhold, dokumenttype="klage", embedding=emb)
    if emb is None and klage_dict["type"] == "tekst":
        return f"{filnavn} gemt som klage, men embedding fejlede."
    return f"{filnavn} automatisk gemt i vidensbanken som klage."


# ---------- SIDEBAR ----------
with st.sidebar:
    if ER_ADMIN:
        # Admin-badge så du tydeligt kan se at du er logget ind som admin
        st.markdown(
            """
            <div style='background-color:#1E3A8A; color:white; padding:6px 10px;
            border-radius:4px; font-size:0.85em; margin-bottom:8px;'>
            🔧 ADMIN MODE
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.title("Juriitech")
    st.caption("Juridisk AI til pakkerejseklager")

    antal = hent_antal_sager()
    st.metric(label="Sager i vidensbanken", value=antal)

    if not ER_ADMIN:
        # Bruger-interface: kort og venligt
        st.caption(
            "Analyser klagesager fra Pakkerejse-Ankenævnet med AI der har læst "
            "alle tidligere afgørelser og TUI's egne rejsevilkår."
        )
        st.divider()
        st.caption(
            "**Sådan gør du:**\n\n"
            "1. Upload hele sagen fra Nævnet (ZIP eller enkeltfiler)\n"
            "2. Få tjekliste over hvad der mangler\n"
            "3. Stil spørgsmål og få juridisk analyse\n"
            "4. Generér anonymiserede bilag\n"
            "5. Generér udkast til svarbrev\n"
            "6. Download alt som Word"
        )

    if ER_ADMIN:
        st.divider()
        st.caption("🔧 **Administrative værktøjer** — kun synlige for dig som admin.")

        # ---------- AUTOMATISK HENTNING FRA PAKKEREJSEANKENÆVNET ----------
        st.subheader("Hent direkte fra Ankenævnet")
        st.caption(
            "Scrape nye kendelser direkte fra pakkerejseankenaevnet.dk. "
            "Hver sag dedupes på URL, så du kan trykke flere gange uden at duplikere. "
            "Scannede PDF'er gemmes også, men uden embedding (Juriitech læser dem via vision)."
        )

        max_pr_koersel = st.selectbox(
            "Max antal sager pr. kørsel",
            options=[50, 100, 200, 500, "Alle"],
            index=0,
            help="Start lavt første gang så du kan se hvor mange der er i alt.",
        )

        kol_a, kol_b = st.columns(2)
        with kol_a:
            tael_knap = st.button("Tæl kun", help="Dry-run — tæl hvor mange der er på siden uden at hente")
        with kol_b:
            hent_knap = st.button("Hent nye sager", type="primary")

        if tael_knap:
            from scraper import tael_alle_kendelser_paa_siden
            with st.spinner("Tæller kendelser på siden..."):
                antal_paa_siden, _ = tael_alle_kendelser_paa_siden()
            st.info(
                f"Der findes **{antal_paa_siden}** PDF-kendelser på arkivet lige nu. "
                f"Estimeret pladsforbrug: ~{antal_paa_siden * 30 // 1024} MB."
            )

        if hent_knap:
            from scraper import scrape_nye_sager
            loft = None if max_pr_koersel == "Alle" else int(max_pr_koersel)

            log_placeholder = st.empty()
            log_linjer = []

            def _progress(msg):
                log_linjer.append(msg)
                if len(log_linjer) % 3 == 0 or msg.startswith("=") or msg.startswith("✅"):
                    log_placeholder.code(
                        "\n".join(log_linjer[-25:]), language="text"
                    )

            with st.spinner("Scraper pakkerejseankenaevnet.dk — det kan tage et par minutter..."):
                try:
                    stats = scrape_nye_sager(max_sager=loft, progress_callback=_progress)
                    log_placeholder.code(
                        "\n".join(log_linjer[-25:]), language="text"
                    )
                    st.success(
                        f"Hentning færdig. Gemt: {stats['gemt']}, "
                        f"fejlede: {stats['fejlede']}, scannede: {stats['scannede']}."
                    )
                    if stats["fundet_paa_siden"] - stats["allerede_i_db"] - stats["gemt"] > 0:
                        st.info(
                            "Der er flere nye sager tilbage. Tryk 'Hent nye sager' igen "
                            "for at fortsætte."
                        )
                except Exception as e:
                    st.error(f"Scraping fejlede: {e}")

        st.divider()

        # ---------- AUTOMATISK HENTNING AF TUI-VILKÅR ----------
        st.subheader("Hent TUI's rejsevilkår")
        st.caption(
            "Scrape juridisk indhold fra tui.dk — kun sider om vilkår, regler, "
            "retningslinjer, procedurer og andre juridisk relevante emner."
        )

        tui_max = st.selectbox(
            "Max antal sider pr. kørsel",
            options=[20, 40, 80, 150],
            index=1,
            help="TUI.dk har ~20-40 relevante juridiske sider — 40 er normalt rigeligt.",
            key="tui_max",
        )

        tui_hent_knap = st.button(
            "Hent juridisk indhold fra tui.dk",
            type="secondary",
            key="tui_hent",
        )

        if tui_hent_knap:
            from tui_scraper import scrape_tui_vilkaar

            tui_log_placeholder = st.empty()
            tui_log_linjer = []

            def _tui_progress(msg):
                tui_log_linjer.append(msg)
                if len(tui_log_linjer) % 3 == 0 or msg.startswith("=") or msg.startswith("✅"):
                    tui_log_placeholder.code(
                        "\n".join(tui_log_linjer[-25:]), language="text"
                    )

            with st.spinner("Scraper tui.dk — henter juridisk indhold..."):
                try:
                    tui_stats = scrape_tui_vilkaar(
                        max_sider=int(tui_max),
                        progress_callback=_tui_progress,
                    )
                    tui_log_placeholder.code(
                        "\n".join(tui_log_linjer[-25:]), language="text"
                    )
                    st.success(
                        f"TUI-scraping færdig. Besøgte: {tui_stats['besogte']}, "
                        f"gemt: {tui_stats['gemt']}, allerede i db: "
                        f"{tui_stats['allerede_i_db']}, fejlede: {tui_stats['fejlede']}."
                    )
                except Exception as e:
                    st.error(f"TUI-scraping fejlede: {e}")


# ---------- HOVEDSKÆRM ----------
st.title("Juriitech")
st.caption("Juridisk AI-assistent til pakkerejseklager")


# ---------- ANALYSE AF NY SAG ----------
st.header("Analysér en ny sag fra Ankenævnet")
st.caption(
    "Upload **hele sagspakken** fra Ankenævnet — enten som ZIP-fil eller ved at "
    "vælge flere filer på én gang (høringsbrev, klageskema, bilag 02-07 osv.). "
    "Programmet pakker ZIP ud, læser hver fil, gætter dens rolle i sagen, "
    "og behandler dem alle samlet som én sag."
)

uploadede_sagsfiler = st.file_uploader(
    "Upload sagen (ZIP, PDF eller Word — gerne flere filer)",
    type=["zip", "pdf", "docx"],
    accept_multiple_files=True,
    key="sag_uploader",
)

# Tjek om uploadet har ændret sig (enten ny fil eller andet antal filer)
_aktuel_sagsfiler_signatur = tuple(sorted(
    (f.name, f.size) for f in uploadede_sagsfiler or []
))
if uploadede_sagsfiler and _aktuel_sagsfiler_signatur != st.session_state.get(
    "sidste_sagsfil_signatur"
):
    with st.spinner(f"Læser {len(uploadede_sagsfiler)} filer..."):
        sag_data = laes_sag_fra_filer(uploadede_sagsfiler)
        st.session_state.aktuel_sag = sag_data
        st.session_state.sidste_sagsfil_signatur = _aktuel_sagsfiler_signatur
        st.session_state.sidste_klage_filnavn = None  # reset legacy state

        # Auto-gem hver fil i databasen (dokumenttype='klage')
        gemt_nu = []
        sprunget_over = []
        for fil in sag_data.get("filer", []):
            if sag_findes(fil["filnavn"]):
                sprunget_over.append(fil["filnavn"])
                continue
            if fil["type"] == "tekst" and fil.get("tekst", "").strip():
                emb = embed_dokument(fil["tekst"])
                gem_sag_i_db(
                    fil["filnavn"], fil["tekst"],
                    dokumenttype="klage", embedding=emb,
                )
            else:
                # Scannet PDF — gem placeholder
                gem_sag_i_db(
                    fil["filnavn"],
                    f"[Scannet sagsbilag — analyseres via vision. Filnavn: {fil['filnavn']}]",
                    dokumenttype="klage",
                )
            gemt_nu.append(fil["filnavn"])

        if gemt_nu:
            st.toast(f"{len(gemt_nu)} filer gemt i vidensbanken.")
        if sprunget_over:
            st.toast(f"{len(sprunget_over)} filer var allerede i databasen.")

# Knap til at rydde sagen
if st.session_state.get("aktuel_sag"):
    sag = st.session_state.aktuel_sag
    filer = sag.get("filer") or []
    antal_tekst = sum(1 for f in filer if f["type"] == "tekst")
    antal_scannet = sum(1 for f in filer if f["type"] == "pdf_bytes")

    kol1, kol2 = st.columns([4, 1])
    with kol1:
        st.success(
            f"Sag klar til analyse: **{len(filer)} filer** "
            f"({antal_tekst} læst, {antal_scannet} scannede PDF'er)"
        )
    with kol2:
        if st.button("Ryd sag"):
            st.session_state.aktuel_sag = None
            st.session_state.sidste_sagsfil_signatur = None
            st.session_state.sagsakter = ""
            st.session_state.auto_vurdering_tekst = None
            st.session_state.auto_vurdering_for_signatur = None
            st.session_state.seneste_svar = None
            st.session_state.seneste_svarbrev = None
            st.session_state.seneste_tjekliste = None
            st.session_state.seneste_anonymisering = None
            st.rerun()

    # Vis oversigt over filerne i sagen (foldbar)
    with st.expander(f"Se de {len(filer)} filer i sagen", expanded=False):
        for i, fil in enumerate(filer, 1):
            rolle = fil.get("rolle", "ukendt").replace("_", " ")
            tegn_info = (
                f" — {len(fil.get('tekst') or '')} tegn læst"
                if fil["type"] == "tekst" else " — scannet PDF"
            )
            st.markdown(f"**{i}. {fil['filnavn']}** · *{rolle}*{tegn_info}")

    # ---------- AUTOMATISK FØRSTEVURDERING ----------
    # Når en sag er uploadet (ny signatur), kør en kort analyse med
    # sandsynlighedsvurdering så brugeren får det farvekodede dashboard
    # med det samme — uden at skulle stille et spørgsmål først.
    skal_auto_vurdere = (
        st.session_state.auto_vurdering_for_signatur
        != st.session_state.sidste_sagsfil_signatur
    )
    if skal_auto_vurdere:
        with st.spinner(
            "Juriitech laver en første vurdering af sagen — tager 20-40 sekunder..."
        ):
            try:
                auto_svar, rel_sager = spoerg_ai_med_sag(
                    spoergsmaal=(
                        "Lav en kort juridisk førstevurdering af sagen "
                        "baseret på de uploadede dokumenter. Du SKAL afslutte "
                        "med en sandsynlighedsvurderings-sektion der indeholder "
                        "præcis denne struktur — procenterne skal summe til 100:\n\n"
                        "**Fuld medhold til klager:** X%\n"
                        "**Delvist medhold til klager:** Y%\n"
                        "**Afvisning af klagen:** Z%\n\n"
                        "Selv hvis sagen er ufuldstændigt oplyst, estimér de tre "
                        "procenter baseret på hvad du KAN udlede. Angiv eventuelt "
                        "'Lavt grundlag' hvis et estimat er særligt usikkert."
                    ),
                    sager=[],
                    sag=st.session_state.aktuel_sag,
                    sagsakter=st.session_state.get("sagsakter", ""),
                    returner_relevante=True,
                )
                st.session_state.auto_vurdering_tekst = auto_svar
                st.session_state.relevante_sager = rel_sager
                st.session_state.auto_vurdering_for_signatur = (
                    st.session_state.sidste_sagsfil_signatur
                )

                # Gem også i arkivet
                sag_filer_for_arkiv = st.session_state.aktuel_sag.get("filer") or []
                klage_fn_for_arkiv = None
                for fil in sag_filer_for_arkiv:
                    if fil.get("rolle") == "klageskema":
                        klage_fn_for_arkiv = fil["filnavn"]
                        break
                gem_i_arkiv(
                    titel=(
                        f"Førstevurdering — {klage_fn_for_arkiv}"
                        if klage_fn_for_arkiv else "Førstevurdering"
                    ),
                    type_="analyse",
                    indhold=auto_svar,
                    klage_filnavn=klage_fn_for_arkiv,
                    spoergsmaal="Automatisk førstevurdering ved upload",
                )
            except Exception as e:
                st.warning(f"Kunne ikke lave automatisk førstevurdering: {e}")

    # Vis dashboard + selve teksten hvis vi har en førstevurdering
    if st.session_state.auto_vurdering_tekst:
        st.markdown("### Førstevurdering af sagen")
        vis_udfalds_dashboard(st.session_state.auto_vurdering_tekst)

        # Visuelle kort for de 3-5 mest relevante tidligere sager
        rel = st.session_state.get("relevante_sager") or []
        afgoerelser_ud = [r for r in rel if (r.get("dokumenttype") or "").lower() == "afgoerelse"]
        vilkaar_ud = [r for r in rel if (r.get("dokumenttype") or "").lower() == "vilkaar"]

        if afgoerelser_ud:
            st.markdown("### De mest relevante tidligere afgørelser")
            st.caption(
                "Disse afgørelser fra Pakkerejse-Ankenævnet minder mest om din nuværende sag. "
                "Juriitech bruger dem aktivt som juridisk præcedens i analysen ovenfor."
            )
            from badges import udled_afgoerelsesdato
            for i, sag_ref in enumerate(afgoerelser_ud[:5], 1):
                sim = sag_ref.get("similarity") or 0
                sim_pct = int(sim * 100)
                kilde = sag_ref.get("kilde_url") or "Uploadet manuelt"
                afgoerelses_dato = udled_afgoerelsesdato(
                    sag_ref.get("indhold"),
                    filnavn=sag_ref.get("filnavn"),
                )
                dato_str = afgoerelses_dato or "dato ikke angivet"
                uddrag = (sag_ref.get("indhold") or "")[:400]

                # Farvekodning af relevans
                if sim_pct >= 70:
                    farve = "#059669"  # grøn — meget relevant
                    etiket = "Meget høj relevans"
                elif sim_pct >= 55:
                    farve = "#CA8A04"  # gul — moderat
                    etiket = "Relevant"
                else:
                    farve = "#6B7280"  # grå — lavere
                    etiket = "Muligvis relevant"

                with st.container(border=True):
                    kol_a, kol_b = st.columns([5, 1])
                    with kol_a:
                        st.markdown(f"**{i}. {sag_ref.get('filnavn', 'ukendt')}**")
                        st.caption(f"Afgjort {dato_str}  ·  {etiket}")
                    with kol_b:
                        st.markdown(
                            f"<div style='text-align:right; font-size:1.4rem; "
                            f"font-weight:700; color:{farve};'>{sim_pct}%</div>"
                            f"<div style='text-align:right; font-size:0.75rem; "
                            f"color:#6B7280;'>match</div>",
                            unsafe_allow_html=True,
                        )
                    with st.expander("Se uddrag af afgørelsen"):
                        st.text(uddrag + ("..." if len(uddrag) == 400 else ""))
                        if sag_ref.get("kilde_url"):
                            st.markdown(
                                f"[Åbn original på pakkerejseankenaevnet.dk]"
                                f"({sag_ref['kilde_url']})"
                            )

        if vilkaar_ud:
            st.markdown("### Relevante passager fra TUI's rejsevilkår")
            st.caption("Disse sektioner af vilkårene er relevante for denne sagstype.")
            for i, vk in enumerate(vilkaar_ud[:3], 1):
                sim_pct = int((vk.get("similarity") or 0) * 100)
                with st.container(border=True):
                    st.markdown(
                        f"**{vk.get('filnavn', 'ukendt')}** · {sim_pct}% match"
                    )
                    if vk.get("kilde_url"):
                        st.caption(f"Kilde: {vk['kilde_url']}")
                    with st.expander("Se uddrag"):
                        st.text((vk.get("indhold") or "")[:500])

        with st.expander("Se den fulde førstevurdering med argumentation", expanded=False):
            st.markdown(st.session_state.auto_vurdering_tekst)

    # ---------- SAGSAKTER (C4C, e-mails, bookingdetaljer) ----------
    with st.expander(
        "Sagsakter til denne klage — C4C-notater, e-mails, bookingdetaljer",
        expanded=False,
    ):
        st.caption(
            "Paste al relevant intern information om *denne* klage ind her: "
            "destinationens reklamationsrapport fra C4C, e-mail-korrespondance "
            "med kunden, bookingbekræftelsen, tilkøb, osv. Juriitech bruger det "
            "som ekstra kontekst i sin analyse. Teksten gemmes IKKE permanent "
            "i vidensbanken — kun for denne specifikke analyse."
        )
        st.session_state.sagsakter = st.text_area(
            "Sagsakter",
            value=st.session_state.get("sagsakter", ""),
            height=200,
            placeholder=(
                "Eksempel:\n\n"
                "— C4C-reklamation fra destination (2024-08-14) —\n"
                "Kunde klagede over rengøringsstandard dag 2. Destination "
                "undersøgte og tilbød værelsesskift som kunde accepterede...\n\n"
                "— E-mail fra kunde (2024-08-20) —\n"
                "...\n\n"
                "— Bookingdetaljer —\n"
                "Boookingnr: 12345678, Afrejse 10/8-2024, TUI Blue Hotel Rhodos..."
            ),
            label_visibility="collapsed",
        )
        if st.session_state.sagsakter:
            st.caption(
                f"✏️ {len(st.session_state.sagsakter)} tegn sagsakter — "
                f"inkluderes i næste analyse"
            )

st.divider()


# ---------- SPØRGSMÅL / CHAT ----------
st.header("Stil spørgsmål til dine sager")

# Opdatér antal efter evt. auto-gem ovenfor
antal = hent_antal_sager()

if st.session_state.get("aktuel_sag"):
    _sag_filer = st.session_state.aktuel_sag.get("filer") or []
    st.info(
        f"Samtalen tager udgangspunkt i den uploadede sag "
        f"(**{len(_sag_filer)} filer**) og hele vidensbanken ({antal} sager)."
    )
else:
    st.caption(
        f"Samtalen kører pt. kun mod vidensbanken ({antal} sager). "
        f"Upload en sag ovenfor for at analysere konkret."
    )

spoergsmaal = st.text_input(
    "Hvad vil du vide?",
    placeholder="fx 'Giv mig en komplet analyse af sagen' eller 'Hvilke tidligere sager minder mest om denne?'",
)

if spoergsmaal:
    with st.spinner("Juriitech analyserer..."):
        sager = hent_alle_sager()

        if not sager:
            st.warning("Vidensbanken er tom. Upload først nogle tidligere afgørelser i sidebaren.")
        else:
            if st.session_state.get("aktuel_sag"):
                svar = spoerg_ai_med_sag(
                    spoergsmaal,
                    sager,
                    st.session_state.aktuel_sag,
                    sagsakter=st.session_state.get("sagsakter", ""),
                )
                # Titel: brug første fil med rolle 'klageskema' eller 'høring', ellers første fil
                sag_filer = st.session_state.aktuel_sag.get("filer") or []
                hoved_filnavn = None
                for rolle_prio in ("klageskema", "høring"):
                    for fil in sag_filer:
                        if fil.get("rolle") == rolle_prio:
                            hoved_filnavn = fil["filnavn"]
                            break
                    if hoved_filnavn:
                        break
                if not hoved_filnavn and sag_filer:
                    hoved_filnavn = sag_filer[0]["filnavn"]
            else:
                svar = spoerg_ai(spoergsmaal, sager)
                hoved_filnavn = None

            st.session_state.seneste_svar = {
                "spoergsmaal": spoergsmaal,
                "svar": svar,
                "klage_filnavn": hoved_filnavn,
            }
            # Gem automatisk i arkivet så juristen kan finde den igen
            titel = (
                f"Analyse af sag — {hoved_filnavn}"
                if hoved_filnavn
                else f"Spørgsmål: {spoergsmaal[:60]}"
            )
            gem_i_arkiv(
                titel=titel,
                type_="analyse",
                indhold=svar,
                klage_filnavn=hoved_filnavn,
                spoergsmaal=spoergsmaal,
                sagsakter=st.session_state.get("sagsakter", "") or None,
            )
            # Vis dashboard med sandsynligheder øverst, derefter det fulde svar
            vis_udfalds_dashboard(svar)
            st.chat_message("assistant").write(svar)

# Download-knap til seneste analyse
if st.session_state.seneste_svar:
    senste = st.session_state.seneste_svar
    docx_bytes = analyse_til_docx(
        senste["spoergsmaal"],
        senste["svar"],
        klage_filnavn=senste.get("klage_filnavn"),
    )
    filnavn_base = (senste.get("klage_filnavn") or "analyse").rsplit(".", 1)[0]
    st.download_button(
        label="Download analyse som Word",
        data=docx_bytes,
        file_name=f"analyse_{filnavn_base}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key="download_analyse",
    )


# ---------- ANONYMISERINGSASSISTENT ----------
if st.session_state.get("aktuel_sag"):
    st.divider()
    st.header("Anonymisér bilag til Nævnet")
    st.caption(
        "Juriitech producerer anonymiserede versioner af alle tekst-baserede bilag "
        "efter Pakkerejse-Ankenævnets retningslinjer (K for klager, R for "
        "rejsearrangør, B1/B2 for bipersoner, CPR-numre fjernes, osv.). "
        "Høringsbrev og vejledninger springes automatisk over — de skal ikke "
        "sendes tilbage. Scannede PDF'er kræver manuel behandling."
    )

    if st.button("Anonymisér alle bilag", type="secondary"):
        filer = st.session_state.aktuel_sag.get("filer") or []
        tekstfiler_der_skal_behandles = [
            f for f in filer
            if f.get("type") == "tekst"
            and f.get("rolle") not in ("vejledning", "høring")
            and (f.get("tekst") or "").strip()
        ]
        antal = len(tekstfiler_der_skal_behandles)

        with st.spinner(
            f"Juriitech anonymiserer {antal} bilag — tager ca. {antal * 15} sekunder..."
        ):
            resultater = anonymiser_sag(st.session_state.aktuel_sag)
            st.session_state.seneste_anonymisering = resultater

    if st.session_state.seneste_anonymisering:
        resultater = st.session_state.seneste_anonymisering
        ok_antal = sum(1 for r in resultater if r["status"] == "ok")
        sprunget_antal = sum(1 for r in resultater if r["status"] == "sprunget_over")
        fejl_antal = sum(1 for r in resultater if r["status"] == "fejl")

        st.success(
            f"Anonymisering færdig. {ok_antal} anonymiseret, "
            f"{sprunget_antal} sprunget over, "
            f"{fejl_antal} fejlede."
        )

        st.caption(
            "**Tjek resultaterne manuelt før du sender til Nævnet.** "
            "AI-anonymisering er et hjælpeværktøj, ikke en garanti. "
            "Gennemgå hver fil for at sikre at alle personhenførbare oplysninger "
            "er fjernet korrekt."
        )

        for r in resultater:
            if r["status"] == "ok":
                prefix = "[OK]"
            elif r["status"] == "sprunget_over":
                prefix = "[Sprunget over]"
            else:
                prefix = "[Fejl]"

            with st.expander(f"{prefix} {r['filnavn']}  —  {r['bemaerkning']}"):
                if r["status"] == "ok":
                    st.markdown("**Anonymiseret tekst:**")
                    st.text_area(
                        "Anonymiseret indhold",
                        value=r["anonymiseret_tekst"],
                        height=400,
                        key=f"anon_visning_{r['filnavn']}",
                        label_visibility="collapsed",
                    )
                    # Download som Word
                    from eksport import markdown_til_docx_bytes
                    docx_bytes = markdown_til_docx_bytes(
                        r["anonymiseret_tekst"],
                        titel=f"Anonymiseret: {r['filnavn']}",
                        undertitel="Anonymiseret efter Pakkerejse-Ankenævnets retningslinjer",
                    )
                    fn_base = r["filnavn"].rsplit(".", 1)[0]
                    st.download_button(
                        label="Download anonymiseret version som Word",
                        data=docx_bytes,
                        file_name=f"anonymiseret_{fn_base}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"anon_download_{r['filnavn']}",
                    )
                else:
                    st.info(r["bemaerkning"])


# ---------- AUTO-TJEKLISTE MOD HØRINGSBREV ----------
if st.session_state.get("aktuel_sag"):
    st.divider()
    st.header("Tjekliste mod høringsbrev")
    st.caption(
        "Læser Ankenævnets høringsbrev og sammenholder med de uploadede bilag. "
        "Viser hvilke af Nævnets ønskede punkter der er dækket, og hvad der mangler. "
        "Kør den INDEN svarbrevet — så du ved hvad du skal hente fra TUI's systemer først."
    )

    if st.button("Generer tjekliste", type="secondary"):
        with st.spinner("Juriitech læser høringsbrevet og gennemgår bilagene — 20-40 sekunder..."):
            tjekliste = generer_tjekliste(sag=st.session_state.aktuel_sag)
            st.session_state.seneste_tjekliste = {
                "indhold": tjekliste,
                "filer_antal": len(st.session_state.aktuel_sag.get("filer") or []),
            }
            # Auto-gem i arkivet
            sag_filer = st.session_state.aktuel_sag.get("filer") or []
            klage_fn = None
            for fil in sag_filer:
                if fil.get("rolle") == "klageskema":
                    klage_fn = fil["filnavn"]
                    break
            gem_i_arkiv(
                titel=f"Tjekliste — {klage_fn}" if klage_fn else "Tjekliste",
                type_="tjekliste",
                indhold=tjekliste,
                klage_filnavn=klage_fn,
            )

    if st.session_state.seneste_tjekliste:
        st.markdown("---")
        st.markdown(st.session_state.seneste_tjekliste["indhold"])


# ---------- SVARBREV-GENERATOR ----------
if st.session_state.get("aktuel_sag"):
    st.divider()
    st.header("Generer svarbrev til Nævnet")
    st.caption(
        "Lav et komplet udkast til svarbrev fra rejseselskabet til Pakkerejseankenævnet. "
        "Brevet struktureres automatisk (indledning, faktum, stillingtagen, juridisk "
        "argumentation, konklusion, afslutning) med præcise henvisninger til "
        "vidensbanken, TUI's vilkår og sagens bilag. Du kan redigere udkastet bagefter i Word."
    )

    ekstra_instrukser = st.text_input(
        "Særlige instrukser (valgfrit)",
        placeholder="fx 'læg særlig vægt på force majeure-forbeholdet' eller 'anerkend 2.000 kr. men bestrid resten'",
    )

    if st.button("Generer udkast til svarbrev", type="primary"):
        with st.spinner("Juriitech udarbejder svarbrevet — tager 30-60 sekunder..."):
            svarbrev = generer_svarbrev_til_sag(
                sag=st.session_state.aktuel_sag,
                sagsakter=st.session_state.get("sagsakter", ""),
                ekstra_instrukser=ekstra_instrukser,
            )
            # Titel: find klageskema eller første fil
            sag_filer = st.session_state.aktuel_sag.get("filer") or []
            klage_fn = None
            for fil in sag_filer:
                if fil.get("rolle") == "klageskema":
                    klage_fn = fil["filnavn"]
                    break
            if not klage_fn and sag_filer:
                klage_fn = sag_filer[0]["filnavn"]

            st.session_state.seneste_svarbrev = {
                "klage_filnavn": klage_fn,
                "ekstra_instrukser": ekstra_instrukser,
                "svarbrev": svarbrev,
            }
            # Auto-gem i arkivet
            gem_i_arkiv(
                titel=f"Svarbrev — {klage_fn}" if klage_fn else "Svarbrev",
                type_="svarbrev",
                indhold=svarbrev,
                klage_filnavn=klage_fn,
                sagsakter=st.session_state.get("sagsakter", "") or None,
                ekstra_instrukser=ekstra_instrukser or None,
            )

    if st.session_state.seneste_svarbrev:
        st.markdown("---")
        st.subheader("Udkast til svarbrev")
        st.markdown(st.session_state.seneste_svarbrev["svarbrev"])

        # Download-knap til svarbrevet
        svarbrev_docx = svarbrev_til_docx(
            st.session_state.seneste_svarbrev["svarbrev"],
            klage_filnavn=st.session_state.seneste_svarbrev["klage_filnavn"],
        )
        sb_filnavn_base = (
            st.session_state.seneste_svarbrev["klage_filnavn"] or "svarbrev"
        ).rsplit(".", 1)[0]
        st.download_button(
            label="Download svarbrev som Word",
            data=svarbrev_docx,
            file_name=f"svarbrev_{sb_filnavn_base}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            key="download_svarbrev",
        )


# ---------- ARKIV OVER TIDLIGERE ANALYSER OG SVARBREVE ----------
st.divider()
with st.expander("Mine tidligere analyser og svarbreve", expanded=False):
    arkiv_items = hent_arkiv(begraens=100)

    if not arkiv_items:
        st.caption(
            "Arkivet er tomt. Analyser og svarbreve du genererer "
            "gemmes automatisk her."
        )
    else:
        st.caption(
            f"Viser de {len(arkiv_items)} seneste indgange. "
            "Klik på en for at se den igen — ingen nyt AI-kald, ingen omkostning."
        )

        # Filter på type
        filter_valg = st.radio(
            "Vis",
            options=["Alle", "Analyser", "Svarbreve", "Tjeklister"],
            horizontal=True,
            key="arkiv_filter",
        )

        filtreret = arkiv_items
        if filter_valg == "Analyser":
            filtreret = [a for a in arkiv_items if a["type"] == "analyse"]
        elif filter_valg == "Svarbreve":
            filtreret = [a for a in arkiv_items if a["type"] == "svarbrev"]
        elif filter_valg == "Tjeklister":
            filtreret = [a for a in arkiv_items if a["type"] == "tjekliste"]

        for item in filtreret:
            from badges import badge
            if item["type"] == "svarbrev":
                type_badge_html = badge("Svarbrev", "purple")
            elif item["type"] == "tjekliste":
                type_badge_html = badge("Tjekliste", "blue")
            else:
                type_badge_html = badge("Analyse", "gray")
            dato_str = (
                item["oprettet_dato"].strftime("%d-%m-%Y %H:%M")
                if item.get("oprettet_dato") else "ukendt"
            )
            with st.expander(f"{item['titel']}  —  {dato_str}"):
                st.markdown(type_badge_html, unsafe_allow_html=True)
                if item.get("spoergsmaal"):
                    st.caption(f"**Spørgsmål:** {item['spoergsmaal']}")
                if item.get("ekstra_instrukser"):
                    st.caption(f"**Instrukser:** {item['ekstra_instrukser']}")
                if item.get("sagsakter"):
                    with st.expander("Brugte sagsakter (klik for at se)"):
                        st.text(item["sagsakter"])
                st.markdown("---")
                # Vis dashboard hvis det er en analyse med sandsynligheder
                if item["type"] == "analyse":
                    vis_udfalds_dashboard(item["indhold"])
                st.markdown(item["indhold"])

                # Download som Word
                if item["type"] == "svarbrev":
                    docx_bytes = svarbrev_til_docx(
                        item["indhold"], klage_filnavn=item.get("klage_filnavn")
                    )
                    fn_base = (item.get("klage_filnavn") or "svarbrev").rsplit(".", 1)[0]
                    label = "⬇️ Download svarbrev som Word"
                    file_name = f"svarbrev_{fn_base}_{item['id']}.docx"
                else:
                    docx_bytes = analyse_til_docx(
                        item.get("spoergsmaal") or "",
                        item["indhold"],
                        klage_filnavn=item.get("klage_filnavn"),
                    )
                    fn_base = (item.get("klage_filnavn") or "analyse").rsplit(".", 1)[0]
                    label = "⬇️ Download analyse som Word"
                    file_name = f"analyse_{fn_base}_{item['id']}.docx"

                kol_a, kol_b = st.columns([3, 1])
                with kol_a:
                    st.download_button(
                        label=label,
                        data=docx_bytes,
                        file_name=file_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"download_arkiv_{item['id']}",
                    )
                with kol_b:
                    if st.button("🗑️ Slet", key=f"slet_arkiv_{item['id']}"):
                        slet_arkiv_entry(item["id"])
                        st.rerun()
