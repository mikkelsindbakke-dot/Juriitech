"""
test_gdpr_pipeline.py

Verifikation af GDPR-pipelinens kerne-logik mod produktions-DB.
Tester:
- vurder_k_anonymitet returnerer korrekt count + maa_dele-flag
- skriv_audit indsætter korrekt række i gdpr_audit_log
- trigger_auto_anonymisering finder INGEN rækker når der er nul
  'aktiv' rækker med anonymiseres_efter < NOW() (forventet i dag —
  vi har sat eksisterende sager til 'aktiv' uden tidsstempel)

Kører IKKE den faktiske AI-anonymisering (den kræver Anthropic-credits
og rør på rigtige sager). Den testes manuelt før Fase 4-deploy.

Bruges:
    python3 test_gdpr_pipeline.py

Exit code 0 = OK, 1 = fejl.
"""

import sys

from database import _connect
from gdpr_pipeline import (
    K_ANONYMITET_TAERSKEL,
    skriv_audit,
    trigger_auto_anonymisering,
    vurder_k_anonymitet,
)


def _green(s): return f"\033[32m{s}\033[0m"
def _red(s): return f"\033[31m{s}\033[0m"


def tjek(navn, betingelse, fejl_hint=""):
    if betingelse:
        print(f"  {_green('✓')} {navn}")
        return True
    print(f"  {_red('✗')} {navn}")
    if fejl_hint:
        print(f"      hint: {fejl_hint}")
    return False


def test_konstanter():
    print("\n--- Konstanter ---")
    fejl = 0
    if not tjek("K_ANONYMITET_TAERSKEL er 5",
                K_ANONYMITET_TAERSKEL == 5):
        fejl += 1
    return fejl


def test_k_anonymitet_med_tom_pulje():
    """Når shared_patterns er tom, skal nyt mønster ikke kunne deles
    (k_count=1, ikke ≥5)."""
    print("\n--- K-anonymitet på tom pulje ---")
    fejl = 0
    # Brug et meget specifikt mønster der garantert ikke findes
    k_count, maa_dele = vurder_k_anonymitet(
        sag_kategori="test_unique_kategori_xyz",
        udfald_kategori="test_unique_udfald_abc",
        region="test_unique_region_def",
    )
    if not tjek(f"k_count = 1 (ny+0 eksisterende), faktisk: {k_count}",
                k_count == 1):
        fejl += 1
    if not tjek("maa_dele = False (k_count<5)",
                not maa_dele):
        fejl += 1
    return fejl


def test_k_anonymitet_med_kunstig_pulje():
    """Tilføj 4 kunstige mønstre, verificer at det 5. trigger maa_dele=True."""
    print("\n--- K-anonymitet med kunstig pulje (k=5 trigger) ---")
    fejl = 0
    conn = _connect()
    cur = conn.cursor()
    test_kategori = "test_kanon_kategori"
    test_udfald = "test_kanon_udfald"
    test_region = "test_kanon_region"

    try:
        # Indsæt 4 kunstige mønstre. CHECK-constraint kræver k_count >= 5,
        # så hver row skal have k_count=5 (det er en intern lager-værdi
        # der dokumenterer hvor stor klyngen var DA mønstret blev gemt).
        for i in range(4):
            cur.execute("""
                INSERT INTO shared_patterns
                (sag_kategori, udfald_kategori, region,
                 anonymiseret_tekst, k_count)
                VALUES (%s, %s, %s, %s, %s)
            """, (test_kategori, test_udfald, test_region,
                  f"kunstig test {i}", 5))
        conn.commit()

        # Vurder: nyt mønster vil bringe total til 5
        k_count, maa_dele = vurder_k_anonymitet(
            test_kategori, test_udfald, test_region, conn=conn)
        if not tjek(f"k_count = 5 (4 eksist + 1 ny), faktisk: {k_count}",
                    k_count == 5):
            fejl += 1
        if not tjek("maa_dele = True (k_count≥5)",
                    maa_dele):
            fejl += 1

        # Cleanup — fjern kunstige rækker
        cur.execute("""
            DELETE FROM shared_patterns
            WHERE sag_kategori = %s
              AND udfald_kategori = %s
              AND region = %s
        """, (test_kategori, test_udfald, test_region))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return fejl


def test_skriv_audit():
    """Skriv en audit-row, verificer den findes, slet den igen."""
    print("\n--- skriv_audit ---")
    fejl = 0
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM tenants LIMIT 1")
        tid_row = cur.fetchone()
        if tid_row is None:
            tjek("Mindst én tenant findes", False,
                 "kør migration_b1_tenants.py")
            return 1
        tid = tid_row[0]

        skriv_audit(
            "test-pipeline-sag", tid, "upload",
            metadata={"test": True, "source": "test_gdpr_pipeline"},
        )
        cur.execute("""
            SELECT metadata FROM gdpr_audit_log
            WHERE sag_id = 'test-pipeline-sag'
              AND tenant_id = %s
            ORDER BY tidspunkt DESC LIMIT 1
        """, (tid,))
        row = cur.fetchone()
        if not tjek("Audit-row indsat",
                    row is not None and row[0].get("test") is True):
            fejl += 1
        # Cleanup
        cur.execute("""
            DELETE FROM gdpr_audit_log
            WHERE sag_id = 'test-pipeline-sag' AND tenant_id = %s
        """, (tid,))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return fejl


def test_trigger_finder_ingen_aktive():
    """Verificer trigger_auto_anonymisering returnerer foersogt=0
    (alle 'aktiv' rækker har anonymiseres_efter=NULL og bliver
    derfor ikke fanget af WHERE-clausen)."""
    print("\n--- trigger_auto_anonymisering på dagens DB ---")
    fejl = 0
    result = trigger_auto_anonymisering(maks_per_kørsel=5)
    if not tjek(
        f"foersogt = 0, faktisk: {result['foersogt']}",
        result["foersogt"] == 0,
        "Hvis ≠0: nogen har sat anonymiseres_efter på en sag i prod"
    ):
        fejl += 1
    if not tjek(
        f"lykkedes = 0, faktisk: {result['lykkedes']}",
        result["lykkedes"] == 0,
    ):
        fejl += 1
    return fejl


def main():
    print("\n=== GDPR Fase 3 pipeline-test ===")
    samlet_fejl = 0
    samlet_fejl += test_konstanter()
    samlet_fejl += test_k_anonymitet_med_tom_pulje()
    samlet_fejl += test_k_anonymitet_med_kunstig_pulje()
    samlet_fejl += test_skriv_audit()
    samlet_fejl += test_trigger_finder_ingen_aktive()
    print()
    if samlet_fejl == 0:
        print(_green("=== ALLE TESTS BESTÅET ==="))
        return 0
    print(_red(f"=== {samlet_fejl} TESTS FEJLET ==="))
    return 1


if __name__ == "__main__":
    sys.exit(main())
