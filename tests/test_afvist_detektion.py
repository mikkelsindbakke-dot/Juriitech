"""
Tests for ai_engine._check_klagen_afvist.

Detekterer kanoniske Pakkerejse-Ankenævn afvisnings-formuleringer i
afgørelses-tekst. Bruges til at sætte tilkendt_beloeb='Afvist' i
match-info når AI'en returnerer Ukendt — så UI'et kan vise 'Afvist'
i stedet for 'ukendt' (commit fd84c56).

Test-strategi:
- Hver kanonisk formulering skal matche
- Også varianter med [Anonymiseret] klammer-labels
- Afgørelser uden afvisning skal returnere False
- Tom/None input håndteres pænt
"""
import pytest

from ai_engine import _check_klagen_afvist


pytestmark = pytest.mark.logic


class TestKanoniskeAfvisningsFormuleringer:
    """De faktiske formuleringer Pakkerejse-Ankenævnet bruger."""

    def test_klageren_krav_tages_ikke_til_foelge(self):
        assert _check_klagen_afvist("Klagerens krav tages ikke til følge.")

    def test_klagers_krav_tages_ikke_til_foelge(self):
        assert _check_klagen_afvist("Klagers krav tages ikke til følge.")

    def test_klagen_tages_ikke_til_foelge(self):
        assert _check_klagen_afvist("Klagen tages ikke til følge.")

    def test_klagen_kan_ikke_tages_til_foelge(self):
        # Bemærk ord-rækkefølge: "klagen kan ikke tages" matcher mønsteret
        # i AFVIST_PATTERNS. Den omvendte rækkefølge "klagen ikke kan" er
        # IKKE i mønsteret og skal heller ikke matche (det er ikke en
        # kanonisk Pakkerejse-Ankenævn-formulering).
        assert _check_klagen_afvist(
            "Klagen kan ikke tages til følge."
        )

    def test_klagen_afvises(self):
        assert _check_klagen_afvist("Klagen afvises.")

    def test_indklagede_frifindes(self):
        assert _check_klagen_afvist("Indklagede frifindes.")

    def test_anonymiseret_indklagede_frifindes(self):
        # Pakkerejse-Ankenævn anonymiserer parts-navne med klammer
        assert _check_klagen_afvist("[Indklagede] frifindes.")

    def test_anonymiseret_rejsearrangoer_frifindes(self):
        assert _check_klagen_afvist("[Rejsearrangøren] frifindes.")

    def test_naevnet_kan_ikke_give_klager_medhold(self):
        assert _check_klagen_afvist(
            "Nævnet kan ikke give klageren medhold i sagen."
        )

    def test_klager_kan_ikke_gives_medhold(self):
        assert _check_klagen_afvist("Klageren kan ikke gives medhold.")


class TestCaseInsensitivitet:
    def test_uppercase(self):
        assert _check_klagen_afvist("KLAGEN AFVISES.")

    def test_lowercase(self):
        assert _check_klagen_afvist("klagen afvises")

    def test_mixed_case(self):
        assert _check_klagen_afvist("Klagen Afvises")


class TestNegativCases:
    """Afgørelser der IKKE er afvisninger må ikke fejlagtigt flagges."""

    def test_fuld_medhold_returnerer_false(self):
        assert not _check_klagen_afvist(
            "Indklagede skal betale klageren 5.000 kr."
        )

    def test_delvist_medhold_returnerer_false(self):
        assert not _check_klagen_afvist(
            "Indklagede skal betale klageren 2.500 kr. som forholdsmæssigt afslag."
        )

    def test_neutral_tekst_returnerer_false(self):
        assert not _check_klagen_afvist(
            "Klager rejste til Mallorca i juli 2024 sammen med ægtefælle."
        )

    def test_klage_om_at_klagen_ikke_skal_afvises_returnerer_false(self):
        # Hvis klager argumenterer FOR at klagen ikke skal afvises,
        # er det ikke en afvisning — men vi har INGEN regex der ville
        # fange det ord-billede direkte. Tester for at sikre vi ikke
        # over-fanger.
        assert not _check_klagen_afvist(
            "Klager mener at sagen ikke bør afvises på formaliteten."
        )


class TestEdgeCases:
    def test_tom_streng(self):
        assert _check_klagen_afvist("") is False

    def test_none(self):
        assert _check_klagen_afvist(None) is False

    def test_lang_tekst_med_afvisning_til_sidst(self):
        # Realistisk scenarie: afgørelses-tekst på flere sider, hvor
        # konklusionen ligger sidst
        tekst = (
            "Sagen drejer sig om en pakkerejse til Mallorca i juli 2024. "
            "Klageren har gjort gældende, at hotellet ikke svarede til "
            "beskrivelsen i kataloget. " * 50
            + "\n\nNævnets bemærkninger og afgørelse:\n"
            + "Klagen tages ikke til følge."
        )
        assert _check_klagen_afvist(tekst)
