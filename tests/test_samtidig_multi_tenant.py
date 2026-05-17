"""
Virtuel samtidigheds-test: 3 danske tenants + 1 norsk tenant kører
tenant-bevidste kodeveje PARALLELT.

Formål: bekræfte at multi-tenant-isolationen holder under samtidig
last — at tenant A's sprog/branding ALDRIG lækker ind i tenant B's
output. ContextVar er designet til per-request-isolation, men hvis
ÉN kodevej bruger en modul-global i stedet for et per-request-lookup,
bryder isolationen sammen netop ved samtidighed.

Vi simulerer FastAPI's request-model: hver "request" = én tråd der
sætter sin egen aktiv-profil via saet_aktiv_profil() og kører en
batteri af tenant-bevidste funktioner i en stram løkke. Hvis nogen
funktion lækker, vil mindst én tråd se en forkert værdi.
"""
import concurrent.futures
import threading

import pytest

from selskab_profiler import saet_aktiv_profil, reset_aktiv_profil
from ai_engine import (
    _hent_sprog,
    _hent_navn,
    _hent_klageorgan_navn,
    _sprog,
    _sprog_caps,
    _sprog_direktiv,
    _sprog_anchor_end,
    _system_prompt,
    byg_svarbrev_opgave,
    _byg_foerstevurdering_schema,
)


pytestmark = pytest.mark.logic


# ─────────── Tenant-profiler (4 stk: 3 DA + 1 NO) ───────────

TUI = {
    "id": 1,
    "slug": "tui",
    "navn": "TUI",
    "sagsbehandler": "TUI Customer Care",
    "by": "Frederiksberg",
    "anonymisering_suffix": "TUI",
    "interne_team_navne": ["After Travel", "Customer Service"],
    "klageorgan_navn": "Pakkerejse-Ankenævnet",
    "klageorgan_url": "https://www.pakkerejseankenaevnet.dk",
    "rejsevilkaar_kilde_url": "https://www.tui.dk/",
    "sprog": "da",
    "land": "DK",
    "lov_navn": "Pakkerejseloven",
}

APOLLO = {
    "id": 2,
    "slug": "apollo",
    "navn": "Apollo Rejser",
    "sagsbehandler": "Apollo Kundeservice",
    "by": "København",
    "anonymisering_suffix": "Apollo",
    "interne_team_navne": ["Kundeservice"],
    "klageorgan_navn": "Pakkerejse-Ankenævnet",
    "klageorgan_url": "https://www.pakkerejseankenaevnet.dk",
    "rejsevilkaar_kilde_url": "https://www.apollorejser.dk/",
    "sprog": "da",
    "land": "DK",
    "lov_navn": "Pakkerejseloven",
}

SPIES = {
    "id": 3,
    "slug": "spies",
    "navn": "Spies",
    "sagsbehandler": "Spies Kundeservice",
    "by": "København",
    "anonymisering_suffix": "Spies",
    "interne_team_navne": ["Kundeservice"],
    "klageorgan_navn": "Pakkerejse-Ankenævnet",
    "klageorgan_url": "https://www.pakkerejseankenaevnet.dk",
    "rejsevilkaar_kilde_url": "https://www.spies.dk/",
    "sprog": "da",
    "land": "DK",
    "lov_navn": "Pakkerejseloven",
}

FJORD = {
    "id": 11,
    "slug": "fjordtravel",
    "navn": "FjordTravel AS",
    "sagsbehandler": "FjordTravel Kundeservice",
    "by": "Oslo",
    "anonymisering_suffix": "FjordTravel",
    "interne_team_navne": ["Kundeservice"],
    "klageorgan_navn": "Pakkereisenemnda",
    "klageorgan_url": "https://www.pakkereisenemnda.no",
    "rejsevilkaar_kilde_url": "https://www.fjordtravel.no/",
    "sprog": "no",
    "land": "NO",
    "lov_navn": "Pakkereiseloven",
}

DK_TENANTS = [TUI, APOLLO, SPIES]
ALLE_TENANTS = [TUI, APOLLO, SPIES, FJORD]


# ─────────── Forventet output pr. tenant ───────────

def forventet(profil):
    """Returnerer dict med forventede outputs for en given tenant."""
    er_no = profil["sprog"] == "no"
    return {
        "hent_sprog": "no" if er_no else "da",
        "sprog": "norsk bokmål" if er_no else "dansk",
        "sprog_caps": "NORSK BOKMÅL" if er_no else "DANSK",
        "direktiv_tom": not er_no,   # DK: tom streng. NO: ikke-tom.
        "anchor_tom": not er_no,
        "navn": profil["navn"],
        "klageorgan": profil["klageorgan_navn"],
    }


def kør_tenant_batteri(profil, iterationer=60):
    """
    Kører tenant-bevidste funktioner i en stram løkke for ÉN tenant.
    Returnerer en liste af fejl-strenge (tom = alt OK).

    Køres i sin egen tråd — ContextVar skal holde profilen isoleret
    fra de øvrige tråde.
    """
    fejl = []
    f = forventet(profil)
    navn = profil["navn"]

    token = saet_aktiv_profil(profil)
    try:
        for i in range(iterationer):
            # ─── Sprog-helpers ───
            if _hent_sprog() != f["hent_sprog"]:
                fejl.append(
                    f"[{navn} #{i}] _hent_sprog()={_hent_sprog()!r} "
                    f"forventet {f['hent_sprog']!r}"
                )
            if _sprog() != f["sprog"]:
                fejl.append(
                    f"[{navn} #{i}] _sprog()={_sprog()!r} forventet {f['sprog']!r}"
                )
            if _sprog_caps() != f["sprog_caps"]:
                fejl.append(
                    f"[{navn} #{i}] _sprog_caps()={_sprog_caps()!r} "
                    f"forventet {f['sprog_caps']!r}"
                )
            direktiv = _sprog_direktiv()
            if f["direktiv_tom"] and direktiv != "":
                fejl.append(f"[{navn} #{i}] _sprog_direktiv() ikke tom for DK")
            if not f["direktiv_tom"] and "NORSK" not in direktiv:
                fejl.append(f"[{navn} #{i}] _sprog_direktiv() mangler NORSK for NO")
            anchor = _sprog_anchor_end()
            if f["anchor_tom"] and anchor != "":
                fejl.append(f"[{navn} #{i}] _sprog_anchor_end() ikke tom for DK")
            if not f["anchor_tom"] and anchor == "":
                fejl.append(f"[{navn} #{i}] _sprog_anchor_end() tom for NO")

            # ─── Branding-helpers ───
            if _hent_navn() != f["navn"]:
                fejl.append(
                    f"[{navn} #{i}] _hent_navn()={_hent_navn()!r} "
                    f"forventet {f['navn']!r}"
                )
            if _hent_klageorgan_navn() != f["klageorgan"]:
                fejl.append(
                    f"[{navn} #{i}] _hent_klageorgan_navn()="
                    f"{_hent_klageorgan_navn()!r} forventet {f['klageorgan']!r}"
                )

            # ─── System-prompt: sprog SKAL matche tenant ───
            sp = _system_prompt()
            if f["hent_sprog"] == "no":
                if "NORSK" not in sp.upper():
                    fejl.append(f"[{navn} #{i}] _system_prompt() ikke norsk for NO-tenant")
            else:
                # DK-system-prompt må ikke være den norske
                if "Pakkereisenemnda" in sp:
                    fejl.append(f"[{navn} #{i}] _system_prompt() er norsk for DK-tenant")
    finally:
        reset_aktiv_profil(token)

    return fejl


# ─────────── Test 1: Sekventiel sanity (uden samtidighed) ───────────

class TestSekventiel:
    """Bekræft først at hver tenant er korrekt isoleret SET ALENE,
    før vi tester samtidighed."""

    @pytest.mark.parametrize("profil", ALLE_TENANTS, ids=lambda p: p["slug"])
    def test_tenant_batteri_sekventielt(self, profil):
        fejl = kør_tenant_batteri(profil, iterationer=20)
        assert fejl == [], f"{len(fejl)} fejl:\n" + "\n".join(fejl[:20])


# ─────────── Test 2: Samtidig kørsel (4 tenants parallelt) ───────────

class TestSamtidig:
    """
    Kører alle 4 tenants i parallelle tråde. Hvis nogen tenant-bevidst
    funktion bruger modul-global state i stedet for ContextVar/per-
    request-lookup, vil mindst én tråd se en forkert værdi.
    """

    def test_fire_tenants_parallelt(self):
        # Barrier sikrer at alle 4 tråde starter deres løkke SAMTIDIG —
        # maksimal interleaving, bedste chance for at fange en leak.
        barrier = threading.Barrier(len(ALLE_TENANTS))

        def opgave(profil):
            barrier.wait()
            return kør_tenant_batteri(profil, iterationer=150)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(ALLE_TENANTS)
        ) as ex:
            resultater = list(ex.map(opgave, ALLE_TENANTS))

        alle_fejl = []
        for profil, fejl in zip(ALLE_TENANTS, resultater):
            alle_fejl.extend(fejl)

        assert alle_fejl == [], (
            f"{len(alle_fejl)} isolations-fejl under samtidig kørsel:\n"
            + "\n".join(alle_fejl[:30])
        )

    def test_gentaget_under_pres(self):
        """Kører den parallelle test 5 gange — races er ikke-deterministiske,
        så gentagelse øger chancen for at fange en sjælden leak."""
        for runde in range(5):
            barrier = threading.Barrier(len(ALLE_TENANTS))

            def opgave(profil):
                barrier.wait()
                return kør_tenant_batteri(profil, iterationer=80)

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(ALLE_TENANTS)
            ) as ex:
                resultater = list(ex.map(opgave, ALLE_TENANTS))

            for profil, fejl in zip(ALLE_TENANTS, resultater):
                assert fejl == [], (
                    f"Runde {runde}: {len(fejl)} fejl for {profil['navn']}:\n"
                    + "\n".join(fejl[:15])
                )


# ─────────── Test 3: Svarbrev-prompt pr. tenant ───────────

class TestSvarbrevPrTenant:
    """
    byg_svarbrev_opgave shadow'er REJSESELSKAB_NAVN lokalt, så svarbrev-
    prompten SKAL afspejle den aktive tenant — også under samtidighed.
    """

    @pytest.mark.parametrize("profil", ALLE_TENANTS, ids=lambda p: p["slug"])
    def test_svarbrev_indeholder_tenant_navn(self, profil):
        token = saet_aktiv_profil(profil)
        try:
            prompt = byg_svarbrev_opgave(inkluder_kildehenvisninger=False)
        finally:
            reset_aktiv_profil(token)

        # Tenant-navnet skal optræde i prompten
        assert profil["navn"] in prompt, (
            f"{profil['navn']} mangler i svarbrev-prompt"
        )

        if profil["sprog"] == "no":
            # Norsk svarbrev: norsk åbnings-sætning + norsk klageorgan
            assert "legge frem sine bemerkninger" in prompt, (
                "Norsk åbnings-sætning mangler i NO-svarbrev"
            )
            assert "JURIDISK NORSK BOKMÅL" in prompt
            assert profil["klageorgan_navn"] in prompt
            # Andre tenants' navne må IKKE lække ind
            for andet in ["TUI", "Apollo Rejser", "Spies"]:
                assert andet not in prompt, (
                    f"Fremmed tenant-navn '{andet}' lækkede ind i "
                    f"{profil['navn']}s svarbrev"
                )
        else:
            # DK svarbrev: dansk åbnings-sætning
            assert "komme med sine bemærkninger" in prompt
            assert "legge frem sine bemerkninger" not in prompt

    def test_svarbrev_samtidigt_fire_tenants(self):
        """Byg svarbrev-prompts for alle 4 tenants parallelt — verificér
        at hver prompt indeholder KUN sin egen tenants navn."""
        barrier = threading.Barrier(len(ALLE_TENANTS))

        def byg(profil):
            barrier.wait()
            resultater = []
            for _ in range(40):
                token = saet_aktiv_profil(profil)
                try:
                    p = byg_svarbrev_opgave(inkluder_kildehenvisninger=False)
                finally:
                    reset_aktiv_profil(token)
                resultater.append(p)
            return profil, resultater

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(ALLE_TENANTS)
        ) as ex:
            udfald = list(ex.map(byg, ALLE_TENANTS))

        fejl = []
        andre_navne = {
            "tui": ["Apollo Rejser", "Spies", "FjordTravel AS"],
            "apollo": ["TUI", "Spies", "FjordTravel AS"],
            "spies": ["TUI", "Apollo Rejser", "FjordTravel AS"],
            "fjordtravel": ["TUI", "Apollo Rejser", "Spies"],
        }
        for profil, prompts in udfald:
            for idx, p in enumerate(prompts):
                if profil["navn"] not in p:
                    fejl.append(f"{profil['navn']} #{idx}: eget navn mangler")
                for fremmed in andre_navne[profil["slug"]]:
                    # 'Spies' er substreng-følsom — tjek ordgrænse løst
                    if fremmed in p:
                        fejl.append(
                            f"{profil['navn']} #{idx}: fremmed navn "
                            f"'{fremmed}' lækkede ind"
                        )
        assert fejl == [], f"{len(fejl)} svarbrev-leaks:\n" + "\n".join(fejl[:20])


# ─────────── Test 4: Foerstevurdering-schema pr. tenant ───────────

class TestSchemaPrTenant:
    """
    _byg_foerstevurdering_schema(sprog) bygger tool-use-schemaet. Schema-
    felternes 'description' er det AI'en spejler mest — så de SKAL
    afspejle den aktive tenant (navn + sprog), ikke en hardcoded default.
    """

    @pytest.mark.parametrize("profil", ALLE_TENANTS, ids=lambda p: p["slug"])
    def test_schema_navn_matcher_tenant(self, profil):
        token = saet_aktiv_profil(profil)
        try:
            schema = _byg_foerstevurdering_schema(profil["sprog"])
        finally:
            reset_aktiv_profil(token)

        schema_str = str(schema)

        # Schemaet nævner reiseselskapet ved navn i flere beskrivelser.
        # Det navn SKAL være den aktive tenants — ikke en fremmed tenants.
        for fremmed in ["TUI", "Apollo Rejser", "Spies", "FjordTravel AS"]:
            if fremmed == profil["navn"]:
                continue
            assert fremmed not in schema_str, (
                f"{profil['navn']}s foerstevurdering-schema indeholder "
                f"fremmed tenant-navn '{fremmed}'"
            )
