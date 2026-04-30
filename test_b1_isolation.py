"""
Cross-tenant isolation test for Phase B1.

KØRSEL (fra terminalen, i projektmappen):
    python test_b1_isolation.py

Hvad det gør:
  1. Opretter to test-tenants ('test_alpha', 'test_beta') i tabellen.
  2. Indsætter et privat dokument, en arkiv-indgang og en gemt sag for HVER tenant.
  3. Verifiér systematisk at:
     - alpha-tenant ser KUN alphas private docs (+ alle public docs)
     - beta-tenant ser KUN betas private docs (+ alle public docs)
     - alpha kan ikke slette betas data
     - alpha kan ikke læse betas gemte sager
  4. Rydder op (sletter test-data + test-tenants) — sikkert at re-køre.

Hvis ALLE tests passerer, er tenant-isolationen vandtæt for B1.

VIGTIGT: Dette script ROR PRODUKTIONS-DB'en — men kun med 'test_*'-
prefixede rækker som ryddes automatisk efter testen. Det er sikkert
at køre flere gange.
"""

import sys
import psycopg2
import os
from dotenv import load_dotenv

from database import (
    opret_tabeller,
    opret_tenant,
    hent_tenant_by_slug,
    gem_sag_i_db,
    hent_alle_sager,
    soeg_i_arkiv,
    gem_i_arkiv,
    hent_arkiv,
    slet_arkiv_entry,
    gem_sag_state,
    hent_gemte_sager,
    hent_gemt_sag,
    slet_gemt_sag,
)

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")


# ─── HJÆLPERE ──────────────────────────────────────────────────

resultater = []  # (passed: bool, navn: str, detail: str)


def assert_eq(faktisk, forventet, navn):
    ok = faktisk == forventet
    resultater.append((ok, navn, f"forventet={forventet!r}, fik={faktisk!r}"))
    status = "✅" if ok else "❌"
    print(f"  {status} {navn}: forventet={forventet!r}, fik={faktisk!r}")


def assert_true(udsagn, navn):
    ok = bool(udsagn)
    resultater.append((ok, navn, f"udsagn={udsagn!r}"))
    status = "✅" if ok else "❌"
    print(f"  {status} {navn}: {udsagn!r}")


def assert_false(udsagn, navn):
    ok = not udsagn
    resultater.append((ok, navn, f"udsagn={udsagn!r}"))
    status = "✅" if ok else "❌"
    print(f"  {status} {navn}: {udsagn!r}")


# ─── SETUP ─────────────────────────────────────────────────────

def cleanup_test_data():
    """Ryd op: slet alle test_* tenants og deres data (CASCADE/manual)."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    # Find test-tenant ids
    cur.execute(
        "SELECT id FROM tenants WHERE slug LIKE 'test\\_%' ESCAPE '\\'"
    )
    test_ids = [r[0] for r in cur.fetchall()]
    if not test_ids:
        cur.close()
        conn.close()
        return
    placeholders = ",".join(["%s"] * len(test_ids))
    # Slet relateret data først
    cur.execute(
        f"DELETE FROM analyse_arkiv WHERE tenant_id IN ({placeholders})",
        test_ids,
    )
    cur.execute(
        f"DELETE FROM gemte_sager WHERE tenant_id IN ({placeholders})",
        test_ids,
    )
    cur.execute(
        f"DELETE FROM mine_dokumenter WHERE tenant_id IN ({placeholders})",
        test_ids,
    )
    # Slet brugere knyttet til test-tenants
    cur.execute(
        f"DELETE FROM users WHERE tenant_id IN ({placeholders})",
        test_ids,
    )
    # Slet tenants
    cur.execute(
        f"DELETE FROM tenants WHERE id IN ({placeholders})",
        test_ids,
    )
    conn.commit()
    cur.close()
    conn.close()


def setup_test_tenants():
    """Opret to dummy-tenants. Returnér (alpha_id, beta_id)."""
    alpha_id = opret_tenant(
        slug="test_alpha", navn="TestAlpha", sagsbehandler="TestAlpha",
        by="Alpha-by", logo_filnavn="static/logos/test_alpha.png",
    )
    beta_id = opret_tenant(
        slug="test_beta", navn="TestBeta", sagsbehandler="TestBeta",
        by="Beta-by", logo_filnavn="static/logos/test_beta.png",
    )
    return alpha_id, beta_id


# ─── TEST-CASES ────────────────────────────────────────────────

def test_dokumenter(alpha_id, beta_id):
    print()
    print("─" * 60)
    print("  TEST: mine_dokumenter isolation")
    print("─" * 60)

    # Indsæt private dokumenter for hver tenant
    gem_sag_i_db(
        filnavn="test_alpha_private.txt",
        tekst="Alpha's hemmelige dokument",
        dokumenttype="klage",
        tenant_id=alpha_id,
        is_public=False,
    )
    gem_sag_i_db(
        filnavn="test_beta_private.txt",
        tekst="Beta's hemmelige dokument",
        dokumenttype="klage",
        tenant_id=beta_id,
        is_public=False,
    )

    # Alpha sætter tenant_id eksplicit; bør se sit eget men IKKE betas
    alpha_sager = hent_alle_sager(tenant_id=alpha_id)
    alpha_filnavne = {s["filnavn"] for s in alpha_sager}
    assert_true(
        "test_alpha_private.txt" in alpha_filnavne,
        "Alpha kan se sit eget private dokument",
    )
    assert_false(
        "test_beta_private.txt" in alpha_filnavne,
        "Alpha kan IKKE se Betas private dokument",
    )

    # Beta omvendt
    beta_sager = hent_alle_sager(tenant_id=beta_id)
    beta_filnavne = {s["filnavn"] for s in beta_sager}
    assert_true(
        "test_beta_private.txt" in beta_filnavne,
        "Beta kan se sit eget private dokument",
    )
    assert_false(
        "test_alpha_private.txt" in beta_filnavne,
        "Beta kan IKKE se Alphas private dokument",
    )

    # Test soeg_i_arkiv (stikordsøgning)
    alpha_soeg = soeg_i_arkiv(stikord="hemmelige", tenant_id=alpha_id)
    alpha_soeg_filnavne = {s["filnavn"] for s in alpha_soeg}
    assert_true(
        "test_alpha_private.txt" in alpha_soeg_filnavne,
        "Alpha-stikordssøgning finder eget dokument",
    )
    assert_false(
        "test_beta_private.txt" in alpha_soeg_filnavne,
        "Alpha-stikordssøgning finder IKKE Betas dokument",
    )


def test_arkiv(alpha_id, beta_id):
    print()
    print("─" * 60)
    print("  TEST: analyse_arkiv isolation")
    print("─" * 60)

    alpha_arkiv_id = gem_i_arkiv(
        titel="Alpha-test analyse", type_="analyse",
        indhold="Alpha-indhold", tenant_id=alpha_id,
    )
    beta_arkiv_id = gem_i_arkiv(
        titel="Beta-test analyse", type_="analyse",
        indhold="Beta-indhold", tenant_id=beta_id,
    )

    alpha_arkiv = hent_arkiv(tenant_id=alpha_id)
    alpha_titler = {a["titel"] for a in alpha_arkiv}
    assert_true(
        "Alpha-test analyse" in alpha_titler,
        "Alpha kan se sin egen arkiv-indgang",
    )
    assert_false(
        "Beta-test analyse" in alpha_titler,
        "Alpha kan IKKE se Betas arkiv-indgang",
    )

    # Alpha forsøger at slette Betas arkiv-entry — skal afvises
    afvist = slet_arkiv_entry(beta_arkiv_id, tenant_id=alpha_id)
    assert_false(
        afvist,
        "Alpha kan IKKE slette Betas arkiv-entry",
    )
    # Bekræft at Betas entry stadig findes
    beta_arkiv = hent_arkiv(tenant_id=beta_id)
    beta_titler = {a["titel"] for a in beta_arkiv}
    assert_true(
        "Beta-test analyse" in beta_titler,
        "Betas arkiv-entry overlever Alphas slet-forsøg",
    )

    # Alpha kan slette sit eget
    ok = slet_arkiv_entry(alpha_arkiv_id, tenant_id=alpha_id)
    assert_true(ok, "Alpha kan slette sin egen arkiv-entry")


def test_gemte_sager(alpha_id, beta_id):
    print()
    print("─" * 60)
    print("  TEST: gemte_sager isolation")
    print("─" * 60)

    alpha_sag_id = gem_sag_state(
        titel="Alpha-test sag", state_json='{"alpha":true}',
        tenant_id=alpha_id,
    )
    beta_sag_id = gem_sag_state(
        titel="Beta-test sag", state_json='{"beta":true}',
        tenant_id=beta_id,
    )

    alpha_sager = hent_gemte_sager(tenant_id=alpha_id)
    alpha_titler = {s["titel"] for s in alpha_sager}
    assert_true(
        "Alpha-test sag" in alpha_titler,
        "Alpha ser sin egen gemte sag",
    )
    assert_false(
        "Beta-test sag" in alpha_titler,
        "Alpha ser IKKE Betas gemte sag",
    )

    # Alpha forsøger at læse Betas sag — skal returnere None
    beta_sag_for_alpha = hent_gemt_sag(beta_sag_id, tenant_id=alpha_id)
    assert_eq(
        beta_sag_for_alpha, None,
        "Alpha kan IKKE læse Betas gemte sag (returns None)",
    )

    # Alpha kan læse sin egen
    alpha_sag = hent_gemt_sag(alpha_sag_id, tenant_id=alpha_id)
    assert_true(
        alpha_sag is not None,
        "Alpha kan læse sin egen gemte sag",
    )

    # Alpha forsøger at slette Betas — skal fejle
    ok_slet = slet_gemt_sag(beta_sag_id, tenant_id=alpha_id)
    assert_false(
        ok_slet,
        "Alpha kan IKKE slette Betas gemte sag",
    )
    # Bekræft Betas overlever
    beta_sag = hent_gemt_sag(beta_sag_id, tenant_id=beta_id)
    assert_true(
        beta_sag is not None,
        "Betas gemte sag overlever Alphas slet-forsøg",
    )


# ─── MAIN ──────────────────────────────────────────────────────

def main():
    print()
    print("═" * 60)
    print("  Phase B1 — Cross-tenant isolation test")
    print("═" * 60)

    # Sørg for schema er klar
    opret_tabeller()

    # Ryd op fra evt. tidligere kørsler
    cleanup_test_data()

    # Setup
    print()
    print("Opretter test-tenants...")
    alpha_id, beta_id = setup_test_tenants()
    if not alpha_id or not beta_id:
        print("❌ Kunne ikke oprette test-tenants — afbryder.")
        return
    print(f"  Alpha-tenant id={alpha_id}, Beta-tenant id={beta_id}")

    # Kør tests
    try:
        test_dokumenter(alpha_id, beta_id)
        test_arkiv(alpha_id, beta_id)
        test_gemte_sager(alpha_id, beta_id)
    finally:
        # Ryd ALTID op, selv hvis tests fejler
        print()
        print("Rydder op...")
        cleanup_test_data()
        print("  ✓  Test-tenants og data slettet")

    # Summary
    print()
    print("═" * 60)
    bestaaet = sum(1 for r in resultater if r[0])
    fejlet = len(resultater) - bestaaet
    print(f"  Resultat: {bestaaet}/{len(resultater)} tests bestået")
    if fejlet > 0:
        print(f"  ⚠️  {fejlet} tests FEJLEDE — tenant-isolation er IKKE vandtæt")
        print()
        for ok, navn, detail in resultater:
            if not ok:
                print(f"    ❌ {navn}")
                print(f"       {detail}")
        sys.exit(1)
    else:
        print("  ✅ Alle isolation-tests bestået — Phase B1 er sikkert deploy-klar")
    print("═" * 60)


if __name__ == "__main__":
    main()
