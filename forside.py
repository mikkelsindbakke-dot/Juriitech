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
    chat_om_sag,
    generer_svarbrev_til_sag,
    generer_tjekliste,
    anonymiser_sag,
    anonymiser_valgte_filer,
    opsummer_matches_til_visning,
    udled_sandsynligheder_strukturelt,
    udled_sagsresume_strukturelt,
    udled_alle_klagepunkter,
    udled_tidsforhold,
    udled_sagsmetadata,
    udled_bilag_overskrifter,
)
from embeddings import embed_dokument
from eksport import analyse_til_docx, svarbrev_til_docx
from vurdering import vis_dashboard as vis_udfalds_dashboard
from ui import (
    thinking,
    render_analyse_som_pillars,
    render_sagsresume,
    render_tidslinje,
    vis_brugerfejl,
)


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
    /* Mørke tekstfarver + øget opacitet på baggrunden så teksten er
       let læselig på små pille-størrelser. Matcher paletten i
       udfaldsdashboardet. */
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

    /* BEMÆRK: vi har tidligere haft en @media (prefers-color-scheme: dark)
       regel der lavede badges om til lyse farver hvis brugerens OS kørte
       i dark mode. Streamlit er dog tvunget til light-theme overalt,
       så dark-mode tekstfarverne endte på lys baggrund → ulæselige.
       Derfor er dark-mode blokken fjernet bevidst her. */

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

    /* KONSEKVENT FONT-FAMILY i HELE pillaren — både overskrift og
       brødtekst bruger samme serif-font. Det giver et editorial,
       sammenhængende look. !important sikrer at Streamlit's
       default-fonts (Inter via base.css) ikke overstyrer. */
    .analyse-pillar-title,
    .analyse-pillar-body,
    .analyse-pillar-body p,
    .analyse-pillar-body li,
    .analyse-pillar-body strong,
    .analyse-pillar-body span,
    .analyse-pillar-body div {
        font-family: 'Source Serif 4', Georgia, serif !important;
    }

    .analyse-pillar-title {
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

    /* ========== TIDSLINJE — vertikal Apple Health-style timeline ========== */
    .tidslinje-advarsel {
        background: rgba(217, 119, 6, 0.12);
        border-left: 4px solid #D97706;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 18px;
    }
    .tidslinje-advarsel-titel {
        font-weight: 700;
        color: #92400E !important;
        font-size: 0.95rem;
        margin-bottom: 4px;
    }
    .tidslinje-advarsel-tekst {
        color: #78350F !important;
        font-size: 0.9rem;
        line-height: 1.55;
    }

    .tidslinje-container {
        position: relative;
        padding-left: 8px;
        margin-top: 8px;
    }
    .tidslinje-container::before {
        content: '';
        position: absolute;
        left: 13px;
        top: 12px;
        bottom: 12px;
        width: 2px;
        background: rgba(0, 0, 0, 0.1);
        z-index: 0;
    }
    .tidslinje-item {
        position: relative;
        margin-bottom: 14px;
        padding-left: 32px;
        min-height: 24px;
    }
    .tidslinje-item:last-child {
        margin-bottom: 0;
    }
    .tidslinje-dot {
        position: absolute;
        left: 6px;
        top: 8px;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        border: 3px solid white;
        z-index: 1;
    }
    .tidslinje-card {
        background: rgba(255, 255, 255, 0.7);
        padding: 10px 14px;
        border-radius: 10px;
        border: 1px solid rgba(0, 0, 0, 0.06);
    }
    .tidslinje-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: baseline;
        margin-bottom: 4px;
    }
    .tidslinje-dato {
        font-weight: 700 !important;
        color: #111827 !important;
        font-size: 0.95rem;
    }
    .tidslinje-tid {
        color: #4B5563 !important;
        font-size: 0.88rem;
        font-weight: 500;
    }
    .tidslinje-aktoer {
        color: #6B7280 !important;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
        background: rgba(99, 102, 241, 0.08);
        padding: 2px 8px;
        border-radius: 100px;
    }
    .tidslinje-beskrivelse {
        color: #1F2937 !important;
        font-size: 0.95rem;
        line-height: 1.55;
    }

    /* ========== TIDSFORHOLD-TIDSLINJE — vist i den gule tidsforhold-pillar
       Layout: dato i venstre kolonne (130px), lodret linje, dot, tekst i højre.
       Begivenheder efter hjemkomst dæmpes visuelt så fokus er på destinationen. */
    .tf-tidslinje {
        position: relative;
        padding-left: 0;
        margin-top: 12px;
    }
    .tf-tidslinje::before {
        content: '';
        position: absolute;
        left: 152px;
        top: 12px;
        bottom: 12px;
        width: 2px;
        background: rgba(146, 64, 14, 0.18);
        z-index: 0;
    }
    .tf-tidslinje-item {
        position: relative;
        display: flex;
        align-items: flex-start;
        gap: 0;
        margin-bottom: 14px;
        min-height: 28px;
    }
    .tf-tidslinje-item:last-child {
        margin-bottom: 0;
    }
    .tf-tidslinje-dato-kolonne {
        flex: 0 0 130px;
        width: 130px;
        max-width: 130px;
        text-align: right;
        padding-right: 22px;
        padding-top: 10px;
        box-sizing: border-box;
    }
    .tf-tidslinje-dato {
        display: block;
        font-weight: 700;
        color: #92400E !important;
        font-size: 0.92rem;
        line-height: 1.25;
        white-space: nowrap;
    }
    .tf-tidslinje-dato.efter-hjemkomst {
        color: #9CA3AF !important;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .tf-tidslinje-tid {
        display: block;
        font-weight: 600;
        color: #B45309 !important;
        font-size: 0.78rem;
        line-height: 1.2;
        margin-top: 2px;
    }
    .tf-tidslinje-fase {
        display: block;
        font-size: 0.7rem;
        font-weight: 600;
        color: #B45309 !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-top: 3px;
        opacity: 0.78;
    }
    .tf-tidslinje-fase.efter-hjemkomst {
        color: #9CA3AF !important;
        opacity: 0.65;
    }
    .tf-tidslinje-dato-ukendt {
        display: block;
        font-style: italic;
        font-weight: 500;
        color: #9CA3AF !important;
        font-size: 0.8rem;
        line-height: 1.25;
    }
    .tf-tidslinje-dot {
        position: absolute;
        left: 145px;
        top: 12px;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        border: 3px solid #FEF3C7;
        z-index: 1;
    }
    .tf-tidslinje-tekst {
        flex: 1 1 auto;
        margin-left: 30px;
        background: rgba(255, 255, 255, 0.55);
        padding: 10px 14px;
        border-radius: 10px;
        border: 1px solid rgba(146, 64, 14, 0.1);
        color: #1F2937 !important;
        font-size: 0.95rem !important;
        line-height: 1.55;
    }
    .tf-tidslinje-tekst strong {
        color: #92400E !important;
        font-weight: 700;
    }
    .tf-tidslinje-tekst.efter-hjemkomst {
        background: rgba(255, 255, 255, 0.35);
        border: 1px dashed rgba(146, 64, 14, 0.12);
        color: #6B7280 !important;
        font-size: 0.88rem !important;
        opacity: 0.72;
    }
    .tf-tidslinje-tekst.efter-hjemkomst strong {
        color: #6B7280 !important;
        font-weight: 600;
    }
    @media (max-width: 640px) {
        .tf-tidslinje::before { left: 88px; }
        .tf-tidslinje-dot { left: 81px; }
        .tf-tidslinje-dato-kolonne {
            flex: 0 0 70px;
            width: 70px;
            max-width: 70px;
            padding-right: 14px;
        }
        .tf-tidslinje-dato { font-size: 0.82rem; }
        .tf-tidslinje-tekst { margin-left: 26px; font-size: 0.9rem !important; }
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

    /* ========== JURIITECH PAX-LOGO I SIDEBAREN ========== */
    /* Lavendel 'j', sort 'uriitech', og en gul taleboble-pille med PAX
       der har en lille "tail" nederst til højre — matcher det officielle
       juriitech PAX-logo. */
    .jp-logo {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        font-weight: 800;
        font-size: 1.35rem;
        letter-spacing: -0.035em;
        line-height: 1;
        margin: 0 0 0.35rem 0;
        user-select: none;
    }
    /* Wordmark-wrapper sikrer at j + uriitech sidder som ét ord,
       uden at flex-gap'et i den ydre container skyder dem fra hinanden. */
    .jp-wordmark {
        display: inline-flex;
        align-items: baseline;
    }
    .jp-j {
        color: #6E74F0;     /* mørkere indigo/lavendel — matcher logoet tættere */
        font-weight: 800;
    }
    .jp-rest {
        color: #0A0B0F;
        font-weight: 800;
    }
    /* Den gule taleboble */
    .jp-pax {
        position: relative;
        display: inline-block;
        background: #F5B53B;   /* gul/amber matchende logoet */
        color: #0A0B0F;
        font-weight: 800;
        font-size: 0.78em;
        letter-spacing: 0;
        padding: 3px 8px 3px 9px;
        border-radius: 5px;
        line-height: 1.1;
        margin-left: 2px;
    }
    /* Den lille 'hale' under taleboblen — lidt til højre */
    .jp-pax::after {
        content: "";
        position: absolute;
        bottom: -5px;
        right: 10px;
        width: 8px;
        height: 8px;
        background: #F5B53B;
        clip-path: polygon(0 0, 100% 0, 50% 100%);
    }

    /* ========== PAX WORDMARK — juriitech-signatur øverst på siden ========== */
    /* Matcher landing-sidens wordmark (indigo 'j', sort resten) i kompakt format. */
    .pax-wordmark {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        font-size: 1.45rem;
        font-weight: 800;
        letter-spacing: -0.035em;
        line-height: 1;
        margin: 0 0 0.75rem 0;
        padding: 0;
        display: inline-flex;
        align-items: baseline;
        user-select: none;
    }
    .pax-wordmark-j {
        color: #6366F1;
        font-weight: 800;
    }
    .pax-wordmark-rest {
        color: #0A0B0F;
        font-weight: 800;
    }

    /* ========== BRUGERFEJL-BOKS — venlig fejl-UI med Sentry-info ========== */
    /* Vises når noget går galt under fx svarbrev-generering eller
       anonymisering. Bruger en blød rosa pastel matchende vores andre
       advarsels-bokse, plus et venligt ikon og humor i tonen. */
    .brugerfejl-boks {
        display: flex;
        align-items: flex-start;
        gap: 16px;
        background: linear-gradient(135deg, #FDE9EE 0%, #FEF3F5 100%);
        border-left: 4px solid #EC4899;
        padding: 18px 22px;
        border-radius: 14px;
        margin: 16px 0;
        box-shadow: 0 1px 3px rgba(236, 72, 153, 0.08);
    }
    .brugerfejl-ikon {
        font-size: 1.6rem;
        line-height: 1;
        flex-shrink: 0;
        padding-top: 2px;
    }
    .brugerfejl-indhold {
        flex: 1;
        min-width: 0;
    }
    .brugerfejl-titel {
        font-family: 'Source Serif 4', Georgia, serif;
        font-size: 1.15rem;
        font-weight: 700;
        color: #9F1239;
        margin-bottom: 6px;
        letter-spacing: -0.01em;
    }
    .brugerfejl-tekst {
        color: #1F2937;
        font-size: 0.95rem;
        line-height: 1.55;
        margin-bottom: 8px;
    }
    .brugerfejl-tekst strong {
        color: #9F1239;
    }
    .brugerfejl-ekstra {
        color: #4B5563;
        font-size: 0.88rem;
        font-style: italic;
        margin-bottom: 8px;
    }
    .brugerfejl-tips {
        color: #4B5563;
        font-size: 0.88rem;
        line-height: 1.5;
        margin-top: 6px;
    }
    .brugerfejl-tips ul {
        margin: 4px 0 0 0;
        padding-left: 22px;
    }
    .brugerfejl-tips li {
        margin-bottom: 2px;
    }

    /* ========== VIDENSTANK STABEL — lyse pastel-kort i vertikal stabel ========== */
    .videnstank-stak {
        margin: 1.25rem 0 1rem 0;
        display: flex;
        flex-direction: column;
        gap: 8px;
    }
    .videnstank-titel {
        color: rgba(71, 85, 105, 0.75);
        font-family: 'Inter', sans-serif;
        font-size: 0.68rem;
        font-weight: 600;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
        padding-left: 2px;
    }
    .videnstank-kort {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 0.85rem 1rem;
        border-radius: 12px;
        border: 1px solid rgba(17, 24, 39, 0.04);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .videnstank-kort:hover {
        transform: translateX(2px);
        box-shadow: 0 2px 10px -4px rgba(17, 24, 39, 0.08);
    }
    .videnstank-navn {
        font-family: 'Inter', sans-serif;
        font-size: 0.92rem;
        font-weight: 600;
        line-height: 1.3;
        color: #111827;
        letter-spacing: -0.005em;
    }
    /* '+' foran antal — bruger kortets accent-farve for at fremhæve */
    .videnstank-plus {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 22px;
        height: 22px;
        font-family: 'Inter', sans-serif;
        font-size: 1rem;
        font-weight: 800;
        color: var(--accent);
        flex-shrink: 0;
    }
    /* Lille prik som neutral markør på kort uden '+' */
    .videnstank-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--accent);
        margin-left: 7px;
        margin-right: 7px;
        flex-shrink: 0;
        opacity: 0.85;
    }

    /* ========== RESUME-GRID (inde i Apple Health pillar) ========== */
    /* Emne-linjen lige under pillar-overskriften — lidt større og
       fremhævet, men stadig lysere end selve overskriften. */
    .sagsresume-emne-in-pillar {
        font-family: 'Inter', sans-serif;
        font-size: 1.05rem;
        font-weight: 500;
        line-height: 1.45;
        color: #1F2937;
        margin: 0 0 1.25rem 0;
    }
    .sagsresume-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.85rem;
    }
    .sagsresume-celle {
        background: rgba(255, 255, 255, 0.55);
        border: 1px solid rgba(17, 24, 39, 0.05);
        border-radius: 12px;
        padding: 0.9rem 1.05rem;
    }
    .sagsresume-celle-bred {
        grid-column: 1 / -1;
    }
    .sagsresume-celle-titel {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: rgba(71, 85, 105, 0.9);
        margin-bottom: 0.4rem;
    }
    .sagsresume-celle-body {
        font-size: 0.92rem;
        line-height: 1.55;
        color: #1F2937;
    }
    .sagsresume-celle-body p {
        margin: 0 !important;
        color: #1F2937 !important;
    }
    .sagsresume-liste {
        margin: 0 !important;
        padding-left: 1.1rem !important;
    }
    .sagsresume-liste li {
        margin-bottom: 0.3rem !important;
        color: #1F2937 !important;
    }
    .sagsresume-liste li:last-child {
        margin-bottom: 0 !important;
    }
    .sagsresume-tom {
        color: rgba(100, 116, 139, 0.8) !important;
        font-style: italic;
        margin: 0 !important;
    }
    @media (max-width: 720px) {
        .sagsresume-grid { grid-template-columns: 1fr; }
        .sagsresume-celle-bred { grid-column: auto; }
    }
    /* Forventet udfald — fremhævet som det sidste, vigtigste felt i kortet. */
    .sagsresume-udfald {
        margin-top: 1.1rem;
        padding: 0.95rem 1.15rem;
        background: rgba(255, 255, 255, 0.8);
        border-radius: 12px;
        border-left: 4px solid var(--pillar-accent, #00D4C2);
    }
    .sagsresume-udfald-label {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: rgba(71, 85, 105, 0.95);
        margin-bottom: 0.3rem;
    }
    .sagsresume-udfald-tekst {
        font-family: 'Source Serif 4', Georgia, serif;
        font-size: 1.1rem;
        font-weight: 600;
        line-height: 1.35;
        color: #0F172A;
        letter-spacing: -0.01em;
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

    /* Stakket layout: primær tekst + rullende fase under */
    .thinking-stack {
        display: flex;
        flex-direction: column;
        gap: 2px;
        flex: 1;
        min-width: 0;
    }
    .thinking-stack .thinking-text {
        animation: none;
        color: #111827;
        font-weight: 600;
        font-size: 0.98rem;
    }
    .thinking-fase {
        color: rgba(71, 85, 105, 0.85);
        font-size: 0.85rem;
        font-weight: 400;
        letter-spacing: 0.01em;
        transition: opacity 0.35s ease;
    }
    .thinking-timer {
        font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
        font-size: 0.82rem;
        color: rgba(71, 85, 105, 0.7);
        background: rgba(99, 102, 241, 0.08);
        padding: 3px 9px;
        border-radius: 999px;
        flex-shrink: 0;
        font-variant-numeric: tabular-nums;
    }

    @media (prefers-color-scheme: dark) {
        .thinking-wrapper {
            background: rgba(99, 102, 241, 0.1);
            border-color: rgba(99, 102, 241, 0.2);
        }
        .thinking-text {
            color: rgba(203, 213, 225, 0.9);
        }
        .thinking-stack .thinking-text { color: #F1F5F9; }
        .thinking-fase { color: rgba(203, 213, 225, 0.75); }
        .thinking-timer {
            color: rgba(203, 213, 225, 0.75);
            background: rgba(99, 102, 241, 0.18);
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

# ---------- SCROLL-TIL-TOP EFTER GENÅBNING AF GEMT SAG ----------
# Når brugeren åbner en gemt sag, sætter gemte_sager.py flaget
# '_scroll_til_top'. Her tjekker vi for det og injicerer JavaScript der
# scroller til toppen. Streamlit tegner indholdet gradvist, så vi bruger
# en MutationObserver der scroller hver gang der kommer ny content —
# indtil siden har været stabil i 500ms, hvorefter observeren stopper.
if st.session_state.pop("_scroll_til_top", False):
    from streamlit.components.v1 import html as _scroll_html
    _scroll_html(
        """
        <script>
          (function() {
            var doc;
            try { doc = window.parent.document; }
            catch (e) { doc = document; }

            function findScrollContainer() {
              // Prøv alle de containere Streamlit kan bruge som scroll-parent
              return (
                doc.querySelector('section.main') ||
                doc.querySelector('[data-testid="stMainBlockContainer"]') ||
                doc.querySelector('[data-testid="stAppViewContainer"]') ||
                doc.querySelector('[data-testid="stMain"]') ||
                doc.scrollingElement ||
                doc.documentElement
              );
            }

            function scrollToTopHard() {
              try {
                var c = findScrollContainer();
                if (c) {
                  c.scrollTop = 0;
                  if (c.scrollTo) c.scrollTo(0, 0);
                }
                doc.body.scrollTop = 0;
                doc.documentElement.scrollTop = 0;
                if (doc.defaultView && doc.defaultView.scrollTo) {
                  doc.defaultView.scrollTo(0, 0);
                }
                // Scroll også denne iframes window (fallback)
                window.scrollTo(0, 0);
              } catch (e) { /* ignorer */ }
            }

            // Første kørsel
            scrollToTopHard();

            // MutationObserver: scroll hver gang Streamlit tegner nyt.
            // Stop efter siden har været stille i 500ms, eller efter 5 sek.
            var stopTimer = null;
            var observer = null;
            function resetStopTimer() {
              if (stopTimer) clearTimeout(stopTimer);
              stopTimer = setTimeout(function() {
                if (observer) observer.disconnect();
              }, 500);
            }
            try {
              observer = new MutationObserver(function() {
                scrollToTopHard();
                resetStopTimer();
              });
              observer.observe(doc.body, { childList: true, subtree: true });
              resetStopTimer();
              // Absolut sikkerhedsgrænse
              setTimeout(function() {
                if (observer) observer.disconnect();
              }, 5000);
            } catch (e) { /* ignorer */ }

            // Backup-kald efter faste tidsintervaller
            [60, 200, 500, 1000, 2000, 3500].forEach(function(ms) {
              setTimeout(scrollToTopHard, ms);
            });
          })();
        </script>
        """,
        height=0,
    )

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
if "sagsresume" not in st.session_state:
    st.session_state.sagsresume = None


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

    # juriitech PAX-logo: lavendel 'j' + sort 'uriitech' + gul taleboble med PAX
    st.markdown(
        '<div class="jp-logo">'
        '<span class="jp-wordmark">'
        '<span class="jp-j">j</span><span class="jp-rest">uriitech</span>'
        '</span>'
        '<span class="jp-pax">PAX</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.caption("Juridisk AI til Pakkerejse-Ankenævnet")

    # ---------- VIDENSTANK — LYSE STABLEDE PASTELKORT ----------
    # Vertikal stabel af fire små pillers, hver i sin egen Apple Health-
    # pastel der matcher en sektion i hovedindholdet. Lys æstetik,
    # minimalistisk typografi — flugter med resten af siden.
    # VIGTIGT: HTML må ikke indrykkes med 4+ mellemrum, ellers opfatter
    # markdown-parseren det som kodeblok.
    st.markdown(
        '<div class="videnstank-stak">'
        '<div class="videnstank-titel">Videnstank</div>'
        '<div class="videnstank-kort" style="background:#E7F5DD;--accent:#76D672;">'
        '<span class="videnstank-dot"></span>'
        '<span class="videnstank-navn">+500 afgørelser</span>'
        '</div>'
        '<div class="videnstank-kort" style="background:#F0EEFD;--accent:#6366F1;">'
        '<span class="videnstank-dot"></span>'
        '<span class="videnstank-navn">Hele Pakkerejseloven</span>'
        '</div>'
        '<div class="videnstank-kort" style="background:#FDE9EE;--accent:#EC4899;">'
        '<span class="videnstank-dot"></span>'
        '<span class="videnstank-navn">Anonymiseringsregler</span>'
        '</div>'
        '<div class="videnstank-kort" style="background:#FDEFD7;--accent:#F59E0B;">'
        '<span class="videnstank-dot"></span>'
        '<span class="videnstank-navn">Dine uploadede sager</span>'
        '</div>'
        '</div>',
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

# juriitech-wordmark øverst — samme stil som landing-siden (indigo 'j',
# sort resten), men i mindre format så det er en diskret brand-signatur.
st.markdown(
    """
    <div class="pax-wordmark">
        <span class="pax-wordmark-j">j</span><span class="pax-wordmark-rest">uriitech</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------- HJÆLPER: Tilføj nye filer til en eksisterende sag ----------
def _tilfoej_nye_filer_til_sag(nye_filer):
    """ADDS nye filer til den eksisterende aktuelle sag, uden at
    erstatte de allerede scannede filer. Bruges når brugeren i active
    state uploader yderligere bilag og klikker 'Tilføj filer'.
    """
    if not nye_filer:
        return

    aktuel = st.session_state.get("aktuel_sag") or {"filer": []}
    eksisterende_filnavne = {
        f.get("filnavn") for f in (aktuel.get("filer") or [])
    }
    # Filtrer fra: filer der allerede er i sagen
    rene_nye = [
        f for f in nye_filer if f.name not in eksisterende_filnavne
    ]
    if not rene_nye:
        st.toast("Disse filer er allerede i sagen.")
        return

    with st.spinner(f"Læser {len(rene_nye)} nye filer..."):
        ny_data = laes_sag_fra_filer(rene_nye)
        nye_dicts = ny_data.get("filer", []) if ny_data else []

        # Append til eksisterende sag
        kombinerede_filer = list(aktuel.get("filer") or []) + nye_dicts
        st.session_state.aktuel_sag = {
            **aktuel,
            "filer": kombinerede_filer,
        }

        # Opdater scannet-signatur så førstevurdering re-trigges
        ny_signatur = tuple(sorted(
            (f["filnavn"], len(f.get("tekst") or ""))
            for f in kombinerede_filer
        ))
        st.session_state.sidste_sagsfil_signatur = ny_signatur

        # Auto-gem nye filer i databasen
        for fil in nye_dicts:
            if sag_findes(fil["filnavn"]):
                continue
            if fil["type"] == "tekst" and fil.get("tekst", "").strip():
                emb = embed_dokument(fil["tekst"])
                gem_sag_i_db(
                    fil["filnavn"], fil["tekst"],
                    dokumenttype="klage", embedding=emb,
                )
            else:
                gem_sag_i_db(
                    fil["filnavn"],
                    f"[Scannet sagsbilag — analyseres via vision. "
                    f"Filnavn: {fil['filnavn']}]",
                    dokumenttype="klage",
                )

        st.toast(f"{len(nye_dicts)} nye filer tilføjet til sagen.")

    st.rerun()


# ---------- HJÆLPER: Scan og gem filer ----------
# Defineres her så både empty-state-knappen (inde i _kol_upload) og
# active-state-knappen (efter columns) kan kalde samme logik uden
# kode-duplikation.
def _udfor_scan_filer_og_gem(uploadede_filer, ny_signatur):
    """Læs uploadede filer, gem i database, opdatér session state.
    Kaldes når brugeren trykker Scan filer / Opdatér filer."""
    with st.spinner(f"Læser {len(uploadede_filer)} filer..."):
        sag_data = laes_sag_fra_filer(uploadede_filer)
        st.session_state.aktuel_sag = sag_data
        st.session_state.sidste_sagsfil_signatur = ny_signatur
        st.session_state.sidste_klage_filnavn = None  # reset legacy

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
                    f"[Scannet sagsbilag — analyseres via vision. "
                    f"Filnavn: {fil['filnavn']}]",
                    dokumenttype="klage",
                )
            gemt_nu.append(fil["filnavn"])

        if gemt_nu:
            st.toast(
                f"{len(gemt_nu)} nye filer tilføjet til vidensbanken."
            )
        if sprunget_over:
            # Vigtig nuance: filerne SCANNES og ANALYSERES — vi springer
            # bare den dobbelte DB-gem-handling over for at undgå
            # dubletter i søge-arkivet.
            st.toast(
                f"{len(sprunget_over)} filer findes allerede i "
                "vidensbanken — alle filer indgår dog i analysen."
            )

    # Force rerun straks efter scan så hero-sektionen forsvinder og UI'et
    # skifter rent over i active state — uden den "transitions-flicker"
    # hvor hero + grøn bar + loading vises samtidigt.
    st.rerun()


# Empty state: stor hero-sektion med Apple Health-lavendel-baggrund
_har_aktiv_sag = bool(st.session_state.get("aktuel_sag"))

if not _har_aktiv_sag:
    # Side-by-side: hero til venstre, upload-widget til højre.
    # På smalle skærme stakkes de automatisk af Streamlit.
    _kol_hero, _kol_upload = st.columns([1, 1], gap="medium")

    with _kol_hero:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg, #EEEAFF 0%, #F4F1FF 100%);
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
                    Analysér en sag fra <span style="color: #4F46E5;">Pakkerejse-Ankenævnet</span>
                </h1>
                <p style="
                    font-family: 'Inter', sans-serif;
                    font-size: 0.95rem;
                    line-height: 1.45;
                    color: #4B5563;
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
            type=["zip", "pdf", "docx", "png", "jpg", "jpeg", "mp4"],
            accept_multiple_files=True,
            key="sag_uploader",
            help=(
                "Understøtter ZIP, PDF, Word, billeder (PNG/JPG) og MP4. "
                "MP4 læses ikke af juriitech PAX, men sagen analyseres "
                "fortsat på basis af de øvrige filer. Flere filer kan "
                "vælges samtidigt."
            ),
        )

        # Scan-knappen placeres direkte i upload-kolonnen så den sidder
        # umiddelbart under upload-feltet — flugtende med hero-boksen
        # til venstre. Knappen vises kun når der er nye/ændrede filer.
        _aktuel_sig_inline = tuple(sorted(
            (f.name, f.size) for f in uploadede_sagsfiler or []
        ))
        _sidste_sig_inline = st.session_state.get(
            "sidste_sagsfil_signatur"
        )
        if (
            uploadede_sagsfiler
            and _aktuel_sig_inline != _sidste_sig_inline
        ):
            _knap_tekst_inline = (
                "Opdatér filer"
                if _sidste_sig_inline is not None
                else "Scan filer"
            )
            if st.button(
                _knap_tekst_inline,
                type="primary",
                use_container_width=True,
                key="scan_filer_btn_inline",
                help=(
                    "Klik når du er klar — først da læses filerne og "
                    "analysen starter. Du kan uploade flere filer først."
                ),
            ):
                _udfor_scan_filer_og_gem(
                    uploadede_sagsfiler, _aktuel_sig_inline
                )
else:
    # Active state: brug en SEPARAT file_uploader med eget key.
    # Tidligere genbrugte vi 'sag_uploader' fra empty state, men det
    # gav state-konflikter når brugeren klikkede X — siden scrollede
    # til toppen og virkede broken. Med eget key er state isoleret:
    # X-klik fjerner kun fra DENNE uploader, ikke fra den scannede sag.
    # Scannede filer styres separat via 'Ryd sag' eller via at uploade
    # flere og klikke 'Opdatér filer'.
    st.markdown(
        "<div style='margin-top: 8px; color: #6B7280; font-size: 0.88rem;'>"
        "Vil du tilføje flere sagsfiler til den aktuelle sag? "
        "Upload dem her — klik derefter 'Opdatér filer'. For at fjerne "
        "scannede filer eller starte forfra, brug 'Ryd sag' nedenfor."
        "</div>",
        unsafe_allow_html=True,
    )
    uploadede_sagsfiler = st.file_uploader(
        "Tilføj flere sagsfiler",
        type=["zip", "pdf", "docx", "png", "jpg", "jpeg", "mp4"],
        accept_multiple_files=True,
        key="sag_uploader_active",  # SEPARAT key fra empty state
        label_visibility="collapsed",
    )

# Beregn upload-signatur for at detektere om der er nye/ændrede filer.
# I empty state bruges denne signatur til at trigge "Scan filer"-knappen.
# I active state bruges separat logik nedenfor til at "Tilføje filer".
_aktuel_sagsfiler_signatur = tuple(sorted(
    (f.name, f.size) for f in uploadede_sagsfiler or []
))
_sidste_scannet_signatur = st.session_state.get("sidste_sagsfil_signatur")
_har_uskannede_aendringer = (
    bool(uploadede_sagsfiler)
    and _aktuel_sagsfiler_signatur != _sidste_scannet_signatur
)
_har_scannet_filer_foer = _sidste_scannet_signatur is not None

# I active state — vis "Tilføj filer"-knap når der er nye filer i den
# separate uploader (sag_uploader_active) der IKKE allerede er i sagen.
# Vi sammenligner mod aktuel_sag.filer i stedet for sidste_signatur, så
# X-klik på en ALLEREDE-scannet fil ikke fejlagtigt udløser noget.
if _har_aktiv_sag and uploadede_sagsfiler:
    _eksisterende_filnavne = {
        f.get("filnavn")
        for f in (st.session_state.aktuel_sag.get("filer") or [])
    }
    _nye_kun = [
        f for f in uploadede_sagsfiler
        if f.name not in _eksisterende_filnavne
    ]
    if _nye_kun:
        _btn_kol, _spacer_kol = st.columns([1.3, 3])
        with _btn_kol:
            if st.button(
                f"Tilføj {len(_nye_kun)} nye filer",
                type="primary",
                use_container_width=True,
                key="tilfoej_nye_filer_btn",
                help=(
                    "Tilføj de nye filer til den eksisterende sag. "
                    "Allerede scannede filer bevares."
                ),
            ):
                _tilfoej_nye_filer_til_sag(_nye_kun)

# Knap til at rydde sagen
if st.session_state.get("aktuel_sag"):
    sag = st.session_state.aktuel_sag
    filer = sag.get("filer") or []
    antal_tekst = sum(1 for f in filer if f["type"] == "tekst")
    antal_scannet = sum(1 for f in filer if f["type"] == "pdf_bytes")

    # Lille mellemrum så success-baren aldrig klistrer op mod hero-sektion
    # eller upload-feltet ovenfor — også hvis Streamlit ikke når at rerunne
    # før success-baren rendres.
    st.markdown("<div style='height: 12px'></div>", unsafe_allow_html=True)

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
            st.session_state.sagsresume = None
            st.session_state.chat_historik = []
            st.session_state.anon_resultater_per_fil = {}
            # Ryd alle sag-specifikke svarbrev-instrukser fra session state
            # så de ikke siver med til en ny sag.
            for _key in list(st.session_state.keys()):
                if (
                    _key.startswith("svarbrev_instrukser_")
                    or _key.startswith("ny_instruks_input_")
                    or _key.startswith("tilfoej_btn_")
                    or _key.startswith("fjern_instruks_")
                ):
                    del st.session_state[_key]
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
        with thinking(
            "juriitech PAX laver en grundig første vurdering af sagen",
            faser=[
                "Identificerer alle klagepunkter klager rejser...",
                "Kortlægger tidsforhold mellem mangler og reklamation...",
                "Læser sagsakterne og høringsbrevet...",
                "Søger i vidensbanken efter tidligere afgørelser...",
                "Sammenholder med pakkerejseloven og rejsevilkårene...",
                "Identificerer de stærkeste forsvarsargumenter...",
                "Vurderer sandsynligheder for de tre udfald...",
                "Skriver konklusion og strategi...",
            ],
        ):
            try:
                # FØRST: Udtræk udtømmende liste over ALLE klagepunkter
                # i en dedikeret AI-kald. Listen bruges som autoritativ
                # 'source of truth' i alle downstream-prompts (resume,
                # førstevurdering, svarbrev) — så ingen klagepunkter
                # overses. Dette er kritisk for kvaliteten af outputtet.
                alle_klagepunkter = udled_alle_klagepunkter(
                    sag=st.session_state.aktuel_sag,
                    sagsakter_tekst=st.session_state.get("sagsakter", ""),
                )
                st.session_state.alle_klagepunkter = alle_klagepunkter

                # OG SAMTIDIG: Udtræk tidsforhold mellem konstatering af
                # mangler og kontakt til TUI. Pakkerejse-Ankenævnet
                # vægter rettidig reklamation MEGET HØJT — det er ofte
                # afgørende. Vi udtrækker det som dedikeret strukturet
                # data så det aldrig overses i analysen eller svarbrevet.
                tidsforhold = udled_tidsforhold(
                    sag=st.session_state.aktuel_sag,
                    sagsakter_tekst=st.session_state.get("sagsakter", ""),
                )
                st.session_state.tidsforhold = tidsforhold

                # Byg klagepunkter-blok der injiceres i førstevurderings-
                # prompten så AI'en bruger den verificerede liste.
                # KRITISK: Listen skal vises som BULLETS i én sektion
                # ('Klagens kernepunkter'), IKKE som separate top-level
                # sektioner. Tidligere bug: AI'en lavede 17+ pillars
                # i stedet for at samle bullets under én overskrift.
                if alle_klagepunkter:
                    klagepunkter_facit = (
                        "VERIFICERET LISTE OVER ALLE KLAGEPUNKTER "
                        "(udtrukket separat):\n"
                    )
                    for _i, _kp in enumerate(alle_klagepunkter, 1):
                        klagepunkter_facit += f"  {_i}. {_kp}\n"
                    klagepunkter_facit += (
                        f"\nTotal: {len(alle_klagepunkter)} klagepunkter.\n\n"
                        "FORMAT-KRITISK INSTRUKTION:\n"
                        "Disse klagepunkter skal listes som BULLETS "
                        "(- punkt 1\\n- punkt 2 osv.) under ÉN sektion "
                        "med titlen '**2. Klagens kernepunkter**'. De "
                        "må ABSOLUT IKKE blive separate nummererede "
                        "top-level sektioner i analysen — det ville "
                        "ødelægge layoutet med 10-20 mini-pillars i "
                        "stedet for de 5 hoved-pillars. Brug ÉN sektion, "
                        "MANGE bullets.\n\n"
                    )
                else:
                    klagepunkter_facit = ""

                # Byg tidsforhold-blok hvis vi har en problematisk
                # forsinkelse — så bliver det IKKE blot nævnt, men
                # fremhævet eksplicit som forsvarsargument
                tidsforhold_facit = ""
                if (
                    tidsforhold
                    and tidsforhold.get("har_problematisk_forsinkelse")
                    and not tidsforhold.get("kunne_ikke_udledes")
                ):
                    tidsforhold_facit = (
                        "VERIFICERET TIDSFORHOLD — REKLAMATIONSRETTIDIGHED "
                        "(udtrukket separat — SKAL fremhæves i analysen):\n"
                        "Pakkerejse-Ankenævnet vægter rettidig "
                        "reklamation MEGET HØJT. Følgende er udledt:\n\n"
                    )
                    if tidsforhold.get("samlet_vurdering"):
                        tidsforhold_facit += (
                            f"  Samlet vurdering: "
                            f"{tidsforhold['samlet_vurdering']}\n\n"
                        )
                    for _obs in tidsforhold.get(
                        "konkrete_observationer", []
                    ):
                        tidsforhold_facit += f"  • {_obs}\n"
                    tidsforhold_facit += (
                        "\nDette tidsforhold udgør et VIGTIGT forsvars-"
                        "argument for TUI og SKAL adresseres i analysen "
                        "— enten som eget afsnit eller integreret i den "
                        "juridiske vurdering. Brug konkrete datoer.\n\n"
                    )

                auto_svar, rel_sager = spoerg_ai_med_sag(
                    spoergsmaal=(
                        klagepunkter_facit +
                        tidsforhold_facit +
                        "Lav en struktureret juridisk førstevurdering af sagen "
                        "baseret på de uploadede dokumenter.\n\n"
                        "═══════════════════════════════════════════════════\n"
                        "ABSOLUT KRAV TIL STRUKTUR — PRÆCIS 5 SEKTIONER:\n"
                        "═══════════════════════════════════════════════════\n"
                        "Output SKAL bestå af PRÆCIS 5 top-level sektioner — "
                        "hverken flere eller færre. Hver sektion skal starte "
                        "med en linje på formen '**N. Titel**' (med blank "
                        "linje før — splitter detekterer sektioner sådan).\n\n"
                        "INDE I HVER SEKTION må der gerne være underpunkter "
                        "som bullets (-) eller nummereret liste (1. 2. 3.) "
                        "— men disse må IKKE have blank linje før, så de "
                        "ikke fejlagtigt opfattes som nye top-level sektioner.\n\n"
                        "ALLE klagepunkter (uanset hvor mange) går som "
                        "BULLETS inde i sektion 2 — IKKE som egne sektioner.\n\n"
                        "═══════════════════════════════════════════════════\n"
                        "DE 5 SEKTIONER (følg rækkefølgen præcist):\n"
                        "═══════════════════════════════════════════════════\n\n"
                        "1. **Kort resume af sagen** (2-4 sætninger)\n"
                        "2. **Klagens kernepunkter** — KRITISK FORMAT: "
                        "Listed ALLE klagepunkter (fra den verificerede "
                        "liste ovenfor) som bullets med '-' foran hver. "
                        "Det skal være ÉN sektion med MANGE bullets, "
                        "IKKE mange sektioner. Eksempel-format:\n"
                        "   - Klagepunkt 1: kort beskrivelse\n"
                        "   - Klagepunkt 2: kort beskrivelse\n"
                        "   - osv.\n"
                        "Alle klagepunkter klager rejser mod TUI skal med "
                        "— uden undtagelse. Læs hele klagen igennem TO "
                        "GANGE og kryds hvert klagepunkt af, før du "
                        "skriver. Hvis klager nævner 8 problemer, listes "
                        "8 bullets. Hvis 17, listes 17 bullets — men "
                        "stadig som bullets i ÉN sektion, ikke 17 "
                        "sektioner. Eksempler på ting der ofte overses: "
                        "kommunikations-problemer med guiden, manglende "
                        "informationer, små afgivelser fra det aftalte, "
                        "ventetider, sløvhed i kompensation, tone i "
                        "korrespondance osv.\n"
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
                        "'Lavt grundlag' hvis et estimat er særligt usikkert.\n\n"
                        "═══════════════════════════════════════════════════\n"
                        "OVERSKRIFTER ER FASTLÅSTE — INGEN OMSKRIVNING\n"
                        "═══════════════════════════════════════════════════\n"
                        "Du SKAL bruge PRÆCIS disse 5 overskrifter, i denne "
                        "rækkefølge, ord-for-ord (kun nummer + titel "
                        "som vist — ingen omskrivninger, ingen synonymer, "
                        "ingen tilføjede ord):\n\n"
                        "  1. **Kort resume af sagen**\n"
                        "  2. **Klagens kernepunkter**\n"
                        "  3. **Rejseselskabets stillingtagen indtil nu**\n"
                        "  4. **Kort juridisk vurdering**\n"
                        "  5. **Sandsynlighedsvurdering**\n\n"
                        "FORBUDTE alternativer (eksempler — opfind ALDRIG "
                        "egne titler):\n"
                        "  ✗ 'Sagsfremstilling' (skal være 'Kort resume af sagen')\n"
                        "  ✗ 'Resumé' eller 'Resumé af klagen' (skal være "
                        "'Kort resume af sagen')\n"
                        "  ✗ 'Klagepunkter' eller 'Klagers påstande' "
                        "(skal være 'Klagens kernepunkter')\n"
                        "  ✗ 'TUI's håndtering' eller 'Rejseselskabets "
                        "håndtering' (skal være 'Rejseselskabets "
                        "stillingtagen indtil nu')\n"
                        "  ✗ 'Juridisk analyse' eller 'Juridisk vurdering' "
                        "uden 'Kort' (skal være 'Kort juridisk vurdering')\n"
                        "  ✗ 'Konklusion', 'Vurdering', 'Anbefaling' "
                        "(skal være 'Sandsynlighedsvurdering')\n"
                        "  ✗ Ekstra sektioner som 'Anbefalinger', "
                        "'Næste skridt', 'Bemærkninger', 'Kildehenvisninger' "
                        "som top-level — disse må KUN optræde som "
                        "underpunkter eller bullets inde i en af de 5 "
                        "fastlåste sektioner.\n\n"
                        "Hvis du fristes til at omdøbe en overskrift fordi "
                        "den 'passer bedre' til sagen — LAD VÆRE. "
                        "Skabelonen er fast. Indholdet tilpasses sagen — "
                        "overskrifterne gør ikke."
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

                # Generér struktureret resume af sagen — lynoverblik der vises
                # umiddelbart efter førstevurderingen så juristen hurtigt
                # fanger sagens essens.
                with st.spinner("Sammenfatter sagens essens..."):
                    _resume = udled_sagsresume_strukturelt(
                        analyse_tekst=auto_svar,
                        sagsakter_tekst=st.session_state.get("sagsakter", ""),
                    )
                st.session_state.sagsresume = _resume

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
                vis_brugerfejl(
                    "den automatiske førstevurdering",
                    exception=e,
                    kort_ekstra=(
                        "Sagen er stadig uploadet — du kan trykke 'Ryd sag' "
                        "og prøve at uploade igen, eller vente et øjeblik "
                        "og refreshe siden."
                    ),
                )

    # Vis dashboard + selve teksten hvis vi har en førstevurdering
    if st.session_state.auto_vurdering_tekst:
        st.markdown("### Førstevurdering af sagen")

        # ---------- ADVARSLER OM FILER DER IKKE ER LÆST ----------
        # To kategorier:
        #   1) MP4-videoer — understøttede, men læses ikke (skal gennemses manuelt)
        #   2) Filer i ikke-understøttede formater, korrupte PDF'er, tomme
        #      DOCX'er osv. — markeret som 'fil_ikke_laest' i processor
        # I begge tilfælde er førstevurderingen lavet ud fra resten af
        # filerne. Vi gør det tydeligt for brugeren hvilke filer der
        # ikke indgår — og hvorfor.
        _sag_filer = (st.session_state.aktuel_sag or {}).get("filer") or []
        _sagsakter_filer = st.session_state.get("sagsakter_filer") or []
        _alle_filer = _sag_filer + _sagsakter_filer

        _mp4_filer = [
            f.get("filnavn", "ukendt.mp4")
            for f in _alle_filer
            if f.get("type") == "mp4_skipped"
        ]
        _ulaeselige_filer = [
            (f.get("filnavn", "ukendt"), f.get("aarsag", "kunne ikke læses"))
            for f in _alle_filer
            if f.get("type") == "fil_ikke_laest"
        ]

        if _mp4_filer:
            _mp4_liste = ", ".join(f"<code>{navn}</code>" for navn in _mp4_filer)
            st.markdown(
                f"""
                <div style="
                    background-color: #FEF3C7;
                    color: #92400E;
                    padding: 12px 16px;
                    border-radius: 8px;
                    margin-bottom: 10px;
                    border-left: 4px solid #F59E0B;
                    font-size: 0.92rem;
                ">
                    <strong>Bemærk — video-filer ikke analyseret:</strong>
                    juriitech PAX læser ikke MP4-filer. Følgende fil(er) skal
                    gennemses manuelt som supplement til analysen nedenfor:
                    {_mp4_liste}.
                </div>
                """,
                unsafe_allow_html=True,
            )

        if _ulaeselige_filer:
            _liste_html = "".join(
                f"<li><code>{navn}</code> — "
                f"<span style='opacity:0.85;'>{aarsag}</span></li>"
                for navn, aarsag in _ulaeselige_filer
            )
            st.markdown(
                f"""
                <div style="
                    background-color: #FEF3C7;
                    color: #92400E;
                    padding: 12px 16px 10px 16px;
                    border-radius: 8px;
                    margin-bottom: 16px;
                    border-left: 4px solid #F59E0B;
                    font-size: 0.92rem;
                ">
                    <strong>Bemærk — filer der ikke kunne læses:</strong>
                    juriitech PAX kunne ikke læse følgende fil(er), og de
                    indgår derfor ikke i analysen nedenfor. Førstevurderingen
                    er lavet ud fra de øvrige filer, tidligere afgørelser og
                    pakkerejselovgivningen.
                    <ul style="margin: 6px 0 0 0; padding-left: 20px;">
                        {_liste_html}
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

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

        # ---------- KONSEKUTIV SEKTION-NUMMERERING ----------
        # Hver pillar på siden får et fortløbende nummer (1, 2, 3, ...)
        # uanset om de renderes via render_sagsresume, inline markdown
        # eller render_analyse_som_pillars. Vi sporer tælleren her og
        # passerer det til hver render-funktion.
        _pillar_nummer = 1

        # ---------- RESUME AF SAGEN — ALTID sektion 1 efter dashboardet ----------
        # KRITISK: Resume SKAL altid vises som sektion 1. Hvis det
        # strukturerede resume af en eller anden grund mangler (fx fordi
        # AI-kaldet fejlede), viser vi en fallback-pillar med et kort
        # uddrag fra førstevurderingen — så juristen aldrig oplever en
        # tom plads hvor sektion 1 burde være.
        _har_struktureret_resume = bool(st.session_state.get("sagsresume"))
        if _har_struktureret_resume:
            render_sagsresume(
                st.session_state.sagsresume,
                accent="#00D4C2",
                bg="#FDE9EE",
                nummer=_pillar_nummer,
            )
        else:
            # Fallback: ekstrahér første afsnit fra førstevurderingen
            # som simpelt resume så pillaren altid er der.
            import html as _html_res
            _vurd_tekst = (
                st.session_state.get("auto_vurdering_tekst") or ""
            )
            # Find første "indholds"-paragraf (skip overskrifter)
            _resume_fallback = ""
            for _para in _vurd_tekst.split("\n\n"):
                _stripped = _para.strip()
                if (
                    _stripped
                    and not _stripped.startswith(("#", "*", "-", "1.", "2."))
                    and len(_stripped) > 80
                ):
                    _resume_fallback = _stripped[:600]
                    if len(_stripped) > 600:
                        _resume_fallback += "…"
                    break
            if not _resume_fallback:
                _resume_fallback = (
                    "Et struktureret resume af sagen kunne ikke "
                    "udledes automatisk. Kig i førstevurderingen "
                    "nedenfor for sagens detaljer."
                )
            st.markdown(
                f'<div class="analyse-pillar"'
                ' style="--pillar-bg: #FDE9EE; '
                '--pillar-accent: #00D4C2;">'
                '<div class="analyse-pillar-accent-dot"></div>'
                f'<h2 class="analyse-pillar-title">{_pillar_nummer}. '
                'Resume af sagen</h2>'
                '<div class="analyse-pillar-body">'
                f'<p>{_html_res.escape(_resume_fallback)}</p>'
                '</div></div>',
                unsafe_allow_html=True,
            )
        _pillar_nummer += 1

        # ---------- TIDSFORHOLD — ALTID sektion 2 (rettidig reklamation) ----------
        # Pakkerejse-Ankenævnet vægter rettidig reklamation MEGET HØJT,
        # så denne sektion vises ALTID som sektion 2 — uanset om vi har
        # detekteret en problematisk forsinkelse eller ej. Indholdet
        # tilpasses status: tidslinje hvis observationer findes, gul
        # advarsel hvis problematisk forsinkelse, eller neutral 'ingen
        # bekymringer'-besked hvis tidsforhold er rene.
        _tf = st.session_state.get("tidsforhold")

        import html as _html_tf
        import re as _re_tf

        # Beslut tilstand for tidsforholds-pillaren
        _tf_begivenheder = (_tf or {}).get("begivenheder") or []
        _tf_har_observationer = bool(
            _tf and (
                _tf.get("konkrete_observationer")
                or _tf_begivenheder
            )
        )
        _tf_problematisk = bool(
            _tf
            and _tf.get("har_problematisk_forsinkelse")
            and not _tf.get("kunne_ikke_udledes")
        )
        _tf_kunne_ikke = bool(_tf and _tf.get("kunne_ikke_udledes"))

        # Vælg farvepalet baseret på alvorlighed
        if _tf_problematisk:
            _tf_bg = "#FEF3C7"      # gul (advarsel)
            _tf_accent = "#D97706"  # orange
            _tf_intro_html = (
                '<p style="font-weight: 600; color: #92400E;">'
                'Pakkerejse-Ankenævnet vægter rettidig reklamation '
                'højt. juriitech PAX har identificeret følgende '
                'relevante tidsforhold der bør indgå som '
                'forsvarsargument:</p>'
            )
        elif _tf_har_observationer:
            _tf_bg = "#E5F0FD"      # lyseblå (informativt)
            _tf_accent = "#007AFF"  # blå
            _tf_intro_html = (
                '<p style="font-weight: 500; color: #1E40AF;">'
                'Pakkerejse-Ankenævnet vægter rettidig reklamation højt. '
                'Følgende tidsforhold er identificeret i sagen:</p>'
            )
        else:
            _tf_bg = "#F3F4F6"      # grå (intet at se her)
            _tf_accent = "#9CA3AF"  # grå
            _tf_intro_html = ""

        # Byg observationer som tidslinje (hvis nogen).
        #
        # Ny layout (efter feedback fra Mikkels kollega): datoen står i
        # en venstre-kolonne (130px) inden selve teksten, så man hurtigt
        # kan scanne hvad der er sket hvornår. Begivenheder EFTER
        # hjemkomst dæmpes visuelt (lavere opacity, gråtoner) fordi
        # tidsforløbet PÅ DESTINATIONEN er det vigtigste juridisk —
        # alt efter "afgang"-typen er sekundært men må gerne være med.
        #
        # Hvis vi har struktureret 'begivenheder'-array fra
        # udled_tidsforhold bruges det som primær kilde. Ellers falder vi
        # tilbage til parsing af 'konkrete_observationer' (fri tekst).
        _tf_observationer_html = ""

        # Hjælpefunktion: marker datoer/tidspunkter med <strong> i fri tekst
        _date_pattern = _re_tf.compile(
            r'(\d{1,2}\.?\s*(?:januar|februar|marts|april|'
            r'maj|juni|juli|august|september|oktober|'
            r'november|december)(?:\s+\d{4})?)',
            _re_tf.IGNORECASE,
        )

        if _tf_begivenheder:
            # ---- STRUKTURERET TIDSLINJE (foretrukken vej) ----
            # Find index for "afgang" — alt derefter er post-hjemkomst og
            # vises dæmpet.
            _afgang_idx = None
            for _i, _b in enumerate(_tf_begivenheder):
                if (_b.get("type") or "").strip().lower() == "afgang":
                    _afgang_idx = _i
                    break

            _items_html = []
            for _i, _b in enumerate(_tf_begivenheder):
                _dato = _html_tf.escape(_b.get("dato") or "")
                _tidspunkt = _html_tf.escape(_b.get("tidspunkt") or "")
                _aktoer = _html_tf.escape(_b.get("aktoer") or "")
                _besk = _html_tf.escape(_b.get("beskrivelse") or "")
                _bet = (_b.get("betydning") or "neutral").lower()
                _typ = (_b.get("type") or "").strip().lower()

                # Farve på dot ud fra juridisk betydning for TUI
                if _bet == "negativ_for_tui":
                    _dot_color = "#DC2626"
                    _dot_glow = "rgba(220, 38, 38, 0.25)"
                elif _bet == "positiv_for_tui":
                    _dot_color = "#16A34A"
                    _dot_glow = "rgba(22, 163, 74, 0.25)"
                else:
                    _dot_color = "#6B7280"
                    _dot_glow = "rgba(107, 114, 128, 0.2)"

                # Er denne begivenhed efter hjemkomst?
                _efter_hjem = (
                    _afgang_idx is not None and _i > _afgang_idx
                )
                _eh_klasse = " efter-hjemkomst" if _efter_hjem else ""

                # Fase-label (lille uppercase tekst over datoen) hjælper
                # med hurtig orientering — fx "PÅ DESTINATION" eller
                # "EFTER HJEMKOMST"
                if _typ == "ankomst":
                    _fase_label = "Ankomst"
                elif _typ == "afgang":
                    _fase_label = "Hjemrejse"
                elif _efter_hjem:
                    _fase_label = "Efter hjemkomst"
                else:
                    _fase_label = "På destination"

                # Dim posten endnu mere hvis efter hjemkomst (mindre
                # punktstørrelse på dot)
                _dot_size_style = (
                    "width: 11px; height: 11px; top: 14px; "
                    "opacity: 0.55;"
                    if _efter_hjem else ""
                )

                _tid_html = (
                    f'<span class="tf-tidslinje-tid">{_tidspunkt}</span>'
                    if _tidspunkt else ""
                )

                _aktoer_html = (
                    f'<strong>{_aktoer}:</strong> ' if _aktoer else ""
                )

                _items_html.append(
                    '<div class="tf-tidslinje-item">'
                    '<div class="tf-tidslinje-dato-kolonne">'
                    f'<span class="tf-tidslinje-dato{_eh_klasse}">'
                    f'{_dato}</span>'
                    f'{_tid_html}'
                    f'<span class="tf-tidslinje-fase{_eh_klasse}">'
                    f'{_fase_label}</span>'
                    '</div>'
                    f'<div class="tf-tidslinje-dot" '
                    f'style="background: {_dot_color}; '
                    f'box-shadow: 0 0 0 4px {_dot_glow};'
                    f'{_dot_size_style}"></div>'
                    f'<div class="tf-tidslinje-tekst{_eh_klasse}">'
                    f'{_aktoer_html}{_besk}'
                    '</div>'
                    '</div>'
                )

            _tf_observationer_html = (
                '<div class="tf-tidslinje">'
                + "".join(_items_html)
                + '</div>'
            )

        elif _tf and _tf.get("konkrete_observationer"):
            # ---- FALLBACK: parse fri tekst hvis begivenheder mangler ----
            _items_html = []
            for _obs in _tf["konkrete_observationer"]:
                _obs_lower = _obs.lower()
                if any(w in _obs_lower for w in (
                    "for sen", "forsinket", "efter hjemkomst",
                    "ikke rettidig", "for sent",
                )):
                    _dot_color = "#DC2626"
                    _dot_glow = "rgba(220, 38, 38, 0.25)"
                elif any(w in _obs_lower for w in (
                    "rettidig", "samme dag", "umiddelbart",
                )):
                    _dot_color = "#16A34A"
                    _dot_glow = "rgba(22, 163, 74, 0.25)"
                else:
                    _dot_color = "#6B7280"
                    _dot_glow = "rgba(107, 114, 128, 0.2)"

                # Forsøg at trække den FØRSTE dato ud i venstre kolonne
                _obs_safe = _html_tf.escape(_obs)
                _match = _date_pattern.search(_obs_safe)
                if _match:
                    _dato_kolonne = _match.group(1)
                    # Fjern datoen fra teksten (kun første forekomst) —
                    # ellers står den dobbelt
                    _resttekst = (
                        _obs_safe[:_match.start()]
                        + _obs_safe[_match.end():]
                    ).strip(" ,–-")
                    _resttekst = _date_pattern.sub(
                        r'<strong>\1</strong>', _resttekst
                    )
                else:
                    _dato_kolonne = ""
                    _resttekst = _date_pattern.sub(
                        r'<strong>\1</strong>', _obs_safe
                    )

                _eh = "efter hjemkomst" in _obs_lower
                _eh_klasse = " efter-hjemkomst" if _eh else ""

                if _dato_kolonne:
                    _venstre_html = (
                        f'<span class="tf-tidslinje-dato{_eh_klasse}">'
                        f'{_dato_kolonne}</span>'
                    )
                else:
                    _venstre_html = (
                        '<span class="tf-tidslinje-dato-ukendt">'
                        'Dato ukendt</span>'
                    )

                _items_html.append(
                    '<div class="tf-tidslinje-item">'
                    '<div class="tf-tidslinje-dato-kolonne">'
                    f'{_venstre_html}'
                    '</div>'
                    f'<div class="tf-tidslinje-dot" '
                    f'style="background: {_dot_color}; '
                    f'box-shadow: 0 0 0 4px {_dot_glow};"></div>'
                    f'<div class="tf-tidslinje-tekst{_eh_klasse}">'
                    f'{_resttekst}'
                    '</div>'
                    '</div>'
                )

            _tf_observationer_html = (
                '<div class="tf-tidslinje">'
                + "".join(_items_html)
                + '</div>'
            )

        # Lille "Rejseperiode"-chip øverst, så man hurtigt ser hvilke
        # datoer destinationen dækker (gør timing-vurderingen lettere).
        _rejseperiode = (_tf or {}).get("rejseperiode") or ""
        _rejseperiode_html = ""
        if _rejseperiode and _tf_har_observationer:
            _rp_safe = _html_tf.escape(_rejseperiode)
            _rejseperiode_html = (
                '<div style="display: inline-flex; align-items: center; '
                'gap: 8px; padding: 6px 14px; border-radius: 100px; '
                'background: rgba(255,255,255,0.6); '
                'border: 1px solid rgba(146,64,14,0.18); '
                'font-weight: 600; color: #92400E; font-size: 0.88rem; '
                'margin: 4px 0 12px 0;">'
                '<span style="opacity:0.7;">Rejseperiode:</span>'
                f'<span>{_rp_safe}</span>'
                '</div>'
            )

        # Vælg body-tekst baseret på tilstand
        if _tf_problematisk and _tf and _tf.get("samlet_vurdering"):
            _tf_body = (
                f'<p>{_html_tf.escape(_tf.get("samlet_vurdering"))}</p>'
                f'{_rejseperiode_html}'
                f'{_tf_observationer_html}'
            )
        elif _tf_har_observationer:
            _samlet = _html_tf.escape(_tf.get("samlet_vurdering") or "")
            _tf_body = (
                (f'<p>{_samlet}</p>' if _samlet else "")
                + _rejseperiode_html
                + _tf_observationer_html
            )
        elif _tf_kunne_ikke:
            _tf_body = (
                '<p>juriitech PAX kunne ikke udlede konkrete '
                'tidsforhold (datoer for henvendelser til TUI vs '
                'konstatering af mangler) ud fra materialet. '
                'Tilføj evt. mail-korrespondance eller datoer i '
                'sagsakter for at få et tidslinje-overblik.</p>'
            )
        else:
            _tf_body = (
                '<p>Der er ikke identificeret problematiske tidsforhold '
                'i sagen — klagers reklamation virker rettidig på baggrund '
                'af det tilgængelige materiale. Tjek dog altid manuelt '
                'om der er datoer der ikke fremgår af bilagene.</p>'
            )

        st.markdown(
            f'<div class="analyse-pillar"'
            f' style="--pillar-bg: {_tf_bg}; '
            f'--pillar-accent: {_tf_accent};">'
            '<div class="analyse-pillar-accent-dot"></div>'
            f'<h2 class="analyse-pillar-title">{_pillar_nummer}. '
            'Tidsforhold og rettidig reklamation</h2>'
            '<div class="analyse-pillar-body">'
            f'{_tf_intro_html}'
            f'{_tf_body}'
            '</div></div>',
            unsafe_allow_html=True,
        )
        _pillar_nummer += 1

        # Visuelle kort for de 3-5 mest relevante tidligere sager.
        # Indrammes i en Apple Health-pillar med overskriften "Relevante
        # referencer" — det erstatter den tekstuelle referencer-pillar i
        # analysen, så vi ikke har to sektioner der viser det samme.
        rel = st.session_state.get("relevante_sager") or []
        afgoerelser_ud = [r for r in rel if (r.get("dokumenttype") or "").lower() == "afgoerelse"]
        vilkaar_ud = [r for r in rel if (r.get("dokumenttype") or "").lower() == "vilkaar"]

        # FILTRER svage matches HELT VÆK. Brugeren skal ikke spilde tid
        # på sager der ikke har juridisk relevans for den nye sag.
        # Hvis AI'en har markeret en match som juridisk_relevant_match=
        # false (kun overfladiske ligheder som destination, rejsearrangør
        # eller generisk 'mangel'), inkluderes den IKKE i visningen.
        # Hvis ingen af top-5 matches er juridisk relevante, vises
        # 'Relevante referencer'-sektionen slet ikke.
        _match_info_alle = st.session_state.get("match_info") or []
        _filtreret_afgoerelser = []
        _filtreret_match_info = []
        _relevans_per_idx = []
        for _idx, _ag in enumerate(afgoerelser_ud[:5]):
            _info = (
                _match_info_alle[_idx]
                if _idx < len(_match_info_alle)
                else {}
            )
            _er_relevant = _info.get("juridisk_relevant_match", True)
            if _er_relevant:
                _filtreret_afgoerelser.append(_ag)
                _filtreret_match_info.append(_info)
                _relevans_per_idx.append(True)
        afgoerelser_ud = _filtreret_afgoerelser

        if afgoerelser_ud:
            # Apple Health-pillar wrapper — lavendel baggrund, indigo accent
            st.markdown(
                f'<div class="analyse-pillar"'
                ' style="--pillar-bg: #EEEAFF; --pillar-accent: #6366F1;">'
                '<div class="analyse-pillar-accent-dot"></div>'
                f'<h2 class="analyse-pillar-title">{_pillar_nummer}. Relevante referencer</h2>'
                '<div class="analyse-pillar-body">'
                '<p>Disse afgørelser fra Pakkerejse-Ankenævnet minder mest om '
                'din nuværende sag. juriitech PAX bruger dem aktivt som '
                'juridisk præcedens i analysen.</p>'
                '</div></div>',
                unsafe_allow_html=True,
            )
            _pillar_nummer += 1
            from badges import udled_afgoerelsesdato, badge

            # Brug den FILTREREDE liste — kun juridisk relevante matches
            match_info_list = _filtreret_match_info

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
                            st.markdown(
                                udfald_badge_html,
                                unsafe_allow_html=True,
                            )
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

        # Juridisk førstevurdering som Apple-Health-inspirerede pillars.
        # Vi springer tre sektioner over for at undgå duplikater:
        #   - resume (vises allerede som strukturelt kort ovenfor)
        #   - referencer (vises allerede som visuelle kort ovenfor)
        #   - sandsynlighedsvurdering (vises allerede i dashboardet øverst)
        # Tilbage er den reelt nye analyse: juridisk argumentation og
        # konklusion.
        if st.session_state.auto_vurdering_tekst:
            render_analyse_som_pillars(
                st.session_state.auto_vurdering_tekst,
                skip_resume=_har_struktureret_resume,
                skip_referencer=bool(afgoerelser_ud),
                skip_sandsynlighed=True,
                # Konklusion flyttes op som 'Forventet udfald' i sagsresume-
                # kortet ovenfor — vi undgår at duplikere den her.
                skip_konklusion=_har_struktureret_resume,
                start_nummer=_pillar_nummer,
            )

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
                automatisk, så vurderingen tager højde for ny
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

# ---------- 'Stil spørgsmål til sagen'-sektionen er fjernet bevidst ----------
# Den gentog i praksis bare førstevurderingen + sagsresume og var ikke
# nødvendig for det primære flow. chat_om_sag() i ai_engine.py bevares
# til evt. fremtidig genbrug, men ingen UI kalder den længere.


# ---------- ANONYMISERINGSASSISTENT ----------
if st.session_state.get("aktuel_sag"):
    # Apple Health-inspireret sektionsintro: rose-pastel med pink accent
    st.markdown(
        """
        <div class="analyse-pillar"
             style="--pillar-bg: #FDE9EE; --pillar-accent: #EC4899;">
            <div class="analyse-pillar-accent-dot"></div>
            <h2 class="analyse-pillar-title">Anonymisér bilag til Nævnet</h2>
            <div class="analyse-pillar-body">
                <p>Vælg de bilag du ønsker at anonymisere — både sagsfiler
                og sagsakter du selv har uploadet. juriitech PAX producerer
                anonymiserede versioner efter Pakkerejse-Ankenævnets
                retningslinjer (Klager for klager, medrejsende for
                bipersoner, CPR-numre fjernes osv.).</p>
                <p>Nye sagsakter du uploader dukker automatisk op i listen
                herunder.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------- BYG SAMLET LISTE AF KANDIDAT-FILER ----------
    # Kombinér sagens hovedfiler + sagsakter i én liste. Markér kilden
    # så brugeren kan se hvad der kommer hvorfra. Filer der alligevel
    # ikke kan anonymiseres (høringsbrev, vejledninger, scannede PDF'er)
    # vises som grå/deaktiverede med forklaring.
    _sag_filer = (st.session_state.aktuel_sag or {}).get("filer") or []
    _sagsakter_filer = st.session_state.get("sagsakter_filer") or []

    _anon_kandidater = []
    for f in _sag_filer:
        _anon_kandidater.append({**f, "_kilde": "sag"})
    for f in _sagsakter_filer:
        _anon_kandidater.append({**f, "_kilde": "sagsakt"})

    def _kan_anonymiseres(fil):
        """True hvis filen kan anonymiseres tekstuelt af PAX."""
        if fil.get("rolle") in ("vejledning", "høring"):
            return False
        if fil.get("type") in ("pdf_bytes", "image_bytes", "mp4_skipped"):
            return False
        if fil.get("type") != "tekst":
            return False
        return bool((fil.get("tekst") or "").strip())

    def _hvorfor_ikke(fil):
        """Forklaring når en fil ikke kan anonymiseres automatisk."""
        if fil.get("rolle") == "vejledning":
            return "Vejledning fra Nævnet — anonymiseres ikke"
        if fil.get("rolle") == "høring":
            return "Høringsbrev fra Nævnet — skal ikke sendes tilbage"
        if fil.get("type") == "pdf_bytes":
            return "Scannet PDF — kræver OCR, gør manuelt"
        if fil.get("type") == "image_bytes":
            return "Billede — kan ikke anonymiseres tekstuelt"
        if fil.get("type") == "mp4_skipped":
            return "Video — kan ikke anonymiseres tekstuelt"
        if fil.get("type") != "tekst":
            return "Filformat understøttes ikke"
        if not (fil.get("tekst") or "").strip():
            return "Tom fil"
        return ""

    if not _anon_kandidater:
        st.info(
            "Ingen bilag at anonymisere endnu. Upload sagsfiler eller "
            "sagsakter ovenfor."
        )
    else:
        # Initialiser persistent map (filnavn → resultat) så allerede
        # anonymiserede filer overlever re-render og nye uploads.
        if "anon_resultater_per_fil" not in st.session_state:
            st.session_state.anon_resultater_per_fil = {}

        # ---------- CHECKBOX-LISTE (i form, så siden ikke scroller) ----------
        # KRITISK: vi wrapper checkboxes + submit-knap i en st.form.
        # Uden form'en re-runner Streamlit hele siden hver gang
        # brugeren klikker en checkbox — og siden scroller dermed tilbage
        # til toppen. Brugere oplever det som om "alt forsvinder", fordi
        # anonymiserings-sektionen ligger langt nede på en lang side.
        # Med form'en batch'es alle checkbox-klik, og siden re-runs kun
        # når "Anonymisér valgte" trykkes.
        with st.form("anonymisering_valg_form"):
            st.markdown("**Vælg de bilag du ønsker at anonymisere:**")

            _valgte_filnavne_inputs = {}  # filnavn → checkbox-key
            for i, fil in enumerate(_anon_kandidater):
                filnavn = fil.get("filnavn", f"fil{i}")
                kilde_label = (
                    "Sagsakt" if fil.get("_kilde") == "sagsakt" else "Sag"
                )
                rolle_label = (fil.get("rolle") or "").replace("_", " ")

                kol_cb, kol_meta, kol_status = st.columns([5, 2, 3])

                with kol_cb:
                    if _kan_anonymiseres(fil):
                        cb_key = f"anon_valg_{i}_{filnavn}"
                        st.checkbox(filnavn, key=cb_key)
                        _valgte_filnavne_inputs[filnavn] = cb_key
                    else:
                        st.markdown(
                            f"<span style='color:rgba(100,116,139,0.75);"
                            f"font-size:0.92rem;'>☐ {filnavn}</span>",
                            unsafe_allow_html=True,
                        )

                with kol_meta:
                    st.markdown(
                        f"<span style='color:rgba(100,116,139,0.8);"
                        f"font-size:0.8rem;'>{kilde_label}"
                        + (
                            f" · {rolle_label}"
                            if rolle_label and rolle_label != "ukendt"
                            else ""
                        )
                        + "</span>",
                        unsafe_allow_html=True,
                    )

                with kol_status:
                    if filnavn in st.session_state.anon_resultater_per_fil:
                        res = st.session_state.anon_resultater_per_fil[filnavn]
                        if res.get("status") == "ok":
                            st.markdown(
                                "<span style='color:#15803D;font-size:0.82rem;"
                                "font-weight:500;'>✓ Anonymiseret</span>",
                                unsafe_allow_html=True,
                            )
                        elif res.get("status") == "fejl":
                            st.markdown(
                                "<span style='color:#B91C1C;"
                                "font-size:0.82rem;'>Fejl</span>",
                                unsafe_allow_html=True,
                            )
                    elif not _kan_anonymiseres(fil):
                        st.markdown(
                            f"<span style='color:rgba(100,116,139,0.7);"
                            f"font-size:0.78rem;font-style:italic;'>"
                            f"{_hvorfor_ikke(fil)}</span>",
                            unsafe_allow_html=True,
                        )

            # Submit-knap inde i form'en — udløser anonymisering
            kol_btn1, _kol_btn2 = st.columns([2, 5])
            with kol_btn1:
                _anon_submitted = st.form_submit_button(
                    "Anonymisér valgte",
                    type="primary",
                )

        # Saml valgte filnavne baseret på session_state (sat når form
        # submittes — på det tidspunkt har Streamlit opdateret state)
        _valgte_filnavne = [
            fn for fn, key in _valgte_filnavne_inputs.items()
            if st.session_state.get(key)
        ]

        if _anon_submitted:
            if not _valgte_filnavne:
                st.warning(
                    "Vælg mindst én fil at anonymisere — sæt et flueben "
                    "før du klikker."
                )
            else:
                # Byg liste af fil-dicts der matcher filnavnene
                valgte_filer = [
                    fil for fil in _anon_kandidater
                    if fil.get("filnavn") in _valgte_filnavne
                    and _kan_anonymiseres(fil)
                ]

                with thinking(
                    f"juriitech PAX anonymiserer {len(valgte_filer)} bilag",
                    faser=[
                        "Identificerer personnavne, CPR, adresser og kontaktdata...",
                        "Erstatter klagers navn konsekvent med 'Klager'...",
                        "Maskerer booking-numre og bankoplysninger...",
                        "Bevarer hotelnavne, destinationer og rejsedatoer...",
                        "Tjekker hver fil igennem for missede oplysninger...",
                    ],
                ):
                    try:
                        nye_resultater = anonymiser_valgte_filer(valgte_filer)
                    except Exception as e:
                        vis_brugerfejl(
                            "anonymisering af bilag",
                            exception=e,
                            kort_ekstra=(
                                "De valgte bilag er stadig markeret — du "
                                "kan trygt prøve igen."
                            ),
                        )
                        nye_resultater = []

                # Flet ind i den persistente map, så tidligere resultater
                # bevares hvis de ikke er blevet genkørt nu. Vi husker
                # også HVILKE filer der lige nu blev anonymiseret, så vi
                # kan vise dem åbne (expanded=True) i resultat-sektionen
                # nedenunder — i stedet for at scrolle siden til toppen
                # via st.rerun() (som tidligere fik brugere til at tro,
                # at alt var forsvundet).
                netop_anonymiserede_filnavne = []
                for r in nye_resultater:
                    st.session_state.anon_resultater_per_fil[r["filnavn"]] = r
                    netop_anonymiserede_filnavne.append(r["filnavn"])

                # Gem flag i session state så vi i resultat-loopet kan
                # se hvilke filer der skal vises åbne
                st.session_state["_netop_anonymiserede"] = (
                    netop_anonymiserede_filnavne
                )

        # ---------- RESULTAT-BOKSE ----------
        resultater_map = st.session_state.anon_resultater_per_fil
        færdige = [r for r in resultater_map.values() if r.get("status") == "ok"]

        if færdige:
            st.markdown("---")

            # Hvis brugeren lige har anonymiseret, vis prominent
            # success-besked — i stedet for at lade dem gætte, at det
            # virkede.
            netop_anonymiserede = st.session_state.get(
                "_netop_anonymiserede", []
            )
            if netop_anonymiserede:
                st.success(
                    f"✓ {len(netop_anonymiserede)} bilag er anonymiseret. "
                    "Gennemgå indholdet nedenunder og download som Word "
                    "eller PDF når du er tilfreds."
                )

            st.markdown("**Anonymiserede bilag — klar til download:**")
            st.caption(
                "Tjek resultatet manuelt før du sender til Nævnet. "
                "AI-anonymisering er et hjælpeværktøj, ikke en garanti."
            )

            for r in færdige:
                fn_base = r["filnavn"].rsplit(".", 1)[0]
                # Åbn expanderen hvis denne fil lige blev anonymiseret —
                # så brugeren straks kan se og downloade resultatet.
                _er_netop_anonymiseret = (
                    r["filnavn"] in netop_anonymiserede
                )

                with st.expander(
                    f"✓ {r['filnavn']}  —  {r['bemaerkning']}",
                    expanded=_er_netop_anonymiseret,
                ):
                    st.text_area(
                        "Anonymiseret indhold",
                        value=r["anonymiseret_tekst"],
                        height=320,
                        key=f"anon_visning_{r['filnavn']}",
                        label_visibility="collapsed",
                    )

                    from eksport import (
                        markdown_til_docx_bytes,
                        markdown_til_pdf_bytes,
                    )

                    kol_docx, kol_pdf = st.columns(2)
                    with kol_docx:
                        try:
                            docx_bytes = markdown_til_docx_bytes(
                                r["anonymiseret_tekst"],
                                titel=f"Anonymiseret: {r['filnavn']}",
                                undertitel=(
                                    "Anonymiseret efter Pakkerejse-"
                                    "Ankenævnets retningslinjer"
                                ),
                            )
                            st.download_button(
                                label="Download som Word",
                                data=docx_bytes,
                                file_name=f"anonymiseret_{fn_base}.docx",
                                mime=(
                                    "application/vnd.openxmlformats-"
                                    "officedocument.wordprocessingml.document"
                                ),
                                key=f"anon_docx_{r['filnavn']}",
                                use_container_width=True,
                            )
                        except Exception as e:
                            st.caption(f"Word-eksport fejlede: {e}")

                    with kol_pdf:
                        try:
                            pdf_bytes = markdown_til_pdf_bytes(
                                r["anonymiseret_tekst"],
                                titel=f"Anonymiseret: {r['filnavn']}",
                                undertitel=(
                                    "Anonymiseret efter Pakkerejse-"
                                    "Ankenævnets retningslinjer"
                                ),
                            )
                            st.download_button(
                                label="Download som PDF",
                                data=pdf_bytes,
                                file_name=f"anonymiseret_{fn_base}.pdf",
                                mime="application/pdf",
                                key=f"anon_pdf_{r['filnavn']}",
                                use_container_width=True,
                            )
                        except Exception as e:
                            st.caption(f"PDF-eksport fejlede: {e}")

        # Fejlede filer vises separat i en kort linje
        fejlede = [r for r in resultater_map.values() if r.get("status") == "fejl"]
        if fejlede:
            with st.expander(f"⚠ {len(fejlede)} fil(er) fejlede", expanded=False):
                for r in fejlede:
                    st.markdown(f"- **{r['filnavn']}:** {r['bemaerkning']}")

    # ============================================================
    # BILAG-HÅNDTERING (vælg hvilke bilag der skal med + beskrivelser)
    # ============================================================
    # Lever inde i samme overordnede sektion som anonymisering, fordi
    # filerne er identiske — men UI'et lever UDENFOR formen så toggles
    # og tekstfelter reagerer øjeblikkeligt (ikke batched bag submit).
    #
    # Rækkefølgen er Nævnets konvention:
    #   - Selve svarbrevet er ALTID første bilag (typisk Bilag A)
    #   - Bogstaverne er KONTINUERLIGE på tværs af høringer:
    #     1. høring starter ved A; 2. høring starter ved næste ledige
    #     bogstav efter 1. høring osv. Brugeren angiver start-bogstav
    #     manuelt (de ved selv hvor de er kommet til).
    if _anon_kandidater:
        st.markdown("---")
        st.markdown("### Bilag til svarbrevet")
        st.caption(
            "Vælg hvilke bilag der skal medsendes svarbrevet til Nævnet. "
            "Selve svarbrevet er altid første bilag. Beskrivelserne "
            "er auto-foreslået af PAX — ret dem hvis de skal være "
            "anderledes."
        )

        # ---------- STATE-NØGLER (scopet til sag-signatur) ----------
        # Beregnes inline her — selve svarbrev-sektionen længere nede
        # bruger den samme formel, så de to sektioner deler ikke
        # nøgle-namespace utilsigtet.
        _bilag_aktiv_sag_id = (
            st.session_state.get("aktiv_gemt_sag_id") or "ny_sag"
        )
        _bilag_sag_sig = (
            st.session_state.get("sidste_sagsfil_signatur") or ()
        )
        _bilag_signatur = f"{_bilag_aktiv_sag_id}_{hash(_bilag_sag_sig)}"
        _bilag_inkl_key = f"bilag_inkluder_{_bilag_signatur}"
        _bilag_overskrift_key = f"bilag_overskrift_{_bilag_signatur}"
        _bilag_raekkefolge_key = f"bilag_raekkefolge_{_bilag_signatur}"
        _bilag_startbogstav_key = f"bilag_startbogstav_{_bilag_signatur}"
        _bilag_overskrift_cache_key = (
            f"bilag_overskrift_cache_{_bilag_signatur}"
        )

        # Initialiser state defaults én gang pr. sag
        if _bilag_inkl_key not in st.session_state:
            # Default ON for SAGSAKTER (bruger-uploadet) der IKKE er
            # vejledning/høringsbrev. Default OFF for sag-filer (klagers
            # materialer skal sjældent med som forsvarsbilag).
            _default_inkl = {}
            for f in _anon_kandidater:
                fn = f.get("filnavn") or ""
                kilde = f.get("_kilde")
                rolle = (f.get("rolle") or "").lower()
                if kilde == "sagsakt" and rolle not in ("vejledning", "høring"):
                    _default_inkl[fn] = True
                else:
                    _default_inkl[fn] = False
            st.session_state[_bilag_inkl_key] = _default_inkl

        if _bilag_raekkefolge_key not in st.session_state:
            # Default-rækkefølge = sagsakter først (i upload-rækkefølge),
            # derefter sag-filer (i sag-rækkefølge)
            _orden = []
            for f in _anon_kandidater:
                if f.get("_kilde") == "sagsakt":
                    _orden.append(f.get("filnavn"))
            for f in _anon_kandidater:
                if f.get("_kilde") != "sagsakt":
                    _orden.append(f.get("filnavn"))
            st.session_state[_bilag_raekkefolge_key] = _orden

        if _bilag_startbogstav_key not in st.session_state:
            # Default start-bogstav følger høringssvar-nummeret KUN for
            # 1. høring (= A). For 2./3. høring må brugeren selv skrive
            # det rigtige bogstav, fordi det afhænger af hvor mange
            # bilag de tidligere høringer havde — info vi ikke kender
            # før login + sagshistorik er på plads.
            st.session_state[_bilag_startbogstav_key] = "A"

        # ---------- AUTO-UDFYLD OVERSKRIFTER (lazy, cached) ----------
        # Kun filer DER ER MARKERET som bilag får auto-foreslået
        # overskrift (ellers spilder vi tokens). Når brugeren toggler
        # en ny fil ON tager vi en ny runde.
        _filer_med_inkl = [
            f for f in _anon_kandidater
            if st.session_state[_bilag_inkl_key].get(f.get("filnavn"))
        ]
        # Liste af filnavne der STADIG mangler en cached overskrift
        _cache = st.session_state.get(_bilag_overskrift_cache_key, {})
        _mangler_overskrift = [
            f for f in _filer_med_inkl
            if (f.get("filnavn") or "") not in _cache
        ]

        if _mangler_overskrift:
            with st.spinner(
                f"Foreslår overskrifter til {len(_mangler_overskrift)} bilag…"
            ):
                try:
                    _nye = udled_bilag_overskrifter(_mangler_overskrift)
                except Exception as _e:
                    print(
                        f"DEBUG: udled_bilag_overskrifter UI-kald fejlede: {_e}"
                    )
                    _nye = {
                        (f.get("filnavn") or ""): (f.get("filnavn") or "")
                        .rsplit(".", 1)[0]
                        .replace("_", " ")
                        for f in _mangler_overskrift
                    }
            _cache.update(_nye)
            st.session_state[_bilag_overskrift_cache_key] = _cache

        # Sørg for at hver inkluderet fil har en aktuel overskrift-værdi
        # (initial = cache, brugeren kan derefter overskrive)
        if _bilag_overskrift_key not in st.session_state:
            st.session_state[_bilag_overskrift_key] = {}
        for f in _filer_med_inkl:
            fn = f.get("filnavn") or ""
            if fn not in st.session_state[_bilag_overskrift_key]:
                st.session_state[_bilag_overskrift_key][fn] = (
                    _cache.get(fn) or ""
                )

        # ---------- UI: START-BOGSTAV ----------
        _kol_sb, _kol_hjelp = st.columns([1, 4])
        with _kol_sb:
            st.text_input(
                "Start-bogstav",
                key=_bilag_startbogstav_key,
                max_chars=2,
                help=(
                    "Bilagene navngives kontinuerligt på tværs af "
                    "høringer. Ved 1. høring er det A. Ved 2./3. høring "
                    "skal det være næste ledige bogstav efter forrige "
                    "hørings sidste bilag."
                ),
            )
        with _kol_hjelp:
            _sb_aktuel = (
                st.session_state.get(_bilag_startbogstav_key) or "A"
            ).strip().upper()[:1] or "A"
            st.markdown(
                f"<div style='padding-top: 28px; color: #6B7280; "
                f"font-size: 0.88rem;'>Selve svarbrevet bliver "
                f"<strong>Bilag {_sb_aktuel}</strong>.</div>",
                unsafe_allow_html=True,
            )

        # ---------- UI: PER-FIL CONTROLS ----------
        # Beregn løbende bogstav for hver inkluderet fil i den valgte
        # rækkefølge — dem viser vi som badge på hver række.
        _start_idx = ord(_sb_aktuel) - ord("A")
        _bogstav_per_filnavn = {}
        _filnavne_i_orden = [
            fn for fn in st.session_state[_bilag_raekkefolge_key]
            if st.session_state[_bilag_inkl_key].get(fn)
        ]
        # Bilag #1 er svarbrevet selv → tildelte bilag starter ved +1
        for _i, fn in enumerate(_filnavne_i_orden):
            _b_idx = _start_idx + 1 + _i
            if 0 <= _b_idx < 26:
                _bogstav_per_filnavn[fn] = chr(ord("A") + _b_idx)
            else:
                _bogstav_per_filnavn[fn] = "?"

        # Render rækkerne i den aktuelle rækkefølge — først dem der er
        # MED som bilag (med up/down-pile), derefter dem der er fra-
        # valgt (kun toggle-knap).
        _orden_aktuel = list(st.session_state[_bilag_raekkefolge_key])
        _filnavn_til_fil = {
            (f.get("filnavn") or ""): f for f in _anon_kandidater
        }
        for _idx_orden, fn in enumerate(_orden_aktuel):
            fil = _filnavn_til_fil.get(fn)
            if not fil:
                continue
            er_med = bool(st.session_state[_bilag_inkl_key].get(fn))

            (
                _kol_inkl, _kol_bogstav, _kol_overskrift,
                _kol_op, _kol_ned,
            ) = st.columns([2.0, 0.9, 5.5, 0.5, 0.5])

            with _kol_inkl:
                # Toggle: medtag denne fil som bilag?
                _ny_vaerdi = st.checkbox(
                    fn,
                    value=er_med,
                    key=f"bilag_cb_{_bilag_signatur}_{_idx_orden}_{fn}",
                )
                if _ny_vaerdi != er_med:
                    st.session_state[_bilag_inkl_key][fn] = _ny_vaerdi
                    st.rerun()

            with _kol_bogstav:
                if er_med:
                    bogstav = _bogstav_per_filnavn.get(fn, "?")
                    st.markdown(
                        f"<div style='padding-top: 6px; font-weight: 700; "
                        f"color: #92400E;'>Bilag {bogstav}</div>",
                        unsafe_allow_html=True,
                    )

            with _kol_overskrift:
                if er_med:
                    _ny_tekst = st.text_input(
                        "Beskrivelse",
                        value=st.session_state[_bilag_overskrift_key].get(
                            fn, ""
                        ),
                        key=(
                            f"bilag_tekst_{_bilag_signatur}_"
                            f"{_idx_orden}_{fn}"
                        ),
                        label_visibility="collapsed",
                        placeholder="Bilag-beskrivelse…",
                    )
                    st.session_state[_bilag_overskrift_key][fn] = _ny_tekst

            with _kol_op:
                if er_med and _idx_orden > 0:
                    if st.button(
                        "↑",
                        key=f"bilag_op_{_bilag_signatur}_{_idx_orden}_{fn}",
                        help="Flyt op",
                    ):
                        _o = st.session_state[_bilag_raekkefolge_key]
                        _o[_idx_orden - 1], _o[_idx_orden] = (
                            _o[_idx_orden], _o[_idx_orden - 1]
                        )
                        st.rerun()

            with _kol_ned:
                if er_med and _idx_orden < len(_orden_aktuel) - 1:
                    if st.button(
                        "↓",
                        key=(
                            f"bilag_ned_{_bilag_signatur}_"
                            f"{_idx_orden}_{fn}"
                        ),
                        help="Flyt ned",
                    ):
                        _o = st.session_state[_bilag_raekkefolge_key]
                        _o[_idx_orden], _o[_idx_orden + 1] = (
                            _o[_idx_orden + 1], _o[_idx_orden]
                        )
                        st.rerun()


# ---------- AUTO-TJEKLISTE MOD HØRINGSBREV ----------
if st.session_state.get("aktuel_sag"):
    # Apple Health-inspireret sektionsintro: lyseblå pastel med blå accent
    st.markdown(
        """
        <div class="analyse-pillar"
             style="--pillar-bg: #E5F0FD; --pillar-accent: #007AFF;">
            <div class="analyse-pillar-accent-dot"></div>
            <h2 class="analyse-pillar-title">Tjekliste mod høringsbrev</h2>
            <div class="analyse-pillar-body">
                <p>Læser Ankenævnets høringsbrev og sammenholder med de
                uploadede bilag. Viser hvilke af Nævnets ønskede punkter
                der er dækket, og hvad der mangler.</p>
                <p>Kør den <strong>inden</strong> svarbrevet — så du ved
                hvad du skal hente fra TUI's systemer først.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Generer tjekliste", type="secondary"):
        with thinking(
            "juriitech PAX gennemgår sagen mod Nævnets høringsbrev",
            faser=[
                "Læser høringsbrevet fra Nævnet...",
                "Identificerer alle ønskede oplysninger og dokumenter...",
                "Gennemgår de uploadede bilag...",
                "Markerer hvad der er dækket og hvad der mangler...",
                "Skriver punktvis tjekliste...",
            ],
        ):
            try:
                tjekliste = generer_tjekliste(sag=st.session_state.aktuel_sag)
            except Exception as e:
                vis_brugerfejl(
                    "tjeklisten mod høringsbrevet",
                    exception=e,
                    kort_ekstra="Prøv igen — sagens filer er stadig indlæst.",
                )
                tjekliste = None
        if tjekliste:
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
    # Apple Health-inspireret sektionsintro: peach-pastel med amber accent
    st.markdown(
        """
        <div class="analyse-pillar"
             style="--pillar-bg: #FDEFD7; --pillar-accent: #F59E0B;">
            <div class="analyse-pillar-accent-dot"></div>
            <h2 class="analyse-pillar-title">Generer svarbrev til Nævnet</h2>
            <div class="analyse-pillar-body">
                <p>Lav et kompakt udkast til svarbrev fra TUI til
                Pakkerejseankenævnet. Brevet holdes til max 1-2 A4-sider
                og er struktureret som en kort indledning efterfulgt af
                en samlet juridisk vurdering — med præcise henvisninger
                til rejsevilkårene, pakkerejseloven og sagens bilag.</p>
                <p>Du kan redigere udkastet bagefter i Word eller PDF.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------- SÆRLIGE INSTRUKSER (multi-instruks med tilføj/fjern) ----------
    # Listen er scopet til den AKTUELLE sag via en case-id, så instrukser
    # fra én sag aldrig siver over i en anden.
    _aktiv_sag_id = st.session_state.get("aktiv_gemt_sag_id") or "ny_sag"
    _sag_sig = st.session_state.get("sidste_sagsfil_signatur") or ()
    _instrukser_key = f"svarbrev_instrukser_liste_{_aktiv_sag_id}_{hash(_sag_sig)}"

    if _instrukser_key not in st.session_state:
        st.session_state[_instrukser_key] = []

    st.markdown("**Særlige instrukser** (valgfrit)")
    st.caption(
        "Tilføj én eller flere instrukser der skal påvirke svarbrevet. "
        "Instrukserne bruges KUN til denne sag — de nulstilles når du "
        "åbner en anden sag."
    )

    _ny_instruks_key = f"ny_instruks_input_{_aktiv_sag_id}_{hash(_sag_sig)}"

    def _tilfoej_instruks():
        ny = (st.session_state.get(_ny_instruks_key) or "").strip()
        if ny:
            st.session_state[_instrukser_key].append(ny)
            # Ryd input-feltet — Streamlit kræver at vi sætter til ""
            st.session_state[_ny_instruks_key] = ""

    kol_input, kol_btn = st.columns([4, 1])
    with kol_input:
        st.text_input(
            "Skriv en instruks",
            placeholder=(
                "fx 'læg særlig vægt på force majeure-forbeholdet' eller "
                "'anerkend 2.000 kr. men bestrid resten'"
            ),
            key=_ny_instruks_key,
            label_visibility="collapsed",
            on_change=_tilfoej_instruks,
        )
    with kol_btn:
        st.button(
            "Tilføj instruks",
            on_click=_tilfoej_instruks,
            use_container_width=True,
            key=f"tilfoej_btn_{_aktiv_sag_id}_{hash(_sag_sig)}",
        )

    # Vis tilføjede instrukser som små pille-kort med fjern-knap
    _instrukser_liste = st.session_state.get(_instrukser_key, [])
    if _instrukser_liste:
        for _idx, _instr in enumerate(_instrukser_liste):
            kol_tekst, kol_fjern = st.columns([10, 1])
            with kol_tekst:
                st.markdown(
                    f"<div style='background:#F0EEFD; border-left: 3px solid "
                    f"#6366F1; padding: 8px 12px; border-radius: 8px; "
                    f"margin: 4px 0; font-size: 0.92rem; color: #1F2937;'>"
                    f"<strong>{_idx + 1}.</strong> {_instr}</div>",
                    unsafe_allow_html=True,
                )
            with kol_fjern:
                if st.button(
                    "✕",
                    key=f"fjern_instruks_{_aktiv_sag_id}_{hash(_sag_sig)}_{_idx}",
                    help="Fjern denne instruks",
                ):
                    st.session_state[_instrukser_key].pop(_idx)
                    st.rerun()

    # Saml alle instrukser til én streng der sendes til AI'en
    ekstra_instrukser = ""
    if _instrukser_liste:
        ekstra_instrukser = "\n".join(
            f"- {instr}" for instr in _instrukser_liste
        )

    # Toggle: skal svarbrevet inkludere kildehenvisninger?
    # Default: NEJ (slået fra) — brevet bliver kortere og mere flydende.
    # Hvis brugeren slår det til, inkluderer brevet "[Bilag XX, s. Y]",
    # paragraf-referencer og vilkårshenvisninger.
    _inkluder_kildehenvisninger = st.toggle(
        "Vil du tilføje kildehenvisninger til dit svarbrev?",
        value=False,
        key=f"toggle_kildehenvisninger_{_aktiv_sag_id}_{hash(_sag_sig)}",
        help=(
            "Når slået TIL: Svarbrevet indeholder eksplicitte "
            "henvisninger til bilag (fx '[Bilag 04, s. 1]'), "
            "rejsevilkår (fx 'jf. vilkårenes pkt. 5.1') og lovparagraffer "
            "(fx 'jf. § 22'). Når slået FRA (standard): Brevet skrives "
            "uden kildehenvisninger og bliver mere flydende og "
            "naturligt at læse."
        ),
    )

    # ---------- BREVHOVED-FELTER (sagsnummer, klagers navn, høringssvar) ----------
    # Disse felter sættes på selve brevhovedet i den downloadede Word-fil.
    # Sagsnummer og klagers navn forsøges auto-udtrukket fra sagen via et
    # lille AI-kald (cached pr. sag-signatur så vi ikke kalder igen ved
    # hver rerender). Brugeren kan altid rette manuelt før download.
    _meta_cache_key = f"sagsmetadata_{_aktiv_sag_id}_{hash(_sag_sig)}"
    if _meta_cache_key not in st.session_state:
        # Kør lazy auto-udtræk én gang pr. sag-signatur. Fejler stille.
        with st.spinner("Henter sagsdata til brevhoved…"):
            try:
                _meta = udled_sagsmetadata(
                    sag=st.session_state.aktuel_sag,
                    sagsakter_tekst=st.session_state.get("sagsakter", "") or "",
                )
            except Exception as _meta_e:
                print(f"DEBUG: udled_sagsmetadata UI-kald fejlede: {_meta_e}")
                _meta = {"sagsnummer": "", "klagers_navn": ""}
        st.session_state[_meta_cache_key] = _meta

    _meta_default = st.session_state[_meta_cache_key]

    st.markdown("**Brevhoved**")
    st.caption(
        "Disse felter sættes på selve svarbrevet. Sagsnummer og klagers "
        "navn er forsøgt udtrukket automatisk — ret dem hvis de ikke "
        "passer."
    )

    _sagsnr_key = f"svarbrev_sagsnr_{_aktiv_sag_id}_{hash(_sag_sig)}"
    _navn_key = f"svarbrev_klager_{_aktiv_sag_id}_{hash(_sag_sig)}"

    # Initial-værdier sættes kun første gang feltet renderes — derefter
    # styrer Streamlits widget-state værdien (så brugerens redigeringer
    # bevares ved reruns).
    if _sagsnr_key not in st.session_state:
        st.session_state[_sagsnr_key] = _meta_default.get("sagsnummer", "")
    if _navn_key not in st.session_state:
        st.session_state[_navn_key] = _meta_default.get("klagers_navn", "")

    _kol_sagsnr, _kol_navn = st.columns(2)
    with _kol_sagsnr:
        st.text_input(
            "Sagsnummer",
            key=_sagsnr_key,
            placeholder="fx 25-109-8024327",
        )
    with _kol_navn:
        st.text_input(
            "Klagers fulde navn",
            key=_navn_key,
            placeholder="fx Laura Stephanie Uhler",
        )

    # Høringssvar-nummer: 1, 2 eller 3 — vises som segmented control så
    # kun én værdi kan være valgt ad gangen. Default = 1.
    _hoer_key = f"svarbrev_hoeringssvar_{_aktiv_sag_id}_{hash(_sag_sig)}"
    if _hoer_key not in st.session_state:
        st.session_state[_hoer_key] = 1
    st.segmented_control(
        "Høringssvar-nummer",
        options=[1, 2, 3],
        format_func=lambda n: f"{n}. høringssvar",
        selection_mode="single",
        key=_hoer_key,
        help=(
            "Hvilken runde høringssvar er dette? Vises i 'Vedr.'-linjen "
            "øverst på brevet."
        ),
    )

    if st.button("Generer udkast til svarbrev", type="primary"):
        with thinking(
            "juriitech PAX udarbejder svarbrevet til Nævnet",
            faser=[
                "Læser klagen, bilagene og sagsakterne...",
                "Finder relevante rejsevilkår og lovparagraffer...",
                "Bygger juridisk argumentation for forsvaret...",
                "Skriver indledning, faktum og stillingtagen...",
                "Formulerer konklusion og påstand...",
                "Sikrer at klagerens navn er fuldt anonymiseret...",
            ],
        ):
            try:
                # Genbrug både klagepunkter-liste og tidsforhold fra
                # førstevurderingen hvis de findes — sparer to AI-kald
                # og sikrer konsistens mellem analyse og svarbrev.
                # Hvis de ikke findes (fx hvis brugeren skipper
                # førstevurdering), udtrækker generer_svarbrev_til_sag
                # dem selv.
                _gemte_klagepunkter = st.session_state.get(
                    "alle_klagepunkter"
                )
                _gemt_tidsforhold = st.session_state.get("tidsforhold")
                svarbrev = generer_svarbrev_til_sag(
                    sag=st.session_state.aktuel_sag,
                    sagsakter=st.session_state.get("sagsakter", ""),
                    ekstra_instrukser=ekstra_instrukser,
                    inkluder_kildehenvisninger=_inkluder_kildehenvisninger,
                    verificerede_klagepunkter=_gemte_klagepunkter,
                    tidsforhold=_gemt_tidsforhold,
                )
            except Exception as e:
                vis_brugerfejl(
                    "udkast til svarbrev",
                    exception=e,
                    kort_ekstra=(
                        "Dine instrukser er gemt — du kan trykke knappen "
                        "igen om et øjeblik."
                    ),
                )
                svarbrev = None

        if svarbrev:
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

        # Download-knap til svarbrevet — sender brevhoved-felter med så
        # selve Word-filens header kan bygges (sagsnr, klagers navn,
        # høringssvar-nummer, plus selskabs-profil til logo + by).
        _docx_sagsnr = (st.session_state.get(_sagsnr_key) or "").strip()
        _docx_navn = (st.session_state.get(_navn_key) or "").strip()
        _docx_hoer = st.session_state.get(_hoer_key) or 1

        # ---------- BYG BILAG-LISTE TIL HEADER ----------
        # Læser fra de samme state-keys som bilag-håndteringssektionen
        # ovenfor brugte. Hvis brugeren ikke har konfigureret bilag
        # (eller anonymiseringssektionen aldrig blev rendret), ender vi
        # med en tom liste — så bygger svarbrevet bare uden bilag-blok.
        _bilag_aktiv_sag_id_dl = (
            st.session_state.get("aktiv_gemt_sag_id") or "ny_sag"
        )
        _bilag_sag_sig_dl = (
            st.session_state.get("sidste_sagsfil_signatur") or ()
        )
        _bilag_sig_dl = (
            f"{_bilag_aktiv_sag_id_dl}_{hash(_bilag_sag_sig_dl)}"
        )
        _inkl_map = st.session_state.get(
            f"bilag_inkluder_{_bilag_sig_dl}"
        ) or {}
        _overskrift_map = st.session_state.get(
            f"bilag_overskrift_{_bilag_sig_dl}"
        ) or {}
        _orden_dl = st.session_state.get(
            f"bilag_raekkefolge_{_bilag_sig_dl}"
        ) or []
        _start_bogstav_dl = (
            st.session_state.get(f"bilag_startbogstav_{_bilag_sig_dl}")
            or "A"
        ).strip().upper()[:1] or "A"

        # Selskabs-navn til den første bilag-overskrift (svarbrevet selv)
        try:
            from selskab_profiler import hent_navn as _hent_selskab_navn
            _selskab_navn_dl = _hent_selskab_navn() or "TUI"
        except Exception:
            _selskab_navn_dl = "TUI"

        _bilag_liste_dl = [
            {
                "bogstav": _start_bogstav_dl,
                "overskrift": f"{_selskab_navn_dl}s bemærkninger til sagen",
            }
        ]
        # Tilføj de valgte filer i den valgte rækkefølge
        _bogstav_idx = ord(_start_bogstav_dl) - ord("A") + 1
        for _fn in _orden_dl:
            if not _inkl_map.get(_fn):
                continue
            if _bogstav_idx >= 26:
                # Defensivt — stopper ved Z
                break
            _bilag_liste_dl.append({
                "bogstav": chr(ord("A") + _bogstav_idx),
                "overskrift": (
                    _overskrift_map.get(_fn) or _fn
                ).strip(),
            })
            _bogstav_idx += 1

        svarbrev_docx = svarbrev_til_docx(
            st.session_state.seneste_svarbrev["svarbrev"],
            klage_filnavn=st.session_state.seneste_svarbrev["klage_filnavn"],
            sagsnummer=_docx_sagsnr,
            klagers_navn=_docx_navn,
            hoeringssvar_nr=_docx_hoer,
            bilag_liste=_bilag_liste_dl,
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
                "sandsynligheder_dict": st.session_state.get("sandsynligheder_dict"),
                "sagsresume": st.session_state.get("sagsresume"),
                "seneste_svar": st.session_state.get("seneste_svar"),
                "seneste_svarbrev": st.session_state.get("seneste_svarbrev"),
                "seneste_tjekliste": st.session_state.get("seneste_tjekliste"),
                "seneste_anonymisering": st.session_state.get("seneste_anonymisering"),
                # Nyere felter — sag-specifik data der ELLERS kunne lække
                # mellem sager hvis vi ikke gemmer/gendanner dem konsekvent
                "tidsforhold": st.session_state.get("tidsforhold"),
                "alle_klagepunkter": st.session_state.get(
                    "alle_klagepunkter"
                ) or [],
                "chat_historik": st.session_state.get("chat_historik") or [],
                "anon_resultater_per_fil": st.session_state.get(
                    "anon_resultater_per_fil"
                ) or {},
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
