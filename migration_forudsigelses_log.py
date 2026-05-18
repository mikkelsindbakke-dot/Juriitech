"""
migration_forudsigelses_log.py — opretter tabellen 'forudsigelses_log'.

Engangs-migration. Kør:

    DATABASE_URL=... python3 migration_forudsigelses_log.py

Tabellen er en REN TILFØJELSE — den rører ingen eksisterende tabeller,
kolonner eller queries. Den bruges af den bagvedliggende feedback-løkke
(se forudsigelses_eval.py) til at måle hvor præcist PAX forudsiger
nævnsafgørelser. Intet i den er synligt for brugeren.

Idempotent: CREATE TABLE IF NOT EXISTS — kan køres flere gange uden
skade.

GDPR: tabellen indeholder INGEN klager- eller persondata — kun
sagsnummer, tenant_id, PAX' egne sandsynligheds-tal + konklusion, og
det faktiske udfald. Sagsnummer er et offentligt nævns-journalnummer.
"""
import os
import sys

import psycopg2

DB_URL = os.getenv("DATABASE_URL")

DDL = """
CREATE TABLE IF NOT EXISTS forudsigelses_log (
    id                          SERIAL PRIMARY KEY,
    -- Join-nøgle: nævnets sagsnummer som PAX udtrak ved upload.
    sagsnummer                  TEXT NOT NULL,
    -- Normaliseret form (se forudsigelses_eval.normaliser_sagsnummer)
    -- til robust matchning mod offentliggjorte afgørelser.
    sagsnummer_norm             TEXT NOT NULL,
    tenant_id                   INTEGER,
    -- PAX' forudsigelse på analyse-tidspunktet.
    forudsagt_fuld_medhold      INTEGER,
    forudsagt_delvist_medhold   INTEGER,
    forudsagt_afvisning         INTEGER,
    forudsagt_konklusion        TEXT,
    -- PAX' mest sandsynlige bud (argmax af de tre tal ovenfor).
    pax_bucket                  TEXT,
    oprettet                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Udfyldes senere af forudsigelses_eval.py 'match'-mode, når
    -- nævnet har offentliggjort den faktiske afgørelse.
    faktisk_udfald              TEXT,
    faktisk_dokument_id         INTEGER,
    traf_rigtigt                BOOLEAN,
    matchet_tidspunkt           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_forudsigelses_log_sagsnummer_norm
    ON forudsigelses_log (sagsnummer_norm);

-- Til 'match'-mode der finder endnu-ikke-matchede rækker.
CREATE INDEX IF NOT EXISTS idx_forudsigelses_log_umatchet
    ON forudsigelses_log (faktisk_udfald)
    WHERE faktisk_udfald IS NULL;
"""


def main():
    if not DB_URL:
        print("FEJL: DATABASE_URL ikke sat.")
        sys.exit(1)

    conn = psycopg2.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(DDL)
        conn.commit()
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'forudsigelses_log'"
        )
        findes = cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM forudsigelses_log")
        antal = cur.fetchone()[0]
        cur.close()
        print(
            f"✓ Migration færdig. Tabel 'forudsigelses_log' "
            f"{'findes' if findes else 'MANGLER (?)'} — {antal} rækker."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
