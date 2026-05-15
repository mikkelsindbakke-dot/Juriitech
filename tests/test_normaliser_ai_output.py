"""
Tests for ai_engine._normalisér_ai_output.

Generel post-processor der fanger AI-output-ord der ikke findes i
hverken dansk eller norsk (hallucinationer) eller systematiske
formatfejl. Køres på output fra alle AI-funktioner der producerer
fri tekst der vises direkte i UI'et.

Mest fremtrædende case: "meggæster" — ikke et dansk ord, men AI'en
har genereret det i klage-analyser. Skal normaliseres til "andre
gæster" / "andre gjester" afhængigt af sprog.
"""
import pytest

from ai_engine import _normalisér_ai_output, _rens_kategori_prefix


pytestmark = pytest.mark.logic


class TestMeggaster:
    def test_simpel_meggaster_bliver_gaester(self):
        """Med qualifier ('britiske') bevares qualifieren — 'britiske
        meggæster' bliver 'britiske gæster' (ikke 'britiske andre gæster')."""
        ind = "Klager blev truet af britiske meggæster ved poolen."
        ud = _normalisér_ai_output(ind)
        assert "meggæster" not in ud.lower()
        assert "britiske gæster" in ud

    def test_meggaster_uden_qualifier(self):
        ind = "Andre meggæster udviste truende adfærd."
        ud = _normalisér_ai_output(ind)
        assert "meggæster" not in ud

    def test_meggaster_med_qualifier_bibeholdes(self):
        """'britiske meggæster' skal blive 'britiske gæster' — ikke
        'britiske andre gæster' (dobbelt-qualifier ville være klodset)."""
        ind = "Trusler fra britiske meggæster ved bassenget."
        ud = _normalisér_ai_output(ind)
        assert "britiske meggæster" not in ud
        assert "britiske gæster" in ud
        assert "andre gæster" not in ud or "britiske andre" not in ud

    def test_multiple_occurrences_replaced(self):
        ind = "meggæster råbte. Senere kom flere meggæster til poolen."
        ud = _normalisér_ai_output(ind)
        assert "meggæster" not in ud

    def test_capitalized_first_letter(self):
        ind = "Meggæster ankom kl. 14."
        ud = _normalisér_ai_output(ind)
        assert "Meggæster" not in ud
        # Resultatet kan rimeligvis være 'Andre gæster' eller 'Gæster' —
        # vi tester kun at det forbudte ord er væk.


class TestUaendret:
    def test_tom_streng(self):
        assert _normalisér_ai_output("") == ""

    def test_none_returnerer_tom(self):
        # Defensiv: må ikke crashe ved None
        assert _normalisér_ai_output(None) == ""

    def test_normal_tekst_uaendret(self):
        ind = "Klager rejste til Cypern den 22. juli 2024."
        ud = _normalisér_ai_output(ind)
        assert ud == ind

    def test_lignende_men_korrekte_ord_uaendret(self):
        """Sikrer at vi ikke fanger 'medgæster' (legitimt sammensat ord)
        eller andre ord der tilfældigvis indeholder 'gæster'."""
        ind = "Klager rejste med medrejsende og andre gæster."
        ud = _normalisér_ai_output(ind)
        assert ud == ind


class TestRensKategoriPrefix:
    def test_kontekst_prefix_med_tankestreg_strippes(self):
        ind = "Kontekst — Rejsens samlede pris var 28.912 DKK [Bilag 03]"
        ud = _rens_kategori_prefix(ind)
        assert ud == "Rejsens samlede pris var 28.912 DKK [Bilag 03]"

    def test_kontekst_prefix_med_bold_markdown(self):
        ind = "**Kontekst** — Hændelsen fandt sted 30. juli 2024"
        ud = _rens_kategori_prefix(ind)
        assert ud == "Hændelsen fandt sted 30. juli 2024"

    def test_klagepunkt_prefix_strippes(self):
        ind = "Klagepunkt — TUI's After Travel henviste forkert"
        ud = _rens_kategori_prefix(ind)
        assert ud == "TUI's After Travel henviste forkert"

    def test_detalje_prefix_strippes(self):
        ind = "Detalje — Klager booked Silver Sands selv"
        ud = _rens_kategori_prefix(ind)
        assert ud == "Klager booked Silver Sands selv"

    def test_normal_streng_uden_prefix_uaendret(self):
        ind = "TUI's sagsbehandling var langsom — første svar 15-8-2024"
        ud = _rens_kategori_prefix(ind)
        assert ud == ind

    def test_kontekst_inde_i_saetningen_bevares(self):
        """Stripper KUN i starten, ikke når 'kontekst' indgår normalt
        i en sætning."""
        ind = "Sætningen handler om kontekst — og andre forhold"
        ud = _rens_kategori_prefix(ind)
        assert ud == ind

    def test_bindestreg_alternativer(self):
        """Em-dash, en-dash og almindelig bindestreg."""
        for sep in ["—", "–", "-"]:
            ind = f"Kontekst {sep} indhold her"
            ud = _rens_kategori_prefix(ind)
            assert ud == "indhold her", f"fejlede for separator '{sep}'"

    def test_case_insensitive(self):
        ind = "KONTEKST — vigtig information"
        ud = _rens_kategori_prefix(ind)
        assert ud == "vigtig information"
