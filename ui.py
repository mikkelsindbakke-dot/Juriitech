"""
Custom UI-komponenter til Juriitech.

Indeholder:
  - thinking(): Claude-inspireret pulsende gradient-prik som spinner
  - render_analyse_som_pillars(): Apple-Health-inspireret pillar-layout
    for den juridiske førstevurdering
"""

import re
from contextlib import contextmanager

import streamlit as st


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
            _components_html(widget_html, height=84)
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

    for line in lines:
        if is_section_start.match(line):
            # Afslut forrige sektion
            if current_title is not None:
                sections.append((current_title, "\n".join(current_body).strip()))
            current_title = _parse_titel(line)
            current_body = []
        else:
            current_body.append(line)

    # Gem sidste sektion
    if current_title is not None:
        sections.append((current_title, "\n".join(current_body).strip()))
    elif current_body:
        # Ingen sektion-headers fundet — returner hele teksten som én sektion
        sections.append(("Juridisk førstevurdering", "\n".join(current_body).strip()))

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


def render_sagsresume(resume_dict):
    """
    Renderer et kompakt 'Resume af sagen'-kort med fire felter:
    emne, klagepunkter, krav og TUI's håndtering. Designet til at blive
    placeret umiddelbart efter førstevurderingen så juristen lynhurtigt
    kan fange essensen af sagen uden at læse hele analysen.

    resume_dict forventes at indeholde nøglerne:
        emne, klagepunkter (liste), krav, tui_handtering
    """
    if not resume_dict or not isinstance(resume_dict, dict):
        return

    import html as _html

    emne = _html.escape(str(resume_dict.get("emne") or "").strip())
    krav = _html.escape(str(resume_dict.get("krav") or "").strip())
    tui = _html.escape(str(resume_dict.get("tui_handtering") or "").strip())
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

    st.markdown(
        f"""
        <div class="sagsresume-kort">
            <div class="sagsresume-header">
                <span class="sagsresume-label">Resume af sagen</span>
                <span class="sagsresume-hint">Lynoverblik</span>
            </div>
            <div class="sagsresume-emne">{emne}</div>
            <div class="sagsresume-grid">
                <div class="sagsresume-celle">
                    <div class="sagsresume-celle-titel">Klagepunkter</div>
                    <div class="sagsresume-celle-body">{punkter_html}</div>
                </div>
                <div class="sagsresume-celle">
                    <div class="sagsresume-celle-titel">Klagers krav</div>
                    <div class="sagsresume-celle-body"><p>{krav}</p></div>
                </div>
                <div class="sagsresume-celle sagsresume-celle-bred">
                    <div class="sagsresume-celle-titel">TUI's håndtering indtil nu</div>
                    <div class="sagsresume-celle-body"><p>{tui}</p></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_analyse_som_pillars(svar_tekst, skip_resume=False):
    """
    Renderer en juridisk analyse som Apple-Health-inspirerede "pillars"
    med farvede baggrunde per sektion, store serif-overskrifter, og
    fremhævede kildehenvisninger.

    skip_resume: hvis True, springes den første sektion over hvis den
    ligner et resume (overskrift starter med 'resume', 'kort resume',
    'opsummering', 'oversigt'). Bruges når det strukturerede sagsresume
    allerede vises separat, så vi undgår dobbelt-indhold.
    """
    if not svar_tekst:
        return

    sektioner = _split_analyse_i_sektioner(svar_tekst)

    # Evt. skip første sektion hvis den er et resume
    if skip_resume and sektioner:
        foerste_titel = (sektioner[0][0] or "").lower()
        if any(nogleord in foerste_titel for nogleord in (
            "resume", "resumé", "opsummering", "oversigt"
        )):
            sektioner = sektioner[1:]

    for i, (titel, body) in enumerate(sektioner):
        accent, bg = _PILLAR_PALETTER[i % len(_PILLAR_PALETTER)]

        # Escape titel så specialtegn ikke bryder HTML
        import html as _html
        titel_safe = _html.escape(titel)

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
                <h2 class="analyse-pillar-title">{titel_safe}</h2>
                <div class="analyse-pillar-body">{body_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
