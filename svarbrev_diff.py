"""
Diff-beregning for svarbrevs-revisioner.

Sammenligner to versioner af et svarbrev på afsnits-niveau og markerer
hvert afsnit i den nye version som 'uændret', 'ny' eller 'ændret'.
Bruges til UI-rendering der highlight'er ændringer for juristen.

Afsnits-niveau er bevidst valgt over ord/karakter-niveau:
  • Juridisk arbejdsgang fokuserer på 'er det her afsnit ændret?', ikke
    på enkeltord-forskelle.
  • Markdown-rendering pr. afsnit bevares uden at ord-niveau-diff
    spammer hver sætning med spans.
"""

from difflib import SequenceMatcher


# Tærskler for klassifikation af afsnit. Kalibreret empirisk:
# - 0.98 (ikke 0.95): Korte afsnit med talændringer (fx "3.500 kr." →
#   "4.200 kr.") scorer 0.9512 på SequenceMatcher og ville fejlagtigt
#   blive markeret "uændret" ved den gamle grænse på 0.95. Logikken
#   er: status = "uændret" hvis score >= grænsen — for at fange
#   0.9512 som "ændret" skal grænsen sættes OVER 0.9512, ikke under.
#   0.98 er valgt fordi ægte identiske afsnit scorer 1.0 præcist, og
#   der er et klart spring fra 0.9512 (én talændring) til 1.0
#   (identisk) — kritisk for jurister der ikke må overse beløbsændringer.
# - 0.40 (ikke 0.70 som oprindeligt foreslået): Et afsnit der får en
#   kort tilføjet sætning scorer ~0.50; 0.40-tærsklen sikrer at
#   sådanne revisioner klassificeres som "ændret" frem for "ny".
_GRAENSE_UAENDRET = 0.98
_GRAENSE_AENDRET = 0.40


def afsnits_diff(gammel: str, ny: str) -> list[dict]:
    """
    Sammenligner to svarbrevs-versioner og returnerer afsnit-listen
    fra den NYE version, hver markeret med status.

    Args:
        gammel: tekst-versionen af det FORRIGE udkast (eller "" / None
                hvis intet forrige udkast findes).
        ny: tekst-versionen af det NYESTE udkast.

    Returns:
        Liste af dicts på formen:
          [{"tekst": str, "status": "uændret" | "ny" | "ændret"}, ...]

        Hvis gammel er tom: alle afsnit markeres som "ny".
        Hvis ny er tom: returnerer tom liste.
    """
    if not ny or not ny.strip():
        return []

    ny_afsnit = _split_afsnit(ny)

    if not gammel or not gammel.strip():
        return [{"tekst": a, "status": "ny"} for a in ny_afsnit]

    gammel_afsnit = _split_afsnit(gammel)

    resultat = []
    for nyt in ny_afsnit:
        bedste_score = 0.0
        for gam in gammel_afsnit:
            score = SequenceMatcher(None, gam, nyt).ratio()
            if score > bedste_score:
                bedste_score = score

        if bedste_score >= _GRAENSE_UAENDRET:
            status = "uændret"
        elif bedste_score >= _GRAENSE_AENDRET:
            status = "ændret"
        else:
            status = "ny"

        resultat.append({"tekst": nyt, "status": status})

    return resultat


def _split_afsnit(tekst: str) -> list[str]:
    """
    Splitter tekst i afsnit på dobbelte newlines. Trimmer whitespace
    pr. afsnit og dropper helt-tomme afsnit.
    """
    raa = (tekst or "").split("\n\n")
    return [a.strip() for a in raa if a and a.strip()]
