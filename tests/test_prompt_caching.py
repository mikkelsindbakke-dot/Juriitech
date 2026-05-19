"""
Tests for prompt-caching-wrapper i ai_engine.

Verificerer at _system_med_cache:
  • Returnerer korrekt content-block-format som Anthropic SDK forventer
  • Inkluderer cache_control-direktivet på alle blokke
  • Bevarer prompten 1:1 (ingen trimning, ingen format-ændring)

Selve cache-rabatten verificeres af Anthropic på serversiden — vi tester
KUN at vi sender de korrekte instruktioner. End-to-end-verifikation
(faktisk cache-hit) kræver et live-kald og cache-usage-report fra
Anthropic, hvilket ikke hører hjemme i en unit-test.
"""
import pytest

from ai_engine import _system_med_cache


pytestmark = pytest.mark.logic


class TestSystemMedCache:
    def test_returnerer_liste(self):
        ud = _system_med_cache("dummy prompt")
        assert isinstance(ud, list)
        assert len(ud) == 1

    def test_indeholder_korrekt_content_block_format(self):
        ud = _system_med_cache("dummy prompt")
        blok = ud[0]
        assert blok["type"] == "text"
        assert blok["text"] == "dummy prompt"
        assert blok["cache_control"] == {"type": "ephemeral"}

    def test_bevarer_prompt_uaendret(self):
        # Lange prompts med specialtegn skal komme retur uden ændringer
        prompt = (
            "Du er en juridisk konsulent.\n\n"
            "REGLER:\n"
            "  1. Brug danske termer\n"
            "  2. Citér bilag som [Bilag 03, s. 1]\n"
            "Tegn som æøå, ¿¿, %%, $$ skal ikke escapes."
        )
        ud = _system_med_cache(prompt)
        assert ud[0]["text"] == prompt

    def test_tom_prompt_giver_tom_text_block(self):
        # Defensivt: vi crasher ikke på tom streng (selvom det ikke giver
        # mening i praksis — minimum 1024 tokens for cache-rabat)
        ud = _system_med_cache("")
        assert ud[0]["text"] == ""
        assert ud[0]["cache_control"] == {"type": "ephemeral"}


class TestIntegrationMedSystemPrompt:
    """
    SYSTEM_PROMPT er den primære cache-kandidat (~3000 tokens, identisk
    mellem alle sager). Vi verificerer at den faktiske constant kan
    wrappes uden at miste indhold.
    """

    def test_system_prompt_kan_wrappes(self):
        from ai_engine import SYSTEM_PROMPT
        ud = _system_med_cache(SYSTEM_PROMPT)
        assert ud[0]["text"] == SYSTEM_PROMPT
        # Sanity: prompten er stor nok til at cache faktisk hjælper
        # (Sonnet kræver ~1024 tokens minimum — 1024 * 4 chars/token = 4096)
        assert len(SYSTEM_PROMPT) > 3000, (
            "SYSTEM_PROMPT er kortere end forventet — caching giver "
            "muligvis ingen rabat"
        )


class TestActualAICallSendesMedCache:
    """
    Integration-check: mocker Anthropic-klienten og verificerer at den
    faktiske AI-funktion sender system-parameteren som content-block-liste
    med cache_control. Hvis nogen kommer til at omdøbe eller fjerne
    _system_med_cache-kaldet i fremtiden fanger denne test det.
    """

    def test_generer_tjekliste_sender_cached_system(self, monkeypatch):
        import ai_engine

        kald_args = {}

        class _FakeResponse:
            class _Content:
                text = "stub"
            content = [_Content()]
            stop_reason = "end_turn"

        class _FakeMessages:
            def create(self, **kwargs):
                kald_args.update(kwargs)
                return _FakeResponse()

        class _FakeClient:
            messages = _FakeMessages()

        monkeypatch.setattr(ai_engine, "client", _FakeClient())

        sag = {
            "filer": [
                {"filnavn": "Høring R.docx", "rolle": "høring", "tekst": "x"}
            ]
        }
        ai_engine.generer_tjekliste(sag)

        system_param = kald_args.get("system")
        assert isinstance(system_param, list), (
            "system skal være en liste af content-blokke (cache-format), "
            "ikke en string"
        )
        assert system_param[0].get("cache_control") == {"type": "ephemeral"}, (
            "cache_control skal være sat på system-blokken"
        )
