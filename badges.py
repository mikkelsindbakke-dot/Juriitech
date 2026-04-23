"""
Badge-komponent i Notion/Apple Health-stil + dato-udledning.

Lille farvet tag der vises inline for hurtigt at kommunikere status,
plus en helper der prøver at udlede afgørelsesdatoen fra dokumentets
egen tekst.
"""

import re


DANSKE_MAANEDER = {
    "januar": 1, "februar": 2, "marts": 3, "april": 4,
    "maj": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def udled_afgoerelsesdato(indhold, filnavn=None):
    """
    Forsøger at udlede afgørelsesdatoen fra dokumentets indhold.
    Returnerer en formateret streng (fx "15-03-2024" eller "2024"),
    eller None hvis intet kan findes.

    Strategier i rækkefølge:
      1. "den DD. måned YYYY" (fx "den 15. marts 2024")
      2. "den DD.MM.YYYY" eller "den DD/MM/YYYY"
      3. Løs "DD.MM.YYYY" i de første 3000 tegn
      4. År fra filnavn (fx "24-290.pdf" -> 2024)
    """
    uddrag = (indhold or "")[:3000]

    # 1. "den 15. marts 2024"
    m = re.search(
        r"den\s+(\d{1,2})\.\s*(januar|februar|marts|april|maj|juni|juli|"
        r"august|september|oktober|november|december)\s+(\d{4})",
        uddrag,
        re.IGNORECASE,
    )
    if m:
        dag = int(m.group(1))
        maaned = DANSKE_MAANEDER[m.group(2).lower()]
        aar = int(m.group(3))
        return f"{dag:02d}-{maaned:02d}-{aar}"

    # 2. "den 15.03.2024" / "den 15-03-2024" / "den 15/03/2024"
    m = re.search(r"den\s+(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})", uddrag)
    if m:
        return f"{int(m.group(1)):02d}-{int(m.group(2)):02d}-{m.group(3)}"

    # 3. Generel "DD.MM.YYYY" i de første par tusinde tegn
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", uddrag)
    if m:
        # Sanity check på dag og måned
        dag = int(m.group(1))
        maaned = int(m.group(2))
        if 1 <= dag <= 31 and 1 <= maaned <= 12:
            return f"{dag:02d}-{maaned:02d}-{m.group(3)}"

    # 4. Fallback: år fra filnavn (fx "24-290.pdf" → 2024)
    if filnavn:
        m = re.match(r"(\d{2})-\d+", filnavn)
        if m:
            aar_kort = int(m.group(1))
            aar = (1900 + aar_kort) if aar_kort >= 50 else (2000 + aar_kort)
            return str(aar)

    return None


# Tilgængelige badge-farver — matcher CSS-klasserne i app.py
FARVER = ("green", "red", "yellow", "blue", "gray", "purple")


def badge(tekst, farve="gray"):
    """Returnerer HTML for et badge. Brug med unsafe_allow_html=True."""
    if farve not in FARVER:
        farve = "gray"
    return f'<span class="badge badge-{farve}">{tekst}</span>'


def flere_badges(liste):
    """Returnerer HTML for flere badges ved siden af hinanden.
    liste = [(tekst, farve), (tekst, farve), ...]"""
    return "".join(badge(t, f) for t, f in liste)


def udfalds_badge_fra_tekst(tekst):
    """
    Forsøger automatisk at udlede udfaldet af en afgørelse ud fra indholdet.
    Returnerer et badge (tekst + farve) der passer til udfaldet, eller None
    hvis det ikke kan udledes.
    """
    if not tekst:
        return None
    t = tekst.lower()[:4000]  # kig kun i starten for hastighed

    # Klar markering af afvisning (giv prioritet da den oftest står eksplicit)
    if re.search(r"(kan ikke tages til følge|tages ikke til følge|afvises)", t):
        return ("Afvist", "green")  # afvisning = godt for rejseselskabet

    # Fuld medhold til klager
    if re.search(r"fuld\s*medhold|klager\s+tilkendes\s+det\s+fulde", t):
        return ("Fuld medhold klager", "red")

    # Delvist medhold
    if re.search(r"delvis(?:t)?\s+medhold|tilkendes\s+.*kr\b", t):
        return ("Delvist medhold", "yellow")

    return None


def doktype_badge(dokumenttype):
    """Badge for dokumenttypen — afgørelse, klage, vilkår."""
    if dokumenttype == "afgoerelse":
        return badge("Afgørelse", "purple")
    if dokumenttype == "klage":
        return badge("Klage", "blue")
    if dokumenttype == "vilkaar":
        return badge("Vilkår", "gray")
    return badge("Ukendt", "gray")


def relevans_badge(similarity):
    """Badge der viser hvor relevant et match er (0-1 score)."""
    if similarity is None:
        return ""
    pct = int(similarity * 100)
    if pct >= 70:
        return badge(f"{pct}% match", "green")
    if pct >= 55:
        return badge(f"{pct}% match", "yellow")
    return badge(f"{pct}% match", "gray")


# ---------- TUI-VILKÅR: tekst-oprydning og titel-udledning ----------

def fix_mojibake(tekst):
    """
    Repareret UTF-8 tekst der er blevet dekodet som Latin-1 (mojibake).
    Typiske symptomer: 'Ã¦' i stedet for 'æ', 'Ã¸' for 'ø', 'Ã¥' for 'å'.
    """
    if not tekst:
        return tekst
    if not any(s in tekst for s in ("Ã¦", "Ã¸", "Ã¥", "Ã†", "Ã˜", "Ã…", "Â")):
        return tekst
    try:
        repareret = tekst.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
        if repareret and len(repareret) >= len(tekst) * 0.5:
            return repareret
    except Exception:
        pass
    return tekst


def pæn_titel_fra_vilkår_filnavn(filnavn):
    """Udled en pæn læsbar titel fra et TUI-vilkår-filnavn."""
    if not filnavn:
        return "TUI rejsevilkår"

    basis = filnavn.rsplit("/", 1)[-1]
    basis = re.sub(r"\.html?$", "", basis, flags=re.IGNORECASE)

    if "__" in basis:
        titel = basis.split("__", 1)[1].strip()
    else:
        titel = re.sub(r"^tui_", "", basis, flags=re.IGNORECASE)
        titel = titel.replace("_", " ").replace("-", " ")

    titel = fix_mojibake(titel)
    titel = re.sub(r"[_]+", " ", titel)
    titel = re.sub(r"\s+", " ", titel).strip()

    if titel and titel[0].islower():
        titel = titel[0].upper() + titel[1:]

    return titel or "TUI rejsevilkår"


def find_mest_relevante_afsnit(tekst, soege_kontekst, max_afsnit=2, min_laengde=80):
    """
    Del tekst op i afsnit og returner de 1-2 afsnit der har størst
    ordoverlapning med søgekonteksten. Hurtig heuristik, ingen AI nødvendig.
    """
    if not tekst:
        return []
    tekst = fix_mojibake(tekst)

    afsnit = re.split(r"\n\s*\n+", tekst.strip())
    afsnit = [a.strip() for a in afsnit if len(a.strip()) >= min_laengde]

    if not afsnit:
        return []
    if not soege_kontekst:
        return afsnit[:max_afsnit]

    STOP = {
        "og", "i", "er", "det", "den", "en", "et", "at", "som", "for",
        "til", "med", "af", "på", "har", "skal", "kan", "om", "men",
        "the", "a", "is", "of", "to", "for", "and", "in", "that",
    }
    def ord_set(s):
        o = re.findall(r"[A-Za-zæøåÆØÅ]{3,}", s.lower())
        return {w for w in o if w not in STOP}

    søg_ord = ord_set(soege_kontekst)
    if not søg_ord:
        return afsnit[:max_afsnit]

    scored = []
    for a in afsnit:
        a_ord = ord_set(a)
        overlap = len(søg_ord & a_ord)
        laengde_boost = min(len(a) / 500, 1.0) * 0.5
        score = overlap + laengde_boost
        scored.append((score, a))

    scored.sort(reverse=True, key=lambda x: x[0])
    top = [a for s, a in scored[:max_afsnit] if s > 0]
    return top or afsnit[:max_afsnit]
