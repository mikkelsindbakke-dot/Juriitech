"""
Cross-country isolation test for Norge-tenants.

Verifies at hent_alle_sager + hent_sager_af_type filtrerer offentlige
docs på land — så norske tenants ikke ser danske offentlige docs og
omvendt.

KØRSEL:
    python test_norge_rag_isolation.py

Forudsætninger:
  - DATABASE_URL i .env peger på prod-DB
  - TUI-tenant (id=1, land=DK) og FjordTravel (id=11, land=NO) eksisterer

VIGTIGT: READ-ONLY mod prod-DB — ingen INSERT/UPDATE/DELETE.

Oracle: vi spørger DB direkte hvor mange docs DER SKAL returneres
(public-i-land + private-for-tenant) og sammenligner med funktionens
output. Funktionen er korrekt hvis count'ene matcher.
"""

import os
import sys

from dotenv import load_dotenv
load_dotenv(".env")
load_dotenv("pax-next/.env.local", override=False)

import psycopg2
from database import hent_alle_sager, hent_sager_af_type


TUI_TENANT_ID = 1            # land=DK
FJORD_TENANT_ID = 11         # land=NO


def _oracle_count(cur, *, tenant_id, land, dokumenttype=None):
    """
    Direkte SQL-oracle: hvor mange docs er public-i-land ELLER private-for-tenant?
    Dette er den KORREKTE adfærd som funktionerne skal matche.
    """
    sql = """
        SELECT COUNT(*) FROM mine_dokumenter
        WHERE ((is_public = TRUE AND land = %s) OR tenant_id = %s)
    """
    params = [land, tenant_id]
    if dokumenttype is not None:
        sql += " AND dokumenttype = %s"
        params.append(dokumenttype)
    cur.execute(sql, params)
    return cur.fetchone()[0]


def _oracle_land_leak(cur, *, tenant_id, andet_land, dokumenttype=None):
    """
    Antal docs som funktionen ville returnere MED det andet lands public-docs
    (dvs. lækken — det vi VIL teste mod).
    """
    sql = """
        SELECT COUNT(*) FROM mine_dokumenter
        WHERE is_public = TRUE AND land = %s
    """
    params = [andet_land]
    if dokumenttype is not None:
        sql += " AND dokumenttype = %s"
        params.append(dokumenttype)
    cur.execute(sql, params)
    return cur.fetchone()[0]


def afsnit(titel):
    print(f"\n{'=' * 70}\n{titel}\n{'=' * 70}")


def kraev(betingelse, beskrivelse):
    if betingelse:
        print(f"  ✅ {beskrivelse}")
        return 0
    else:
        print(f"  ❌ {beskrivelse}")
        return 1


def main():
    fejl = 0
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    # ─── TEST 1: hent_alle_sager for FjordTravel ───
    afsnit("TEST 1: hent_alle_sager(FjordTravel, land=NO) skal returnere kun NO-public + Fjord-private")
    forventet = _oracle_count(cur, tenant_id=FJORD_TENANT_ID, land="NO")
    laek_potentiel = _oracle_land_leak(cur, tenant_id=FJORD_TENANT_ID, andet_land="DK")
    faktisk = hent_alle_sager(tenant_id=FJORD_TENANT_ID, land="NO")
    fejl += kraev(
        len(faktisk) == forventet,
        f"FjordTravel får {len(faktisk)} docs (forventet {forventet}, "
        f"hvis bug så ville lække {laek_potentiel} ekstra DK-docs)",
    )

    # ─── TEST 2: hent_sager_af_type('lovgivning') for FjordTravel ───
    afsnit("TEST 2: hent_sager_af_type('lovgivning', FjordTravel, land=NO) — kun norske paragrafer")
    forventet = _oracle_count(cur, tenant_id=FJORD_TENANT_ID, land="NO", dokumenttype="lovgivning")
    laek_potentiel = _oracle_land_leak(cur, tenant_id=FJORD_TENANT_ID, andet_land="DK", dokumenttype="lovgivning")
    faktisk = hent_sager_af_type("lovgivning", tenant_id=FJORD_TENANT_ID, land="NO")
    fejl += kraev(
        len(faktisk) == forventet,
        f"FjordTravel lovgivning: {len(faktisk)} (forventet {forventet}, "
        f"DK-lækage potentiale: {laek_potentiel})",
    )

    # ─── TEST 3: hent_alle_sager for TUI ───
    afsnit("TEST 3: hent_alle_sager(TUI, land=DK) skal returnere kun DK-public + TUI-private (uændret fra pre-Norge)")
    forventet = _oracle_count(cur, tenant_id=TUI_TENANT_ID, land="DK")
    laek_potentiel = _oracle_land_leak(cur, tenant_id=TUI_TENANT_ID, andet_land="NO")
    faktisk = hent_alle_sager(tenant_id=TUI_TENANT_ID, land="DK")
    fejl += kraev(
        len(faktisk) == forventet,
        f"TUI får {len(faktisk)} docs (forventet {forventet}, "
        f"hvis bug så ville lække {laek_potentiel} NO-docs ind)",
    )

    # ─── TEST 4: hent_sager_af_type('lovgivning') for TUI ───
    afsnit("TEST 4: hent_sager_af_type('lovgivning', TUI, land=DK) — kun danske paragrafer (uændret fra pre-Norge)")
    forventet = _oracle_count(cur, tenant_id=TUI_TENANT_ID, land="DK", dokumenttype="lovgivning")
    laek_potentiel = _oracle_land_leak(cur, tenant_id=TUI_TENANT_ID, andet_land="NO", dokumenttype="lovgivning")
    faktisk = hent_sager_af_type("lovgivning", tenant_id=TUI_TENANT_ID, land="DK")
    fejl += kraev(
        len(faktisk) == forventet,
        f"TUI lovgivning: {len(faktisk)} (forventet {forventet}, "
        f"NO-lækage potentiale: {laek_potentiel})",
    )

    # ─── TEST 5: pre/post statistik for at sandsynliggøre "DK-PAX uændret" ───
    afsnit("TEST 5: Bekræft 'dansk PAX uændret' — TUI's tal matcher pre-Norge-state")
    print(f"  TUI total via hent_alle_sager:           {len(hent_alle_sager(tenant_id=TUI_TENANT_ID))}")
    cur.execute("SELECT COUNT(*) FROM mine_dokumenter WHERE land='DK' AND is_public=TRUE")
    dk_public = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM mine_dokumenter WHERE tenant_id=%s", (TUI_TENANT_ID,))
    tui_private = cur.fetchone()[0]
    print(f"  Forventet (DK-public + TUI-private):     {dk_public + tui_private}")
    print(f"    DK-public docs:                        {dk_public}")
    print(f"    TUI's private docs:                    {tui_private}")
    print(f"  (Disse tal skal være IDENTISKE efter fix — det er den 'pre-Norge'-tilstand)")

    cur.close()
    conn.close()

    afsnit("RESULTAT")
    if fejl == 0:
        print("  🎉 ALLE TESTS PASSEREDE — RAG-isolation er korrekt")
        return 0
    else:
        print(f"  💥 {fejl} TEST(S) FEJLEDE — fix nødvendig")
        return 1


if __name__ == "__main__":
    sys.exit(main())
