"""
GDPR Fase 4.2 migration: Markér eksisterende 'aktiv'-sager til
auto-anonymisering.

Sætter anonymiseres_efter = NOW() + INTERVAL '24 hours' på alle
eksisterende rækker hvor:
  - anonymiserings_status = 'aktiv'
  - is_public = FALSE
  - anonymiseres_efter IS NULL (ikke allerede markeret)
  - tenant_id IS NOT NULL

Når cron-jobbet aktiveres (Fase 4.3), vil disse rækker blive
gradvist anonymiseret.

KØR KUN ÉN GANG efter pipelinen er testet på en eller flere sager
manuelt. Dette er en stor batch — der kan være 100+ sager der
køres gennem AI-anonymisering på samme cron-cyklus.

Bruges:
    python3 migration_gdpr_aktiver_eksisterende.py [--dry-run]
"""

import sys

from database import _connect


def main(dry_run=False):
    conn = _connect()
    cur = conn.cursor()

    # Tæl først
    cur.execute("""
        SELECT COUNT(*) FROM mine_dokumenter
        WHERE anonymiserings_status = 'aktiv'
          AND is_public = FALSE
          AND anonymiseres_efter IS NULL
          AND tenant_id IS NOT NULL
    """)
    antal = cur.fetchone()[0]
    print(f"Fundet {antal} sager der vil blive markeret til anonymisering")

    if dry_run:
        print("DRY RUN — ingen ændringer udført")
        return

    if antal == 0:
        print("Intet at gøre.")
        return

    bekraefter = input(
        f"\nMarkér disse {antal} sager til anonymisering om 24 timer? "
        "Skriv 'ja' for at fortsætte: "
    )
    if bekraefter.strip().lower() != "ja":
        print("Afbrudt.")
        return

    cur.execute("""
        UPDATE mine_dokumenter
        SET anonymiseres_efter = NOW() + INTERVAL '24 hours'
        WHERE anonymiserings_status = 'aktiv'
          AND is_public = FALSE
          AND anonymiseres_efter IS NULL
          AND tenant_id IS NOT NULL
    """)
    conn.commit()
    print(
        f"Markerede {cur.rowcount} sager — anonymiseres "
        "om 24 timer (når cron kører)"
    )
    cur.close()
    conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
