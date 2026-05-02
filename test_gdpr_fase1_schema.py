"""
test_gdpr_fase1_schema.py

Verifikations-script for GDPR Fase 1 schema-ændringer.
Kører mod produktions-DB (via .env).

Bruges:
    python3 test_gdpr_fase1_schema.py

Exit code 0 = alle tjek bestået. 1 = mindst ét tjek fejlet.

Følger samme mønster som test_b1_isolation.py.
"""

import json
import sys
import psycopg2

from database import _connect, opret_tabeller


def _green(s):
    return f"\033[32m{s}\033[0m"


def _red(s):
    return f"\033[31m{s}\033[0m"


def tjek(navn, betingelse, fejl_hint=""):
    if betingelse:
        print(f"  {_green('✓')} {navn}")
        return True
    print(f"  {_red('✗')} {navn}")
    if fejl_hint:
        print(f"      hint: {fejl_hint}")
    return False


def hovedtest():
    print("\n=== GDPR Fase 1 schema-verifikation ===\n")
    conn = _connect()
    cur = conn.cursor()
    fejl = 0

    # ---- Task 1: anonymiserings_status + anonymiseres_efter ----
    print("Task 1 — mine_dokumenter kolonner:")
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='mine_dokumenter'
          AND column_name IN ('anonymiserings_status', 'anonymiseres_efter')
    """)
    fundet = {r[0] for r in cur.fetchall()}
    if not tjek("anonymiserings_status findes",
                "anonymiserings_status" in fundet):
        fejl += 1
    if not tjek("anonymiseres_efter findes",
                "anonymiseres_efter" in fundet):
        fejl += 1

    cur.execute("""
        SELECT COUNT(*) FROM pg_constraint
        WHERE conname='mine_dokumenter_anon_status_check'
    """)
    if not tjek("CHECK-constraint på status-værdier findes",
                cur.fetchone()[0] == 1):
        fejl += 1

    cur.execute("""
        SELECT COUNT(*) FROM mine_dokumenter
        WHERE anonymiserings_status='pending'
    """)
    pending_antal = cur.fetchone()[0]
    if not tjek(
        "Ingen rækker har status='pending' (backfill virkede)",
        pending_antal == 0,
        f"{pending_antal} rækker har 'pending' — kør opret_tabeller() igen"
    ):
        fejl += 1

    # ---- Task 2: gdpr_audit_log ----
    print("\nTask 2 — gdpr_audit_log tabel:")
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name='gdpr_audit_log'
    """)
    if not tjek("Tabel findes", cur.fetchone()[0] == 1):
        fejl += 1

    try:
        cur.execute("SELECT id FROM tenants LIMIT 1")
        tid_row = cur.fetchone()
        if tid_row is None:
            tjek("Mindst én tenant findes (forudsætning)", False,
                 "kør migration_b1_tenants.py først")
            fejl += 1
        else:
            tid = tid_row[0]
            cur.execute("""
                INSERT INTO gdpr_audit_log
                (sag_id, tenant_id, handling, metadata)
                VALUES (%s, %s, %s, %s::jsonb)
                RETURNING id
            """, ("schema-test", tid, "upload",
                  json.dumps({"verifikation": True})))
            ins_id = cur.fetchone()[0]
            cur.execute(
                "DELETE FROM gdpr_audit_log WHERE id=%s", (ins_id,))
            conn.commit()
            tjek("Insert + delete-cyklus virker", True)
    except Exception as e:
        conn.rollback()
        tjek("Insert + delete-cyklus virker", False, str(e))
        fejl += 1

    cur.execute("""
        SELECT COUNT(*) FROM pg_constraint
        WHERE conname='gdpr_audit_log_handling_check'
    """)
    if not tjek("CHECK-constraint på handling-værdier findes",
                cur.fetchone()[0] == 1):
        fejl += 1

    # ---- Task 3: shared_patterns ----
    print("\nTask 3 — shared_patterns tabel:")
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name='shared_patterns'
    """)
    if not tjek("Tabel findes", cur.fetchone()[0] == 1):
        fejl += 1

    cur.execute("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name='shared_patterns' AND column_name='tenant_id'
    """)
    if not tjek("Tabel har INGEN tenant_id (designprincip)",
                cur.fetchone()[0] == 0,
                "tenant_id må ALDRIG findes på shared_patterns"):
        fejl += 1

    try:
        cur.execute("""
            INSERT INTO shared_patterns
            (sag_kategori, udfald_kategori, region,
             anonymiseret_tekst, k_count)
            VALUES (%s, %s, %s, %s, %s)
        """, ("test", "test", "test", "test", 4))
        conn.commit()
        tjek("k_count<5 blokeret af CHECK-constraint", False,
             "k_count=4 burde have fejlet, men insert lykkedes")
        fejl += 1
        cur.execute("""
            DELETE FROM shared_patterns
            WHERE sag_kategori='test' AND k_count=4
        """)
        conn.commit()
    except psycopg2.errors.CheckViolation:
        conn.rollback()
        tjek("k_count<5 blokeret af CHECK-constraint", True)

    cur.execute("""
        SELECT COUNT(*) FROM pg_indexes
        WHERE tablename='shared_patterns'
          AND indexname='idx_shared_patterns_embedding'
    """)
    if not tjek("HNSW-index på embedding findes",
                cur.fetchone()[0] == 1):
        fejl += 1

    print()
    cur.close()
    conn.close()
    if fejl == 0:
        print(_green("=== ALLE TJEK BESTÅET ==="))
        return 0
    print(_red(f"=== {fejl} TJEK FEJLET ==="))
    return 1


if __name__ == "__main__":
    sys.exit(hovedtest())
