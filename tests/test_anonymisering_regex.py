"""
Tests for anonymisering_pdf._patterns_via_regex.

Disse regex'er er den deterministiske del af anonymiseringen — de
finder CPR, e-mails og telefonnumre uden at involvere AI'en. Hvis de
brækker, lækker vi følsomme data til Pakkerejse-Ankenævnet, så de
SKAL være korrekte.

Test-strategi:
- Positive cases: hver kategori skal matche typiske eksempler
- Negative cases: lignende mønstre der IKKE skal matche (fx datoer,
  pris-tags, sagsnumre)
- Boundary cases: tom streng, tekst uden følsomme data
"""
import pytest

from anonymisering_pdf import _patterns_via_regex


pytestmark = pytest.mark.regex


# ─────────── CPR ───────────

class TestCPR:
    def test_matcher_cpr_med_bindestreg(self):
        targets = _patterns_via_regex("Klagers CPR er 010190-1234.")
        assert {"streng": "010190-1234", "kategori": "cpr"} in targets

    def test_matcher_cpr_uden_bindestreg(self):
        targets = _patterns_via_regex("CPR 0101901234 noteret")
        assert {"streng": "0101901234", "kategori": "cpr"} in targets

    def test_matcher_ikke_dato_format_dd_mm_yyyy(self):
        # 25-04-2026 er en dato, ikke et CPR — den må IKKE blive flagged.
        # CPR-regex'en kræver 6 cifre + valgfri bindestreg + 4 cifre
        # uden ekstra bindestreger imellem.
        targets = _patterns_via_regex("Rejsen var 25-04-2026.")
        cpr_targets = [t for t in targets if t["kategori"] == "cpr"]
        assert cpr_targets == []

    def test_matcher_ikke_kort_tal(self):
        targets = _patterns_via_regex("Pris: 12.345 kr.")
        cpr_targets = [t for t in targets if t["kategori"] == "cpr"]
        assert cpr_targets == []

    def test_finder_flere_cpr_i_samme_tekst(self):
        targets = _patterns_via_regex(
            "Klager 010190-1234, medrejsende 0202911234"
        )
        cpr_strings = [t["streng"] for t in targets if t["kategori"] == "cpr"]
        assert "010190-1234" in cpr_strings
        assert "0202911234" in cpr_strings


# ─────────── E-mail (kun lokal-del redactes, domænet bevares) ───────────

class TestEmail:
    def test_matcher_simpel_email(self):
        targets = _patterns_via_regex("Skriv til klage@tui.dk")
        assert {"streng": "klage", "kategori": "email_lokaldel"} in targets

    def test_matcher_email_med_dots(self):
        targets = _patterns_via_regex("Anders.Andersen@hotel.com siger...")
        assert {"streng": "Anders.Andersen", "kategori": "email_lokaldel"} in targets

    def test_matcher_email_med_plus_alias(self):
        targets = _patterns_via_regex("kontakt anders+klage@firma.dk")
        assert {"streng": "anders+klage", "kategori": "email_lokaldel"} in targets

    def test_bevarer_domaene_via_kun_lokaldel_capture(self):
        # Hele pointen: vi redactes KUN lokaldelen så domænet bevares.
        # Det gør anonymiseringen mindre invasiv (Nævnet kan stadig se
        # at det er fra hotellet, men ikke hvilken person).
        targets = _patterns_via_regex("info@grand-resort-hotel.com")
        email_strings = [t["streng"] for t in targets if t["kategori"] == "email_lokaldel"]
        assert "info" in email_strings
        # Domænet selv må IKKE være i targets
        for t in targets:
            assert "grand-resort-hotel.com" not in t["streng"]

    def test_matcher_ikke_url(self):
        # http://example.com/path bør ikke fange noget her — vi har
        # ingen regex der ligner URLs, men sikrer at vi ikke uheldigvis
        # matcher noget der ligner email.
        targets = _patterns_via_regex("Se https://www.tui.dk for detaljer")
        emails = [t for t in targets if t["kategori"] == "email_lokaldel"]
        assert emails == []


# ─────────── Telefon (DK + internationalt) ───────────

class TestTelefon:
    def test_matcher_internationalt_format_dk(self):
        targets = _patterns_via_regex("Ring +45 12 34 56 78 før kl. 17")
        tlf_strings = [t["streng"] for t in targets if t["kategori"] == "telefon"]
        assert "12 34 56 78" in tlf_strings

    def test_matcher_internationalt_format_uk(self):
        targets = _patterns_via_regex("Tel +44 20 7946 0958 (London)")
        tlf_strings = [t["streng"] for t in targets if t["kategori"] == "telefon"]
        # Vi capture'er alt fra første ciffer efter +44 til det sidste
        # ikke-mellemrum før noget ikke-cifret
        assert any("7946" in s for s in tlf_strings)

    def test_matcher_dk_lokalt_format_med_omraade(self):
        # "928 56 14 14" — typisk Apollo/TUI rejseguide-nummer
        targets = _patterns_via_regex("Resort-tlf 928 56 14 14")
        tlf_strings = [t["streng"] for t in targets if t["kategori"] == "telefon"]
        assert "56 14 14" in tlf_strings

    def test_matcher_ikke_pris_med_kr(self):
        # "1.500 kr." og "12.345 kr." er priser, ikke telefoner
        targets = _patterns_via_regex("Klager kræver 1.500 kr. som kompensation")
        tlf_targets = [t for t in targets if t["kategori"] == "telefon"]
        assert tlf_targets == []


# ─────────── Edge cases ───────────

class TestEdgeCases:
    def test_tom_streng_giver_tom_liste(self):
        assert _patterns_via_regex("") == []

    def test_kun_normal_tekst_giver_tom_liste(self):
        targets = _patterns_via_regex(
            "Klager rejste til Mallorca og var meget skuffet over hotellet."
        )
        assert targets == []

    def test_kombineret_tekst_med_alle_kategorier(self):
        tekst = (
            "Klagers CPR 010190-1234 og email klage@tui.dk. "
            "Ring +45 12 34 56 78 for opfølgning."
        )
        targets = _patterns_via_regex(tekst)
        kategorier = {t["kategori"] for t in targets}
        assert "cpr" in kategorier
        assert "email_lokaldel" in kategorier
        assert "telefon" in kategorier
