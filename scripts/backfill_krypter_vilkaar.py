"""
Back-fill: kryptér 'vilkaar'-dokumenter i mine_dokumenter.

Disse dokumenter er TUI's egne offentlige FAQ/T&C-sider scrapet fra tui.dk.
De indeholder INGEN PII, men er gemt med is_public=FALSE fordi de er
tenant-scopede (kun TUI har behov for dem som RAG-kontekst). For at
opretholde rod-princippet "alt private data er krypteret at-rest" så
ingen revisor behøver at lave undtagelser, krypterer vi dem retroaktivt.

Idempotent: kører kun på rækker hvor er_krypteret=FALSE og indhold er sat.

Kør med:
    python3 scripts/backfill_krypter_vilkaar.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import _connect, _kryptering_aktiv, _ENCRYPTION_KEY


def main() -> int:
    if not _kryptering_aktiv():
        print("ENCRYPTION_KEY mangler — kan ikke kryptere. Afbryder.")
        return 1

    conn = _connect()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT COUNT(*)
              FROM mine_dokumenter
             WHERE is_public = FALSE
               AND dokumenttype = 'vilkaar'
               AND er_krypteret = FALSE
               AND indhold IS NOT NULL
            """
        )
        antal = cur.fetchone()[0]
        if antal == 0:
            print("Ingen vilkaar-dokumenter at back-fille. Allerede 100% dækket.")
            return 0

        print(f"Krypterer {antal} vilkaar-dokumenter ...")

        # Server-side encryption via pgcrypto. Sletter plaintext-feltet
        # samtidig — så det rå indhold ikke længere ligger i klartekst.
        cur.execute(
            """
            UPDATE mine_dokumenter
               SET indhold_krypteret = pgp_sym_encrypt(indhold::text, %s::text),
                   indhold = NULL,
                   er_krypteret = TRUE,
                   updated_at = NOW()
             WHERE is_public = FALSE
               AND dokumenttype = 'vilkaar'
               AND er_krypteret = FALSE
               AND indhold IS NOT NULL
            """,
            (_ENCRYPTION_KEY,),
        )
        opdaterede = cur.rowcount
        conn.commit()
        print(f"✓ Krypterede {opdaterede} rækker")

        # Verifikation
        cur.execute(
            """
            SELECT COUNT(*) AS ukrypteret
              FROM mine_dokumenter
             WHERE is_public = FALSE
               AND dokumenttype = 'vilkaar'
               AND er_krypteret = FALSE
            """
        )
        resterende = cur.fetchone()[0]
        if resterende == 0:
            print("✓ Alle private vilkaar-docs er nu krypteret")
            return 0
        print(f"❌ {resterende} rækker er stadig ukrypteret — undersøg")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
