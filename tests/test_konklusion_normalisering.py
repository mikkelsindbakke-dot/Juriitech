"""
Tests for ai_engine._normalisér_konklusion.

Den akademiske formulering 'sagen anbefales overvejende afvist' skal
rewrites til prædiktiv stil 'sagen forventes overvejende afvist' før
konklusionen vises i UI'et. Dette er en deterministisk post-processor
der løber efter AI-kaldet og fanger tilfælde hvor modellen ignorerede
prompt-instruktionen.
"""
import pytest

from ai_engine import _normalisér_konklusion


pytestmark = pytest.mark.logic


class TestErstatningAfAnbefales:
    def test_overvejende_afvist(self):
        ind = (
            "Sagen anbefales overvejende afvist, da konflikten skyldes "
            "tredjemands adfærd."
        )
        ud = _normalisér_konklusion(ind)
        assert "anbefales" not in ud.lower()
        assert "Sagen forventes overvejende afvist" in ud

    def test_delvist_afvist(self):
        ind = "Sagen anbefales delvist afvist da reklamationen var for sen."
        ud = _normalisér_konklusion(ind)
        assert ud.startswith("Sagen forventes delvist afvist")

    def test_lowercase_input_giver_lowercase_output(self):
        ind = "klagen anbefales afvist"
        ud = _normalisér_konklusion(ind)
        assert "klagen forventes afvist" == ud

    def test_midt_i_saetning(self):
        ind = "I dette tilfælde anbefales sagen at ende med delvist medhold."
        ud = _normalisér_konklusion(ind)
        assert "forventes" in ud
        assert "anbefales" not in ud


class TestUaendret:
    def test_saetning_uden_anbefales_er_uaendret(self):
        ind = "Sagen forventes afvist på grund af manglende dokumentation."
        ud = _normalisér_konklusion(ind)
        assert ud == ind

    def test_andre_ord_med_anbefal_stamme_paavirkes_ikke(self):
        # \b-grænsen i regex'en skal sikre at 'anbefaling' ikke rewrites
        ind = "Vores juridiske anbefaling står ved magt."
        ud = _normalisér_konklusion(ind)
        assert ud == ind

    def test_tom_streng_returneres_uaendret(self):
        assert _normalisér_konklusion("") == ""
        assert _normalisér_konklusion(None) is None
