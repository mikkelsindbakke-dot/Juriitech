"""
Selskabs-profiler — kobler en bruger til et rejseselskab.

Et "selskab" er rejseselskabet brugeren arbejder for (TUI, Spies, Apollo
osv.). Hver profil indeholder de oplysninger der bruges på et svarbrev:

  • navn        — selskabets juridiske navn (vises i bilag-overskrifter
                  og evt. fodtekst)
  • by          — den by hvor selskabet hører hjemme; bruges i datolinjen
                  ("Frederiksberg, 29-04-2026")
  • logo_fil    — relativ sti til selskabets logo (PNG, helst transparent
                  baggrund). Vises øverst til højre på svarbrevet.
                  Hvis filen mangler springes logoet over uden at crashe.

PÅ SIGT: Når login-systemet er live, slår vi profilen op ud fra brugerens
email/organisation (fx "@tui.dk" → tui-profilen). Indtil videre er der en
hårdkodet AKTIV_PROFIL der defaulter til "tui" — det er TUI som er den
første kunde, så det er pragmatisk.

Sådan udvider man til et nyt selskab:
  1. Drop logoet i static/logos/<key>.png
  2. Tilføj en entry til SELSKAB_PROFILER nedenfor
  3. (Senere, når login er live: knyt email-domæne → profil-key)
"""

from pathlib import Path


# ---------- PROFIL-DEFINITIONER ----------
# Keyen ('tui', 'spies', ...) er det interne ID. Den bruges også som
# logo-filnavn under static/logos/.
SELSKAB_PROFILER = {
    "tui": {
        "navn": "TUI",
        "by": "Frederiksberg",
        "logo_fil": "static/logos/tui.png",
    },
    "spies": {
        "navn": "Spies",
        "by": "København",
        "logo_fil": "static/logos/spies.png",
    },
    "apollo": {
        "navn": "Apollo",
        "by": "København",
        "logo_fil": "static/logos/apollo.png",
    },
}


# ---------- AKTIV PROFIL ----------
# Indtil login er live er denne hårdkodet. Når login lander erstattes
# det med et opslag baseret på den autentificerede brugers email-domæne
# eller organisation. Hold derfor ALT logik om "hvilket selskab er aktivt"
# inde i hent_aktiv_profil() — så er der ét sted at ændre.
AKTIV_PROFIL_KEY = "tui"


def hent_aktiv_profil():
    """
    Returnerer dict for det aktuelt aktive selskab. Falder tilbage til
    TUI hvis nøglen er ukendt (defensiv — bør aldrig ske, men forhindrer
    KeyError hvis nogen ændrer AKTIV_PROFIL_KEY uden at tilføje profilen).
    """
    return SELSKAB_PROFILER.get(AKTIV_PROFIL_KEY) or SELSKAB_PROFILER["tui"]


def hent_profil(key):
    """Slå en profil op på key. Returnerer None hvis ukendt."""
    return SELSKAB_PROFILER.get(key)


def hent_logo_sti(profil=None):
    """
    Returnerer en absolut sti til logo-filen for den angivne profil
    (eller den aktive profil hvis intet er angivet). Returnerer None
    hvis filen ikke findes på disk — så kalderen kan rendere uden logo
    i stedet for at crashe.
    """
    p = profil or hent_aktiv_profil()
    rel = p.get("logo_fil")
    if not rel:
        return None
    # Sti er relativ til projekt-rod (samme mappe som denne fil ligger i)
    abs_sti = Path(__file__).resolve().parent / rel
    return str(abs_sti) if abs_sti.exists() else None


def hent_navn(profil=None):
    """Returnerer selskabets navn (fx 'TUI')."""
    return (profil or hent_aktiv_profil()).get("navn", "")


def hent_by(profil=None):
    """Returnerer den by der vises i svarbrevets datolinje."""
    return (profil or hent_aktiv_profil()).get("by", "")
