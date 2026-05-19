"""
Opretter analyse_jobs-tabellen der bruges af pg-boss-baserede background
jobs til at gemme input-filer + analyse-resultater.

Idempotent — kan køres flere gange uden problemer.

Kør med:
    python3 scripts/opret_analyse_jobs_tabel.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import _connect


def main() -> int:
    conn = _connect()
    try:
        cur = conn.cursor()

        # ─── analyse_jobs ───
        # Hovedtabel for asynkrone foerstevurderings-jobs.
        #
        # Status-lifecycle:
        #   pending → running → (completed | failed)
        #
        # input_*-kolonner persisterer input så worker kan retry'e selv
        # om frontend allerede har lukket forbindelsen. Auto-anonymisering
        # rydder dem efter 24t.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS analyse_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id INTEGER NOT NULL
                    REFERENCES tenants(id) ON DELETE RESTRICT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                user_email TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed')),
                idempotency_key TEXT,
                input_sagsakter TEXT,
                input_filer_meta JSONB,
                resultat JSONB,
                fejl_besked TEXT,
                fejl_kategori TEXT,
                anthropic_tokens_input INTEGER,
                anthropic_tokens_output INTEGER,
                forsoeg INTEGER NOT NULL DEFAULT 0,
                oprettet TIMESTAMPTZ DEFAULT NOW(),
                startet TIMESTAMPTZ,
                faerdig TIMESTAMPTZ,
                anonymiseres_efter TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '24 hours')
            )
        """)

        # Idempotent ADD COLUMN for eksisterende installs.
        for kolonne_def in [
            "ADD COLUMN IF NOT EXISTS user_email TEXT",
            "ADD COLUMN IF NOT EXISTS idempotency_key TEXT",
            "ADD COLUMN IF NOT EXISTS fejl_kategori TEXT",
            "ADD COLUMN IF NOT EXISTS anthropic_tokens_input INTEGER",
            "ADD COLUMN IF NOT EXISTS anthropic_tokens_output INTEGER",
        ]:
            cur.execute(f"ALTER TABLE analyse_jobs {kolonne_def}")

        # ─── analyse_job_filer ───
        # Separat tabel til upload-bytes (kan være op til 30 MB pr. job).
        # Adskilt fra analyse_jobs så JSONB-resultat-queries ikke trækker
        # bytes med. ON DELETE CASCADE: ryger med når job slettes.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS analyse_job_filer (
                id SERIAL PRIMARY KEY,
                job_id UUID NOT NULL
                    REFERENCES analyse_jobs(id) ON DELETE CASCADE,
                filnavn TEXT NOT NULL,
                bytes BYTEA NOT NULL,
                mime_type TEXT,
                oprettet TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # ─── Indekser ───
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyse_jobs_tenant_status
            ON analyse_jobs (tenant_id, status, oprettet DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyse_jobs_idempotency
            ON analyse_jobs (idempotency_key)
            WHERE idempotency_key IS NOT NULL
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyse_jobs_anonymiseres
            ON analyse_jobs (anonymiseres_efter)
            WHERE status IN ('completed', 'failed')
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyse_job_filer_job_id
            ON analyse_job_filer (job_id)
        """)

        conn.commit()
        cur.close()
        print("✓ analyse_jobs + analyse_job_filer er klar")

        # Verificér
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name='analyse_jobs'
            ORDER BY ordinal_position
        """)
        print("\nKolonner i analyse_jobs:")
        for navn, dtype in cur.fetchall():
            print(f"  {navn:30s} {dtype}")
        cur.close()
        return 0
    except Exception as e:
        conn.rollback()
        print(f"FEJL: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
