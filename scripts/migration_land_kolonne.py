"""
migration_land_kolonne.py

Tilføj 'land'-kolonne til mine_dokumenter — forbereder PAX til
multi-land RAG (Norge, Sverige, Tyskland osv.).

EFFEKT PÅ EKSISTERENDE DATA:
- Alle eksisterende rækker får automatisk land='DK' (DEFAULT)
- Backfill verificerer at INGEN rækker har NULL bagefter
- Eksisterende queries der IKKE nævner land virker uændret
- Når RAG-queries opdateres til at filtrere på land, vil danske
  tenants se PRÆCIS SAMME data (alle deres data er 'DK')

IDEMPOTENT:
- Kan køres flere gange uden skade — bruger IF NOT EXISTS
- Hvis kolonnen allerede findes, springes oprettelse over

SIKKERHED:
- IKKE destruktiv — kun ADD COLUMN + UPDATE WHERE NULL
- Tager en pg_dump af mine_dokumenter FØR migrationen ved --backup-flag
- Verificerer slut-tilstand før den rapporterer succes

KØRSEL:
  # Tør-kørsel (vis hvad der ville ske):
  python3 scripts/migration_land_kolonne.py

  # Kør for alvor:
  python3 scripts/migration_land_kolonne.py --execute

  # Kør med backup først (anbefalet i prod):
  python3 scripts/migration_land_kolonne.py --execute --backup
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime

ROD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROD)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(ROD, ".env"))
load_dotenv(os.path.join(ROD, "pax-next", ".env.local"), override=False)

import psycopg2  # noqa: E402


def _get_db_url():
    url = os.getenv("DATABASE_URL")
    if not url:
        print("FEJL: DATABASE_URL er ikke sat (tjek .env)")
        sys.exit(1)
    return url


def _tag_backup(db_url, backup_fil):
    """Eksporterer mine_dokumenter + tenants til SQL-fil før migration."""
    print(f"\n→ Tager backup af kritiske tabeller til {backup_fil} ...")
    proc = subprocess.run(
        [
            "pg_dump",
            "--no-owner",
            "--no-privileges",
            "--table=mine_dokumenter",
            "--table=tenants",
            "--data-only",
            "--column-inserts",
            db_url,
        ],
        stdout=open(backup_fil, "w"),
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        print(f"FEJL: pg_dump fejlede:\n{proc.stderr}")
        sys.exit(1)
    print(f"  ✓ Backup gemt ({os.path.getsize(backup_fil)} bytes)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Faktisk kør migrationen (uden flag: tør-kørsel).",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Tag pg_dump-backup før migration kører.",
    )
    args = parser.parse_args()

    db_url = _get_db_url()

    sql_steps = [
        # 1. Tilføj kolonne med DEFAULT 'DK' — alle eksisterende rækker
        #    får automatisk 'DK' i samme operation.
        (
            "Tilføj 'land'-kolonne (DEFAULT 'DK')",
            "ALTER TABLE mine_dokumenter "
            "ADD COLUMN IF NOT EXISTS land TEXT DEFAULT 'DK';",
        ),
        # 2. Eksplicit backfill for at fange evt. NULL-rækker. I praksis
        #    burde DEFAULT have håndteret dem, men dette er belt-and-
        #    suspenders for fremtidige re-migrationer.
        (
            "Backfill: sæt land='DK' hvor NULL",
            "UPDATE mine_dokumenter SET land = 'DK' WHERE land IS NULL;",
        ),
        # 3. NOT NULL-constraint så vi sikrer at fremtidige INSERTs altid
        #    angiver land. Også beskytter mod NULL-bugs i kode.
        (
            "Sæt NOT NULL på land",
            "ALTER TABLE mine_dokumenter "
            "ALTER COLUMN land SET NOT NULL;",
        ),
        # 4. Index for hurtige filter-queries på land + is_public-kombinationen.
        #    Det er præcis det RAG-queries kommer til at filtrere på.
        (
            "Opret index på (land, is_public)",
            "CREATE INDEX IF NOT EXISTS idx_mine_dokumenter_land_public "
            "ON mine_dokumenter(land, is_public);",
        ),
    ]

    print("=" * 70)
    print("MIGRATION: tilføj 'land'-kolonne til mine_dokumenter")
    print("=" * 70)

    if not args.execute:
        print("\nTØR-KØRSEL (ingen ændringer kørt). Tilføj --execute for at køre.\n")
        for navn, sql in sql_steps:
            print(f"-- {navn}")
            print(sql)
            print()
        print("Brug --execute for at køre migrationen.")
        return

    # Backup hvis ønsket
    if args.backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_fil = os.path.join(
            ROD, f"backup-pre-land-migration-{stamp}.sql"
        )
        _tag_backup(db_url, backup_fil)

    print("\n→ Forbinder til database ...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False  # vi committer manuelt så vi kan rollback ved fejl

    try:
        cur = conn.cursor()

        # Snapshot FØR migration
        cur.execute("SELECT COUNT(*) FROM mine_dokumenter")
        antal_for = cur.fetchone()[0]
        print(f"  Antal rækker FØR: {antal_for}")

        # Kør hvert step
        for navn, sql in sql_steps:
            print(f"\n→ {navn}")
            cur.execute(sql)
            print(f"  ✓ {cur.statusmessage}")

        # Verificér slut-tilstand
        cur.execute("SELECT COUNT(*) FROM mine_dokumenter")
        antal_efter = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM mine_dokumenter WHERE land IS NULL"
        )
        antal_null = cur.fetchone()[0]
        cur.execute(
            "SELECT land, COUNT(*) FROM mine_dokumenter "
            "GROUP BY land ORDER BY land"
        )
        fordeling = cur.fetchall()

        if antal_for != antal_efter:
            raise RuntimeError(
                f"Antal rækker ændret under migration! "
                f"Før={antal_for}, efter={antal_efter}. ROLLBACK."
            )
        if antal_null > 0:
            raise RuntimeError(
                f"{antal_null} rækker har stadig NULL i land-kolonnen. "
                f"ROLLBACK."
            )

        # Tjek at index findes
        cur.execute(
            "SELECT 1 FROM pg_indexes "
            "WHERE indexname = 'idx_mine_dokumenter_land_public'"
        )
        if not cur.fetchone():
            raise RuntimeError("Index blev ikke oprettet. ROLLBACK.")

        # Alt OK — commit
        conn.commit()

        print("\n" + "=" * 70)
        print("✓ MIGRATION GENNEMFØRT")
        print("=" * 70)
        print(f"Antal rækker: {antal_efter} (uændret fra {antal_for})")
        print(f"NULL-rækker:  {antal_null} (skal være 0)")
        print(f"\nFordeling pr. land:")
        for land, antal in fordeling:
            print(f"  {land}: {antal:,}")
        print(
            "\nNæste skridt: deploy kode-ændringer der bruger 'land'-kolonnen "
            "(RAG-queries i database.py)."
        )

    except Exception as e:
        conn.rollback()
        print(f"\n✗ FEJL: {e}")
        print("Migrationen er rullet tilbage — INGEN ændringer er gemt.")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
