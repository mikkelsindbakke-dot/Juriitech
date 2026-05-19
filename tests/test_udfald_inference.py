"""
Tests for beløb-baseret udfald-inference.

Når AI'en returnerer "Ukendt" for udfald, bruger vi de konkrete beløb
til at udlede udfaldet matematisk:
  • tilkendt >= klagers krav  → "Fuld medhold til klager"
  • 0 < tilkendt < krav         → "Delvist medhold"
  • tilkendt = 0 / "Afvist"   → "Afvist"

Dette er reglen fra Mikkel:
  "Hvis der er overensstemmelse mellem hvad klager krævede og hvad
  nævnet tilkendte, skal sagen markeres som medhold til klager.
  Hvis en del er tilkendt → delvis medhold. Hvis 0 / afvist → afvist."
"""
import pytest

from ai_engine import _parse_beloeb_til_tal, _infer_udfald_fra_beloeb


pytestmark = pytest.mark.logic


class TestParseBeloebTilTal:
    def test_normalt_dansk_format(self):
        assert _parse_beloeb_til_tal("12.500 kr.") == 12500.0
        assert _parse_beloeb_til_tal("1.234 kr.") == 1234.0
        assert _parse_beloeb_til_tal("500 kr.") == 500.0

    def test_dansk_format_med_oerer(self):
        assert _parse_beloeb_til_tal("1.234,56 kr.") == 1234.56
        assert _parse_beloeb_til_tal("3.746,00 kr.") == 3746.0

    def test_kun_tal(self):
        assert _parse_beloeb_til_tal("500") == 500.0
        assert _parse_beloeb_til_tal("12500") == 12500.0

    def test_med_mellemrum_som_tusindseparator(self):
        assert _parse_beloeb_til_tal("12 500 kr.") == 12500.0

    def test_afvist_er_nul(self):
        assert _parse_beloeb_til_tal("Afvist") == 0.0
        assert _parse_beloeb_til_tal("afvist") == 0.0

    def test_nul_kr_er_nul(self):
        assert _parse_beloeb_til_tal("0 kr.") == 0.0
        assert _parse_beloeb_til_tal("0") == 0.0

    def test_ukendt_returnerer_none(self):
        assert _parse_beloeb_til_tal("ukendt") is None
        assert _parse_beloeb_til_tal("Ukendt") is None
        assert _parse_beloeb_til_tal("") is None
        assert _parse_beloeb_til_tal(None) is None


class TestInferUdfaldFraBeloeb:
    def test_fuld_medhold_naar_tilkendt_lig_krav(self):
        # Klager fik præcis hvad der blev krævet
        assert (
            _infer_udfald_fra_beloeb("12.500 kr.", "12.500 kr.")
            == "Fuld medhold til klager"
        )

    def test_fuld_medhold_naar_tilkendt_mere_end_krav(self):
        # Nævnet tilkendte mere end klagerens oprindelige krav
        assert (
            _infer_udfald_fra_beloeb("10.000 kr.", "12.500 kr.")
            == "Fuld medhold til klager"
        )

    def test_delvist_medhold(self):
        # Tilkendt < krav men > 0
        assert (
            _infer_udfald_fra_beloeb("12.500 kr.", "4.000 kr.")
            == "Delvist medhold"
        )
        assert (
            _infer_udfald_fra_beloeb("100.000 kr.", "1 kr.")
            == "Delvist medhold"
        )

    def test_afvist_naar_tilkendt_nul(self):
        assert (
            _infer_udfald_fra_beloeb("12.500 kr.", "0 kr.") == "Afvist"
        )

    def test_afvist_naar_tilkendt_streng_afvist(self):
        assert (
            _infer_udfald_fra_beloeb("12.500 kr.", "Afvist") == "Afvist"
        )

    def test_kan_ikke_udlede_naar_krav_mangler(self):
        # Uden at vide hvad klager krævede kan vi ikke afgøre om det er
        # fuld eller delvis medhold (men afvist kan vi stadig udlede)
        assert _infer_udfald_fra_beloeb("ukendt", "4.000 kr.") is None
        assert _infer_udfald_fra_beloeb("", "4.000 kr.") is None

    def test_afvist_udledes_selv_uden_krav(self):
        # Tilkendt=0 / "Afvist" giver "Afvist" selv om krav er ukendt —
        # afvisning er entydig
        assert _infer_udfald_fra_beloeb("ukendt", "0 kr.") == "Afvist"
        assert _infer_udfald_fra_beloeb("ukendt", "Afvist") == "Afvist"

    def test_kan_ikke_udlede_naar_tilkendt_mangler(self):
        assert _infer_udfald_fra_beloeb("12.500 kr.", "ukendt") is None
        assert _infer_udfald_fra_beloeb("12.500 kr.", "") is None

    def test_kan_ikke_udlede_naar_begge_mangler(self):
        assert _infer_udfald_fra_beloeb("ukendt", "ukendt") is None

    def test_realistisk_pakkerejse_eksempel(self):
        # Typisk format fra Pakkerejse-Ankenævnets afgørelser
        assert (
            _infer_udfald_fra_beloeb("3.746,00 kr.", "3.746,00 kr.")
            == "Fuld medhold til klager"
        )
        assert (
            _infer_udfald_fra_beloeb("8.500 kr.", "2.500 kr.")
            == "Delvist medhold"
        )
