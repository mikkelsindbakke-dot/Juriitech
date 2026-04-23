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


# ---------- OPSÆTNING ----------
st.set_page_config(
    page_title="Juriitech",
    page_icon="⚖️",
    layout="wide",
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


def _auto_gem_klage_i_db(klage_dict):
    """
    Gemmer en uploadet klage i databasen med dokumenttype='klage', hvis den
    ikke allerede findes. Returnerer en statusstreng til brug i UI'en.
    """
    filnavn = klage_dict.get("filnavn")
    if not filnavn:
        return None

    if sag_findes(filnavn):
        return f"ℹ️ {filnavn} findes allerede i vidensbanken — ikke gemt igen."

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
        return f"⚠️ {filnavn} gemt som klage, men embedding fejlede."
    return f"✅ {filnavn} automatisk gemt i vidensbanken som klage."


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

    st.title("Juriitech ⚖️")
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
            "💡 **Sådan gør du:**\n\n"
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
        st.subheader("🌐 Hent direkte fra Ankenævnet")
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
            tael_knap = st.button("🔢 Tæl kun", help="Dry-run — tæl hvor mange der er på siden uden at hente")
        with kol_b:
            hent_knap = st.button("⬇️ Hent nye sager", type="primary")

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
        st.subheader("📘 Hent TUI's rejsevilkår")
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
            "⬇️ Hent juridisk indhold fra tui.dk",
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
st.title("Juriitech ⚖️")


# ---------- ANALYSE AF NY SAG ----------
st.header("📄 Analysér en ny sag fra Ankenævnet")
st.caption(
    "Upload **hele sagspakken** fra Ankenævnet — enten som ZIP-fil eller ved at "
    "vælge flere filer på én gang (høringsbrev, klageskema, bilag 02-07 osv.). "
    "Programmet pakker ZIP ud, læser hver fil, gætter dens rolle i sagen (høring, "
    "klageskema, bilag), og behandler dem alle samlet som én sag."
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
            st.toast(f"✅ {len(gemt_nu)} filer gemt i vidensbanken.")
        if sprunget_over:
            st.toast(f"ℹ️ {len(sprunget_over)} filer var allerede i databasen.")

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
            st.rerun()

    # Vis oversigt over filerne i sagen (foldbar)
    with st.expander(f"📋 Se de {len(filer)} filer i sagen", expanded=False):
        for i, fil in enumerate(filer, 1):
            rolle = fil.get("rolle", "ukendt").replace("_", " ")
            ikon = "📄" if fil["type"] == "tekst" else "🖼️"
            tegn_info = (
                f" — {len(fil.get('tekst') or '')} tegn læst"
                if fil["type"] == "tekst" else " — scannet PDF"
            )
            st.markdown(f"**{i}. {ikon} {fil['filnavn']}** *({rolle})*{tegn_info}")

    # ---------- SAGSAKTER (C4C, e-mails, bookingdetaljer) ----------
    with st.expander(
        "📎 Sagsakter til denne klage — C4C-notater, e-mails, bookingdetaljer",
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
st.header("💬 Stil spørgsmål til dine sager")

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
        label="⬇️ Download analyse (inkl. sandsynlighedsvurdering) som Word",
        data=docx_bytes,
        file_name=f"analyse_{filnavn_base}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key="download_analyse",
    )


# ---------- ANONYMISERINGSASSISTENT ----------
if st.session_state.get("aktuel_sag"):
    st.divider()
    st.header("🔒 Anonymisér bilag til Nævnet")
    st.caption(
        "Juriitech producerer anonymiserede versioner af alle tekst-baserede bilag "
        "efter Pakkerejse-Ankenævnets retningslinjer (K for klager, R for "
        "rejsearrangør, B1/B2 for bipersoner, CPR-numre fjernes, osv.). "
        "Høringsbrev og vejledninger springes automatisk over — de skal ikke "
        "sendes tilbage. Scannede PDF'er kræver manuel behandling."
    )

    if st.button("🔒 Anonymisér alle bilag", type="secondary"):
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
            f"Anonymisering færdig. ✅ {ok_antal} anonymiseret, "
            f"ℹ️ {sprunget_antal} sprunget over, "
            f"⚠️ {fejl_antal} fejlede."
        )

        st.caption(
            "⚠️ **Tjek resultaterne manuelt før du sender til Nævnet.** "
            "AI-anonymisering er et hjælpeværktøj, ikke en garanti. "
            "Gennemgå hver fil for at sikre at alle personhenførbare oplysninger "
            "er fjernet korrekt."
        )

        for r in resultater:
            if r["status"] == "ok":
                ikon = "✅"
            elif r["status"] == "sprunget_over":
                ikon = "ℹ️"
            else:
                ikon = "⚠️"

            with st.expander(f"{ikon} {r['filnavn']}  —  {r['bemaerkning']}"):
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
                        label="⬇️ Download anonymiseret version som Word",
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
    st.header("📋 Tjekliste mod høringsbrev")
    st.caption(
        "Læser Ankenævnets høringsbrev og sammenholder med de uploadede bilag. "
        "Viser hvilke af Nævnets ønskede punkter der er dækket, og hvad der mangler. "
        "Kør den INDEN svarbrevet — så du ved hvad du skal hente fra TUI's systemer først."
    )

    if st.button("🔎 Generer tjekliste", type="secondary"):
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
    st.header("✉️ Generer svarbrev til Nævnet")
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

    if st.button("📝 Generer udkast til svarbrev", type="primary"):
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
            label="⬇️ Download svarbrev som Word",
            data=svarbrev_docx,
            file_name=f"svarbrev_{sb_filnavn_base}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            key="download_svarbrev",
        )


# ---------- ARKIV OVER TIDLIGERE ANALYSER OG SVARBREVE ----------
st.divider()
with st.expander("📚 Mine tidligere analyser og svarbreve", expanded=False):
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
            if item["type"] == "svarbrev":
                ikon = "📝"
            elif item["type"] == "tjekliste":
                ikon = "📋"
            else:
                ikon = "🔎"
            dato_str = (
                item["oprettet_dato"].strftime("%d-%m-%Y %H:%M")
                if item.get("oprettet_dato") else "ukendt"
            )
            with st.expander(f"{ikon} {item['titel']}  —  {dato_str}"):
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
