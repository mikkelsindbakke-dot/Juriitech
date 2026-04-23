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

    # Fjern markdown-markører så regex er mere robust
    ren = re.sub(r"\*{1,3}", "", tekst)

    # FULD MEDHOLD — fang mange variationer:
    # "fuld medhold til klager: 30%", "fuldt medhold: 30 %", "Fuld medhold: 30 pct"
    patterns_fuld = [
        r"fuld(?:t|\s+)?\s+medhold(?:\s+til\s+klage(?:r|n))?[^0-9\n]{0,40}(\d{1,3})\s*(?:%|pct|procent)",
        r"(\d{1,3})\s*(?:%|pct|procent)[^0-9\n]{0,20}fuld(?:t|\s+)?\s+medhold",
    ]
    for p in patterns_fuld:
        m = re.search(p, ren, re.IGNORECASE)
        if m:
            resultat["fuld_medhold"] = int(m.group(1))
            break

    # DELVIST MEDHOLD
    patterns_delvist = [
        r"delvis(?:t|\s+)?\s+medhold(?:\s+til\s+klage(?:r|n))?[^0-9\n]{0,40}(\d{1,3})\s*(?:%|pct|procent)",
        r"(\d{1,3})\s*(?:%|pct|procent)[^0-9\n]{0,20}delvis(?:t|\s+)?\s+medhold",
    ]
    for p in patterns_delvist:
        m = re.search(p, ren, re.IGNORECASE)
        if m:
            resultat["delvist_medhold"] = int(m.group(1))
            break

    # AFVISNING
    patterns_afvist = [
        r"afvis(?:ning|t)(?:\s+af\s+klage(?:n|r)?)?[^0-9\n]{0,50}(\d{1,3})\s*(?:%|pct|procent)",
        r"(\d{1,3})\s*(?:%|pct|procent)[^0-9\n]{0,20}afvis(?:ning|t)",
    ]
    for p in patterns_afvist:
        m = re.search(p, ren, re.IGNORECASE)
        if m:
            resultat["afvist"] = int(m.group(1))
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


def vis_dashboard(svar_tekst):
    """
    Viser et visuelt dashboard med de tre sandsynligheder.
    Kaldes før selve AI-svaret renderes.

    Returnerer True hvis dashboard blev vist, False hvis parsing fejlede.
    """
    s = parse_sandsynligheder(svar_tekst)
    if not s["fandt_alle_tre"]:
        return False

    fuld = s["fuld_medhold"]
    delvist = s["delvist_medhold"]
    afvist = s["afvist"]

    mest_key, mest_pct, mest_label = _mest_sandsynlige(s)

    # Farvekodning — set fra rejseselskabets perspektiv:
    #   afvist (godt for TUI) = grøn
    #   delvist medhold = gul
    #   fuld medhold (dårligt for TUI) = rød
    if mest_key == "afvist":
        banner_farve = "#1E8449"   # grøn
        banner_ikon = ""
        strategi = "Gode udsigter. Byg forsvaret stærkt — dokumentér at kravet ikke er berettiget."
    elif mest_key == "delvist_medhold":
        banner_farve = "#CA8A04"   # gul/orange
        banner_ikon = ""
        strategi = "Blandet billede. Overvej et forligstilbud der afspejler det forventede delvise udfald."
    else:
        banner_farve = "#B91C1C"   # rød
        banner_ikon = ""
        strategi = "Risiko for fuldt medhold. Overvej forligstilbud og stærkt fokus på formildende forhold."

    # Øverste banner
    st.markdown(
        f"""
        <div style="
            background-color: {banner_farve};
            color: white;
            padding: 16px 20px;
            border-radius: 8px;
            margin-bottom: 16px;
        ">
            <div style="font-size: 0.85em; opacity: 0.9; letter-spacing: 0.08em;">
                MEST SANDSYNLIGE UDFALD
            </div>
            <div style="font-size: 1.6em; font-weight: bold; margin-top: 4px;">
                {mest_label} — {mest_pct} %
            </div>
            <div style="font-size: 0.9em; opacity: 0.95; margin-top: 8px;">
                Anbefalet strategi: {strategi}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Tre procent-metrics side om side
    k1, k2, k3 = st.columns(3)

    with k1:
        st.metric(
            "Fuld medhold til klager",
            f"{fuld} %",
            help="Sandsynlighed for at klageren får fuldt medhold og fuld kompensation",
        )
        st.progress(fuld / 100 if fuld else 0.0)

    with k2:
        st.metric(
            "Delvist medhold til klager",
            f"{delvist} %",
            help="Sandsynlighed for at nævnet tilkender delvis kompensation",
        )
        st.progress(delvist / 100 if delvist else 0.0)

    with k3:
        st.metric(
            "Afvisning af klagen",
            f"{afvist} %",
            help="Sandsynlighed for at nævnet afviser klagen — rejseselskabet får fuldt medhold",
        )
        st.progress(afvist / 100 if afvist else 0.0)

    # Tjek at det summer til ~100 (tolerance for afrunding)
    sum_pct = fuld + delvist + afvist
    if sum_pct < 95 or sum_pct > 105:
        st.caption(
            f"⚠️ De tre procenter summer til {sum_pct} % (bør være ~100). "
            "Tjek den fulde begrundelse nedenfor."
        )

    return True
