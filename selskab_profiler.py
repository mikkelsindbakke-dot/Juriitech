"""
Selskabs-profiler — kobler en bruger til et rejseselskab.

Et "selskab" er rejseselskabet brugeren arbejder for (TUI, Spies, Apollo
osv.). Hver profil indeholder ALT der er tenant-specifikt: navn, by,
logo, anonymiserings-regler, klageorgan, sprog, land, m.m.

PÅ SIGT: Når login-systemet er live, slår vi profilen op ud fra brugerens
email/organisation (fx "@tui.dk" → tui-profilen). Indtil videre er der en
hårdkodet AKTIV_PROFIL_KEY der defaulter til "tui" — det er TUI som er
den første kunde.

Filen er den ENESTE kilde til hvad der varierer per selskab. Resten af
koden henter alle tenant-specifikke værdier herfra via hent_*-funktioner.
Når man tilføjer et nyt selskab er det denne fil + et logo i
static/logos/ der skal opdateres — ingen anden kode.

═══════════════════════════════════════════════════════════════
PROFIL-FELTER
═══════════════════════════════════════════════════════════════

  navn                     — selskabets navn som det vises i tekst
                             (svarbreve, anonymisering, prompts).
                             Eksempel: "TUI", "Apollo", "Spies".

  sagsbehandler            — det navn der underskriver svarbreve. Tit
                             samme som navn, men kan være afdelings-
                             specifikt (fx "Apollo Kundeservice").

  by                       — by der vises i svarbrevets datolinje
                             ("Frederiksberg, 29-04-2026").

  logo_fil                 — relativ sti til logo-PNG (transparent
                             baggrund anbefalet). Vises på svarbrev.
                             Hvis filen mangler springes logoet over
                             uden at crashe.

  anonymisering_suffix     — det selskabs-mærkat der hænges på
                             medarbejder-fornavne i anonymisering.
                             "Maria Hansen, After Travel" → "Maria, TUI"
                             — her er suffixet "TUI".

  interne_team_navne       — liste af team/afdelings-navne der
                             SIGNALERER at en person er ANSAT i selskabet.
                             Bruges af AI-anonymiseringen til at skelne
                             interne medarbejdere (får suffix) fra
                             eksterne samarbejdspartnere (får ikke
                             suffix). Eksempel for TUI:
                             ["After Travel", "Customer service",
                              "kundeservice", "After Sales"].

  klageorgan_navn          — det officielle klageorgan i selskabets land.
                             "Pakkerejse-Ankenævnet" i Danmark, "ARN" i
                             Sverige osv.

  klageorgan_url           — base-URL til klageorganets website (bruges
                             i UI til "Åbn original"-links).

  rejsevilkaar_kilde_url   — URL hvor selskabets officielle rejsevilkår
                             kan scrapes fra (bruges af tenant-specifikke
                             scrapere).

  sprog                    — ISO-639-1 sprogkode for selskabets brugsland
                             ("da", "sv", "no", "fi"). Bruges til at
                             dirigere AI-prompts og UI-tekst.

  land                     — ISO-3166-1 alpha-2 landekode ("DK", "SE",
                             "NO", "FI"). Bruges til at koble til den
                             rette national lov og det rette klageorgan.

  lov_navn                 — navnet på den nationale pakkerejselov i
                             selskabets land ("Pakkerejseloven" i DK,
                             "Paketreselagen" i SE, osv.).

═══════════════════════════════════════════════════════════════
SÅDAN UDVIDER MAN TIL ET NYT SELSKAB
═══════════════════════════════════════════════════════════════

  1. Drop logoet i static/logos/<key>.png
  2. Tilføj en entry til SELSKAB_PROFILER nedenfor med ALLE felter udfyldt
  3. (Senere, når login er live: knyt email-domæne → profil-key)

═══════════════════════════════════════════════════════════════
"""

from pathlib import Path


# ---------- PROFIL-DEFINITIONER ----------
# Keyen ('tui', 'spies', ...) er det interne ID. Den bruges også som
# logo-filnavn under static/logos/.
#
# TUI-profilen er den eneste der er FULDT udfyldt pt. — det er den
# eneste tenant i produktion. Apollo og Spies er skeletter med navn,
# by og logo så vi har strukturen klar; resten af deres felter udfyldes
# når de onboardes som rigtige kunder.
SELSKAB_PROFILER = {
    "tui": {
        "navn": "TUI",
        "sagsbehandler": "TUI",
        "by": "Frederiksberg",
        "logo_fil": "static/logos/tui.png",
        "anonymisering_suffix": "TUI",
        "interne_team_navne": [
            "After Travel",
            "After Sales",
            "Customer service",
            "Customer Service",
            "kundeservice",
            "Kundeservice",
        ],
        "klageorgan_navn": "Pakkerejse-Ankenævnet",
        "klageorgan_url": "https://www.pakkerejseankenaevnet.dk",
        "rejsevilkaar_kilde_url": "https://www.tui.dk/rejse-med-tui/",
        "sprog": "da",
        "land": "DK",
        "lov_navn": "Pakkerejseloven",
    },
    "spies": {
        "navn": "Spies",
        "sagsbehandler": "Spies",
        "by": "København",
        "logo_fil": "static/logos/spies.png",
        # Felter nedenfor udfyldes ved Spies-onboarding:
        "anonymisering_suffix": "Spies",
        "interne_team_navne": [],
        "klageorgan_navn": "Pakkerejse-Ankenævnet",
        "klageorgan_url": "https://www.pakkerejseankenaevnet.dk",
        "rejsevilkaar_kilde_url": "",
        "sprog": "da",
        "land": "DK",
        "lov_navn": "Pakkerejseloven",
    },
    "apollo": {
        "navn": "Apollo",
        "sagsbehandler": "Apollo",
        "by": "København",
        "logo_fil": "static/logos/apollo.png",
        # Felter nedenfor udfyldes ved Apollo-onboarding:
        "anonymisering_suffix": "Apollo",
        "interne_team_navne": [],
        "klageorgan_navn": "Pakkerejse-Ankenævnet",
        "klageorgan_url": "https://www.pakkerejseankenaevnet.dk",
        "rejsevilkaar_kilde_url": "",
        "sprog": "da",
        "land": "DK",
        "lov_navn": "Pakkerejseloven",
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


# ─────────────────────────────────────────────────────────────────
# ACCESSOR-FUNKTIONER
# Én pr. felt — så koden ude i resten af projektet kalder
# hent_navn(), hent_sagsbehandler() osv. Det giver ÉT sted at ændre
# hvis vi senere vil hente fra database (fx pr. login).
# ─────────────────────────────────────────────────────────────────

def hent_navn(profil=None):
    """Returnerer selskabets navn (fx 'TUI', 'Apollo')."""
    return (profil or hent_aktiv_profil()).get("navn", "")


def hent_sagsbehandler(profil=None):
    """
    Returnerer det navn der underskriver svarbreve. Default = samme
    som hent_navn() hvis ikke sat eksplicit.
    """
    p = profil or hent_aktiv_profil()
    return p.get("sagsbehandler") or p.get("navn", "")


def hent_by(profil=None):
    """Returnerer den by der vises i svarbrevets datolinje."""
    return (profil or hent_aktiv_profil()).get("by", "")


def hent_anonymisering_suffix(profil=None):
    """
    Returnerer det suffix der hænges på medarbejder-fornavne ved
    anonymisering. 'Maria Hansen, After Travel' → 'Maria, <suffix>'.
    Default = samme som hent_navn() hvis ikke sat eksplicit.
    """
    p = profil or hent_aktiv_profil()
    return p.get("anonymisering_suffix") or p.get("navn", "")


def hent_interne_team_navne(profil=None):
    """
    Returnerer en liste af team/afdelings-navne der signalerer at en
    person er INTERN medarbejder hos selskabet (frem for ekstern
    samarbejdspartner). Bruges af AI-anonymiseringen til at skelne.
    Returnerer altid en liste (tom liste hvis ikke sat).
    """
    return list((profil or hent_aktiv_profil()).get("interne_team_navne") or [])


def hent_klageorgan_navn(profil=None):
    """
    Returnerer det officielle klageorgan i selskabets land. Eksempel:
    'Pakkerejse-Ankenævnet' (DK), 'ARN' (SE).
    """
    return (profil or hent_aktiv_profil()).get("klageorgan_navn", "")


def hent_klageorgan_url(profil=None):
    """Returnerer base-URL til klageorganets website."""
    return (profil or hent_aktiv_profil()).get("klageorgan_url", "")


def hent_rejsevilkaar_kilde_url(profil=None):
    """
    Returnerer URL hvor selskabets officielle rejsevilkår kan scrapes
    fra. Tom streng hvis ikke sat (fx for selskaber endnu ikke onboardet).
    """
    return (profil or hent_aktiv_profil()).get("rejsevilkaar_kilde_url", "")


def hent_sprog(profil=None):
    """Returnerer ISO-639-1 sprogkode ('da', 'sv', 'no', 'fi')."""
    return (profil or hent_aktiv_profil()).get("sprog", "da")


def hent_land(profil=None):
    """Returnerer ISO-3166-1 alpha-2 landekode ('DK', 'SE', 'NO', 'FI')."""
    return (profil or hent_aktiv_profil()).get("land", "DK")


def hent_lov_navn(profil=None):
    """
    Returnerer navnet på den nationale pakkerejselov i selskabets land
    ('Pakkerejseloven' i DK, 'Paketreselagen' i SE).
    """
    return (profil or hent_aktiv_profil()).get("lov_navn", "Pakkerejseloven")
