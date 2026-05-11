"""
backfill_kryptering.py

Kryptér alle eksisterende plaintext-rows i mine_dokumenter, analyse_arkiv
og gemte_sager, så de matcher det krypterede skema som nye uploads
bruger fra og med Fase 3.

KØRSEL:
    python3 scripts/backfill_kryptering.py --dry-run  # vis hvad der ville ske
    python3 scripts/backfill_kryptering.py            # udfør

SIKKERHED:
- Idempotent: rows med er_krypteret=TRUE springes over
- Per-row transaktion: hvis én row fejler, ruller den enkelte tilbage
  men resten af jobbet fortsætter
- KAN IKKE rulles tilbage: når en row er krypteret og plaintext-kolonnen
  er nullet, er der ingen vej tilbage UDEN ENCRYPTION_KEY
- Estimater for prod: 132 klager + 90 arkiv + 1 gemt sag = ~3 minutter
"""

import sys
import os
import time

# Tilføj parent-dir til path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import (  # noqa: E402
    _connect,
    _kryptering_aktiv,
    _encrypt_sql_expr,
    _encrypt_params,
)


def _kryp_mine_dokumenter(dry_run):
    """
    Kryptér private rækker i mine_dokumenter.
    Public rækker (afgørelser m.fl.) krypteres IKKE.
    """
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, indhold, fil_bytes
        FROM mine_dokumenter
        WHERE is_public = FALSE
          AND er_krypteret = FALSE
          AND dokumenttype IN ('klage', 'bilag', 'svarbrev')
          AND indhold IS NOT NULL
    """)
    rows = cur.fetchall()
    print(f"  mine_dokumenter: {len(rows)} private rows at kryptere")

    okay = fejl = 0
    for dok_id, indhold, fil_bytes in rows:
        try:
            # Krypter indhold (og fil_bytes hvis det findes)
            sets = ["indhold = ''",
                    f"indhold_krypteret = {_encrypt_sql_expr()}",
                    "er_krypteret = TRUE"]
            params = list(_encrypt_params(indhold or ""))

            if fil_bytes:
                # fil_bytes er BYTEA — base64-encode før kryptering
                # (pgp_sym_encrypt vil have text-input)
                import base64
                fil_b64 = base64.b64encode(bytes(fil_bytes)).decode("ascii")
                sets.append("fil_bytes = NULL")
                sets.append(f"fil_bytes_krypteret = {_encrypt_sql_expr()}")
                params.extend(_encrypt_params(fil_b64))

            params.append(dok_id)
            sql = f"UPDATE mine_dokumenter SET {', '.join(sets)} WHERE id = %s"

            if dry_run:
                # Verificér at SQL kan parses (dry-run-validering)
                cur.execute(f"EXPLAIN {sql}", params)
            else:
                cur.execute(sql, params)
                conn.commit()
            okay += 1
        except Exception as e:
            conn.rollback()
            fejl += 1
            print(f"    FEJL row id={dok_id}: {e}")
    cur.close()
    conn.close()
    return okay, fejl


def _kryp_analyse_arkiv(dry_run):
    """Kryptér alle analyse_arkiv-rows (de er alle private)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, spoergsmaal, sagsakter, ekstra_instrukser, indhold
        FROM analyse_arkiv
        WHERE er_krypteret = FALSE
    """)
    rows = cur.fetchall()
    print(f"  analyse_arkiv: {len(rows)} rows at kryptere")

    okay = fejl = 0
    for row in rows:
        ark_id, sp, sa, ek, ind = row
        try:
            sql = f"""
                UPDATE analyse_arkiv
                SET spoergsmaal = '',
                    sagsakter = '',
                    ekstra_instrukser = '',
                    indhold = '',
                    spoergsmaal_krypteret = {_encrypt_sql_expr()},
                    sagsakter_krypteret = {_encrypt_sql_expr()},
                    ekstra_instrukser_krypteret = {_encrypt_sql_expr()},
                    indhold_krypteret = {_encrypt_sql_expr()},
                    er_krypteret = TRUE
                WHERE id = %s
            """
            params = (
                _encrypt_params(sp or "")
                + _encrypt_params(sa or "")
                + _encrypt_params(ek or "")
                + _encrypt_params(ind or "")
                + (ark_id,)
            )
            if dry_run:
                cur.execute(f"EXPLAIN {sql}", params)
            else:
                cur.execute(sql, params)
                conn.commit()
            okay += 1
        except Exception as e:
            conn.rollback()
            fejl += 1
            print(f"    FEJL row id={ark_id}: {e}")
    cur.close()
    conn.close()
    return okay, fejl


def _kryp_gemte_sager(dry_run):
    """Kryptér alle gemte_sager state_json."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, state_json
        FROM gemte_sager
        WHERE er_krypteret = FALSE AND state_json IS NOT NULL
    """)
    rows = cur.fetchall()
    print(f"  gemte_sager: {len(rows)} rows at kryptere")

    okay = fejl = 0
    for sag_id, state_json in rows:
        try:
            sql = f"""
                UPDATE gemte_sager
                SET state_json = '',
                    state_json_krypteret = {_encrypt_sql_expr()},
                    er_krypteret = TRUE
                WHERE id = %s
            """
            params = _encrypt_params(state_json or "") + (sag_id,)
            if dry_run:
                cur.execute(f"EXPLAIN {sql}", params)
            else:
                cur.execute(sql, params)
                conn.commit()
            okay += 1
        except Exception as e:
            conn.rollback()
            fejl += 1
            print(f"    FEJL row id={sag_id}: {e}")
    cur.close()
    conn.close()
    return okay, fejl


def main():
    dry_run = "--dry-run" in sys.argv

    if not _kryptering_aktiv():
        print(
            "FEJL: ENCRYPTION_KEY er ikke sat i miljøet. "
            "Kør 'fly secrets list' eller sæt i .env."
        )
        return 1

    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"=== Backfill kryptering — {mode} ===")
    print()

    t0 = time.time()

    print("Step 1: mine_dokumenter (private klager/bilag/svarbrev)")
    md_ok, md_err = _kryp_mine_dokumenter(dry_run)
    print(f"  → {md_ok} krypteret, {md_err} fejl")
    print()

    print("Step 2: analyse_arkiv (alle private)")
    ar_ok, ar_err = _kryp_analyse_arkiv(dry_run)
    print(f"  → {ar_ok} krypteret, {ar_err} fejl")
    print()

    print("Step 3: gemte_sager (state_json)")
    gs_ok, gs_err = _kryp_gemte_sager(dry_run)
    print(f"  → {gs_ok} krypteret, {gs_err} fejl")
    print()

    elapsed = time.time() - t0
    total_ok = md_ok + ar_ok + gs_ok
    total_err = md_err + ar_err + gs_err

    print(f"=== Færdig på {elapsed:.1f}s ===")
    print(f"Total: {total_ok} krypteret, {total_err} fejl")

    if dry_run:
        print()
        print("Dette var en DRY-RUN. Kør uden --dry-run for at udføre.")

    return 1 if total_err > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
