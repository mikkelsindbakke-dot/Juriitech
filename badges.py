"""
Badge-komponent i Notion/Apple Health-stil.

Lille farvet tag der vises inline for hurtigt at kommunikere status:
udfald af en sag, dokumenttype, relevans-niveau osv.
"""

import re


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
