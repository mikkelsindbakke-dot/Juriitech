"""
Tests for ai_engine._regex_find_beloeb.

Per CLAUDE.md er denne historisk bugged — flere CLAUDE.md-learnings
peger på problemer som "anchor-ord der optræder i begge sider af en
afgørelse" og "Pakkerejse-Ankenævn anonymiserer parts-navne med
klammer-labels". Tests her er bevidst designet til at fange de
historiske faldgruber, så regressioner opdages.

Test-strategi:
- Realistiske afgørelses-uddrag der MATCHER de mønstre regex'en er
  bygget til at fange
- Anonymiserede sætninger med [Klageren] / [Indklagede] klammer-labels
- Negative cases der historisk har givet false positives
- Afviste sager (forventer 'Afvist' som tilkendt_beloeb)
"""
import pytest

from ai_engine import _regex_find_beloeb


pytestmark = pytest.mark.regex


class TestKlagersKrav:
    def test_klager_kraever_eksplicit(self):
        result = _regex_find_beloeb("Klager kræver 5.000 kr. som kompensation.")
        assert result["klagers_krav"] == "5.000 kr."

    def test_klagers_paastand(self):
        result = _regex_find_beloeb(
            "Klagers påstand er 12.500 kr. for manglende standard."
        )
        assert result["klagers_krav"] == "12.500 kr."

    def test_kraever_kompensation_paa(self):
        result = _regex_find_beloeb(
            "Klager kræver kompensation på 8.000 kr. for ødelagt rejse."
        )
        assert result["klagers_krav"] == "8.000 kr."


class TestTilkendtBeloebGrundlaeggende:
    def test_naevnet_tilkender(self):
        result = _regex_find_beloeb("Nævnet tilkender klageren 3.000 kr.")
        assert result["tilkendt_beloeb"] == "3.000 kr."

    def test_klager_tilkendes(self):
        result = _regex_find_beloeb("Klageren tilkendes 2.500 kr.")
        assert result["tilkendt_beloeb"] == "2.500 kr."

    def test_forholdsmaessigt_afslag(self):
        result = _regex_find_beloeb(
            "Klager tilkendes et forholdsmæssigt afslag svarende til 4.500 kr."
        )
        assert result["tilkendt_beloeb"] == "4.500 kr."


class TestAnonymiseredeAfgoerelser:
    """Pakkerejse-Ankenævn anonymiserer parts-navne med klammer-labels.
    Disse SKAL stadig matches korrekt — det er learnings fra CLAUDE.md."""

    def test_indklagede_skal_betale_klageren(self):
        tekst = (
            "[Indklagede] skal inden 30 dage fra dato for kendelsens "
            "forkyndelse betale 3.746 kr. til [Klageren]."
        )
        result = _regex_find_beloeb(tekst)
        assert result["tilkendt_beloeb"] == "3.746 kr."

    def test_rejsearrangoeren_skal_betale_klager(self):
        tekst = "[Rejsearrangøren] skal betale 5.250 kr. til [Klager]."
        result = _regex_find_beloeb(tekst)
        assert result["tilkendt_beloeb"] == "5.250 kr."

    def test_indklagede_skal_uden_klammer(self):
        # Også uden klammer skal det matche
        tekst = "Indklagede skal betale klageren 1.500 kr."
        result = _regex_find_beloeb(tekst)
        assert result["tilkendt_beloeb"] == "1.500 kr."


class TestAfvisning:
    """Når sagen er afvist, skal tilkendt_beloeb være 'Afvist',
    IKKE tom streng (jf. ai_engine._check_klagen_afvist + commit fd84c56)."""

    def test_afvist_klagen_giver_afvist(self):
        result = _regex_find_beloeb("Klagen afvises.")
        assert result["tilkendt_beloeb"] == "Afvist"

    def test_indklagede_frifindes_giver_afvist(self):
        result = _regex_find_beloeb("Indklagede frifindes.")
        assert result["tilkendt_beloeb"] == "Afvist"


class TestEdgeCases:
    def test_tom_tekst_giver_tomme_felter(self):
        result = _regex_find_beloeb("")
        assert result == {"klagers_krav": "", "tilkendt_beloeb": ""}

    def test_none_giver_tomme_felter(self):
        result = _regex_find_beloeb(None)
        assert result == {"klagers_krav": "", "tilkendt_beloeb": ""}

    def test_tekst_uden_beloeb_giver_tomme_felter(self):
        result = _regex_find_beloeb(
            "Klager rejste til Mallorca og var meget skuffet."
        )
        assert result == {"klagers_krav": "", "tilkendt_beloeb": ""}

    def test_findes_baade_kraev_og_tilkendt(self):
        # Afgørelse med både klagers krav og Nævnets afgørelse
        tekst = (
            "Klager kræver 10.000 kr. for ødelagt rejse. "
            "Nævnets afgørelse: Indklagede skal betale klageren 4.000 kr."
        )
        result = _regex_find_beloeb(tekst)
        assert result["klagers_krav"] == "10.000 kr."
        assert result["tilkendt_beloeb"] == "4.000 kr."


class TestFalsePositiveImmunitet:
    """Per CLAUDE.md fjernede vi 'kompensation på' / 'godtgørelse på' som
    anchors fordi de optræder i BEGGE sider af en afgørelse. Sikrer at
    tilkendt-detektoren ikke fejlagtigt fanger klagers KRAV som tilkendt."""

    def test_klagers_krav_med_kompensation_paa_er_ikke_tilkendt(self):
        # 'Klager kræver kompensation på X' må IKKE blive til tilkendt_beloeb
        tekst = "Klager kræver kompensation på 7.500 kr."
        result = _regex_find_beloeb(tekst)
        assert result["klagers_krav"] == "7.500 kr."
        # tilkendt_beloeb skal være tomt (eller 'Afvist' hvis tekst nævner
        # afvisning, men det gør den ikke her)
        assert result["tilkendt_beloeb"] == ""
