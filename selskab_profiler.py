"""
Selskabs-profiler — facade ovenpå tenants-tabellen i Postgres.

Hvert "selskab" er en tenant: rejseselskabet brugeren arbejder for
(TUI, Spies, Apollo osv.). I Phase B1 bor selve profil-data i
databasen i stedet for i en hardcoded dict — det betyder at admin
kan oprette nye tenants via UI uden kode-ændringer (Phase B4).

Denne fil bevarer den samme accessor-API som tidligere
(hent_navn, hent_by, hent_logo_sti osv.) — resten af koden behøver
ingen ændringer.

═══════════════════════════════════════════════════════════════
LAGER-LOOKUP-STRATEGI
═══════════════════════════════════════════════════════════════

I dag (B1):
  - Aktiv tenant bestemmes af AKTIV_PROFIL_KEY (hardcoded 'tui')
  - Profil-data hentes fra DB via database.hent_tenant_by_slug()

I B3 (efter login):
  - AKTIV_PROFIL_KEY droppes
  - hent_aktiv_profil() læser fra st.session_state.user.tenant_id
    som sættes når brugeren logger ind via Supabase

Caching: vi cacher tenant-dicten i et modul-level dict så vi ikke
kører en DB-query på HVER hent_navn()-kald. Cachen invalideres når
processen genstarter (godkendt for B1; til B3 vil vi tilføje en
eksplicit refresh-mekanisme efter login).
"""

# ─── AKTIV PROFIL ──────────────────────────────────────────────
# Fallback-default når ingen bruger er logget ind. Bevares i B1 så
# adfærden er identisk med før (alle "brugere" antages at være TUI).
# Erstattes med per-request opslag i Phase B3.
AKTIV_PROFIL_KEY = "tui"

# Modul-level cache så vi ikke spammer DB med queries
_PROFIL_CACHE = {}


# ─── PROFIL-LOOKUP ─────────────────────────────────────────────

def _hent_fra_db(slug):
    """
    Slå tenant op i DB via slug. Cachet pr. proces. Returnerer dict
    eller None hvis tenant ikke findes.

    Lazy import af database for at undgå circular import (database.py
    importerer ikke selskab_profiler, men vi vil gerne være pæne).
    """
    if not slug:
        return None
    if slug in _PROFIL_CACHE:
        return _PROFIL_CACHE[slug]
    try:
        from database import hent_tenant_by_slug
        profil = hent_tenant_by_slug(slug)
        if profil:
            _PROFIL_CACHE[slug] = profil
        return profil
    except Exception as e:
        print(f"DEBUG: selskab_profiler kunne ikke hente tenant {slug}: {e}")
        return None


def _hardcoded_fallback(slug):
    """
    Last-resort fallback hvis DB-opslag fejler (fx hvis migration_b1
    ikke er kørt endnu, eller DB er nede). Returnerer minimal TUI-dict
    så systemet ikke crasher.

    Når DB er sat op korrekt (B1-migration kørt), skulle denne aldrig
    blive ramt.
    """
    if slug == "tui":
        return {
            "id": None,
            "slug": "tui",
            "navn": "TUI",
            "sagsbehandler": "TUI",
            "by": "Frederiksberg",
            "logo_filnavn": "static/logos/tui.png",
            "anonymisering_suffix": "TUI",
            "interne_team_navne": [
                "After Travel", "After Sales",
                "Customer service", "Customer Service",
                "kundeservice", "Kundeservice",
            ],
            "klageorgan_navn": "Pakkerejse-Ankenævnet",
            "klageorgan_url": "https://www.pakkerejseankenaevnet.dk",
            "rejsevilkaar_kilde_url": "https://www.tui.dk/rejse-med-tui/",
            "sprog": "da",
            "land": "DK",
            "lov_navn": "Pakkerejseloven",
        }
    return None


def hent_aktiv_profil():
    """
    Returnerer den aktive tenant's profil-dict.

    B1: AKTIV_PROFIL_KEY (hardcoded 'tui') styrer hvilken tenant.
    B3: vil læse fra st.session_state.user.tenant_id efter login.

    Falder tilbage til hardcoded TUI-fallback hvis DB er utilgængelig
    (defensivt — bør aldrig ramme i produktion).
    """
    # B3-prep: hvis Streamlit-session har en logged-in user, brug deres
    # tenant. I B1 sker dette aldrig fordi vi ikke har login.
    try:
        import streamlit as st
        user = st.session_state.get("user")
        if user and user.get("tenant_id"):
            try:
                from database import hent_tenant_by_id
                profil = hent_tenant_by_id(user["tenant_id"])
                if profil:
                    return profil
            except Exception:
                pass
    except Exception:
        pass

    # B1-default: hardcoded slug-baseret lookup
    profil = _hent_fra_db(AKTIV_PROFIL_KEY)
    if profil:
        return profil
    return _hardcoded_fallback(AKTIV_PROFIL_KEY) or _hardcoded_fallback("tui")


def hent_profil(key):
    """Slå profil op på slug ('tui', 'spies', 'apollo'). None hvis ukendt."""
    return _hent_fra_db(key)


def ryd_cache():
    """
    Tøm profil-cachen. Bruges fx efter at admin har opdateret en
    tenant via admin-siden (Phase B4) så de nye værdier hentes ved
    næste request.
    """
    global _PROFIL_CACHE
    _PROFIL_CACHE = {}


# ─── ACCESSOR-FUNKTIONER ───────────────────────────────────────
# Samme API som før refaktoren — eksisterende kode behøver ingen
# ændringer. Hver henter den aktive profil (eller den specificerede)
# og returnerer det relevante felt med en sensibel default.

def hent_navn(profil=None):
    """Returnerer selskabets navn (fx 'TUI', 'Apollo')."""
    return (profil or hent_aktiv_profil() or {}).get("navn", "")


def hent_sagsbehandler(profil=None):
    """
    Returnerer det navn der underskriver svarbreve. Default = samme
    som hent_navn() hvis ikke sat eksplicit.
    """
    p = profil or hent_aktiv_profil() or {}
    return p.get("sagsbehandler") or p.get("navn", "")


def hent_by(profil=None):
    """Returnerer den by der vises i svarbrevets datolinje."""
    return (profil or hent_aktiv_profil() or {}).get("by", "")


def hent_logo_sti(profil=None):
    """
    Returnerer en absolut sti til logo-filen for den angivne profil
    (eller den aktive profil hvis intet er angivet). Returnerer None
    hvis filen ikke findes på disk — så kalderen kan rendere uden logo
    i stedet for at crashe.
    """
    from pathlib import Path
    p = profil or hent_aktiv_profil() or {}
    rel = p.get("logo_filnavn") or p.get("logo_fil")  # bagudkompat for "logo_fil"
    if not rel:
        return None
    abs_sti = Path(__file__).resolve().parent / rel
    return str(abs_sti) if abs_sti.exists() else None


def hent_anonymisering_suffix(profil=None):
    """
    Returnerer det suffix der hænges på medarbejder-fornavne ved
    anonymisering. 'Maria Hansen, After Travel' → 'Maria, <suffix>'.
    Default = samme som hent_navn() hvis ikke sat eksplicit.
    """
    p = profil or hent_aktiv_profil() or {}
    return p.get("anonymisering_suffix") or p.get("navn", "")


def hent_interne_team_navne(profil=None):
    """
    Returnerer en liste af team/afdelings-navne der signalerer at en
    person er INTERN medarbejder hos selskabet (frem for ekstern
    samarbejdspartner). Bruges af AI-anonymiseringen til at skelne.
    Returnerer altid en liste (tom liste hvis ikke sat).
    """
    return list((profil or hent_aktiv_profil() or {}).get("interne_team_navne") or [])


def hent_klageorgan_navn(profil=None):
    """
    Returnerer det officielle klageorgan i selskabets land. Eksempel:
    'Pakkerejse-Ankenævnet' (DK), 'ARN' (SE).
    """
    return (profil or hent_aktiv_profil() or {}).get(
        "klageorgan_navn", "Pakkerejse-Ankenævnet"
    )


def hent_klageorgan_url(profil=None):
    """Returnerer base-URL til klageorganets website."""
    return (profil or hent_aktiv_profil() or {}).get("klageorgan_url", "")


def hent_rejsevilkaar_kilde_url(profil=None):
    """
    Returnerer URL hvor selskabets officielle rejsevilkår kan scrapes
    fra. Tom streng hvis ikke sat (fx for selskaber endnu ikke onboardet).
    """
    return (profil or hent_aktiv_profil() or {}).get("rejsevilkaar_kilde_url", "")


def hent_sprog(profil=None):
    """Returnerer ISO-639-1 sprogkode ('da', 'sv', 'no', 'fi')."""
    return (profil or hent_aktiv_profil() or {}).get("sprog", "da")


def hent_land(profil=None):
    """Returnerer ISO-3166-1 alpha-2 landekode ('DK', 'SE', 'NO', 'FI')."""
    return (profil or hent_aktiv_profil() or {}).get("land", "DK")


def hent_lov_navn(profil=None):
    """
    Returnerer navnet på den nationale pakkerejselov i selskabets land
    ('Pakkerejseloven' i DK, 'Paketreselagen' i SE).
    """
    return (profil or hent_aktiv_profil() or {}).get("lov_navn", "Pakkerejseloven")
