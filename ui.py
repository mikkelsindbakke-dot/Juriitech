"""
Custom UI-komponenter til Juriitech.

Indeholder:
  - thinking(): Claude-inspireret pulsende gradient-prik som spinner
  - render_analyse_som_pillars(): Apple-Health-inspireret pillar-layout
    for den juridiske førstevurdering
  - vis_brugerfejl(): venlig fejlboks der vises når noget går galt,
    sender automatisk fejlen til Sentry
"""

import re
from contextlib import contextmanager

import streamlit as st


def vis_brugerfejl(handling, exception=None, kort_ekstra=None):
    """
    Viser en venlig fejlboks til brugeren og sender automatisk fejlen
    til Sentry så administratoren får besked.

    handling:    kort beskrivelse af hvad brugeren prøvede at gøre
                 (fx 'generere svarbrev', 'anonymisere bilag').
                 Bruges både i UI'et og som tag i Sentry.
    exception:   den faktiske exception der opstod (sendes til Sentry).
    kort_ekstra: valgfri kort tekst der vises under hovedmeddelelsen
                 (fx 'Prøv igen om et øjeblik' eller info om hvad der
                 skete).
    """
    # Send først til Sentry hvis muligt
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("brugerhandling", handling)
            if exception is not None:
                sentry_sdk.capture_exception(exception)
            else:
                sentry_sdk.capture_message(
                    f"Fejl ved: {handling}", level="error"
                )
    except Exception:
        # Hvis Sentry selv fejler, fortsætter vi alligevel — vi vil ikke
        # at fejl-håndteringen i sig selv crasher appen.
        pass

    import html as _html
    ekstra_html = ""
    if kort_ekstra:
        ekstra_html = (
            f'<div class="brugerfejl-ekstra">{_html.escape(str(kort_ekstra))}</div>'
        )

    handling_safe = _html.escape(str(handling))

    st.markdown(
        '<div class="brugerfejl-boks">'
        '<div class="brugerfejl-ikon">⚠️</div>'
        '<div class="brugerfejl-indhold">'
        '<div class="brugerfejl-titel">'
        'Ups — her gik der noget galt'
        '</div>'
        '<div class="brugerfejl-tekst">'
        f'Vi kunne ikke fuldføre <strong>{handling_safe}</strong>. '
        'Administratoren har automatisk fået besked, og vi løser det '
        'så hurtigt som muligt.'
        '</div>'
        f'{ekstra_html}'
        '<div class="brugerfejl-tips">'
        'Du kan i mellemtiden prøve at:'
        '<ul>'
        '<li>Genindlæse siden (Cmd+R eller Ctrl+R)</li>'
        '<li>Prøve handlingen igen om et øjeblik</li>'
        '<li>Lukke og genåbne sagen</li>'
        '</ul>'
        '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


@contextmanager
def thinking(tekst="juriitech PAX arbejder...", faser=None):
    """
    Context manager der viser en Claude-inspireret pulsende gradient-prik
    med tekst ved siden af, mens kode i with-blokken kører. Forsvinder
    automatisk når blokken er færdig.

    Hvis 'faser' er en liste af strenge, bruges den til at cykle igennem
    beskrivelser af hvad PAX arbejder på lige nu (fx 'Læser sagsakterne',
    'Søger i vidensbanken', 'Vurderer sandsynligheder') — hver vises i
    ~4 sekunder. Samtidig kører en elapsed-timer der viser mm:ss så det
    er tydeligt for brugeren hvor langt processen er nået uden at lovne
    et urealistisk tidsestimat.

    Til JS-drevet version bruger vi streamlit.components.v1.html — det
    er nødvendigt fordi st.markdown af sikkerhedsgrunde fjerner
    <script>-tags. Iframen holder sin egen timer kørende client-side
    selv mens Python venter på Anthropic-svaret.
    """
    placeholder = st.empty()

    if faser:
        # JS-drevet version med roterende faser + elapsed timer.
        # Kører i en lille iframe via st.components.v1.html så JS'en
        # faktisk eksekveres i browseren.
        import json as _json
        from streamlit.components.v1 import html as _components_html

        faser_json = _json.dumps(list(faser))

        # Hele widgetten er selvstændig i iframen — CSS skal derfor være
        # inline her (kan ikke arve fra sidens CSS, da det er en isoleret
        # kontekst).
        widget_html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
  html, body {{ margin: 0; padding: 0; background: transparent;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }}
  .wrap {{
    display: flex; align-items: center; gap: 14px;
    padding: 20px 24px; border-radius: 12px;
    background: rgba(99, 102, 241, 0.05);
    border: 1px solid rgba(99, 102, 241, 0.12);
  }}
  .dot {{
    width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0;
    background: radial-gradient(circle at 30% 30%, #A5B4FC, #6366F1 60%, #4F46E5);
    box-shadow: 0 0 16px rgba(99, 102, 241, 0.45),
                inset -2px -2px 6px rgba(0, 0, 0, 0.12);
    animation: pulse 1.4s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  }}
  @keyframes pulse {{
    0%, 100% {{ transform: scale(0.85); opacity: 0.75; }}
    50%      {{ transform: scale(1.15); opacity: 1; }}
  }}
  .stack {{ display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }}
  .tekst {{ color: #111827; font-weight: 600; font-size: 0.98rem; letter-spacing: 0.01em; }}
  .fase {{
    color: rgba(71, 85, 105, 0.85); font-size: 0.85rem;
    font-weight: 400; letter-spacing: 0.01em;
    transition: opacity 0.35s ease;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  .timer {{
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    font-size: 0.82rem; color: rgba(71, 85, 105, 0.8);
    background: rgba(99, 102, 241, 0.1);
    padding: 3px 10px; border-radius: 999px;
    flex-shrink: 0; font-variant-numeric: tabular-nums;
  }}
  .kvalitet-note {{
    margin-top: 10px; padding: 0 4px;
    color: rgba(71, 85, 105, 0.78);
    font-size: 0.82rem; font-style: italic;
    line-height: 1.5; letter-spacing: 0.01em;
  }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="dot"></div>
    <div class="stack">
      <span class="tekst">{tekst}</span>
      <span class="fase" id="fase">{faser[0]}</span>
    </div>
    <span class="timer" id="timer">0:00</span>
  </div>
  <div class="kvalitet-note">
    Det kan tage et par minutter, da vi serverer det hele samlet.
    Kvalitet tager tid, og vi arbejder ikke med halve svar.
  </div>
  <script>
    (function() {{
      var faser = {faser_json};
      var faseEl = document.getElementById("fase");
      var timerEl = document.getElementById("timer");
      var idx = 0;
      var start = Date.now();
      setInterval(function() {{
        idx = (idx + 1) % faser.length;
        faseEl.textContent = faser[idx];
      }}, 4000);
      setInterval(function() {{
        var s = Math.floor((Date.now() - start) / 1000);
        var m = Math.floor(s / 60);
        var sek = String(s % 60);
        if (sek.length < 2) sek = "0" + sek;
        timerEl.textContent = m + ":" + sek;
      }}, 1000);
    }})();
  </script>
</body>
</html>
"""
        with placeholder:
            _components_html(widget_html, height=140)
    else:
        placeholder.markdown(
            f"""
            <div class="thinking-wrapper">
              <div class="thinking-dot"></div>
              <span class="thinking-text">{tekst}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    try:
        yield
    finally:
        placeholder.empty()


# ---------- APPLE-HEALTH-INSPIRERET PILLAR-LAYOUT ----------

# Tildel en accent-farve per sektion (matcher Apple Health's æstetik
# hvor hver sektion har sin egen farvetone)
# Apple-Health-farver — præcis de pastelbaggrunde Apple selv bruger på
# apple.com/apple-watch/health. Hver tuple = (accent-farve, pastel-baggrund).
_PILLAR_PALETTER = [
    # 1. Kort resume — Rose/Pink (Apple Sleep)
    ("#00D4C2", "#FDE9EE"),
    # 2. Klagens kernepunkter — Lavender (Apple Tune In)
    ("#007AFF", "#EEEAFF"),
    # 3. Rejseselskabets stillingtagen — Light Blue (Apple Hearing)
    ("#007AFF", "#E5F0FD"),
    # 4. Kort juridisk vurdering — Mint Green (Apple Activity)
    ("#76D672", "#E7F5DD"),
    # 5. Sandsynlighedsvurdering — Cream/Peach (Apple Look)
    ("#F59E0B", "#FDEFD7"),
]


def _split_analyse_i_sektioner(tekst):
    """
    Split en markdown-analysetekst op i (titel, krop)-sektioner.

    Genkender sektion-starter som:
      - "## 1. Titel"
      - "1. **Titel**"
      - "**1. Titel**"
      - "### Titel"

    Returnerer liste af (titel, body)-tuples.
    """
    if not tekst:
        return []

    lines = tekst.split("\n")
    sections = []
    current_title = None
    current_body = []

    # Streng header-detektion: linjer der STARTER med tal+punktum (evt. med ##
    # eller ** først). Fleksibel mht. trailing "(2-4 sætninger)" eller "— kommentar".
    is_section_start = re.compile(
        r"^\s*(?:#{1,4}\s+)?"      # evt. ## eller ###
        r"(?:\*\*)?"                # evt. leading **
        r"\d+\.\s+"                 # "1. "
        r"(?:\*\*)?"                # evt. ** før titel
        r"[A-ZÆØÅa-zæøå][^\n]*$"    # titel starter med et bogstav
    )

    def _parse_titel(s):
        """Ryd titel-linjen op til ren tekst."""
        s = s.strip()
        # Fjern leading ## / ###
        s = re.sub(r"^#{1,4}\s+", "", s)
        # Fjern ALLE ** markeringer
        s = s.replace("**", "")
        # Fjern trailing "(parentes-kommentar)"
        s = re.sub(r"\s*\([^)]+\)\s*$", "", s)
        # Fjern trailing "— beskrivelse"
        s = re.sub(r"\s*—\s+.*$", "", s)
        return s.strip()

    # KRITISK: en nummereret linje (fx "1. **Titel**") tæller KUN som
    # top-level sektion-start hvis den enten er først i dokumentet ELLER
    # har en blank linje umiddelbart før. Det forhindrer at nummererede
    # UNDER-punkter (fx "1. Korrekt værelsestype leveret" inde i
    # "Rejseselskabets stillingtagen"-sektionen) bliver fejltolket som
    # nye top-level sektioner — og dermed forskyder hele pillar-strukturen.
    #
    # YDERLIGERE: linjen MÅ IKKE være en lang brødtekst-sætning der
    # tilfældigvis starter med "N.". Vi stiller derfor tre strenge krav
    # til ægte top-level overskrifter:
    #   1) Den indre titel-tekst (uden ## og **) er max ~120 tegn
    #   2) Indeholder IKKE [Bilag-, [Afgørelse- eller [Sag-citationer
    #      (de er ALTID brødtekst, aldrig overskrifter)
    #   3) Indeholder ikke citationstegn ("…") — sætninger med citater
    #      er brødtekst
    def _ligner_aegte_overskrift(linje):
        """Yderligere validering oven på regex-matchet."""
        # Ryd op ligesom _parse_titel
        s = linje.strip()
        s = re.sub(r"^#{1,4}\s+", "", s)
        s = s.replace("**", "").strip()
        # Krav 1: maksimal længde
        if len(s) > 120:
            return False
        # Krav 2: ingen kildehenvisninger
        if re.search(r"\[(Bilag|Afgørelse|Sag|sag)\b", s):
            return False
        # Krav 3: ingen citationstegn
        if '"' in s or '"' in s or '"' in s or '«' in s or '»' in s:
            return False
        # Heuristik: efter at have fjernet det indledende "N. "-prefix
        # (selve sektionsnummeret), hvis den resterende titel indeholder
        # YDERLIGERE sætnings-skift (punkt + mellemrum + stort bogstav)
        # er det en brødsætning, ikke en overskrift.
        s_uden_nr = re.sub(r"^\d+\.\s+", "", s)
        if re.search(r"\.\s+[A-ZÆØÅ]", s_uden_nr):
            return False
        return True

    prev_was_blank = True  # behandl start af dokument som "efter blank linje"
    for line in lines:
        line_is_blank = not line.strip()

        if line_is_blank:
            current_body.append(line)
            prev_was_blank = True
            continue

        ser_ud_som_sektion = (
            bool(is_section_start.match(line))
            and _ligner_aegte_overskrift(line)
        )
        er_top_level = ser_ud_som_sektion and prev_was_blank

        if er_top_level:
            # Afslut forrige sektion
            if current_title is not None:
                sections.append(
                    (current_title, "\n".join(current_body).strip())
                )
            current_title = _parse_titel(line)
            current_body = []
        else:
            current_body.append(line)

        prev_was_blank = False

    # Gem sidste sektion
    if current_title is not None:
        sections.append((current_title, "\n".join(current_body).strip()))
    elif current_body:
        # Ingen sektion-headers fundet — returner hele teksten som én sektion
        sections.append(("Juridisk førstevurdering", "\n".join(current_body).strip()))

    # NB: Safety-net for >8 sektioner er flyttet til
    # render_analyse_som_pillars, så den kan køre EFTER skip-filtrene
    # (resume, referencer, sandsynlighed, konklusion). Ellers kunne
    # filtrerede sektioner fejlagtigt ende i 'Yderligere klagepunkter'.

    return sections


def _markdown_til_html(tekst):
    """
    Simpel markdown → HTML konverter, specialbygget til Claude's analyse-output.
    Håndterer: **bold**, bullets (-, *, •), afsnit.
    Bevarer ` `[citation]`-placeholders så `_highlight_kildehenvisninger` kan
    anvendes bagefter eller før (de bruger unikke markører).
    """
    import html as _html

    if not tekst:
        return ""

    # Midlertidig erstat kildehenvisninger med placeholders så HTML-escaping
    # ikke ødelægger dem. Vi bringer dem tilbage som spans til sidst.
    placeholders = []
    def _save_cite(m):
        placeholders.append(m.group(1))
        return f"\x00CITE{len(placeholders)-1}\x00"
    tekst = re.sub(r"\[([^\[\]]+?)\](?!\()", _save_cite, tekst)

    # Split i blokke (tomme linjer separerer afsnit)
    blokke = re.split(r"\n\s*\n+", tekst.strip())
    html_dele = []

    for blok in blokke:
        linjer = [l.rstrip() for l in blok.split("\n") if l.strip()]
        if not linjer:
            continue

        # Er det en punkt-liste?
        if all(re.match(r"^\s*[-*•]\s+", l) for l in linjer):
            items = []
            for l in linjer:
                indhold = re.sub(r"^\s*[-*•]\s+", "", l)
                indhold = _html.escape(indhold)
                # Bold-konvertering
                indhold = re.sub(
                    r"\*\*([^*\n]+?)\*\*", r"<strong>\1</strong>", indhold
                )
                items.append(f"<li>{indhold}</li>")
            html_dele.append("<ul>" + "".join(items) + "</ul>")
        else:
            # Normalt afsnit — join med mellemrum, konverter bold
            tekst_blok = " ".join(linjer)
            tekst_blok = _html.escape(tekst_blok)
            tekst_blok = re.sub(
                r"\*\*([^*\n]+?)\*\*", r"<strong>\1</strong>", tekst_blok
            )
            html_dele.append(f"<p>{tekst_blok}</p>")

    resultat = "\n".join(html_dele)

    # Bring placeholders tilbage som highlighted citation-spans
    for idx, citation in enumerate(placeholders):
        cite_escaped = _html.escape(citation)
        resultat = resultat.replace(
            f"\x00CITE{idx}\x00",
            f'<span class="analyse-citation">[{cite_escaped}]</span>',
        )

    return resultat


def _highlight_kildehenvisninger(tekst):
    """
    Gør kildehenvisninger som [Bilag 03, s. 1] eller [Afgørelse 19-1467 (2019)]
    visuelt tydelige ved at wrappe dem i en span med særlig styling.

    Markdown-links [text](url) påvirkes IKKE (negativ lookahead for '(').
    """
    if not tekst:
        return tekst
    return re.sub(
        r"\[([^\[\]]+?)\](?!\()",
        r'<span class="analyse-citation">[\1]</span>',
        tekst,
    )


def render_sagsresume(
    resume_dict, accent="#00D4C2", bg="#FDE9EE", nummer=1
):
    """
    Renderer 'Resume af sagen' som en Apple Health-pillar — samme visuelle
    sprog som de øvrige sektioner (farvet pastel baggrund, accent-prik og
    serif-overskrift), men med et struktureret grid indeni der viser
    emne, klagepunkter, klagers krav og TUI's håndtering.

    resume_dict forventes at indeholde nøglerne:
        emne, klagepunkter (liste), krav, tui_handtering

    nummer: heltal — sektion-nummer der prepends til titlen
        (fx "1. Resume af sagen"). Forrige sektioner i siden
        bestemmer hvilket nummer denne får.
    """
    if not resume_dict or not isinstance(resume_dict, dict):
        return

    import html as _html

    emne = _html.escape(str(resume_dict.get("emne") or "").strip())
    krav = _html.escape(str(resume_dict.get("krav") or "").strip())
    tui = _html.escape(str(resume_dict.get("tui_handtering") or "").strip())
    udfald_raw = str(resume_dict.get("forventet_udfald") or "").strip()
    udfald = _html.escape(udfald_raw)
    punkter = resume_dict.get("klagepunkter") or []

    punkter_html = ""
    if punkter:
        punkter_html = "<ul class='sagsresume-liste'>"
        for p in punkter:
            punkter_html += f"<li>{_html.escape(str(p))}</li>"
        punkter_html += "</ul>"
    else:
        punkter_html = (
            "<p class='sagsresume-tom'>Ingen konkrete punkter udledt.</p>"
        )

    # Byg 'Forventet udfald'-blokken som en separat HTML-streng FØR vi
    # bruger den i f-strengen — så Python ikke prøver at evaluere en
    # ikke-eksisterende variabel inde i selve template'n.
    _skjul_udfald = (
        not udfald_raw
        or udfald_raw.lower() in (
            "fremgår ikke",
            "fremgår ikke af grundlaget",
            "vurderingen kunne ikke udledes af analysen",
        )
    )
    if _skjul_udfald:
        udfald_html = ""
    else:
        udfald_html = (
            '<div class="sagsresume-udfald">'
            '<div class="sagsresume-udfald-label">Forventet udfald</div>'
            f'<div class="sagsresume-udfald-tekst">{udfald}</div>'
            '</div>'
        )

    # VIGTIGT: HTML må ikke indrykkes med 4+ mellemrum, ellers opfatter
    # Streamlits markdown-parser linjerne som kodeblokke og renderer
    # </div>-tags som rå tekst.
    html = (
        f'<div class="analyse-pillar" style="--pillar-bg: {bg}; --pillar-accent: {accent};">'
        '<div class="analyse-pillar-accent-dot"></div>'
        f'<h2 class="analyse-pillar-title">{nummer}. Resumé</h2>'
        '<div class="analyse-pillar-body">'
        f'<p class="sagsresume-emne-in-pillar">{emne}</p>'
        '<div class="sagsresume-grid">'
        '<div class="sagsresume-celle">'
        '<div class="sagsresume-celle-titel">Klagepunkter</div>'
        f'<div class="sagsresume-celle-body">{punkter_html}</div>'
        '</div>'
        '<div class="sagsresume-celle">'
        '<div class="sagsresume-celle-titel">Klagers krav</div>'
        f'<div class="sagsresume-celle-body"><p>{krav}</p></div>'
        '</div>'
        '<div class="sagsresume-celle sagsresume-celle-bred">'
        '<div class="sagsresume-celle-titel">TUI\'s håndtering indtil nu</div>'
        f'<div class="sagsresume-celle-body"><p>{tui}</p></div>'
        '</div>'
        '</div>'
        f'{udfald_html}'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_tidslinje(
    tidsforhold,
    accent="#D97706",
    bg="#FEF3C7",
    nummer=2,
):
    """Renderer en kronologisk tidslinje af sagens begivenheder som
    en Apple Health-pillar med vertikal timeline. Hver begivenhed har
    en farvet dot (grøn=positiv for TUI, rød=negativ, grå=neutral),
    dato + evt. tidspunkt, aktør og kort beskrivelse.

    Vises kun når tidsforhold-dictet indeholder begivenheder.
    """
    if not tidsforhold:
        return
    begivenheder = tidsforhold.get("begivenheder") or []
    if not begivenheder:
        return

    import html as _html

    # Eventuel advarsels-banner hvis problematisk forsinkelse
    advarsel_html = ""
    if (
        tidsforhold.get("har_problematisk_forsinkelse")
        and not tidsforhold.get("kunne_ikke_udledes")
    ):
        vurd = _html.escape(
            (tidsforhold.get("samlet_vurdering") or "").strip()
        )
        if vurd:
            advarsel_html = (
                '<div class="tidslinje-advarsel">'
                '<div class="tidslinje-advarsel-titel">'
                '⚠ Reklamationsrettidighed:'
                '</div>'
                f'<div class="tidslinje-advarsel-tekst">{vurd}</div>'
                '</div>'
            )

    # Byg event-liste
    items_html = ""
    for event in begivenheder:
        dato = _html.escape(event.get("dato", "") or "")
        tidspunkt = event.get("tidspunkt")
        tid_html = (
            f'<span class="tidslinje-tid">'
            f'kl. {_html.escape(tidspunkt)}</span>'
            if tidspunkt else ""
        )
        aktoer = _html.escape(event.get("aktoer", "") or "")
        beskrivelse = _html.escape(event.get("beskrivelse", "") or "")
        betydning = event.get("betydning", "neutral")

        # Farvekod dot per betydning
        if betydning == "positiv_for_tui":
            dot_color = "#16A34A"  # grøn
            dot_glow = "rgba(22, 163, 74, 0.25)"
        elif betydning == "negativ_for_tui":
            dot_color = "#DC2626"  # rød
            dot_glow = "rgba(220, 38, 38, 0.25)"
        else:
            dot_color = "#6B7280"  # grå
            dot_glow = "rgba(107, 114, 128, 0.2)"

        items_html += (
            '<div class="tidslinje-item">'
            f'<div class="tidslinje-dot" style="background: {dot_color}; '
            f'box-shadow: 0 0 0 4px {dot_glow};"></div>'
            '<div class="tidslinje-card">'
            '<div class="tidslinje-meta">'
            f'<span class="tidslinje-dato">{dato}</span>'
            f'{tid_html}'
            f'<span class="tidslinje-aktoer">{aktoer}</span>'
            '</div>'
            f'<div class="tidslinje-beskrivelse">{beskrivelse}</div>'
            '</div>'
            '</div>'
        )

    html_out = (
        f'<div class="analyse-pillar" style="--pillar-bg: {bg}; '
        f'--pillar-accent: {accent};">'
        '<div class="analyse-pillar-accent-dot"></div>'
        f'<h2 class="analyse-pillar-title">{nummer}. '
        'Tidslinje over sagens begivenheder</h2>'
        '<div class="analyse-pillar-body">'
        f'{advarsel_html}'
        '<div class="tidslinje-container">'
        f'{items_html}'
        '</div>'
        '</div>'
        '</div>'
    )
    st.markdown(html_out, unsafe_allow_html=True)


def render_analyse_som_pillars(
    svar_tekst,
    skip_resume=False,
    skip_referencer=False,
    skip_sandsynlighed=False,
    skip_konklusion=False,
    start_nummer=1,
    inject_after_titel=None,
):
    """
    Renderer en juridisk analyse som Apple-Health-inspirerede "pillars"
    med farvede baggrunde per sektion, store serif-overskrifter, og
    fremhævede kildehenvisninger.

    Optional skip-flags fjerner sektioner der vises andre steder, så vi
    undgår duplikeret indhold:
      skip_resume        — hvis det strukturerede sagsresume vises separat
      skip_referencer    — hvis referencer vises som visuelle kort separat
      skip_sandsynlighed — hvis udfalds-dashboardet allerede vises øverst
      skip_konklusion    — hvis konklusion-en-linje vises i sagsresume-kortet

    start_nummer: heltal — det første sektion-nummer der bruges i denne
        render. Bruges til at fortsætte sekvensen fra de pillars der
        renderes ovenfor (resume, referencer osv.) — så hele siden har
        konsekutiv 1, 2, 3, 4, 5... nummering på tværs af kald.

    inject_after_titel: dict eller None — hvis sat skal nøglerne være
        substrings (case-insensitive) som matches mod sektions-titlerne.
        Værdien er en callable der køres LIGE EFTER den matchende sektion
        er rendret — bruges fx til at indsætte 'Relevante referencer'
        som fast under-blok efter 'Kort juridisk vurdering'. Hver callable
        kaldes uden argumenter og forventes selv at rendre via st.*.
    """
    if not svar_tekst:
        return

    sektioner = _split_analyse_i_sektioner(svar_tekst)

    def _matcher_nogleord(titel, nogleord_liste):
        t = (titel or "").lower()
        return any(n in t for n in nogleord_liste)

    filtreret = []
    for idx, (titel, body) in enumerate(sektioner):
        # Resume fjernes KUN hvis det er den første sektion (så vi ikke
        # ved et uheld skjuler en anden sektion der tilfældigvis har
        # 'resume' i overskriften).
        if skip_resume and idx == 0 and _matcher_nogleord(titel, (
            "resume", "resumé", "opsummering", "oversigt",
        )):
            continue
        if skip_referencer and _matcher_nogleord(titel, (
            "relevante referencer", "referencer", "præcedens",
        )):
            continue
        if skip_sandsynlighed and _matcher_nogleord(titel, (
            "sandsynlighedsvurdering", "sandsynlighed",
        )):
            continue
        if skip_konklusion and _matcher_nogleord(titel, (
            "konklusion", "afsluttende vurdering",
        )):
            continue
        filtreret.append((titel, body))

    sektioner = filtreret

    # SAFETY-NET: Hvis AI'en alligevel har lavet >8 top-level sektioner
    # EFTER skip-filtreringen, er det med stor sandsynlighed en fejl
    # (klagepunkter splittet ud som egne sektioner). Slå de overskydende
    # sammen i én "Yderligere klagepunkter"-sektion. Vi sætter grænsen
    # ved 8 så der er plads til de 6 låste pillars + lidt luft til
    # legitime ekstra-sektioner. Vigtigt: skip-filtrene har allerede
    # kørt, så vi merger KUN ægte indholds-sektioner.
    MAX_SEKTIONER_EFTER_SKIP = 8
    if len(sektioner) > MAX_SEKTIONER_EFTER_SKIP:
        beholdt = sektioner[:MAX_SEKTIONER_EFTER_SKIP - 1]
        overflødige = sektioner[MAX_SEKTIONER_EFTER_SKIP - 1:]
        sammenfletning = []
        for titel, body in overflødige:
            sammenfletning.append(
                f"- **{titel}**" + (f": {body}" if body else "")
            )
        beholdt.append((
            "Yderligere klagepunkter og detaljer",
            "\n".join(sammenfletning),
        ))
        sektioner = beholdt

    for i, (titel, body) in enumerate(sektioner):
        accent, bg = _PILLAR_PALETTER[i % len(_PILLAR_PALETTER)]

        # Escape titel så specialtegn ikke bryder HTML.
        # Strip eventuelt eksisterende leading nummer fra titlen
        # (fx hvis AI'en allerede har skrevet "1. Klagens kernepunkter")
        # — vi prepender vores eget konsekutive nummer i stedet.
        import html as _html
        titel_uden_nummer = re.sub(
            r"^\s*\d+\.\s*", "", (titel or "")
        )
        titel_safe = _html.escape(titel_uden_nummer)
        sektion_nummer = start_nummer + i

        # Body konverteres fra markdown til HTML (med citation-spans)
        body_html = _markdown_til_html(body)

        st.markdown(
            f"""
            <div class="analyse-pillar"
                 style="
                    --pillar-bg: {bg};
                    --pillar-accent: {accent};
                 ">
                <div class="analyse-pillar-accent-dot"></div>
                <h2 class="analyse-pillar-title">{sektion_nummer}. {titel_safe}</h2>
                <div class="analyse-pillar-body">{body_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Inject-callback hvis denne sektions titel matcher en af de
        # angivne nøgler (case-insensitive substring match). Bruges fx
        # til at indsætte 'Relevante referencer' som fast under-blok
        # efter 'Kort juridisk vurdering'.
        if inject_after_titel:
            titel_lower = (titel or "").lower()
            for nogle_substring, callback in inject_after_titel.items():
                if nogle_substring.lower() in titel_lower:
                    try:
                        callback()
                    except Exception as _e:
                        # Defensivt — en callback-fejl må ikke vælte
                        # rendering af de øvrige sektioner.
                        print(
                            f"DEBUG: inject_after_titel-callback for "
                            f"'{nogle_substring}' fejlede: {_e}"
                        )
                    break


def render_svarbrev_forside_preview(
    sagsnummer="",
    klagers_navn="",
    hoeringssvar_nr=1,
    bilag_liste=None,
    profil_by="",
    logo_b64=None,
):
    """
    Renderer en HTML-approksimation af svarbrevets FORSIDE — det vil
    sige headeren med modtager-adresse, logo, by/dato, Vedr-linje og
    bilag-liste. Bruges som preview lige over selve brødteksten i
    svarbrev-sektionen, så brugeren kan se hvordan downloaden kommer
    til at se ud før de trykker download.

    Layoutet matcher (visuelt — ikke pixel-perfekt) det docx-output som
    eksport.svarbrev_til_docx producerer:
      • PAKKEREJSE-ANKENÆVNETs adresse i top-venstre
      • Selskabs-logo i top-højre (hvis logo_b64 er angivet)
      • Højrejusteret 'By, DD-MM-YYYY' nedenunder
      • 'Vedr.: Sag nr. X – Klagernavn, N. høringssvar' med vandret streg
      • 'Bilag:'-overskrift + 2-kolonne-liste (hvis bilag_liste er udfyldt)

    Parametre:
      sagsnummer       — fx "25-109-8024327" (kan være tom)
      klagers_navn     — fx "Laura Stephanie Uhler" (kan være tom)
      hoeringssvar_nr  — 1, 2 eller 3
      bilag_liste      — list of dicts {"bogstav": "A", "overskrift": "..."}
      profil_by        — fx "Frederiksberg"
      logo_b64         — base64-string (uden 'data:image/png;base64,'-prefix)
                         eller None hvis intet logo
    """
    import html as _html
    from datetime import datetime as _dt

    # Byg Vedr-linjen ud fra de angivne felter
    vedr_dele = ["Vedr.: "]
    if sagsnummer:
        vedr_dele.append(f"Sag nr. {_html.escape(sagsnummer)}")
    if klagers_navn:
        if sagsnummer:
            vedr_dele.append(f" – {_html.escape(klagers_navn)}")
        else:
            vedr_dele.append(_html.escape(klagers_navn))
    if hoeringssvar_nr:
        vedr_dele.append(
            f", {_html.escape(str(hoeringssvar_nr))}. høringssvar"
        )
    vedr_html = "".join(vedr_dele)

    # By + dato (samme format som docx-eksporten)
    by_safe = _html.escape(profil_by or "")
    dato_str = _dt.now().strftime("%d-%m-%Y")
    by_dato = (
        f"{by_safe}, {dato_str}" if by_safe else dato_str
    )

    # Logo: indlejret som base64-img hvis tilgængeligt, ellers placeholder
    if logo_b64:
        logo_html = (
            f'<img src="data:image/png;base64,{logo_b64}" '
            'alt="Selskabs-logo" style="max-width: 150px; '
            'max-height: 70px; height: auto;" />'
        )
    else:
        logo_html = (
            '<div style="color: #9CA3AF; font-size: 0.78rem; '
            'font-style: italic; padding: 8px;">'
            '[Selskabs-logo vises i Word-filen når '
            'static/logos/-filen er på plads]</div>'
        )

    # Bilag-liste (kun hvis der er bilag)
    bilag_html = ""
    if bilag_liste:
        rows_html = ""
        for post in bilag_liste:
            bogstav = _html.escape(str(post.get("bogstav", "")))
            overskrift = _html.escape(str(post.get("overskrift", "")))
            rows_html += (
                f'<tr>'
                f'<td style="padding: 4px 16px 4px 0; font-weight: 600; '
                f'white-space: nowrap; vertical-align: top; '
                f'color: #1F2937;">Bilag {bogstav}</td>'
                f'<td style="padding: 4px 0; color: #1F2937;">'
                f'{overskrift}</td>'
                f'</tr>'
            )
        bilag_html = (
            '<div style="margin-top: 24px;">'
            '<div style="font-weight: 700; font-size: 1rem; '
            'color: #1F2937; margin-bottom: 8px;">Bilag:</div>'
            '<table style="border-collapse: collapse; width: 100%;">'
            f'{rows_html}'
            '</table>'
            '</div>'
        )

    # Hele forsiden
    st.markdown(
        f"""
        <div style="
            background: #FAFAFA;
            border: 1px solid #E5E7EB;
            border-radius: 12px;
            padding: 28px 32px 24px 32px;
            margin: 8px 0 16px 0;
            font-family: 'Calibri', -apple-system, BlinkMacSystemFont, sans-serif;
        ">
            <div style="
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                gap: 24px;
                margin-bottom: 8px;
            ">
                <div style="flex: 1 1 60%; line-height: 1.5;">
                    <div style="font-weight: 700; font-size: 1.02rem;
                                color: #111827;">
                        PAKKEREJSE-ANKENÆVNET
                    </div>
                    <div style="color: #1F2937;">
                        Haldor Topsøes Alle 1, Bygning 91
                    </div>
                    <div style="color: #1F2937;">2800 Kgs. Lyngby</div>
                </div>
                <div style="flex: 0 0 auto; text-align: right;">
                    {logo_html}
                </div>
            </div>
            <div style="
                text-align: right;
                margin-top: 36px;
                font-size: 1rem;
                color: #1F2937;
            ">{by_dato}</div>
            <div style="
                margin-top: 28px;
                font-weight: 700;
                font-size: 1rem;
                color: #111827;
                padding-bottom: 6px;
                border-bottom: 1px solid #111827;
            ">{vedr_html}</div>
            {bilag_html}
            <div style="
                margin-top: 22px;
                color: #6B7280;
                font-size: 0.78rem;
                font-style: italic;
                text-align: center;
                border-top: 1px dashed #E5E7EB;
                padding-top: 12px;
            ">
                Forside-preview — sådan vil headeren se ud i den
                downloadede Word-fil. Brødteksten vises nedenunder.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
