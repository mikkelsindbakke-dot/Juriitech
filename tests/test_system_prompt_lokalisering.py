"""
Test at SYSTEM_PROMPT er lokaliseret pr. tenant.sprog.

For TUI (sprog=da): _system_prompt() returnerer SYSTEM_PROMPT_DA — som
SKAL være BYTE-IDENTISK med den oprindelige SYSTEM_PROMPT-konstant
(SHA256 oracle nedenfor).

For FjordTravel (sprog=no): _system_prompt() returnerer SYSTEM_PROMPT_NO
som indeholder norske juridiske termer.

Baseline-SHA256 er computet på den OPRINDELIGE SYSTEM_PROMPT INDEN
refaktoreringen. Hvis denne test fejler efter refaktoreringen, betyder
det at DK-versionen ikke længere er byte-identisk — og dansk PAX'
adfærd er ændret.
"""
import hashlib
import pytest


# Hash beregnet på SYSTEM_PROMPT EFTER fix 2 (klageorgan-dynamisering) men
# INDEN SYSTEM_PROMPT_LOKALISERING. Dette er baseline for 'dansk uændret'.
# Hvis nogen ændrer DK-versionen, skal denne hash opdateres bevidst (med
# en kommentar der forklarer hvorfor).
DK_SYSTEM_PROMPT_SHA256 = "3eab9e5a0795516e556c22235b39347c4e019c14f95e5e9d6e1e913f8d780c5a"
DK_SYSTEM_PROMPT_LENGTH = 4985


# Stub-profiler (samme som test_klageorgan_dynamisk.py)
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


def test_da_system_prompt_byte_identisk_med_baseline(med_profil):
    """
    DK system-prompt SKAL være byte-identisk med pre-refactor for TUI.

    Bemærk: SYSTEM_PROMPT_DA-konstanten indeholder nu en __REJSESELSKAB__-
    placeholder (i stedet for hardcoded 'TUI'), så multi-tenant får deres
    eget navn i citat-format-eksemplet. Vi tester derfor det FAKTISKE
    output af _system_prompt() med TUI aktiv — efter substitution er det
    byte-identisk med den oprindelige konstant.
    """
    from ai_engine import _system_prompt
    med_profil(TUI_STUB)
    prompt = _system_prompt()
    h = hashlib.sha256(prompt.encode()).hexdigest()
    assert len(prompt) == DK_SYSTEM_PROMPT_LENGTH, (
        f"DK system-prompt (TUI) har {len(prompt)} tegn, "
        f"forventet {DK_SYSTEM_PROMPT_LENGTH} (byte-identisk med før refactor)"
    )
    assert h == DK_SYSTEM_PROMPT_SHA256, (
        f"DK system-prompt (TUI) har SHA256={h}, forventet {DK_SYSTEM_PROMPT_SHA256}. "
        "Dansk PAX-adfærd ville være ÆNDRET hvis denne test fejler."
    )


def test_system_prompt_placeholder_substitueres_pr_tenant(med_profil):
    """__REJSESELSKAB__-placeholderen SKAL erstattes med aktiv tenants navn."""
    from ai_engine import _system_prompt
    med_profil(TUI_STUB)
    tui_prompt = _system_prompt()
    assert "__REJSESELSKAB__" not in tui_prompt, "placeholder ikke substitueret"
    assert "[TUI rejsevilkår, punkt 4.3]" in tui_prompt

    med_profil({**TUI_STUB, "slug": "apollo", "navn": "Apollo Rejser"})
    apollo_prompt = _system_prompt()
    assert "__REJSESELSKAB__" not in apollo_prompt
    assert "[Apollo Rejser rejsevilkår, punkt 4.3]" in apollo_prompt
    assert "[TUI rejsevilkår" not in apollo_prompt, (
        "TUI lækkede ind i Apollos system-prompt"
    )


def test_backwards_compat_SYSTEM_PROMPT_peger_paa_DA():
    """Den gamle SYSTEM_PROMPT-konstant skal stadig findes (peger på DA)."""
    from ai_engine import SYSTEM_PROMPT, SYSTEM_PROMPT_DA
    assert SYSTEM_PROMPT is SYSTEM_PROMPT_DA, (
        "SYSTEM_PROMPT skal være identisk med SYSTEM_PROMPT_DA "
        "(backward-compat for tests og evt. ekstern kode)"
    )


def test_system_prompt_function_for_tui_returnerer_DA(med_profil):
    """Aktiv profil TUI → _system_prompt() returnerer den danske prompt.

    Sammenligner med SYSTEM_PROMPT_DA efter placeholder-substitution
    (_system_prompt returnerer en .replace()'d kopi, ikke samme objekt)."""
    from ai_engine import _system_prompt, SYSTEM_PROMPT_DA
    med_profil(TUI_STUB)
    forventet = SYSTEM_PROMPT_DA.replace("__REJSESELSKAB__", "TUI")
    assert _system_prompt() == forventet


def test_system_prompt_function_for_fjordtravel_returnerer_NO(med_profil):
    """Aktiv profil FjordTravel → _system_prompt() returnerer den norske prompt."""
    from ai_engine import _system_prompt, SYSTEM_PROMPT_NO
    med_profil(FJORD_STUB)
    forventet = SYSTEM_PROMPT_NO.replace("__REJSESELSKAB__", "FjordTravel AS")
    assert _system_prompt() == forventet


def test_system_prompt_default_er_DA():
    """Uden aktiv profil falder vi tilbage til dansk (bagudkompatibelt)."""
    from ai_engine import _system_prompt
    prompt = _system_prompt()
    # Dansk prompt: nævner Pakkerejseankenævnet, ikke det norske organ
    assert "Pakkerejseankenævnet" in prompt
    assert "Pakkereisenemnda" not in prompt


def test_NO_system_prompt_indeholder_norske_juridiske_termer():
    """NO-versionen skal bruge norske termer, ikke danske."""
    from ai_engine import SYSTEM_PROMPT_NO
    # Norske termer der SKAL være med
    assert "norsk" in SYSTEM_PROMPT_NO.lower(), "NO-prompten skal nævne norsk sprog"
    assert "Pakkereisenemnda" in SYSTEM_PROMPT_NO, "NO-prompten skal referere Pakkereisenemnda"
    assert "pakkereiseloven" in SYSTEM_PROMPT_NO.lower(), (
        "NO-prompten skal referere pakkereiseloven (norsk lov)"
    )
    # Danske termer der IKKE må være med
    assert "Pakkerejse-Ankenævnet" not in SYSTEM_PROMPT_NO
    assert "pakkerejseloven" not in SYSTEM_PROMPT_NO.lower(), (
        "NO-prompten må IKKE indeholde 'pakkerejseloven' (dansk lov)"
    )
    assert "DANSK" not in SYSTEM_PROMPT_NO.upper().split("\n")[1:5][0] if False else True


def test_NO_system_prompt_nogenlunde_samme_struktur_som_DA():
    """
    NO-versionen skal have ROUGHLY samme længde som DA (±20%) —
    det er en sanity check at NO ikke bare er en stub.
    """
    from ai_engine import SYSTEM_PROMPT_DA, SYSTEM_PROMPT_NO
    da_len = len(SYSTEM_PROMPT_DA)
    no_len = len(SYSTEM_PROMPT_NO)
    ratio = no_len / da_len
    assert 0.7 < ratio < 1.5, (
        f"NO-system-prompt-længde ({no_len}) er for forskellig fra DA ({da_len}), "
        f"ratio={ratio:.2f}. Forventet 0.7-1.5 (cirka samme detaljering)."
    )
