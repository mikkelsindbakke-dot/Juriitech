"""
Tests for ai_engine._filtrer_og_cap_matches.

Den lignende-sager-liste der vises under analysen havde tidligere
to problemer:
  1. Sager hvor udfaldet ikke kunne udledes fik "Ukendt"-tag og var
     uden konkret prejudikatværdi for juristen.
  2. Listen kunne vokse til 5+ sager, hvilket gjorde scanning langsom.

Denne funktion løser begge i én operation:
  - Filtrerer alle sager med udfald="Ukendt" (case-insensitive) ud.
  - Capper listen til top N (default 3, da reranker'en allerede har
    sorteret efter præcedens-relevans).
"""
import pytest

from ai_engine import _filtrer_og_cap_matches, par_filtrer_relevante_og_matches


pytestmark = pytest.mark.logic


def _mk(udfald="Delvist medhold", sagsnummer="24-001"):
    return {
        "sagsnummer": sagsnummer,
        "titel": "test",
        "udfald": udfald,
        "klagers_krav": "10.000 kr.",
        "tilkendt_beloeb": "5.000 kr.",
        "match_begrundelse": ["test"],
    }


class TestFiltrering:
    def test_ukendt_fjernes(self):
        matches = [
            _mk(udfald="Delvist medhold", sagsnummer="A"),
            _mk(udfald="Ukendt", sagsnummer="B"),
            _mk(udfald="Afvist", sagsnummer="C"),
        ]
        ud = _filtrer_og_cap_matches(matches)
        sagsnumre = [m["sagsnummer"] for m in ud]
        assert sagsnumre == ["A", "C"]

    def test_ukendt_case_insensitive(self):
        matches = [
            _mk(udfald="ukendt", sagsnummer="A"),
            _mk(udfald="UKENDT", sagsnummer="B"),
            _mk(udfald="Ukendt", sagsnummer="C"),
            _mk(udfald="Afvist", sagsnummer="D"),
        ]
        ud = _filtrer_og_cap_matches(matches)
        assert [m["sagsnummer"] for m in ud] == ["D"]

    def test_tom_udfald_filtreres(self):
        matches = [
            _mk(udfald="", sagsnummer="A"),
            _mk(udfald="Delvist medhold", sagsnummer="B"),
        ]
        ud = _filtrer_og_cap_matches(matches)
        assert [m["sagsnummer"] for m in ud] == ["B"]

    def test_manglende_udfald_filtreres(self):
        matches = [
            {"sagsnummer": "A", "titel": "uden udfald-felt"},
            _mk(udfald="Fuld medhold til klager", sagsnummer="B"),
        ]
        ud = _filtrer_og_cap_matches(matches)
        assert [m["sagsnummer"] for m in ud] == ["B"]


class TestCap:
    def test_capper_til_top_3_default(self):
        matches = [
            _mk(udfald="Delvist medhold", sagsnummer=str(i))
            for i in range(10)
        ]
        ud = _filtrer_og_cap_matches(matches)
        assert len(ud) == 3
        assert [m["sagsnummer"] for m in ud] == ["0", "1", "2"]

    def test_cap_n_konfigurerbar(self):
        matches = [
            _mk(udfald="Afvist", sagsnummer=str(i)) for i in range(10)
        ]
        ud = _filtrer_og_cap_matches(matches, max_n=5)
        assert len(ud) == 5

    def test_under_cap_bibeholdes(self):
        matches = [
            _mk(udfald="Fuld medhold til klager", sagsnummer="A"),
            _mk(udfald="Delvist medhold", sagsnummer="B"),
        ]
        ud = _filtrer_og_cap_matches(matches)
        assert len(ud) == 2

    def test_kombineret_filter_og_cap(self):
        """Hvis 8 sager hvor 4 er Ukendt og 4 har klart udfald, og max_n=3:
        kun de første 3 ne-Ukendt sager skal vises."""
        matches = [
            _mk(udfald="Ukendt", sagsnummer="bad-1"),
            _mk(udfald="Delvist medhold", sagsnummer="good-1"),
            _mk(udfald="Ukendt", sagsnummer="bad-2"),
            _mk(udfald="Afvist", sagsnummer="good-2"),
            _mk(udfald="Ukendt", sagsnummer="bad-3"),
            _mk(udfald="Fuld medhold til klager", sagsnummer="good-3"),
            _mk(udfald="Ukendt", sagsnummer="bad-4"),
            _mk(udfald="Delvist medhold", sagsnummer="good-4"),
        ]
        ud = _filtrer_og_cap_matches(matches)
        assert [m["sagsnummer"] for m in ud] == ["good-1", "good-2", "good-3"]


class TestEdgeCases:
    def test_tom_liste(self):
        assert _filtrer_og_cap_matches([]) == []

    def test_alle_ukendt_returnerer_tom(self):
        matches = [_mk(udfald="Ukendt", sagsnummer=str(i)) for i in range(5)]
        assert _filtrer_og_cap_matches(matches) == []

    def test_none_input(self):
        assert _filtrer_og_cap_matches(None) == []


class TestParFiltrer:
    """
    par_filtrer_relevante_og_matches holder rel_sager + match_info i
    parallel. Frontend parrer dem ved index — så filtrering SKAL ske
    samtidigt i begge lister.
    """

    def test_dropper_ukendt_par_synkront(self):
        rel = [
            {"filnavn": "A.pdf"},
            {"filnavn": "B.pdf"},
            {"filnavn": "C.pdf"},
            {"filnavn": "D.pdf"},
        ]
        mi = [
            {"udfald": "Delvist medhold"},
            {"udfald": "Ukendt"},
            {"udfald": "Afvist"},
            {"udfald": "Ukendt"},
        ]
        rel_ud, mi_ud = par_filtrer_relevante_og_matches(rel, mi)
        assert [s["filnavn"] for s in rel_ud] == ["A.pdf", "C.pdf"]
        assert [m["udfald"] for m in mi_ud] == ["Delvist medhold", "Afvist"]
        assert len(rel_ud) == len(mi_ud)

    def test_capper_til_3(self):
        rel = [{"filnavn": f"{i}.pdf"} for i in range(10)]
        mi = [{"udfald": "Delvist medhold"} for _ in range(10)]
        rel_ud, mi_ud = par_filtrer_relevante_og_matches(rel, mi)
        assert len(rel_ud) == 3
        assert len(mi_ud) == 3
        assert [s["filnavn"] for s in rel_ud] == ["0.pdf", "1.pdf", "2.pdf"]

    def test_kombineret_filter_og_cap_synkront(self):
        rel = [{"filnavn": f"{n}.pdf"} for n in ["b1", "g1", "b2", "g2", "b3", "g3", "g4"]]
        mi = [
            {"udfald": "Ukendt"},
            {"udfald": "Delvist medhold"},
            {"udfald": "Ukendt"},
            {"udfald": "Afvist"},
            {"udfald": "Ukendt"},
            {"udfald": "Fuld medhold til klager"},
            {"udfald": "Delvist medhold"},  # skal aldrig nås — cap rammer før
        ]
        rel_ud, mi_ud = par_filtrer_relevante_og_matches(rel, mi)
        assert [s["filnavn"] for s in rel_ud] == ["g1.pdf", "g2.pdf", "g3.pdf"]
        assert len(mi_ud) == 3

    def test_tom_match_info_fallbacker_til_raw_topN(self):
        """Hvis AI-kaldet til match_info fejlede er listen tom — vi viser
        så bare top N rå retrieval-resultater så brugeren ikke får et tomt
        kort i UI'et."""
        rel = [{"filnavn": f"{i}.pdf"} for i in range(5)]
        rel_ud, mi_ud = par_filtrer_relevante_og_matches(rel, [])
        assert len(rel_ud) == 3
        assert mi_ud == []

    def test_tom_rel_sager_returnerer_tom_alt(self):
        rel_ud, mi_ud = par_filtrer_relevante_og_matches(
            [], [{"udfald": "Afvist"}]
        )
        assert rel_ud == []
        assert mi_ud == []

    def test_mi_kortere_end_rel(self):
        """Defensiv: hvis AI returnerede færre match_info end vi har rel-
        sager, må vi ikke crashe — vi iterer kun over match_info-længden."""
        rel = [{"filnavn": "A"}, {"filnavn": "B"}, {"filnavn": "C"}]
        mi = [{"udfald": "Afvist"}]
        rel_ud, mi_ud = par_filtrer_relevante_og_matches(rel, mi)
        assert [s["filnavn"] for s in rel_ud] == ["A"]
        assert len(mi_ud) == 1
