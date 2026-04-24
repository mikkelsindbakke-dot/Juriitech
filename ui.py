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
def thinking(tekst="juriitech PAX arbejder..."):
    """
    Context manager der viser en Claude-inspireret pulsende gradient-prik
    med tekst ved siden af, mens kode i with-blokken kører. Forsvinder
    automatisk når blokken er færdig.
    """
    placeholder = st.empty()
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


def render_analyse_som_pillars(svar_tekst):
    """
    Renderer en juridisk analyse som Apple-Health-inspirerede "pillars"
    med farvede baggrunde per sektion, store serif-overskrifter, og
    fremhævede kildehenvisninger.
    """
    if not svar_tekst:
        return

    sektioner = _split_analyse_i_sektioner(svar_tekst)
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
