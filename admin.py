"""
Administrator-side til tenant- og bruger-management.

KUN tilgængelig for brugere med role='admin'. Adgangskontrollen sker
to steder: (1) i app.py så admin-siden ikke vises i navigationen for
ikke-admins, (2) her i top af filen så ingen kan komme ind via direkte
URL-tilgang.

Funktioner:
  - Tab "Tenants": liste af tenants + opret/edit-form (navn, by,
    sagsbehandler, logo-upload, anonymiserings-suffix, interne team-
    navne, klageorgan, sprog, land, lov-navn).
  - Tab "Brugere": liste af brugere pr. tenant.
  - Tab "Inviter ny bruger": email + tenant + role → sender Supabase
    magic-link invitation OG opretter row i vores users-tabel.

LOGO-OPLOAD-NOTE:
Logoer gemmes som PNG-filer på Fly's disk under static/logos/<slug>.png.
Fly's disk er IKKE persistent på tværs af deploys, så uploadede logoer
forsvinder ved næste 'fly deploy'. Som workaround:
  - Mikkel kan hente logoet ned, committe det til git, og deploye
  - Eller: senere migration til Fly volumes / Supabase Storage
For B4 MVP er disk-baseret OK — første kunde-onboarding (Apollo) sker
sandsynligvis lige før eller efter en deploy så logoet ikke forsvinder.
"""

import io
from pathlib import Path

import streamlit as st

import auth
from database import (
    hent_alle_tenants,
    hent_tenant_by_id,
    hent_tenant_by_slug,
    opret_tenant,
    opdater_tenant,
    hent_users_for_tenant,
)
from selskab_profiler import ryd_cache as ryd_profil_cache


# ═══════════════════════════════════════════════════════════════
# ADGANGSKONTROL
# ═══════════════════════════════════════════════════════════════

if not auth.is_logged_in():
    st.error("Du skal være logget ind for at se denne side.")
    st.stop()

if not auth.is_admin():
    st.error(
        "🛡️ Denne side kræver administrator-rettigheder. "
        "Kontakt platformsadministratoren hvis du mener du burde have adgang."
    )
    st.stop()


# ═══════════════════════════════════════════════════════════════
# HJÆLPERE
# ═══════════════════════════════════════════════════════════════

LOGOS_DIR = Path(__file__).resolve().parent / "static" / "logos"


def _gem_logo(slug, uploaded_file):
    """
    Gemmer en uploaded fil som static/logos/<slug>.png. Returnerer
    True ved succes. Konverterer altid til PNG for ensartethed.
    """
    if not uploaded_file:
        return False
    try:
        LOGOS_DIR.mkdir(parents=True, exist_ok=True)
        sti = LOGOS_DIR / f"{slug}.png"
        # uploaded_file er en Streamlit BytesIO-lignende — bare write bytes
        with open(sti, "wb") as f:
            f.write(uploaded_file.read())
        return True
    except Exception as e:
        st.error(f"Logo-upload fejlede: {e}")
        return False


def _split_team_navne(tekst):
    """
    Konverterer en multiline-tekst til en liste af team-navne.
    Tomme linjer ignoreres. Whitespace trimmes pr. linje.
    """
    if not tekst:
        return []
    return [
        linje.strip()
        for linje in tekst.splitlines()
        if linje.strip()
    ]


def _join_team_navne(liste):
    """Liste → multiline-tekst (én pr. linje)."""
    return "\n".join(liste or [])


def _validér_slug(slug):
    """
    Validerer at slug kun indeholder små bogstaver, tal og bindestreger.
    Returnerer (ok: bool, fejlmeddelelse: str | None).
    """
    import re as _re
    if not slug:
        return False, "Slug må ikke være tom."
    if not _re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
        return False, (
            "Slug må kun indeholde små bogstaver, tal og bindestreger "
            "(fx 'tui', 'apollo-dk', 'spies-se')."
        )
    if len(slug) > 32:
        return False, "Slug må max være 32 tegn."
    return True, None


# ═══════════════════════════════════════════════════════════════
# UI
# ═══════════════════════════════════════════════════════════════

st.title("🛡️ Administration")
st.caption(
    f"Logget ind som **{auth.current_user().get('email', '')}** "
    "(administrator)"
)

tab_tenants, tab_brugere, tab_inviter, tab_gdpr = st.tabs([
    "Tenants (selskaber)",
    "Brugere",
    "Inviter ny bruger",
    "GDPR audit-log",
])


# ───────────────────────────────────────────────────────────────
# TAB: TENANTS
# ───────────────────────────────────────────────────────────────
with tab_tenants:
    st.subheader("Eksisterende selskaber")

    tenants = hent_alle_tenants()
    if not tenants:
        st.info("Ingen tenants oprettet endnu.")
    else:
        for t in tenants:
            with st.expander(
                f"**{t['navn']}**  ·  slug=`{t['slug']}`  ·  id={t['id']}",
                expanded=False,
            ):
                kol_info, kol_logo = st.columns([3, 1])
                with kol_info:
                    st.markdown(f"**By:** {t['by'] or '_(ikke sat)_'}")
                    st.markdown(
                        f"**Sagsbehandler-signatur:** "
                        f"{t['sagsbehandler'] or '_(samme som navn)_'}"
                    )
                    st.markdown(
                        f"**Anonymiserings-suffix:** "
                        f"`{t['anonymisering_suffix'] or t['navn']}`"
                    )
                    st.markdown(
                        f"**Interne team-navne:** "
                        f"{', '.join(t['interne_team_navne']) or '_(ingen)_'}"
                    )
                    st.markdown(
                        f"**Klageorgan:** {t['klageorgan_navn']} "
                        f"({t['klageorgan_url']})"
                    )
                    st.markdown(f"**Land/sprog:** {t['land']} / {t['sprog']}")
                    st.markdown(
                        f"**Rejsevilkår-kilde:** "
                        f"{t['rejsevilkaar_kilde_url'] or '_(ikke sat)_'}"
                    )

                with kol_logo:
                    if t["logo_filnavn"]:
                        logo_sti = LOGOS_DIR.parent.parent / t["logo_filnavn"]
                        if logo_sti.exists():
                            st.image(str(logo_sti), use_container_width=True)
                        else:
                            st.caption(f"_(logo-fil mangler: {t['logo_filnavn']})_")
                    else:
                        st.caption("_(intet logo)_")

                # Aktion-knapper: Rediger + Scrape vilkår
                kol_edit, kol_scrape = st.columns(2)
                with kol_edit:
                    if st.button(
                        "Rediger",
                        key=f"edit_{t['id']}",
                        type="secondary",
                        use_container_width=True,
                    ):
                        st.session_state.admin_edit_tenant_id = t["id"]
                        st.rerun()
                with kol_scrape:
                    har_url = bool(t.get("rejsevilkaar_kilde_url"))
                    if st.button(
                        "🌍 Scrape vilkår nu",
                        key=f"scrape_{t['id']}",
                        type="secondary",
                        use_container_width=True,
                        disabled=not har_url,
                        help=(
                            "Scraper selskabets juridiske sider fra deres "
                            "rejsevilkår-URL. Tilføjer kun nye sider — "
                            "eksisterende dokumenter springes over (idempotent)."
                            if har_url else
                            "Sæt 'Rejsevilkår-kilde URL' under 'Rediger' "
                            "først for at aktivere scraping."
                        ),
                    ):
                        st.session_state.admin_scrape_tenant_id = t["id"]
                        st.rerun()

    # ── Scrape-handler ──
    # Hvis brugeren netop har klikket 'Scrape vilkår nu' på en tenant,
    # viser vi en progress-blok HER (over edit-formularen) og kører scraperen.
    scrape_id = st.session_state.get("admin_scrape_tenant_id")
    if scrape_id:
        scrape_tenant = hent_tenant_by_id(scrape_id)
        if scrape_tenant and scrape_tenant.get("rejsevilkaar_kilde_url"):
            from vilkaar_scraper import scrape_vilkaar  # lazy import — kun ved klik

            st.divider()
            st.subheader(
                f"🌍 Scraper vilkår for {scrape_tenant['navn']}"
            )
            st.caption(
                f"Kilde: `{scrape_tenant['rejsevilkaar_kilde_url']}`  ·  "
                f"tenant_id={scrape_tenant['id']}"
            )

            log_container = st.empty()
            log_lines = []

            def _log(msg):
                log_lines.append(msg)
                log_container.code(
                    "\n".join(log_lines[-30:]),  # vis kun de seneste 30 linjer
                    language="text",
                )

            with st.spinner("Scraper i gang — kan tage 1-3 min..."):
                try:
                    stats = scrape_vilkaar(
                        tenant_id=scrape_tenant["id"],
                        tenant_slug=scrape_tenant["slug"],
                        kilde_url=scrape_tenant["rejsevilkaar_kilde_url"],
                        progress_callback=_log,
                    )
                    st.success(
                        f"✅ Scraping fuldført. "
                        f"Besøgte {stats['besogte']} sider, "
                        f"gemte {stats['gemt']} nye dokumenter "
                        f"({stats['allerede_i_db']} var allerede i DB)."
                    )
                except Exception as e:
                    st.error(f"❌ Scraping fejlede: {e}")

            # Ryd state så vi ikke re-kører ved næste rerun
            st.session_state.admin_scrape_tenant_id = None
            if st.button("OK — luk scrape-output"):
                st.rerun()
            st.stop()  # Forhindr at edit-formular vises samtidig

    st.divider()

    # Vis edit-formular hvis vi er ved at redigere en tenant
    edit_id = st.session_state.get("admin_edit_tenant_id")
    er_redigering = edit_id is not None
    eksisterende = hent_tenant_by_id(edit_id) if er_redigering else None

    if er_redigering and not eksisterende:
        st.warning(f"Tenant id={edit_id} findes ikke. Annulleret redigering.")
        st.session_state.admin_edit_tenant_id = None
        er_redigering = False

    st.subheader(
        "Rediger tenant" if er_redigering else "Opret nyt selskab (tenant)"
    )

    with st.form("tenant_form", clear_on_submit=not er_redigering):
        f_navn = st.text_input(
            "Selskabsnavn (vises i prompts og svarbreve)",
            value=eksisterende["navn"] if eksisterende else "",
            placeholder="fx 'Apollo'",
        )
        f_slug = st.text_input(
            "Slug (intern identifier — små bogstaver, tal, bindestreger)",
            value=eksisterende["slug"] if eksisterende else "",
            placeholder="fx 'apollo'",
            disabled=er_redigering,  # slug kan ikke ændres efter oprettelse
            help=(
                "Bruges som logo-filnavn og intern reference. "
                "Kan IKKE ændres efter oprettelse."
            ),
        )
        f_sagsbehandler = st.text_input(
            "Sagsbehandler-signatur (vises som underskrift på svarbrev)",
            value=eksisterende["sagsbehandler"] if eksisterende else "",
            placeholder="fx 'Apollo Kundeservice'",
            help="Hvis tom, bruges selskabsnavnet.",
        )
        f_by = st.text_input(
            "By (vises i svarbrevets datolinje)",
            value=eksisterende["by"] if eksisterende else "",
            placeholder="fx 'København'",
        )
        f_anonym_suffix = st.text_input(
            "Anonymiserings-suffix (fx 'Apollo' i 'Maria, Apollo')",
            value=(
                eksisterende["anonymisering_suffix"]
                if eksisterende else ""
            ),
            placeholder="fx 'Apollo'",
            help="Hvis tom, bruges selskabsnavnet.",
        )
        f_team_navne = st.text_area(
            "Interne team-navne (én pr. linje — bruges af AI-anonymisering "
            "til at skelne interne medarbejdere fra eksterne partnere)",
            value=_join_team_navne(
                eksisterende["interne_team_navne"]
            ) if eksisterende else "",
            placeholder="After Travel\nKundeservice\nCustomer Service",
            height=100,
        )

        st.markdown("**Klageorgan & lovgivning**")
        f_klageorgan_navn = st.text_input(
            "Klageorgan-navn",
            value=(
                eksisterende["klageorgan_navn"]
                if eksisterende else "Pakkerejse-Ankenævnet"
            ),
        )
        f_klageorgan_url = st.text_input(
            "Klageorgan-URL",
            value=(
                eksisterende["klageorgan_url"]
                if eksisterende
                else "https://www.pakkerejseankenaevnet.dk"
            ),
        )
        f_lov_navn = st.text_input(
            "National lov-navn",
            value=(
                eksisterende["lov_navn"]
                if eksisterende else "Pakkerejseloven"
            ),
        )
        f_rejsevilkaar_url = st.text_input(
            "Rejsevilkår-kilde URL (bruges til scraping af deres officielle vilkår)",
            value=(
                eksisterende["rejsevilkaar_kilde_url"]
                if eksisterende else ""
            ),
            placeholder="fx 'https://www.apollorejser.dk/rejsevilkaar/'",
        )

        kol_sprog, kol_land = st.columns(2)
        with kol_sprog:
            f_sprog = st.selectbox(
                "Sprog",
                options=["da", "sv", "no", "fi"],
                index=["da", "sv", "no", "fi"].index(
                    eksisterende["sprog"] if eksisterende else "da"
                ),
            )
        with kol_land:
            f_land = st.selectbox(
                "Land",
                options=["DK", "SE", "NO", "FI"],
                index=["DK", "SE", "NO", "FI"].index(
                    eksisterende["land"] if eksisterende else "DK"
                ),
            )

        st.markdown("**Logo (valgfrit)**")
        if er_redigering and eksisterende.get("logo_filnavn"):
            st.caption(
                f"Nuværende logo: `{eksisterende['logo_filnavn']}`. "
                "Upload en ny PNG for at erstatte."
            )
        f_logo = st.file_uploader(
            "Upload logo som PNG (kvadratisk anbefalet, ~200x200 px)",
            type=["png", "jpg", "jpeg"],
        )

        kol_save, kol_cancel = st.columns(2)
        with kol_save:
            gem_btn = st.form_submit_button(
                "Gem ændringer" if er_redigering else "Opret tenant",
                type="primary",
                use_container_width=True,
            )
        with kol_cancel:
            if er_redigering:
                annuller_btn = st.form_submit_button(
                    "Annullér",
                    use_container_width=True,
                )
            else:
                annuller_btn = False

    if annuller_btn:
        st.session_state.admin_edit_tenant_id = None
        st.rerun()

    if gem_btn:
        # Validering
        if not f_navn.strip():
            st.error("Selskabsnavn er påkrævet.")
        elif not er_redigering:
            ok, slug_fejl = _validér_slug(f_slug.strip())
            if not ok:
                st.error(slug_fejl)
            else:
                # Tjek at slug ikke allerede findes
                if hent_tenant_by_slug(f_slug.strip()):
                    st.error(
                        f"Slug '{f_slug.strip()}' er allerede i brug."
                    )
                else:
                    # Opret ny tenant
                    ny_id = opret_tenant(
                        slug=f_slug.strip(),
                        navn=f_navn.strip(),
                        sagsbehandler=f_sagsbehandler.strip() or f_navn.strip(),
                        by=f_by.strip(),
                        logo_filnavn=(
                            f"static/logos/{f_slug.strip()}.png"
                            if f_logo else ""
                        ),
                        anonymisering_suffix=(
                            f_anonym_suffix.strip() or f_navn.strip()
                        ),
                        interne_team_navne=_split_team_navne(f_team_navne),
                        klageorgan_navn=f_klageorgan_navn.strip(),
                        klageorgan_url=f_klageorgan_url.strip(),
                        rejsevilkaar_kilde_url=f_rejsevilkaar_url.strip(),
                        sprog=f_sprog,
                        land=f_land,
                        lov_navn=f_lov_navn.strip(),
                    )
                    if ny_id:
                        if f_logo:
                            _gem_logo(f_slug.strip(), f_logo)
                        ryd_profil_cache()
                        st.success(
                            f"✅ Tenant '{f_navn}' oprettet (id={ny_id})."
                        )

                        # Auto-scrape rejsevilkår hvis URL er sat
                        if f_rejsevilkaar_url.strip():
                            with st.spinner(
                                f"Henter rejsevilkår fra "
                                f"{f_rejsevilkaar_url.strip()}..."
                            ):
                                try:
                                    from vilkaar_scraper import (
                                        scrape_vilkaar,
                                    )
                                    scrape_result = scrape_vilkaar(
                                        tenant_id=ny_id,
                                        tenant_slug=f_slug.strip(),
                                        kilde_url=(
                                            f_rejsevilkaar_url.strip()
                                        ),
                                    )
                                    st.success(
                                        f"📥 Vilkår hentet: "
                                        f"{scrape_result.get('gemt', 0)} "
                                        f"nye, "
                                        f"{scrape_result.get('allerede_i_db', 0)} "
                                        f"allerede i DB"
                                    )
                                except Exception as e:
                                    st.warning(
                                        f"⚠️ Kunne ikke hente vilkår "
                                        f"automatisk: {e}. Tenant er "
                                        "oprettet — du kan manuelt scrape "
                                        "fra forsidens admin-panel."
                                    )
                        st.rerun()
                    else:
                        st.error("Tenant kunne ikke oprettes.")
        else:
            # Opdater eksisterende
            felter = {
                "navn": f_navn.strip(),
                "sagsbehandler": f_sagsbehandler.strip() or f_navn.strip(),
                "by": f_by.strip(),
                "anonymisering_suffix": (
                    f_anonym_suffix.strip() or f_navn.strip()
                ),
                "interne_team_navne": _split_team_navne(f_team_navne),
                "klageorgan_navn": f_klageorgan_navn.strip(),
                "klageorgan_url": f_klageorgan_url.strip(),
                "rejsevilkaar_kilde_url": f_rejsevilkaar_url.strip(),
                "sprog": f_sprog,
                "land": f_land,
                "lov_navn": f_lov_navn.strip(),
            }
            if f_logo:
                _gem_logo(eksisterende["slug"], f_logo)
                felter["logo_filnavn"] = (
                    f"static/logos/{eksisterende['slug']}.png"
                )
            ok = opdater_tenant(eksisterende["id"], **felter)
            if ok:
                ryd_profil_cache()
                st.session_state.admin_edit_tenant_id = None
                st.success(f"✅ Tenant '{f_navn}' opdateret.")

                # Hvis rejsevilkaar_kilde_url er ændret, auto-scrape
                gammel_url = (
                    eksisterende.get("rejsevilkaar_kilde_url") or ""
                ).strip()
                ny_url = f_rejsevilkaar_url.strip()
                if ny_url and ny_url != gammel_url:
                    with st.spinner(
                        f"Henter rejsevilkår fra ny URL: {ny_url}..."
                    ):
                        try:
                            from vilkaar_scraper import scrape_vilkaar
                            scrape_result = scrape_vilkaar(
                                tenant_id=eksisterende["id"],
                                tenant_slug=eksisterende["slug"],
                                kilde_url=ny_url,
                            )
                            st.success(
                                f"📥 Vilkår hentet: "
                                f"{scrape_result.get('gemt', 0)} nye, "
                                f"{scrape_result.get('allerede_i_db', 0)} "
                                f"allerede i DB"
                            )
                        except Exception as e:
                            st.warning(
                                f"⚠️ Kunne ikke hente vilkår "
                                f"automatisk: {e}. Du kan manuelt "
                                "scrape fra forsidens admin-panel."
                            )
                st.rerun()
            else:
                st.error("Opdatering fejlede.")


# ───────────────────────────────────────────────────────────────
# TAB: BRUGERE
# ───────────────────────────────────────────────────────────────
with tab_brugere:
    st.subheader("Brugere pr. selskab")

    tenants_for_oversigt = hent_alle_tenants()
    if not tenants_for_oversigt:
        st.info("Ingen tenants endnu.")
    else:
        # Den nuværende admin's id — bruges til at disable slet-knap
        # på sig selv, så man ikke logger sig selv ud per uheld.
        _aktuel_user = auth.current_user() or {}
        _aktuel_user_id = _aktuel_user.get("id")
        # Hvor mange admins findes der i alt — bruges til at disable
        # slet-knappen på den sidste admin (forhindrer at man låser
        # sig selv ude af admin-siden).
        from database import tael_admins as _tael_admins
        _antal_admins = _tael_admins()

        for t in tenants_for_oversigt:
            users = hent_users_for_tenant(t["id"])
            antal = len(users)
            with st.expander(
                f"**{t['navn']}**  ·  {antal} bruger{'e' if antal != 1 else ''}",
                expanded=(antal > 0),
            ):
                if not users:
                    st.caption(
                        "_Ingen brugere endnu. Inviter dem under fanen "
                        "'Inviter ny bruger'._"
                    )
                else:
                    for u in users:
                        ikon = "🛡️" if u["role"] == "admin" else "👤"
                        link_status = (
                            "linket"
                            if u["supabase_user_id"]
                            else "ikke linket endnu (har ikke logget ind)"
                        )
                        kol_info, kol_btn = st.columns([6, 1])
                        with kol_info:
                            st.markdown(
                                f"{ikon} **{u['email']}** "
                                f"({u.get('fulde_navn', '') or '_navn ikke sat_'}) "
                                f"— role=`{u['role']}` — {link_status}"
                            )
                        with kol_btn:
                            er_dig_selv = (u["id"] == _aktuel_user_id)
                            er_sidste_admin = (
                                u["role"] == "admin" and _antal_admins <= 1
                            )
                            if er_dig_selv:
                                st.caption("_(dig)_")
                            elif er_sidste_admin:
                                st.caption("🔒 _sidste admin_")
                            else:
                                # Slet-knap åbner et bekræftelses-trin via
                                # session_state — ingen direkte sletning ved
                                # første klik (destruktivt = to-trins).
                                bekraft_key = f"bekraft_slet_user_{u['id']}"
                                if st.session_state.get(bekraft_key):
                                    # Trin 2: vist bekræftelses-prompt
                                    pass
                                else:
                                    if st.button(
                                        "🗑️",
                                        key=f"slet_user_{u['id']}",
                                        help=f"Slet {u['email']}",
                                    ):
                                        st.session_state[bekraft_key] = True
                                        st.rerun()

                        # Trin 2: bekræftelses-boks (vises kun hvis knappen
                        # er klikket). Lægges UDENFOR kolonnerne så den
                        # kan fylde fuld bredde.
                        bekraft_key = f"bekraft_slet_user_{u['id']}"
                        if st.session_state.get(bekraft_key):
                            with st.container(border=True):
                                st.warning(
                                    f"⚠️ Du er ved at slette **{u['email']}** "
                                    "permanent — både her og i Supabase Auth. "
                                    "Det kan IKKE fortrydes."
                                )
                                kol_ja, kol_nej = st.columns(2)
                                with kol_ja:
                                    if st.button(
                                        "Ja, slet brugeren",
                                        key=f"slet_ja_{u['id']}",
                                        type="primary",
                                        use_container_width=True,
                                    ):
                                        with st.spinner("Sletter..."):
                                            ok, fejl = auth.admin_delete_user(
                                                u["id"]
                                            )
                                        # Ryd bekræftelses-flag uanset udfald
                                        st.session_state[bekraft_key] = False
                                        if ok:
                                            st.success(
                                                f"✅ **{u['email']}** slettet."
                                            )
                                            st.rerun()
                                        else:
                                            st.error(
                                                fejl or "Sletning fejlede."
                                            )
                                with kol_nej:
                                    if st.button(
                                        "Annullér",
                                        key=f"slet_nej_{u['id']}",
                                        use_container_width=True,
                                    ):
                                        st.session_state[bekraft_key] = False
                                        st.rerun()


# ───────────────────────────────────────────────────────────────
# TAB: INVITER NY BRUGER
# ───────────────────────────────────────────────────────────────
with tab_inviter:
    st.subheader("Inviter ny bruger")
    st.caption(
        "Brugeren modtager en email med et invite-link. Når de klikker "
        "linket, lander de på en side hvor de selv vælger deres password "
        "og logger ind. Du behøver ikke videregive noget manuelt."
    )

    tenants_til_invite = hent_alle_tenants()
    if not tenants_til_invite:
        st.warning(
            "Du skal oprette mindst én tenant FØR du kan invitere brugere."
        )
    else:
        with st.form("invite_form", clear_on_submit=True):
            i_email = st.text_input(
                "Email-adresse",
                placeholder="navn@firma.dk",
            )
            i_navn = st.text_input(
                "Fulde navn (valgfrit)",
                placeholder="Maria Hansen",
            )

            tenant_options = {
                f"{t['navn']} ({t['slug']})": t["id"]
                for t in tenants_til_invite
            }
            i_tenant_label = st.selectbox(
                "Tilknyt til selskab",
                options=list(tenant_options.keys()),
            )

            i_role = st.radio(
                "Rolle",
                options=["jurist", "admin"],
                horizontal=True,
                help=(
                    "**jurist**: almindelig bruger der kan analysere sager "
                    "for sit selskab. **admin**: kan også tilgå denne "
                    "admin-side (kun for platforms-administratorer)."
                ),
            )

            i_metode = st.radio(
                "Metode",
                options=[
                    "📧 Send invite-email (anbefalet)",
                    "🔑 Opret med temp password (backup hvis email fejler)",
                ],
                index=0,
                help=(
                    "**Send invite-email**: Brugeren modtager en mail med "
                    "link til at sætte deres egen adgangskode. "
                    "**Opret med temp password**: System genererer et "
                    "midlertidigt password som du videregiver manuelt. "
                    "Brug kun hvis email-leveringen er upålidelig."
                ),
            )

            inviter_btn = st.form_submit_button(
                "Send invitation"
                if "email" in i_metode
                else "Opret med temp password",
                type="primary",
                use_container_width=True,
            )

        if inviter_btn:
            tenant_id = tenant_options.get(i_tenant_label)
            if "email" in i_metode:
                # Email-baseret invite (anbefalet)
                with st.spinner("Sender invite-email..."):
                    ok, fejl = auth.admin_invite_user(
                        email=i_email,
                        tenant_id=tenant_id,
                        role=i_role,
                        fulde_navn=i_navn,
                    )
                if ok:
                    st.success(
                        f"✅ Invitation sendt til **{i_email}**. "
                        f"De er tilknyttet **{i_tenant_label}** som "
                        f"**{i_role}**. Bed dem tjekke deres indbakke "
                        "(inkl. spam-mappen). Linket åbner en side hvor "
                        "de selv vælger deres adgangskode."
                    )
                    if fejl:
                        st.info(fejl)
                else:
                    st.error(fejl or "Invitation fejlede.")
            else:
                # Backup: temp password
                with st.spinner("Opretter bruger..."):
                    ok, fejl, temp_pw = auth.admin_create_user(
                        email=i_email,
                        tenant_id=tenant_id,
                        role=i_role,
                        fulde_navn=i_navn,
                    )
                if ok:
                    st.success(
                        f"✅ Bruger oprettet: **{i_email}** "
                        f"({i_role}) i **{i_tenant_label}**."
                    )
                    st.warning(
                        "🔐 **VIGTIGT — videregiv disse credentials sikkert "
                        "til brugeren** (Signal, telefonisk, eller anden "
                        "krypteret kanal). Send IKKE password i almindelig "
                        "email. Passwordet vises KUN her én gang."
                    )
                    st.code(
                        f"Email:    {i_email}\nPassword: {temp_pw}",
                        language="text",
                    )
                else:
                    st.error(fejl or "Oprettelse fejlede.")


# ───────────────────────────────────────────────────────────────
# TAB: GDPR AUDIT-LOG
# ───────────────────────────────────────────────────────────────
with tab_gdpr:
    st.subheader("GDPR audit-trail")
    st.caption(
        "Dokumentation over alle GDPR-relevante handlinger pr. sag — "
        "upload, analyse, anonymisering, sletning. Kan fremvises ved "
        "kunde-revision."
    )

    from database import _connect

    # ---- Sektion 1: Status-overblik ----
    st.markdown("#### Status-overblik")

    try:
        conn = _connect()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                anonymiserings_status,
                COUNT(*) AS antal
            FROM mine_dokumenter
            WHERE is_public = FALSE
            GROUP BY anonymiserings_status
            ORDER BY anonymiserings_status
        """)
        status_data = cur.fetchall()

        if status_data:
            kolonner = st.columns(len(status_data))
            label_map = {
                'aktiv': '🟢 Aktive sager',
                'anonymiseret': '🔒 Anonymiseret',
                'pending': '⏳ Pending',
                'public': '🌐 Public (irrelevant)',
            }
            for kol, (status, antal) in zip(kolonner, status_data):
                with kol:
                    st.metric(
                        label_map.get(status, status),
                        antal,
                    )

        cur.execute("""
            SELECT COUNT(*) FROM mine_dokumenter
            WHERE anonymiserings_status = 'aktiv'
              AND anonymiseres_efter IS NOT NULL
              AND anonymiseres_efter < NOW()
        """)
        klar_til_pipeline = cur.fetchone()[0]
        if klar_til_pipeline > 0:
            st.warning(
                f"⚠️ **{klar_til_pipeline} sager** har "
                f"anonymiseres_efter i fortiden — venter på cron-job. "
                "Hvis cron ikke er aktiveret endnu, kan du køre "
                "pipelinen manuelt: "
                "`python3 -c 'from gdpr_pipeline import "
                "trigger_auto_anonymisering; "
                "print(trigger_auto_anonymisering())'`"
            )

        cur.execute("""
            SELECT COUNT(*) FROM shared_patterns
        """)
        antal_shared = cur.fetchone()[0]
        st.metric("📊 Mønstre i fælles cross-tenant pulje", antal_shared)

        cur.close()
    except Exception as e:
        st.error(f"Kunne ikke hente status: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    st.divider()

    # ---- Sektion 2: Seneste audit-events ----
    st.markdown("#### Seneste audit-events")

    antal_vis = st.slider(
        "Antal events at vise", 10, 200, 50, step=10,
    )

    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                gdpr_audit_log.tidspunkt,
                tenants.navn AS tenant_navn,
                gdpr_audit_log.sag_id,
                gdpr_audit_log.handling,
                gdpr_audit_log.metadata
            FROM gdpr_audit_log
            LEFT JOIN tenants ON tenants.id = gdpr_audit_log.tenant_id
            ORDER BY gdpr_audit_log.tidspunkt DESC
            LIMIT %s
        """, (antal_vis,))
        events = cur.fetchall()

        if not events:
            st.info(
                "Ingen audit-events endnu. Pipelinen skriver til loggen "
                "når den anonymiserer sager."
            )
        else:
            handling_emoji = {
                'upload': '📤',
                'analyse': '🔍',
                'anonymisering': '🔒',
                'sletning': '🗑️',
                'cross_tenant_share': '📊',
                'tilbage_kald': '↩️',
            }

            for tidspunkt, tenant, sag_id, handling, metadata in events:
                emoji = handling_emoji.get(handling, '•')
                tid_str = (
                    tidspunkt.strftime('%Y-%m-%d %H:%M:%S')
                    if tidspunkt else '?'
                )
                with st.expander(
                    f"{emoji} {tid_str} — {tenant or 'ukendt'} — "
                    f"sag {sag_id} — **{handling}**",
                    expanded=False,
                ):
                    if metadata:
                        st.json(metadata)
                    else:
                        st.caption("(ingen metadata)")

        cur.close()
    except Exception as e:
        st.error(f"Kunne ikke hente audit-events: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
