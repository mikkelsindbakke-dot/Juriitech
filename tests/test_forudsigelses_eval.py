"""
Tests for forudsigelses_eval — pure-logic-delene af forudsigelses-
feedback-løkken.

Feedback-løkken er en BAGVEDLIGGENDE udvikler-funktion: når PAX laver
en førstevurdering gemmer vi forudsigelsen, og når Nævnet senere
offentliggør den faktiske afgørelse matcher vi de to og måler hvor
ofte PAX ramte rigtigt. Intet af dette er synligt for brugeren.

Disse tests dækker de rene funktioner — sagsnummer-/udfalds-
normalisering + ramt/ikke-ramt-beregning — så matchningen er
deterministisk og pålidelig.
"""
import pytest

from forudsigelses_eval import (
    normaliser_sagsnummer,
    normaliser_udfald,
    pax_argmax_bucket,
    beregn_traf_rigtigt,
    udtraek_udfald_fra_afgoerelse,
    udtraek_sagsnummer_fra_afgoerelse,
)


pytestmark = pytest.mark.logic


class TestNormaliserSagsnummer:
    def test_fjerner_pdf_suffix(self):
        assert normaliser_sagsnummer("2026-00660.pdf") == "2026-00660"

    def test_trimmer_whitespace(self):
        assert normaliser_sagsnummer("  25-1234  ") == "25-1234"

    def test_fjerner_anchor_ord(self):
        assert normaliser_sagsnummer("Sag nr. 25-1234") == "25-1234"
        assert normaliser_sagsnummer("Sagsnummer: 2026-00660") == "2026-00660"

    def test_norsk_format_bevares(self):
        assert normaliser_sagsnummer("2026-00660") == "2026-00660"

    def test_dansk_format_bevares(self):
        assert normaliser_sagsnummer("25-109-8024327") == "25-109-8024327"

    def test_tom_og_none(self):
        assert normaliser_sagsnummer("") == ""
        assert normaliser_sagsnummer(None) == ""

    def test_uden_nummer_returnerer_tom(self):
        assert normaliser_sagsnummer("ingen tal her") == ""

    def test_case_insensitiv_pdf(self):
        assert normaliser_sagsnummer("2026-00660.PDF") == "2026-00660"


class TestNormaliserUdfald:
    def test_ikke_medhold_bliver_afvist(self):
        assert normaliser_udfald("Ikke medhold") == "afvist"
        assert normaliser_udfald("ikke medhold") == "afvist"

    def test_afvist_varianter(self):
        assert normaliser_udfald("Afvist") == "afvist"
        assert normaliser_udfald("Klagen afvises") == "afvist"
        assert normaliser_udfald("Indklagede frifindes") == "afvist"

    def test_delvist_medhold(self):
        assert normaliser_udfald("Delvist medhold") == "delvist_medhold"
        assert normaliser_udfald("Delvis medhold") == "delvist_medhold"
        assert normaliser_udfald("delvist medhold til klager") == "delvist_medhold"

    def test_fuld_medhold(self):
        assert normaliser_udfald("Fuld medhold til klager") == "fuld_medhold"
        assert normaliser_udfald("Medhold") == "fuld_medhold"
        assert normaliser_udfald("Fullt medhold") == "fuld_medhold"

    def test_ukendt(self):
        assert normaliser_udfald("ukendt") == "ukendt"
        assert normaliser_udfald("") == "ukendt"
        assert normaliser_udfald(None) == "ukendt"
        assert normaliser_udfald("noget uventet vrøvl") == "ukendt"

    def test_delvist_vinder_over_medhold_substring(self):
        """'Delvis medhold' indeholder 'medhold' — men SKAL klassificeres
        som delvist, ikke fuld. Rækkefølgen i matchningen er vigtig."""
        assert normaliser_udfald("Delvis medhold") == "delvist_medhold"


class TestPaxArgmaxBucket:
    def test_afvisning_hoejest(self):
        assert pax_argmax_bucket(10, 30, 60) == "afvist"

    def test_delvist_hoejest(self):
        assert pax_argmax_bucket(20, 55, 25) == "delvist_medhold"

    def test_fuld_hoejest(self):
        assert pax_argmax_bucket(70, 20, 10) == "fuld_medhold"

    def test_uafgjort_tager_foerste_hoejeste(self):
        # Ved lige procenter: deterministisk valg (fuld > delvist > afvist
        # i tie-break-rækkefølge).
        assert pax_argmax_bucket(40, 40, 20) == "fuld_medhold"

    def test_haandterer_none_som_nul(self):
        assert pax_argmax_bucket(None, 50, 50) in ("delvist_medhold", "afvist")

    def test_alle_nul(self):
        # Degenereret input — må ikke crashe
        assert pax_argmax_bucket(0, 0, 0) == "fuld_medhold"


class TestBeregnTrafRigtigt:
    def test_ramte_rigtigt(self):
        assert beregn_traf_rigtigt("afvist", "afvist") is True

    def test_ramte_forkert(self):
        assert beregn_traf_rigtigt("fuld_medhold", "afvist") is False

    def test_faktisk_ukendt_giver_none(self):
        # Kan ikke score mod et ukendt facit
        assert beregn_traf_rigtigt("delvist_medhold", "ukendt") is None

    def test_delvist_match(self):
        assert beregn_traf_rigtigt("delvist_medhold", "delvist_medhold") is True


class TestUdtraekUdfaldFraAfgoerelse:
    def test_norsk_header_ikke_medhold(self):
        indhold = (
            "Saksnummer: 2026-00660 Dato: 15.04.2026 Tjenesteyter: "
            "Apollo Reiser AS Udfall: Ikke medhold Sammendrag: Krav om "
            "refusjon for transfer."
        )
        assert udtraek_udfald_fra_afgoerelse(indhold) == "afvist"

    def test_dansk_header_udfald(self):
        indhold = (
            "Sagsnummer: 25-1234 Dato: 01.03.2025 Udfald: Delvist medhold "
            "Sammendrag: Klagen angår manglende rengøring."
        )
        assert udtraek_udfald_fra_afgoerelse(indhold) == "delvist_medhold"

    def test_ukendt_header(self):
        indhold = "Saksnummer: 2026-00554 Udfall: ukendt Sammendrag: ..."
        assert udtraek_udfald_fra_afgoerelse(indhold) == "ukendt"

    def test_manglende_header_giver_ukendt(self):
        assert udtraek_udfald_fra_afgoerelse("Ingen header her.") == "ukendt"

    def test_tom_indhold(self):
        assert udtraek_udfald_fra_afgoerelse("") == "ukendt"
        assert udtraek_udfald_fra_afgoerelse(None) == "ukendt"


class TestUdtraekSagsnummerFraAfgoerelse:
    def test_norsk_saksnummer_header(self):
        indhold = "Saksnummer: 2026-00660 Dato: 15.04.2026 Tjenesteyter: X"
        assert udtraek_sagsnummer_fra_afgoerelse(indhold) == "2026-00660"

    def test_dansk_sagsnummer_header(self):
        indhold = "Sagsnummer: 25-1234 Dato: 01.03.2025 Udfald: Medhold"
        assert udtraek_sagsnummer_fra_afgoerelse(indhold) == "25-1234"

    def test_manglende_header(self):
        assert udtraek_sagsnummer_fra_afgoerelse("Ingen header.") == ""

    def test_tom(self):
        assert udtraek_sagsnummer_fra_afgoerelse("") == ""
        assert udtraek_sagsnummer_fra_afgoerelse(None) == ""
