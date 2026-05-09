"""
Tests for processor._gaet_rolle.

Gætter en sagsfils rolle ud fra filnavnet. Kritisk fordi tjekliste-
generationen IKKE virker uden et høringsbrev (rolle='høring'), og
anonymisering filtrerer Nævnets vejledninger fra (rolle='vejledning').
"""
import pytest

from processor import _gaet_rolle


pytestmark = pytest.mark.regex


class TestHoering:
    def test_matcher_hoering_med_oe(self):
        assert _gaet_rolle("Høring R.docx") == "høring"

    def test_matcher_hoering_med_oe_lowercase(self):
        assert _gaet_rolle("høring.pdf") == "høring"

    def test_matcher_hoering_med_oe_ascii(self):
        # Regex'en er h.?ring (én valgfri char mellem h og ring), så den
        # matcher "Høring" (ø = 1 char) men IKKE "hoering" (oe = 2 chars).
        # Det er fint i praksis — Pakkerejse-Ankenævn navngiver altid
        # filer med ø, ikke ascii-fallback. Dokumenteret her som adfærd.
        assert _gaet_rolle("hoering_R.docx") == "ukendt"


class TestKlageskema:
    def test_matcher_klageskema_navn(self):
        assert _gaet_rolle("Klageskema.pdf") == "klageskema"

    def test_matcher_bilag_01_som_klageskema(self):
        # Per regex: bilag\s*0?1 — Bilag 1 / Bilag 01 er konventionelt
        # selve klageskemaet i Pakkerejse-Ankenævn-sager
        assert _gaet_rolle("Bilag 01.pdf") == "klageskema"
        assert _gaet_rolle("Bilag 1.pdf") == "klageskema"
        assert _gaet_rolle("bilag1.pdf") == "klageskema"


class TestBilagSpecifikke:
    def test_billet_giver_bilag_billet(self):
        assert _gaet_rolle("Flybillet.pdf") == "bilag_billet"
        assert _gaet_rolle("Rejsebevis.pdf") == "bilag_billet"

    def test_hotel_giver_bilag_hotel(self):
        assert _gaet_rolle("Hotelbeskrivelse.pdf") == "bilag_hotel"

    def test_mail_giver_bilag_mail(self):
        assert _gaet_rolle("Mail-korrespondance.pdf") == "bilag_mail"
        assert _gaet_rolle("Brev_til_TUI.docx") == "bilag_mail"

    def test_kommentar_giver_bilag_kommentar(self):
        assert _gaet_rolle("Kommentar.pdf") == "bilag_kommentar"


class TestVejledning:
    def test_vejledning(self):
        assert _gaet_rolle("Vejledning.pdf") == "vejledning"

    def test_retningslinjer(self):
        assert _gaet_rolle("Retningslinjer fra Nævnet.pdf") == "vejledning"


class TestFallbacks:
    def test_generel_bilag_uden_specifik_kategori(self):
        assert _gaet_rolle("Bilag 02.pdf") == "bilag"
        assert _gaet_rolle("Bilag 99.pdf") == "bilag"

    def test_ukendt_filnavn_returnerer_ukendt(self):
        assert _gaet_rolle("random_dokument.pdf") == "ukendt"

    def test_tom_streng_returnerer_ukendt(self):
        assert _gaet_rolle("") == "ukendt"


class TestRaekkefoelgeAfMatching:
    """Vigtigt: rækkefølgen i ROLLE_MOENSTRE er bevidst — første match
    vinder. Tester at høring-matching ikke fanger 'klageskema' (begge
    indeholder ikke samme bogstaver), og at klageskema-matching fanger
    'Bilag 01' før det generelle 'bilag'-mønster gør."""

    def test_bilag_01_giver_klageskema_ikke_bilag(self):
        # Hvis 'bilag'-mønsteret kom først, ville Bilag 01 fejlagtigt
        # få rollen 'bilag'. Vi tester at klageskema-mønsteret vinder.
        assert _gaet_rolle("Bilag 01.pdf") == "klageskema"

    def test_hoering_kommer_foer_andre_matches(self):
        # Selv hvis filnavnet indeholder fx 'klageskema', vinder høring
        # hvis det også er der (fordi høring kommer først). I praksis
        # ses det ikke, men det dokumenterer adfærd.
        assert _gaet_rolle("Høring og klageskema.pdf") == "høring"
