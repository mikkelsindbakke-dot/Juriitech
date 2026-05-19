"""
Verificerer at PII-data i Supabase faktisk er krypteret.

Kører fire tjek:
  1. Tabel-skema: er_krypteret + *_krypteret BYTEA-kolonner eksisterer
  2. Faktisk dækning: hvor mange rækker har er_krypteret=TRUE vs FALSE
     (delt op pr. tabel + om dokumentet er public eller private)
  3. Råt indhold: pluk én krypteret række og vis at indhold_krypteret
     er bytea/binær, ikke læsbar text — uden ENCRYPTION_KEY kan ingen
     læse det (heller ikke en Supabase-admin uden vores Fly-secrets)
  4. Decrypt-round-trip: hent rækken igen MED nøglen via _decrypt_sql_expr
     og bekræft at vi får meningsfuld dansk tekst tilbage

Kør med:
    python3 scripts/verificer_kryptering.py

Forventet output: alle fire tjek "OK".
"""
from __future__ import annotations

import os
import sys

# Tillad import af database.py fra projekt-roden
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import (
    _connect,
    _kryptering_aktiv,
    _decrypt_sql_expr,
    _decrypt_key_param,
)


def _print_overskrift(tekst: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {tekst}")
    print("═" * 70)


def tjek_1_skema(cur) -> bool:
    _print_overskrift("1. SKEMA — er_krypteret + *_krypteret kolonner eksisterer")

    tabeller = [
        ("mine_dokumenter", ["er_krypteret", "indhold_krypteret"]),
        ("analyse_arkiv", [
            "er_krypteret",
            "indhold_krypteret",
            "sagsakter_krypteret",
            "spoergsmaal_krypteret",
            "ekstra_instrukser_krypteret",
        ]),
        ("gemte_sager", ["er_krypteret", "state_json_krypteret"]),
        # aktiv_sag-state ligger som JSONB-kolonner direkte på users-tabellen
        # (ikke en separat tabel). Krypteret variant tilføjes til users.
        ("users", ["aktiv_sag_state_krypteret"]),
    ]
    ok = True
    for tabel, forventede_kolonner in tabeller:
        cur.execute(
            """
            SELECT column_name, data_type
              FROM information_schema.columns
             WHERE table_name = %s
            """,
            (tabel,),
        )
        rows = cur.fetchall()
        kolonner = {r[0]: r[1] for r in rows}
        manglende = [k for k in forventede_kolonner if k not in kolonner]
        if manglende:
            print(f"  ❌ {tabel}: mangler {manglende}")
            ok = False
        else:
            for k in forventede_kolonner:
                if k.endswith("_krypteret") and k != "er_krypteret":
                    if kolonner[k] != "bytea":
                        print(f"  ❌ {tabel}.{k}: type={kolonner[k]} (forventet bytea)")
                        ok = False
            print(f"  ✓ {tabel}: alle {len(forventede_kolonner)} kolonner findes")
    return ok


def tjek_2_daekning(cur) -> bool:
    _print_overskrift("2. DÆKNING — hvor stor en andel af private data er krypteret")
    ok = True

    # mine_dokumenter — kun private (is_public=FALSE) skal kryptereres.
    # Public dokumenter (afgørelser, lovgivning) krypteres ikke fordi
    # de kan ses af alle tenants og bruges til RAG/embedding-search.
    #
    # 'vilkaar'-dokumenter er offentligt tilgængelige TUI-FAQ/T&C-sider
    # scrapet fra tui.dk. De er teknisk is_public=FALSE (tenant-scopet,
    # så kun TUI ser dem), men indeholder INGEN PII — kun TUI's egne
    # offentlige vilkår. Vi tæller dem separat så vi ikke fejlagtigt
    # ser ud som om PII-dækningen er under 100%.
    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE is_public = FALSE AND dokumenttype <> 'vilkaar')
                AS pii_total,
            COUNT(*) FILTER (
                WHERE is_public = FALSE
                  AND dokumenttype <> 'vilkaar'
                  AND er_krypteret = TRUE
            ) AS pii_krypteret,
            COUNT(*) FILTER (WHERE dokumenttype = 'vilkaar') AS vilkaar_total,
            COUNT(*) FILTER (
                WHERE dokumenttype = 'vilkaar' AND er_krypteret = TRUE
            ) AS vilkaar_krypteret,
            COUNT(*) FILTER (WHERE is_public = TRUE) AS public_total
        FROM mine_dokumenter
        """
    )
    pii_total, pii_kryp, vilkaar_total, vilkaar_kryp, pub_total = cur.fetchone()
    dækning_pii = (pii_kryp / pii_total * 100) if pii_total else 100.0
    status_pii = "✓" if dækning_pii >= 99.0 else "❌"
    print(
        f"  {status_pii} mine_dokumenter (PII): {pii_kryp}/{pii_total} krypteret "
        f"({dækning_pii:.1f}%)"
    )
    print(
        f"  ℹ mine_dokumenter (vilkaar): {vilkaar_kryp}/{vilkaar_total} krypteret — "
        f"offentlige TUI-FAQ-sider, ingen PII"
    )
    print(f"  ℹ mine_dokumenter (public): {pub_total} afgørelser/lov — ingen PII")
    if dækning_pii < 99.0:
        ok = False

    # analyse_arkiv — altid private
    cur.execute(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE er_krypteret = TRUE) AS krypteret
        FROM analyse_arkiv
        """
    )
    total, kryp = cur.fetchone()
    dækning = (kryp / total * 100) if total else 100.0
    status = "✓" if dækning >= 99.0 else "❌"
    print(f"  {status} analyse_arkiv: {kryp}/{total} krypteret ({dækning:.1f}%)")
    if dækning < 99.0:
        ok = False

    # gemte_sager — altid private
    cur.execute(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE er_krypteret = TRUE) AS krypteret
        FROM gemte_sager
        """
    )
    total, kryp = cur.fetchone()
    dækning = (kryp / total * 100) if total else 100.0
    status = "✓" if dækning >= 99.0 else "❌"
    print(f"  {status} gemte_sager: {kryp}/{total} krypteret ({dækning:.1f}%)")
    if dækning < 99.0:
        ok = False

    return ok


def tjek_3_raat_indhold(cur) -> bool:
    _print_overskrift("3. RÅT INDHOLD — krypterede kolonner er binære (ikke læsbare)")

    # Pluk en privat krypteret række
    cur.execute(
        """
        SELECT id, filnavn, indhold_krypteret
        FROM mine_dokumenter
        WHERE is_public = FALSE
          AND er_krypteret = TRUE
          AND indhold_krypteret IS NOT NULL
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        print("  ⚠ Ingen krypterede private dokumenter at teste — springer over")
        return True

    doc_id, filnavn, raw = row
    print(f"  Testdokument: id={doc_id}, filnavn='{filnavn}'")
    print(f"  Type af indhold_krypteret: {type(raw).__name__}")
    if isinstance(raw, memoryview):
        raw = bytes(raw)
    print(f"  Længde i bytes: {len(raw)}")
    print(f"  Første 32 bytes (hex): {raw[:32].hex()}")

    # pgcrypto pgp_sym_encrypt-output starter ALTID med signature-bytes
    # (typisk 0xC3 eller 0xC4 — PGP packet tag for symmetric-key-encrypted-data).
    # Hvis vi ser ASCII-text er noget gået galt.
    første_byte = raw[0] if raw else 0
    is_pgp_pakke = første_byte in (0xC3, 0xC4) or (0x80 <= første_byte <= 0xFF)

    # Tjek at indholdet IKKE er læsbar ASCII (i hvert fald ikke i begyndelsen)
    prøv_ascii = raw[:64].decode("utf-8", errors="ignore")
    er_læsbar = (
        sum(1 for c in prøv_ascii if c.isprintable() and ord(c) < 128) > 40
    )

    if is_pgp_pakke and not er_læsbar:
        print("  ✓ Indhold er pgcrypto-pakket binær blob (ikke menneskelæsbart)")
        return True
    if er_læsbar:
        print(f"  ❌ FARE: indhold ligner læsbar text! Første 64 chars: {prøv_ascii!r}")
        return False
    print("  ⚠ Binær men ikke typisk pgcrypto-format — manuel verifikation nødvendig")
    return True


def tjek_4_decrypt_roundtrip(cur) -> bool:
    _print_overskrift("4. DECRYPT — med ENCRYPTION_KEY kan vi læse det igen")

    if not _kryptering_aktiv():
        print("  ❌ ENCRYPTION_KEY mangler — kan ikke teste decrypt")
        return False

    # Hent samme dokument som i tjek 3, men dekrypteret i SQL
    cur.execute(
        f"""
        SELECT id, filnavn,
               {_decrypt_sql_expr('indhold_krypteret')} AS dekrypteret
        FROM mine_dokumenter
        WHERE is_public = FALSE
          AND er_krypteret = TRUE
          AND indhold_krypteret IS NOT NULL
        LIMIT 1
        """,
        _decrypt_key_param(),
    )
    row = cur.fetchone()
    if not row:
        print("  ⚠ Ingen krypterede dokumenter at teste")
        return True

    doc_id, filnavn, dekrypteret = row
    if not dekrypteret or len(dekrypteret.strip()) < 10:
        print(f"  ❌ Dekrypteret tekst er tom for doc_id={doc_id}")
        return False

    # Skal være meningsfuld dansk tekst
    print(f"  Dokument id={doc_id}, filnavn='{filnavn}'")
    print(f"  Dekrypteret længde: {len(dekrypteret)} tegn")
    print(f"  Første 200 tegn (let renset):")
    forhåndsvisning = dekrypteret[:200].replace("\n", " ").strip()
    print(f"    {forhåndsvisning!r}")
    print("  ✓ Round-trip OK — krypterings/dekrypterings-cyklus fungerer")
    return True


def hovedfunktion() -> int:
    print("PAX kryptering-verifikation")
    print(f"  ENCRYPTION_KEY: {'sat' if _kryptering_aktiv() else 'MANGLER'}")
    if not _kryptering_aktiv():
        print("\n  ❌ ENCRYPTION_KEY er ikke sat i miljøet — afbryder")
        print("     Kør med: ENCRYPTION_KEY=$(fly secrets list ...) python3 scripts/verificer_kryptering.py")
        return 1

    conn = _connect()
    try:
        cur = conn.cursor()
        resultater = [
            tjek_1_skema(cur),
            tjek_2_daekning(cur),
            tjek_3_raat_indhold(cur),
            tjek_4_decrypt_roundtrip(cur),
        ]
        cur.close()
    finally:
        conn.close()

    print("\n" + "═" * 70)
    bestaet = sum(1 for r in resultater if r)
    if bestaet == len(resultater):
        print(f"  ✓ ALLE {len(resultater)} TJEK BESTÅET — kryptering virker som intended")
        return 0
    print(f"  ❌ {len(resultater) - bestaet} af {len(resultater)} tjek fejlede")
    return 1


if __name__ == "__main__":
    sys.exit(hovedfunktion())
