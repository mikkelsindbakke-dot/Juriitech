"""
TDD-test for det terminale sprog-anchor (recency-bias-fix).

PROBLEM: SYSTEM_PROMPT_NO og _sprog_direktiv() ved promptens start er ikke
nok til at få Claude til at svare på norsk. Brødteksten i AI-analyser kommer
stadig på dansk fordi resten af user-prompten + tool-schema-felternes
beskrivelser er hardcodet dansk, og LLM'er vægter de SENESTE instruktioner
højest (recency bias).

LØSNING: Tilføj en kraftig sprog-anchor til SLUTNINGEN af user-prompten
PLUS norsk-variant af tool-schemaer. Når sprog=da returnerer alle nye
helpers tom streng (eller DA-versionen) — eksisterende dansk PAX-adfærd
skal være byte-identisk.
"""
import pytest


TUI_STUB = {
    "slug": "tui", "navn": "TUI",
    "klageorgan_navn": "Pakkerejse-Ankenævnet",
    "sprog": "da", "land": "DK",
}
FJORD_STUB = {
    "slug": "test-norge-fjordtravel", "navn": "FjordTravel AS",
    "klageorgan_navn": "Pakkereisenemnda",
    "sprog": "no", "land": "NO",
}


@pytest.fixture
def med_profil():
    import selskab_profiler
    tokens = []

    def saet(profil_dict):
        tokens.append(selskab_profiler.saet_aktiv_profil(profil_dict))

    yield saet

    for t in reversed(tokens):
        selskab_profiler.reset_aktiv_profil(t)


# ─────────── _sprog_anchor_end() ───────────

def test_sprog_anchor_end_for_da_er_tom_streng(med_profil):
    """For TUI/DK-tenants skal _sprog_anchor_end() returnere tom streng
    så ingen ekstra tekst tilføjes til danske prompts (byte-identisk).
    """
    from ai_engine import _sprog_anchor_end
    med_profil(TUI_STUB)
    assert _sprog_anchor_end() == ""


def test_sprog_anchor_end_default_uden_profil_er_tom_streng():
    """Ingen aktiv profil → fallback til dansk → tom streng."""
    from ai_engine import _sprog_anchor_end
    assert _sprog_anchor_end() == ""


def test_sprog_anchor_end_for_no_indeholder_norsk_bokmaal(med_profil):
    """For norske tenants skal anchor'en kraftigt presse på norsk bokmål."""
    from ai_engine import _sprog_anchor_end
    med_profil(FJORD_STUB)
    a = _sprog_anchor_end()
    assert a != ""
    # Skal nævne målsproget eksplicit
    assert "NORSK BOKMÅL" in a or "norsk bokmål" in a.lower()


def test_sprog_anchor_end_for_no_indeholder_konkret_norsk_vokabular(med_profil):
    """
    Anchor'en skal give AI'en konkrete norske vokabular-anker så den ikke
    bruger danske ord som 'børn', 'lukkede', 'gæsterne', 'afgørende'.
    Vi tester nogle af de mest kritiske oversættelser.
    """
    from ai_engine import _sprog_anchor_end
    med_profil(FJORD_STUB)
    a = _sprog_anchor_end()
    # Skal indeholde mindst nogle af de norske termer der bruges i vurderinger
    norske_termer = ["barn", "stengt", "oppholdet", "reiseleder",
                     "Pakkereisenemnda", "pakkereiseloven"]
    fundet = [t for t in norske_termer if t in a]
    assert len(fundet) >= 4, (
        f"Forventede mindst 4 norske termer i anchor, fandt kun {fundet}. "
        f"Anchor mangler konkrete vokabular-anker."
    )


def test_sprog_anchor_end_for_no_advarer_mod_danske_ord(med_profil):
    """
    Anchor'en skal eksplicit advare AI'en mod danske ord der ellers
    sniger sig ind (smitter fra dansk-tunge prompts).
    """
    from ai_engine import _sprog_anchor_end
    med_profil(FJORD_STUB)
    a = _sprog_anchor_end().lower()
    # Skal nævne mindst nogle danske ord der skal UNDGÅS
    danske_traps = ["børn", "gæsterne", "opholdet", "afgørende", "rejseleder"]
    fundet = [t for t in danske_traps if t in a]
    assert len(fundet) >= 3, (
        f"Forventede mindst 3 danske 'pas på'-ord i anchor, fandt kun {fundet}."
    )


# ─────────── _byg_foerstevurdering_schema(sprog) ───────────

def test_foerstevurdering_schema_for_da_er_byte_identisk_med_eksisterende():
    """
    FOERSTEVURDERING_SCHEMA (modul-konstanten) skal være IDENTISK med det
    schema-builderen returnerer for sprog='da'. Dvs. dansk PAX-adfærd
    er præcis som før — schemaet ændrer ikke et eneste tegn.
    """
    from ai_engine import _byg_foerstevurdering_schema, FOERSTEVURDERING_SCHEMA
    da_schema = _byg_foerstevurdering_schema("da")
    assert da_schema == FOERSTEVURDERING_SCHEMA, (
        "DA-schemaet fra builder afviger fra modul-konstanten — "
        "byte-identitet er brudt."
    )


def test_foerstevurdering_schema_no_har_norske_beskrivelser():
    """NO-versionen skal bruge norske felt-beskrivelser, ikke danske."""
    from ai_engine import _byg_foerstevurdering_schema
    no_schema = _byg_foerstevurdering_schema("no")

    # Konklusion-feltet havde tidligere 'i klar dansk' hardcodet — det
    # skal nu være 'i klart norsk' (eller 'på norsk') når sprog=no.
    konkl_beskrivelse = (no_schema["properties"]
                                  ["konklusion_en_linje"]["description"])
    assert "dansk" not in konkl_beskrivelse.lower(), (
        f"NO-schema indeholder stadig ordet 'dansk': {konkl_beskrivelse}"
    )
    assert "norsk" in konkl_beskrivelse.lower(), (
        f"NO-schema mangler ordet 'norsk': {konkl_beskrivelse}"
    )


def test_foerstevurdering_schema_no_bevarer_struktur():
    """
    NO-versionen skal have NØJAGTIG samme 6 properties + samme required-
    liste. Schemaets STRUKTUR må aldrig divergere — kun beskrivelses-
    teksterne lokaliseres.
    """
    from ai_engine import _byg_foerstevurdering_schema
    da = _byg_foerstevurdering_schema("da")
    no = _byg_foerstevurdering_schema("no")
    assert set(da["properties"].keys()) == set(no["properties"].keys())
    assert da["required"] == no["required"]
    # Inderste schema struktur (sandsynlighedsvurdering) skal også matche
    da_sand = da["properties"]["sandsynlighedsvurdering"]
    no_sand = no["properties"]["sandsynlighedsvurdering"]
    assert set(da_sand["properties"].keys()) == set(no_sand["properties"].keys())
    assert da_sand["required"] == no_sand["required"]
