import streamlit as st

from processor import extracer_tekst, laes_klage, laes_sag_fra_filer
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
    gem_sag_state,
)
from ai_engine import (
    spoerg_ai,
    spoerg_ai_med_klage,
    generer_svarbrev,
    spoerg_ai_med_sag,
    generer_svarbrev_til_sag,
    generer_tjekliste,
    anonymiser_sag,
    opsummer_matches_til_visning,
    udled_sandsynligheder_strukturelt,
)
from embeddings import embed_dokument
from eksport import analyse_til_docx, svarbrev_til_docx
from vurdering import vis_dashboard as vis_udfalds_dashboard
from ui import thinking, render_analyse_som_pillars


# ---------- OPSÆTNING ----------
st.set_page_config(
    page_title="juriitech PAX",
    page_icon=None,
    layout="wide",
)

# Admin-status er sat af app.py før siden køres — hent bare flaget
ER_ADMIN = st.session_state.get("er_admin", False)

# ---------- SKJUL DELINGS-/MENU-ELEMENTER FOR IKKE-ADMINS ----------
if not ER_ADMIN:
    st.markdown(
        """
        <style>
        /* Skjul Streamlits default hamburger-menu, del-/rapportér-ikoner */
        #MainMenu {visibility: hidden !important;}
        [data-testid="stToolbar"] {visibility: hidden !important;}
        [data-testid="stDeployButton"] {display: none !important;}
        /* Skjul "Made with Streamlit"-footer */
        footer {visibility: hidden !important;}
        .viewerBadge_container__1QSob,
        ._terminalButton_rix23_138,
        ._profileContainer_gzau3_53 { display: none !important; }
        /* Skjul eventuelle "Manage app"-knapper nede i højre hjørne */
        [data-testid="manage-app-button"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
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

    /* Skjul Streamlits auto-genererede anchor-link-ikoner på overskrifter */
    h1 a, h2 a, h3 a, h4 a, h5 a, h6 a,
    .stMarkdown h1 a, .stMarkdown h2 a, .stMarkdown h3 a,
    .stMarkdown h4 a, .stMarkdown h5 a, .stMarkdown h6 a,
    [data-testid="stMarkdownContainer"] h1 a,
    [data-testid="stMarkdownContainer"] h2 a,
    [data-testid="stMarkdownContainer"] h3 a,
    [data-testid="stMarkdownContainer"] h4 a,
    [data-testid="stHeaderActionElements"],
    .stMarkdown .stHeaderActionElements,
    [data-testid="stHeading"] a {
        display: none !important;
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

    /* ========== SIDEBAR — ren hvid/lys æstetik ========== */
    section[data-testid="stSidebar"] {
        background-color: #FAFAFA !important;
        border-right: 1px solid rgba(0, 0, 0, 0.06) !important;
    }

    /* Hovedindholds-baggrund tvinges hvid */
    .stApp, .main, [data-testid="stAppViewContainer"] {
        background-color: #FFFFFF !important;
    }

    /* Sidebarens titel — lidt mindre og mere elegant */
    [data-testid="stSidebar"] h1 {
        font-size: 1.55rem !important;
        margin-bottom: 0.25rem !important;
    }

    /* ========== NAV-MENU — afrundede pillers, ikon + tekst ========== */
    [data-testid="stSidebarNav"] {
        padding-top: 0.6rem !important;
    }
    [data-testid="stSidebarNav"] ul {
        padding: 0 0.35rem !important;
        margin: 0 !important;
    }
    [data-testid="stSidebarNav"] li {
        margin: 2px 0 !important;
        list-style: none !important;
    }
    /* Hver nav-link = pille-look med ikon + tekst side om side */
    [data-testid="stSidebarNav"] a {
        display: flex !important;
        align-items: center !important;
        gap: 12px !important;
        padding: 9px 14px !important;
        border-radius: 10px !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.95rem !important;
        font-weight: 500 !important;
        color: #374151 !important;
        text-decoration: none !important;
        transition: background-color 0.12s ease, color 0.12s ease !important;
        border: none !important;
    }
    [data-testid="stSidebarNav"] a:hover {
        background-color: rgba(17, 24, 39, 0.05) !important;
        color: #111827 !important;
    }
    /* Aktiv side — lysegrå baggrund som i billedet */
    [data-testid="stSidebarNav"] a[aria-current="page"],
    [data-testid="stSidebarNav"] a[data-selected="true"] {
        background-color: rgba(17, 24, 39, 0.08) !important;
        color: #111827 !important;
        font-weight: 600 !important;
    }
    /* Ikoner — ensartet størrelse og neutral farve */
    [data-testid="stSidebarNav"] a span[data-testid="stIconMaterial"],
    [data-testid="stSidebarNav"] a [data-testid="stIconMaterial"] {
        font-size: 20px !important;
        color: #4B5563 !important;
        font-weight: 400 !important;
    }
    [data-testid="stSidebarNav"] a[aria-current="page"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarNav"] a[data-selected="true"] [data-testid="stIconMaterial"] {
        color: #111827 !important;
    }

    /* ========== HVIDT RUM OG LAYOUT (Stripe-inspireret) ========== */
    .main .block-container {
        padding-top: 1.5rem !important;
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

    /* ========== APPLE-HEALTH PILLARS MED FARVEDE BAGGRUNDE ========== */
    /* Bruger præcis de pastelfarver Apple selv bruger på apple.com/apple-watch/health */
    .analyse-pillar {
        background: var(--pillar-bg);
        padding: 3rem 2.5rem;
        border-radius: 24px;
        margin: 1.5rem 0;
        position: relative;
        overflow: hidden;
        color: #111827 !important;
    }

    .analyse-pillar-accent-dot {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: var(--pillar-accent);
        margin-bottom: 1.75rem;
    }

    .analyse-pillar-title {
        font-family: 'Source Serif 4', Georgia, serif !important;
        font-size: 2.4rem !important;
        font-weight: 700 !important;
        line-height: 1.08 !important;
        letter-spacing: -0.025em !important;
        margin: 0 0 1.25rem 0 !important;
        padding: 0 !important;
        border: none !important;
        background: none !important;
        color: #111827 !important;
    }

    .analyse-pillar-body {
        font-family: 'Inter', sans-serif;
        font-size: 1.08rem;
        line-height: 1.75;
        color: #1F2937 !important;
    }

    .analyse-pillar-body p {
        margin: 0 0 1rem 0;
        color: #1F2937 !important;
    }

    .analyse-pillar-body p:last-child {
        margin-bottom: 0;
    }

    .analyse-pillar-body ul {
        padding-left: 1.3rem;
        margin: 0.75rem 0;
    }

    .analyse-pillar-body li {
        margin-bottom: 0.5rem;
        line-height: 1.6;
        color: #1F2937 !important;
    }

    .analyse-pillar-body strong {
        font-weight: 600;
        color: #111827 !important;
    }

    /* Kildehenvisninger — fremhævet i accent-farve på hvid pille */
    .analyse-citation {
        display: inline-block;
        color: #111827 !important;
        font-weight: 600;
        font-size: 0.88em;
        padding: 2px 9px;
        border-radius: 100px;
        background: rgba(255, 255, 255, 0.75);
        white-space: nowrap;
        margin: 0 2px;
        border: 1px solid rgba(17, 24, 39, 0.06);
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
if "sagsakter_filer" not in st.session_state:
    # Liste af dicts: {filnavn, type ('tekst'|'pdf_bytes'|'image_bytes'),
    # tekst, bytes, media_type}
    st.session_state.sagsakter_filer = []
if "sagsakter_signatur" not in st.session_state:
    st.session_state.sagsakter_signatur = None
if "sagsakter_opdaterede_vurdering" not in st.session_state:
    st.session_state.sagsakter_opdaterede_vurdering = False
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
if "match_info" not in st.session_state:
    st.session_state.match_info = []
if "sandsynligheder_dict" not in st.session_state:
    st.session_state.sandsynligheder_dict = None


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
        # så vidensbanken ved at filen findes. Selve analysen sker via juriitech PAX' vision
        # på den fil der ligger i session state.
        indhold = (
            f"[Scannet klage — tekst ikke udtrukket lokalt. "
            f"Analyseres ved upload via juriitech PAX' vision. Filnavn: {filnavn}]"
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

    st.title("juriitech PAX")
    st.caption("Juridisk AI til Pakkerejse-Ankenævnet")

    st.markdown(
        """
        <div style="margin-top: 1.5rem; margin-bottom: 1rem;">
            <div style="font-size: 0.9rem; font-weight: 600; color: #374151;
                        margin-bottom: 0.5rem;">
                juriitech PAX's videnstank
            </div>
            <ul style="list-style: none; padding: 0; margin: 0;
                       font-size: 0.85rem; color: #4B5563;">
                <li style="padding: 4px 0;">
                    <span style="color: #6366F1;">•</span>
                    +500 afgørelser fra Pakkerejse-Ankenævnet
                </li>
                <li style="padding: 4px 0;">
                    <span style="color: #6366F1;">•</span>
                    Pakkerejselovgivningen
                </li>
                <li style="padding: 4px 0;">
                    <span style="color: #6366F1;">•</span>
                    Brugerens uploadede sager
                </li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not ER_ADMIN:
        # Bruger-interface: kort og venligt
        st.caption(
            "Analyser klagesager fra Pakkerejse-Ankenævnet med AI der har læst "
            "alle tidligere afgørelser."
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
            "Scannede PDF'er gemmes også, men uden embedding (juriitech PAX læser dem via vision)."
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
# Empty state: stor hero-sektion med cream/peach-baggrund (Apple Health palette)
_har_aktiv_sag = bool(st.session_state.get("aktuel_sag"))

if not _har_aktiv_sag:
    # Side-by-side: hero til venstre, upload-widget til højre.
    # På smalle skærme stakkes de automatisk af Streamlit.
    _kol_hero, _kol_upload = st.columns([1, 1], gap="medium")

    with _kol_hero:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg, #FDEFD7 0%, #FDF6E6 100%);
                padding: 1.75rem 1.75rem;
                border-radius: 20px;
                min-height: 220px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            ">
                <h1 style="
                    font-family: 'Source Serif 4', Georgia, serif;
                    font-size: 1.9rem;
                    font-weight: 700;
                    line-height: 1.08;
                    letter-spacing: -0.025em;
                    color: #1F2937;
                    margin: 0 0 0.5rem 0;
                ">
                    Analysér en sag fra <span style="color: #92400E;">Pakkerejse-Ankenævnet</span>
                </h1>
                <p style="
                    font-family: 'Inter', sans-serif;
                    font-size: 0.95rem;
                    line-height: 1.45;
                    color: #374151;
                    margin: 0;
                    font-weight: 400;
                ">
                    Kom i gang ved at uploade sagsfilerne — høringsbrev,
                    klageskema og eventuelle bilag.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with _kol_upload:
        uploadede_sagsfiler = st.file_uploader(
            "Upload sagsfilerne her",
            type=["zip", "pdf", "docx"],
            accept_multiple_files=True,
            key="sag_uploader",
            help="Understøtter ZIP, PDF og Word. Flere filer kan vælges samtidigt.",
        )
else:
    uploadede_sagsfiler = st.file_uploader(
        "Upload sagsfilerne",
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
            st.session_state.sagsakter_filer = []
            st.session_state.sagsakter_signatur = None
            st.session_state.sagsakter_opdaterede_vurdering = False
            st.session_state.auto_vurdering_tekst = None
            st.session_state.auto_vurdering_for_signatur = None
            st.session_state.seneste_svar = None
            st.session_state.seneste_svarbrev = None
            st.session_state.seneste_tjekliste = None
            st.session_state.seneste_anonymisering = None
            st.session_state.relevante_sager = []
            st.session_state.match_info = []
            st.session_state.sandsynligheder_dict = None
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
    # Beregn kombineret signatur af sag + sagsakter. Hvis den ændrer sig,
    # genkøres vurderingen så den tager højde for nye sagsakter.
    def _beregn_kombineret_signatur():
        sag_sig = st.session_state.sidste_sagsfil_signatur or ()
        sagsakter_tekst = st.session_state.get("sagsakter", "") or ""
        sagsakter_filer = st.session_state.get("sagsakter_filer", []) or []
        # Signatur = filnavne + total bytes + hash af teksten
        sagsakter_sig = tuple(
            (f["filnavn"], len(f.get("bytes") or b""), len(f.get("tekst") or ""))
            for f in sagsakter_filer
        )
        return (sag_sig, hash(sagsakter_tekst), sagsakter_sig)

    kombineret_sig = _beregn_kombineret_signatur()
    skal_auto_vurdere = (
        st.session_state.auto_vurdering_for_signatur != kombineret_sig
    )

    # Bestem om dette er en re-genkørsel pga. sagsakter (ikke første analyse)
    er_sagsakter_opdatering = (
        skal_auto_vurdere
        and st.session_state.auto_vurdering_for_signatur is not None
        and st.session_state.auto_vurdering_tekst is not None
    )
    if skal_auto_vurdere:
        with st.spinner(
            "juriitech PAX laver en første vurdering af sagen — tager 20-40 sekunder..."
        ):
            try:
                auto_svar, rel_sager = spoerg_ai_med_sag(
                    spoergsmaal=(
                        "Lav en struktureret juridisk førstevurdering af sagen "
                        "baseret på de uploadede dokumenter. Følg præcis denne "
                        "rækkefølge:\n\n"
                        "1. **Kort resume af sagen** (2-4 sætninger)\n"
                        "2. **Klagens kernepunkter** (3-5 punkter i bullet-form)\n"
                        "3. **Rejseselskabets stillingtagen indtil nu** — "
                        "beskriv hvad rejseselskabet (TUI) har gjort, tilbudt "
                        "eller afvist i forhold til klagen INDEN Nævnet blev "
                        "involveret. Fx: 'TUI har afvist reklamationen med "
                        "begrundelsen ...', 'TUI har tilbudt X kr. i "
                        "kompensation', eller 'TUI har ikke svaret'. Udled "
                        "dette fra mail-korrespondance og sagsakter i bilagene. "
                        "Hvis det ikke fremgår tydeligt, skriv 'fremgår ikke af "
                        "bilagene'.\n"
                        "4. **Kort juridisk vurdering** (2-4 sætninger om de "
                        "centrale juridiske spørgsmål)\n"
                        "5. **Sandsynlighedsvurdering** — du SKAL afslutte med "
                        "præcis denne struktur, hvor procenterne summer til 100:\n\n"
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
                    sagsakter_filer=st.session_state.get("sagsakter_filer", []),
                    returner_relevante=True,
                )
                st.session_state.auto_vurdering_tekst = auto_svar
                st.session_state.relevante_sager = rel_sager
                # Husk om denne genkørsel skyldtes sagsakter-ændring
                st.session_state.sagsakter_opdaterede_vurdering = er_sagsakter_opdatering

                # Sikr at dashboardet ALTID kan vises: prøv først tekst-parsing,
                # og hvis den fejler, kør et struktureret fallback-AI-kald der
                # tvinger tre procenter ud.
                from vurdering import parse_sandsynligheder
                _s = parse_sandsynligheder(auto_svar)
                if not _s["fandt_alle_tre"]:
                    with st.spinner("Finjusterer sandsynligheder..."):
                        _strukt = udled_sandsynligheder_strukturelt(auto_svar)
                    st.session_state.sandsynligheder_dict = _strukt
                else:
                    st.session_state.sandsynligheder_dict = {
                        "fuld_medhold": _s["fuld_medhold"],
                        "delvist_medhold": _s["delvist_medhold"],
                        "afvist": _s["afvist"],
                    }

                # Generer struktureret metadata + match-begrundelse for hver
                # relevant afgørelse (til de visuelle kort nedenfor)
                rel_afgoerelser = [
                    r for r in rel_sager
                    if (r.get("dokumenttype") or "").lower() == "afgoerelse"
                ][:5]
                if rel_afgoerelser:
                    st.session_state.match_info = opsummer_matches_til_visning(
                        uploadet_sag=st.session_state.aktuel_sag,
                        relevante_sager=rel_afgoerelser,
                    )
                else:
                    st.session_state.match_info = []
                # Gem den KOMBINEREDE signatur (sag + sagsakter), så vi
                # detekterer ændringer i begge dele
                st.session_state.auto_vurdering_for_signatur = kombineret_sig

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

        # Opdateringsnotifikation — vises hvis sagsakter har ændret vurderingen
        if st.session_state.get("sagsakter_opdaterede_vurdering"):
            st.markdown(
                """
                <div style="
                    background-color: #EEF2FF;
                    color: #3730A3;
                    padding: 12px 16px;
                    border-radius: 8px;
                    margin-bottom: 16px;
                    border-left: 4px solid #6366F1;
                    font-size: 0.92rem;
                ">
                    <strong>Opdateret vurdering:</strong> Disse afsnit er opdateret som
                    følge af de uploadede sagsakter. Analysen tager nu højde for
                    det nye materiale.
                </div>
                """,
                unsafe_allow_html=True,
            )

        vis_udfalds_dashboard(st.session_state.auto_vurdering_tekst)

        # Visuelle kort for de 3-5 mest relevante tidligere sager
        rel = st.session_state.get("relevante_sager") or []
        afgoerelser_ud = [r for r in rel if (r.get("dokumenttype") or "").lower() == "afgoerelse"]
        vilkaar_ud = [r for r in rel if (r.get("dokumenttype") or "").lower() == "vilkaar"]

        if afgoerelser_ud:
            st.markdown("### De mest relevante tidligere afgørelser")
            st.caption(
                "Disse afgørelser fra Pakkerejse-Ankenævnet minder mest om din nuværende sag. "
                "juriitech PAX bruger dem aktivt som juridisk præcedens i analysen ovenfor."
            )
            from badges import udled_afgoerelsesdato, badge

            match_info_list = st.session_state.get("match_info") or []

            for i, sag_ref in enumerate(afgoerelser_ud[:5], 1):
                sim = sag_ref.get("similarity") or 0
                sim_pct = int(sim * 100)
                afgoerelses_dato = udled_afgoerelsesdato(
                    sag_ref.get("indhold"),
                    filnavn=sag_ref.get("filnavn"),
                )
                dato_str = afgoerelses_dato or "dato ikke angivet"

                # Hent den strukturerede match-info hvis den findes
                info = match_info_list[i - 1] if i - 1 < len(match_info_list) else {}
                sagsnummer = info.get("sagsnummer") or (
                    (sag_ref.get("filnavn") or "")
                    .rsplit(".", 1)[0]
                    .replace("_", " ")
                )
                titel = info.get("titel") or ""
                udfald = info.get("udfald") or ""
                klagers_krav = info.get("klagers_krav") or ""
                tilkendt = info.get("tilkendt_beloeb") or ""
                arrangoer = info.get("rejsearrangoer") or ""
                match_begrundelse = info.get("match_begrundelse") or []

                # Udfalds-badge (set fra rejseselskabets perspektiv)
                if "Fuld medhold" in udfald:
                    udfald_badge_html = badge("Fuld medhold klager", "red")
                elif "Delvist" in udfald:
                    udfald_badge_html = badge("Delvist medhold", "yellow")
                elif udfald == "Afvist":
                    udfald_badge_html = badge("Afvist", "green")
                else:
                    udfald_badge_html = ""

                # Farve på match-%
                if sim_pct >= 70:
                    farve = "#059669"
                elif sim_pct >= 55:
                    farve = "#CA8A04"
                else:
                    farve = "#6B7280"

                with st.container(border=True):
                    kol_a, kol_b = st.columns([5, 1])
                    with kol_a:
                        # Overskrift: "Sagsnummer 25-0122 · Navneændring afvist"
                        overskrift_dele = [f"Sagsnummer {sagsnummer}"]
                        if titel:
                            overskrift_dele.append(titel)
                        st.markdown(
                            f"**{i}.  {'  ·  '.join(overskrift_dele)}**"
                        )
                        # Meta + udfaldsbadge
                        meta = f"Afgjort {dato_str}"
                        if arrangoer and arrangoer.lower() != "ukendt":
                            meta += f"  ·  {arrangoer}"
                        st.caption(meta)
                        if udfald_badge_html:
                            st.markdown(udfald_badge_html, unsafe_allow_html=True)
                    with kol_b:
                        st.markdown(
                            f"<div style='text-align:right; font-size:1.4rem; "
                            f"font-weight:700; color:{farve};'>{sim_pct}%</div>"
                            f"<div style='text-align:right; font-size:0.75rem; "
                            f"color:#6B7280;'>match</div>",
                            unsafe_allow_html=True,
                        )

                    with st.expander("Se uddrag af afgørelsen"):
                        # Struktureret sammenligning af krav og tilkendt beløb
                        if klagers_krav or tilkendt:
                            st.markdown("**Beløb**")
                            kol_krav, kol_tilkendt = st.columns(2)
                            with kol_krav:
                                st.caption("Klageren krævede")
                                st.markdown(
                                    f"### {klagers_krav or 'ukendt'}"
                                )
                            with kol_tilkendt:
                                st.caption("Nævnet tilkendte")
                                st.markdown(
                                    f"### {tilkendt or 'ukendt'}"
                                )
                            st.markdown("")

                        # Match-begrundelse (hvorfor Juriitech ser den som match)
                        if match_begrundelse:
                            st.markdown("**Hvorfor juriitech PAX ser det som et match**")
                            for b in match_begrundelse:
                                st.markdown(f"- {b}")
                            st.markdown("")

                        # Rå tekst-uddrag af afgørelsen
                        with st.expander("Se rå tekst fra afgørelsen"):
                            raa = (sag_ref.get("indhold") or "")[:2000]
                            st.text(raa + ("..." if len(raa) == 2000 else ""))

                        if sag_ref.get("kilde_url"):
                            st.markdown(
                                f"[Åbn original på pakkerejseankenaevnet.dk]"
                                f"({sag_ref['kilde_url']})"
                            )

        # Juridisk førstevurdering som Apple-Health-inspirerede pillars —
        # store overskrifter, accent-striber, fremhævede kildehenvisninger.
        if st.session_state.auto_vurdering_tekst:
            render_analyse_som_pillars(st.session_state.auto_vurdering_tekst)

        # TUI's rejsevilkår vises ikke længere som separat sektion på forsiden
        # (for ikke at rode UI'en). De bliver stadig automatisk brugt af Claude
        # som juridisk kontekst i førstevurderingen — de hentes blot via RAG
        # og indgår i prompten uden at være synlige som visuelle kort.


    # ---------- SAGSAKTER — Apple Health-styled sektion ----------
    # Farvet pillar (purple, matcher juriitech primary accent) der skiller sig ud
    st.markdown(
        """
        <div class="analyse-pillar"
             style="--pillar-bg: #F0EEFD; --pillar-accent: #6366F1;">
            <div class="analyse-pillar-accent-dot"></div>
            <h2 class="analyse-pillar-title">Sagsakter til denne sag</h2>
            <div class="analyse-pillar-body">
                <p>Her kan du uploade yderligere filer om sagen, såsom
                mailkorrespondancer, tekstbeskeder, bookingdetaljer,
                screenshots m.m. — altså information som juriitech PAX
                ikke automatisk har adgang til.</p>
                <p>Når du tilføjer sagsakter, genberegnes analysen
                automatisk, så vurderingen tager højde for den nye
                information.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # File uploader — accepterer PDF, DOCX, PNG, JPG
    nye_filer = st.file_uploader(
        "Upload sagsakter (PDF, DOCX, PNG eller JPG)",
        type=["pdf", "docx", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="sagsakter_uploader",
        help=(
            "Uploadede filer persisterer på tværs af handlinger. "
            "Screenshots af skærmbilleder, tekstbeskeder osv. læses "
            "via vision og indgår i analysen."
        ),
    )

    # Håndter nye uploads — tilføj til listen, undgå dubletter
    if nye_filer:
        _eksisterende_navne = {f["filnavn"] for f in st.session_state.sagsakter_filer}
        for f in nye_filer:
            if f.name in _eksisterende_navne:
                continue
            data = f.getvalue()
            navn_lower = f.name.lower()
            if navn_lower.endswith((".png",)):
                st.session_state.sagsakter_filer.append({
                    "filnavn": f.name,
                    "type": "image_bytes",
                    "bytes": data,
                    "media_type": "image/png",
                    "tekst": "",
                })
            elif navn_lower.endswith((".jpg", ".jpeg")):
                st.session_state.sagsakter_filer.append({
                    "filnavn": f.name,
                    "type": "image_bytes",
                    "bytes": data,
                    "media_type": "image/jpeg",
                    "tekst": "",
                })
            elif navn_lower.endswith(".pdf"):
                # Prøv tekstudtræk; hvis for lidt, behandl som scannet PDF
                from io import BytesIO
                from processor import laes_pdf_tekst, SCANNET_TAERSKEL
                try:
                    udtrukket = laes_pdf_tekst(BytesIO(data))
                except Exception:
                    udtrukket = ""
                if len(udtrukket.strip()) >= SCANNET_TAERSKEL:
                    st.session_state.sagsakter_filer.append({
                        "filnavn": f.name,
                        "type": "tekst",
                        "tekst": udtrukket,
                        "bytes": data,
                        "media_type": "application/pdf",
                    })
                else:
                    st.session_state.sagsakter_filer.append({
                        "filnavn": f.name,
                        "type": "pdf_bytes",
                        "bytes": data,
                        "tekst": "",
                        "media_type": "application/pdf",
                    })
            elif navn_lower.endswith(".docx"):
                from io import BytesIO
                from processor import laes_word_tekst
                try:
                    udtrukket = laes_word_tekst(BytesIO(data))
                except Exception:
                    udtrukket = "[Kunne ikke læse DOCX]"
                st.session_state.sagsakter_filer.append({
                    "filnavn": f.name,
                    "type": "tekst",
                    "tekst": udtrukket,
                    "bytes": data,
                    "media_type": None,
                })

    # Vis liste af uploadede sagsakter med fjern-knapper
    if st.session_state.sagsakter_filer:
        st.markdown("**Uploadede sagsakter:**")
        _fil_til_fjern = None
        for idx, fil in enumerate(st.session_state.sagsakter_filer):
            kol_a, kol_b = st.columns([10, 1])
            with kol_a:
                ikon = {
                    "image_bytes": "🖼",
                    "pdf_bytes": "📄",
                    "tekst": "📄",
                }.get(fil["type"], "📄")
                laengde_info = ""
                if fil["type"] == "tekst" and fil.get("tekst"):
                    laengde_info = f" — {len(fil['tekst'])} tegn læst"
                elif fil["type"] == "image_bytes":
                    laengde_info = " — scannes via vision"
                elif fil["type"] == "pdf_bytes":
                    laengde_info = " — scannet PDF (læses via vision)"
                st.markdown(
                    f"<div style='padding: 6px 10px;'>"
                    f"<strong>{fil['filnavn']}</strong>"
                    f"<span style='color: #6B7280;'>{laengde_info}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with kol_b:
                if st.button("✕", key=f"sagsakter_fjern_{idx}", help="Fjern fil"):
                    _fil_til_fjern = idx

        if _fil_til_fjern is not None:
            st.session_state.sagsakter_filer.pop(_fil_til_fjern)
            st.rerun()

    # Free-text notater (bevares til backward compat + bruges til hurtige noter)
    with st.expander("Skriv yderligere noter (valgfri)", expanded=False):
        st.session_state.sagsakter = st.text_area(
            "Noter",
            value=st.session_state.get("sagsakter", ""),
            height=160,
            placeholder=(
                "Yderligere noter du vil inkludere i analysen — fx kommentarer, "
                "status eller sammenfattede oplysninger fra andre kilder."
            ),
            label_visibility="collapsed",
        )

# ---------- SPØRGSMÅL / CHAT (kun synlig når der er en aktiv sag) ----------
# Når ingen sag er uploadet, skjules hele sektionen så forsiden forbliver
# ren og fokuseret på upload-flowet.
spoergsmaal = ""
if st.session_state.get("aktuel_sag"):
    st.divider()
    st.header("Stil spørgsmål til sagen")

    _sag_filer = st.session_state.aktuel_sag.get("filer") or []
    st.caption(
        f"Samtalen tager udgangspunkt i den uploadede sag "
        f"({len(_sag_filer)} filer), tidligere afgørelser fra "
        f"Pakkerejse-Ankenævnet og pakkerejseloven."
    )

    spoergsmaal = st.text_input(
        "Hvad vil du vide?",
        placeholder="fx 'Giv mig en komplet analyse af sagen' eller 'Hvilke tidligere sager minder mest om denne?'",
    )

if spoergsmaal:
    with st.spinner("juriitech PAX analyserer..."):
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
        "juriitech PAX producerer anonymiserede versioner af alle tekst-baserede bilag "
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
            f"juriitech PAX anonymiserer {antal} bilag — tager ca. {antal * 15} sekunder..."
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
        with st.spinner("juriitech PAX læser høringsbrevet og gennemgår bilagene — 20-40 sekunder..."):
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
        with st.spinner("juriitech PAX udarbejder svarbrevet — tager 30-60 sekunder..."):
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


# ---------- GEM SAGEN ----------
# Knappen vises kun hvis brugeren har en aktiv sag
if st.session_state.get("aktuel_sag"):
    st.divider()

    st.markdown(
        """
        <div class="analyse-pillar"
             style="--pillar-bg: #E7F5DD; --pillar-accent: #76D672;">
            <div class="analyse-pillar-accent-dot"></div>
            <h2 class="analyse-pillar-title">Gem din sagsbehandling</h2>
            <div class="analyse-pillar-body">
                <p>Gem alt det du har lavet indtil videre. Du kan genoptage
                sagen præcis hvor du slap — under menupunktet
                <strong>Gemte sager</strong> til venstre.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Foreslået titel baseret på sagens hovedfil (klageskema)
    _sag_filer_for_titel = st.session_state.aktuel_sag.get("filer") or []
    _standard_titel = "Sag uden navn"
    for _f in _sag_filer_for_titel:
        if _f.get("rolle") == "klageskema":
            _standard_titel = _f["filnavn"].rsplit(".", 1)[0]
            break
    if _standard_titel == "Sag uden navn" and _sag_filer_for_titel:
        _standard_titel = _sag_filer_for_titel[0]["filnavn"].rsplit(".", 1)[0]

    gem_titel = st.text_input(
        "Titel på den gemte sag",
        value=st.session_state.get("aktiv_gemt_sag_titel", _standard_titel),
        help="Giv sagen et navn så du kan finde den igen under Gemte sager.",
    )

    kol_gem, kol_status = st.columns([1, 3])
    with kol_gem:
        if st.button("Gem sagen", type="primary", key="gem_sag_knap"):
            import json as _json
            import base64 as _b64

            # Byg state-dict. bytes serialiseres som base64-strenge
            def _serialiser_fil(fil):
                d = dict(fil)
                if d.get("bytes"):
                    d["bytes_b64"] = _b64.b64encode(d["bytes"]).decode("ascii")
                    d.pop("bytes", None)
                return d

            aktuel = st.session_state.aktuel_sag or {}
            state = {
                "aktuel_sag": {
                    **{k: v for k, v in aktuel.items() if k != "filer"},
                    "filer": [
                        _serialiser_fil(f) for f in (aktuel.get("filer") or [])
                    ],
                },
                "sagsakter": st.session_state.get("sagsakter", ""),
                "sagsakter_filer": [
                    _serialiser_fil(f)
                    for f in (st.session_state.get("sagsakter_filer") or [])
                ],
                "auto_vurdering_tekst": st.session_state.get("auto_vurdering_tekst"),
                "relevante_sager": st.session_state.get("relevante_sager") or [],
                "match_info": st.session_state.get("match_info") or [],
                "seneste_svar": st.session_state.get("seneste_svar"),
                "seneste_svarbrev": st.session_state.get("seneste_svarbrev"),
                "seneste_tjekliste": st.session_state.get("seneste_tjekliste"),
                "seneste_anonymisering": st.session_state.get("seneste_anonymisering"),
            }

            # Gem — opdater eksisterende sag hvis vi allerede har et ID
            eksisterende_id = st.session_state.get("aktiv_gemt_sag_id")
            ny_id = gem_sag_state(
                titel=gem_titel or "Sag uden navn",
                state_json=_json.dumps(state, default=str, ensure_ascii=False),
                user_id=None,
                sag_id=eksisterende_id,
            )
            if ny_id:
                st.session_state.aktiv_gemt_sag_id = ny_id
                st.session_state.aktiv_gemt_sag_titel = gem_titel
                st.session_state.sidst_gemt_besked = (
                    f"Sagen '{gem_titel}' er gemt. Du kan finde den under "
                    "'Gemte sager' i menuen."
                )
            else:
                st.session_state.sidst_gemt_besked = "Kunne ikke gemme sagen."
            st.rerun()

    with kol_status:
        if st.session_state.get("sidst_gemt_besked"):
            st.success(st.session_state.sidst_gemt_besked)


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
