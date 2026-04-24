"""
Udtrækker og viser den juridiske sandsynlighedsvurdering fra Claudes analyse.

Claude genererer i hver analyse tre procenter der summer til 100:
  - Fuld medhold til klager
  - Delvist medhold til klager
  - Afvisning af klagen (fuld medhold til rejseselskabet)

Her parser vi dem ud af markdown-svaret og viser dem som et visuelt
dashboard øverst i analysen.
"""

import re

import streamlit as st


def parse_sandsynligheder(tekst):
    """
    Udtrækker de tre sandsynligheder fra AI-analyse-teksten.
    Returnerer en dict:
      {"fuld_medhold": int, "delvist_medhold": int, "afvist": int,
       "fandt_alle_tre": bool}

    Hvis en eller flere procenter ikke kan findes, sættes de til None
    og fandt_alle_tre = False. I så fald kan UI'et vælge at skjule
    dashboard'et.
    """
    if not tekst:
        return {
            "fuld_medhold": None,
            "delvist_medhold": None,
            "afvist": None,
            "fandt_alle_tre": False,
        }

    resultat = {"fuld_medhold": None, "delvist_medhold": None, "afvist": None}

    # Normaliser: fjern markdown-markører, konvertér kolon til mellemrum,
    # sørg for ensartet whitespace
    ren = re.sub(r"\*{1,3}", "", tekst)
    ren = re.sub(r"[–—]", "-", ren)  # forskellige bindestreger → standard

    # FULD MEDHOLD — utroligt permissiv
    patterns_fuld = [
        r"fuld(?:t|\s+)?\s+medhold(?:\s+til\s+klage(?:r|n))?[^0-9\n]{0,60}(\d{1,3})\s*(?:%|pct\.?|procent)",
        r"(\d{1,3})\s*(?:%|pct\.?|procent)[^0-9\n]{0,30}fuld(?:t|\s+)?\s+medhold",
        r"fuld(?:t|\s+)?\s+medhold[^\n]*?:\s*(\d{1,3})",
        r"fuld(?:t|\s+)?\s+medhold.{0,80}?(\d{1,3})",
    ]
    for p in patterns_fuld:
        m = re.search(p, ren, re.IGNORECASE | re.DOTALL)
        if m:
            val = int(m.group(1))
            if 0 <= val <= 100:
                resultat["fuld_medhold"] = val
                break

    # DELVIST MEDHOLD
    patterns_delvist = [
        r"delvis(?:t|\s+)?\s+medhold(?:\s+til\s+klage(?:r|n))?[^0-9\n]{0,60}(\d{1,3})\s*(?:%|pct\.?|procent)",
        r"(\d{1,3})\s*(?:%|pct\.?|procent)[^0-9\n]{0,30}delvis(?:t|\s+)?\s+medhold",
        r"delvis(?:t|\s+)?\s+medhold[^\n]*?:\s*(\d{1,3})",
        r"delvis(?:t|\s+)?\s+medhold.{0,80}?(\d{1,3})",
    ]
    for p in patterns_delvist:
        m = re.search(p, ren, re.IGNORECASE | re.DOTALL)
        if m:
            val = int(m.group(1))
            if 0 <= val <= 100:
                resultat["delvist_medhold"] = val
                break

    # AFVISNING
    patterns_afvist = [
        r"afvis(?:ning|t|else)(?:\s+af\s+klage(?:n|r)?)?[^0-9\n]{0,70}(\d{1,3})\s*(?:%|pct\.?|procent)",
        r"(\d{1,3})\s*(?:%|pct\.?|procent)[^0-9\n]{0,30}afvis(?:ning|t|else)",
        r"afvis(?:ning|t|else)[^\n]*?:\s*(\d{1,3})",
        r"afvis(?:ning|t|else).{0,80}?(\d{1,3})",
    ]
    for p in patterns_afvist:
        m = re.search(p, ren, re.IGNORECASE | re.DOTALL)
        if m:
            val = int(m.group(1))
            if 0 <= val <= 100:
                resultat["afvist"] = val
                break

    resultat["fandt_alle_tre"] = all(
        resultat[k] is not None
        for k in ("fuld_medhold", "delvist_medhold", "afvist")
    )

    return resultat


def _mest_sandsynlige(sandsynligheder):
    """Returnerer ('fuld_medhold'|'delvist_medhold'|'afvist', procent, label)."""
    kandidater = [
        ("fuld_medhold", sandsynligheder.get("fuld_medhold") or 0, "FULD MEDHOLD TIL KLAGER"),
        ("delvist_medhold", sandsynligheder.get("delvist_medhold") or 0, "DELVIST MEDHOLD"),
        ("afvist", sandsynligheder.get("afvist") or 0, "AFVISNING AF KLAGEN"),
    ]
    kandidater.sort(key=lambda x: x[1], reverse=True)
    return kandidater[0]


def _render_fallback_dashboard():
    """
    Render et neutralt dashboard når procenter ikke kan udledes.
    Bruges så sektionen ALTID viser noget meningsfuldt.
    """
    st.markdown(
        """
        <div style="
            background-color: #F3F4F6;
            color: #1F2937;
            padding: 14px 18px;
            border-radius: 8px;
            margin-bottom: 16px;
            border-left: 4px solid #6B7280;
        ">
            <div style="font-size: 0.85em; opacity: 0.85;">
                UDFALDSVURDERING
            </div>
            <div style="font-size: 1.1em; font-weight: 600; margin-top: 4px;">
                Procentfordelingen fremgår af den fulde juridiske vurdering nedenfor
            </div>
            <div style="font-size: 0.9em; margin-top: 8px; opacity: 0.85;">
                juriitech PAX kunne ikke udlede tre præcise procenter fra sagen —
                sandsynligvis fordi materialet er for sparsomt eller udfaldet
                usædvanligt. Læs analysen og sammenhold med relevante afgørelser.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def vis_dashboard(svar_tekst, struktureret_data=None):
    """
    Viser et visuelt dashboard med de tre sandsynligheder.

    struktureret_data (valgfri): dict med nøglerne 'fuld_medhold',
    'delvist_medhold', 'afvist'. Hvis angivet bruges disse i stedet for
    at parse teksten — det betyder dashboardet altid kan vises selv hvis
    regex-parsingen fejler.

    Returnerer True ved fuldt dashboard, False ved fallback.
    """
    if (
        struktureret_data
        and all(
            k in struktureret_data and struktureret_data[k] is not None
            for k in ("fuld_medhold", "delvist_medhold", "afvist")
        )
    ):
        s = {
            "fuld_medhold": int(struktureret_data["fuld_medhold"]),
            "delvist_medhold": int(struktureret_data["delvist_medhold"]),
            "afvist": int(struktureret_data["afvist"]),
            "fandt_alle_tre": True,
        }
    else:
        s = parse_sandsynligheder(svar_tekst)
    if not s["fandt_alle_tre"]:
        # Fallback: altid vis noget i stedet for at skjule sektionen helt
        _render_fallback_dashboard()
        return False

    fuld = s["fuld_medhold"]
    delvist = s["delvist_medhold"]
    afvist = s["afvist"]

    mest_key, mest_pct, mest_label = _mest_sandsynlige(s)

    # Farvekodning — bruger samme pastel-palette som videnstank-sidebaren:
    #   afvist (godt for TUI)      = mint/grøn  (#E7F5DD / #76D672)
    #   delvist medhold            = peach/gul  (#FDEFD7 / #F59E0B)
    #   fuld medhold (dårligt)     = rose/rød   (#FDE9EE / #EC4899)
    FARVER = {
        "fuld_medhold": {
            "bg": "#FDE9EE",
            "accent": "#EC4899",
            "progress": "#EC4899",
        },
        "delvist_medhold": {
            "bg": "#FDEFD7",
            "accent": "#F59E0B",
            "progress": "#F59E0B",
        },
        "afvist": {
            "bg": "#E7F5DD",
            "accent": "#76D672",
            "progress": "#76D672",
        },
    }

    if mest_key == "afvist":
        strategi = "Gode udsigter. Byg forsvaret stærkt — dokumentér at kravet ikke er berettiget."
    elif mest_key == "delvist_medhold":
        strategi = "Blandet billede. Overvej et forligstilbud der afspejler det forventede delvise udfald."
    else:
        strategi = "Risiko for fuldt medhold. Overvej forligstilbud og stærkt fokus på formildende forhold."

    banner_bg = FARVER[mest_key]["bg"]
    banner_accent = FARVER[mest_key]["accent"]

    # Øverste banner — lys pastel baggrund med accent-stribe, matcher
    # resten af forsidens Apple Health-æstetik
    st.markdown(
        f"""
        <div style="
            background-color: {banner_bg};
            color: #111827;
            padding: 18px 22px;
            border-radius: 14px;
            margin-bottom: 16px;
            border-left: 4px solid {banner_accent};
        ">
            <div style="font-size: 0.78rem; color: rgba(71, 85, 105, 0.8);
                 letter-spacing: 0.12em; font-weight: 600;
                 text-transform: uppercase;">
                Mest sandsynlige udfald
            </div>
            <div style="font-size: 1.55rem; font-weight: 700; margin-top: 6px;
                 letter-spacing: -0.015em; color: #0F172A;
                 font-family: 'Source Serif 4', Georgia, serif;">
                {mest_label} — {mest_pct} %
            </div>
            <div style="font-size: 0.92rem; color: #334155; margin-top: 8px;">
                <strong>Anbefalet strategi:</strong> {strategi}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Tre procent-kort side om side — hver med sin pastelfarve
    def _render_udfalds_kort(titel, pct, key):
        farver = FARVER[key]
        progress_width = max(0, min(100, pct or 0))
        st.markdown(
            f"""
            <div style="
                background-color: {farver['bg']};
                border-radius: 12px;
                padding: 14px 16px;
                border: 1px solid rgba(17, 24, 39, 0.04);
                margin-bottom: 6px;
            ">
                <div style="font-size: 0.76rem; color: rgba(71, 85, 105, 0.85);
                     font-weight: 600; letter-spacing: 0.04em;
                     text-transform: uppercase;">
                    {titel}
                </div>
                <div style="font-size: 1.8rem; font-weight: 800;
                     color: {farver['accent']}; line-height: 1.1;
                     letter-spacing: -0.02em; margin-top: 4px;
                     font-variant-numeric: tabular-nums;">
                    {pct} %
                </div>
                <div style="background: rgba(255, 255, 255, 0.6);
                     border-radius: 100px; height: 6px; margin-top: 10px;
                     overflow: hidden;">
                    <div style="background: {farver['progress']};
                         width: {progress_width}%; height: 100%;
                         border-radius: 100px;"></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    k1, k2, k3 = st.columns(3)
    with k1:
        _render_udfalds_kort("Fuld medhold til klager", fuld, "fuld_medhold")
    with k2:
        _render_udfalds_kort("Delvist medhold til klager", delvist, "delvist_medhold")
    with k3:
        _render_udfalds_kort("Afvisning af klagen", afvist, "afvist")

    # Tjek at det summer til ~100 (tolerance for afrunding)
    sum_pct = fuld + delvist + afvist
    if sum_pct < 95 or sum_pct > 105:
        st.caption(
            f"⚠️ De tre procenter summer til {sum_pct} % (bør være ~100). "
            "Tjek den fulde begrundelse nedenfor."
        )

    return True
