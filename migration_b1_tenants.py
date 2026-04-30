"""
Engangs/idempotent migration-script til Phase B1 (multi-tenant).

KØRSEL (fra terminalen, i projektmappen):
    python migration_b1_tenants.py

Hvad det gør:
  1. Sørger for at tenants/users-tabellerne + tenant_id-kolonner er
     oprettet (idempotent via opret_tabeller).
  2. Opretter TUI, Spies og Apollo som tenants i tabellen — med profil-
     data der præcis matcher den gamle hardcoded SELSKAB_PROFILER dict
     i selskab_profiler.py. TUI er fuldt udfyldt; Spies/Apollo er
     skeletter klar til onboarding.
  3. Backfill af eksisterende data:
     - mine_dokumenter med dokumenttype='afgoerelse' → is_public=TRUE
       (Pakkerejse-Ankenævn-afgørelser er offentlig juridisk præcedens
       og deles på tværs af alle tenants)
     - mine_dokumenter med dokumenttype='lovgivning' → is_public=TRUE
       (pakkerejseloven gælder for alle)
     - mine_dokumenter med dokumenttype='vilkaar' → tenant_id=TUI
       (TUI's egne rejsevilkår — kun TUI-brugere ser dem)
     - mine_dokumenter med dokumenttype='klage' → tenant_id=TUI
       (TUI's egne uafgjorte klager)
     - mine_dokumenter med dokumenttype='anonymisering_regler' →
       is_public=TRUE (autoritative regler fra Datatilsynet osv.)
     - analyse_arkiv → tenant_id=TUI (alle eksisterende analyser er TUI's)
     - gemte_sager → tenant_id=TUI (alle gemte sager er TUI's)

Idempotent: Du kan køre scriptet igen uden problem. Det rør kun rækker
hvor tenant_id IS NULL og is_public IS NULL/FALSE — så efter første
kørsel er der ingen ændringer ved efterfølgende kørsler.
"""

import psycopg2
import os
from dotenv import load_dotenv

from database import (
    opret_tabeller,
    hent_tenant_by_slug,
    opret_tenant,
)

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")


# ───────────────────────────────────────────────────────────────
# TENANT-DEFINITIONER
# Skal præcis matche de hardcoded værdier fra selskab_profiler.py
# så TUI-brugere får IDENTISK output som før migrationen.
# ───────────────────────────────────────────────────────────────
TENANTS_TIL_OPRETTELSE = [
    {
        "slug": "tui",
        "navn": "TUI",
        "sagsbehandler": "TUI",
        "by": "Frederiksberg",
        "logo_filnavn": "static/logos/tui.png",
        "anonymisering_suffix": "TUI",
        "interne_team_navne": [
            "After Travel",
            "After Sales",
            "Customer service",
            "Customer Service",
            "kundeservice",
            "Kundeservice",
        ],
        "klageorgan_navn": "Pakkerejse-Ankenævnet",
        "klageorgan_url": "https://www.pakkerejseankenaevnet.dk",
        "rejsevilkaar_kilde_url": "https://www.tui.dk/rejse-med-tui/",
        "sprog": "da",
        "land": "DK",
        "lov_navn": "Pakkerejseloven",
    },
    {
        "slug": "spies",
        "navn": "Spies",
        "sagsbehandler": "Spies",
        "by": "København",
        "logo_filnavn": "static/logos/spies.png",
        "anonymisering_suffix": "Spies",
        "interne_team_navne": [],  # udfyldes ved Spies-onboarding
        "klageorgan_navn": "Pakkerejse-Ankenævnet",
        "klageorgan_url": "https://www.pakkerejseankenaevnet.dk",
        "rejsevilkaar_kilde_url": "",
        "sprog": "da",
        "land": "DK",
        "lov_navn": "Pakkerejseloven",
    },
    {
        "slug": "apollo",
        "navn": "Apollo",
        "sagsbehandler": "Apollo",
        "by": "København",
        "logo_filnavn": "static/logos/apollo.png",
        "anonymisering_suffix": "Apollo",
        "interne_team_navne": [],  # udfyldes ved Apollo-onboarding
        "klageorgan_navn": "Pakkerejse-Ankenævnet",
        "klageorgan_url": "https://www.pakkerejseankenaevnet.dk",
        "rejsevilkaar_kilde_url": "",
        "sprog": "da",
        "land": "DK",
        "lov_navn": "Pakkerejseloven",
    },
]


def opret_tenants_idempotent():
    """Opretter tenants hvis de ikke allerede findes. Returnerer dict slug→id."""
    print("─" * 60)
    print(" Trin 1: Opret/verifér tenants")
    print("─" * 60)
    slug_til_id = {}
    for spec in TENANTS_TIL_OPRETTELSE:
        eksisterende = hent_tenant_by_slug(spec["slug"])
        if eksisterende:
            slug_til_id[spec["slug"]] = eksisterende["id"]
            print(f"  ✓  {spec['slug']:8s} findes allerede (id={eksisterende['id']})")
        else:
            ny_id = opret_tenant(**spec)
            if ny_id:
                slug_til_id[spec["slug"]] = ny_id
                print(f"  ✅  {spec['slug']:8s} oprettet (id={ny_id})")
            else:
                print(f"  ❌  {spec['slug']:8s} kunne IKKE oprettes")
    print()
    return slug_til_id


def backfill_dokumenter(tui_id):
    """
    Backfill mine_dokumenter:
      - afgoerelse, lovgivning, anonymisering_regler → is_public=TRUE
      - klage, vilkaar → tenant_id=TUI
    Kun rækker hvor tenant_id IS NULL OG is_public IS NULL/FALSE rør vi.
    """
    print("─" * 60)
    print(" Trin 2: Backfill mine_dokumenter")
    print("─" * 60)
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # Public typer: afgoerelse, lovgivning, anonymisering_regler
    cur.execute(
        """
        UPDATE mine_dokumenter
        SET is_public = TRUE
        WHERE dokumenttype IN ('afgoerelse', 'lovgivning', 'anonymisering_regler')
          AND (is_public IS NULL OR is_public = FALSE)
          AND tenant_id IS NULL
        """
    )
    public_count = cur.rowcount
    print(f"  Public dokumenter (afgørelser, lovgivning, anonym.regler): {public_count}")

    # TUI-private typer: klage, vilkaar
    cur.execute(
        """
        UPDATE mine_dokumenter
        SET tenant_id = %s, is_public = FALSE
        WHERE dokumenttype IN ('klage', 'vilkaar')
          AND tenant_id IS NULL
        """,
        (tui_id,),
    )
    private_count = cur.rowcount
    print(f"  TUI-private dokumenter (klager, vilkår):                    {private_count}")

    # Catch-all: alt andet vi ikke kender → TUI-private (defensivt)
    cur.execute(
        """
        UPDATE mine_dokumenter
        SET tenant_id = %s, is_public = FALSE
        WHERE tenant_id IS NULL
          AND (is_public IS NULL OR is_public = FALSE)
        """,
        (tui_id,),
    )
    other_count = cur.rowcount
    if other_count:
        print(f"  Ukendt dokumenttype tildelt TUI (defensivt):                {other_count}")

    conn.commit()
    cur.close()
    conn.close()
    print()


def backfill_arkiv(tui_id):
    """analyse_arkiv: alle eksisterende rækker → tenant_id=TUI."""
    print("─" * 60)
    print(" Trin 3: Backfill analyse_arkiv")
    print("─" * 60)
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "UPDATE analyse_arkiv SET tenant_id = %s WHERE tenant_id IS NULL",
        (tui_id,),
    )
    count = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    print(f"  Arkiv-indgange tildelt TUI: {count}")
    print()


def backfill_gemte_sager(tui_id):
    """gemte_sager: alle eksisterende rækker → tenant_id=TUI."""
    print("─" * 60)
    print(" Trin 4: Backfill gemte_sager")
    print("─" * 60)
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "UPDATE gemte_sager SET tenant_id = %s WHERE tenant_id IS NULL",
        (tui_id,),
    )
    count = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    print(f"  Gemte sager tildelt TUI: {count}")
    print()


def vis_summary():
    """Print stats efter migration."""
    print("─" * 60)
    print(" Status efter migration")
    print("─" * 60)
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("SELECT slug, navn, id FROM tenants ORDER BY id")
    print("  Tenants i databasen:")
    for row in cur.fetchall():
        print(f"    id={row[2]:3d}  slug={row[0]:8s}  navn={row[1]}")

    cur.execute(
        "SELECT dokumenttype, "
        "COUNT(*) FILTER (WHERE is_public = TRUE) AS public_count, "
        "COUNT(*) FILTER (WHERE tenant_id IS NOT NULL) AS private_count, "
        "COUNT(*) FILTER (WHERE tenant_id IS NULL AND (is_public IS NULL OR is_public = FALSE)) AS uassigned "
        "FROM mine_dokumenter GROUP BY dokumenttype ORDER BY dokumenttype"
    )
    print()
    print(f"  mine_dokumenter pr. type:  {'type':25s} {'public':>8s} {'private':>8s} {'uassigned':>10s}")
    for row in cur.fetchall():
        print(f"    {row[0] or '(null)':25s} {row[1] or 0:>8d} {row[2] or 0:>8d} {row[3] or 0:>10d}")

    cur.execute(
        "SELECT COUNT(*) FILTER (WHERE tenant_id IS NOT NULL), "
        "COUNT(*) FILTER (WHERE tenant_id IS NULL) FROM analyse_arkiv"
    )
    a_priv, a_un = cur.fetchone()
    print(f"\n  analyse_arkiv:  {a_priv or 0} med tenant, {a_un or 0} unassigned")

    cur.execute(
        "SELECT COUNT(*) FILTER (WHERE tenant_id IS NOT NULL), "
        "COUNT(*) FILTER (WHERE tenant_id IS NULL) FROM gemte_sager"
    )
    g_priv, g_un = cur.fetchone()
    print(f"  gemte_sager:    {g_priv or 0} med tenant, {g_un or 0} unassigned")

    cur.close()
    conn.close()


def main():
    print()
    print("═" * 60)
    print(" Phase B1 migration: multi-tenant backfill")
    print("═" * 60)
    print()

    # Sørg for at schema er opdateret
    opret_tabeller()

    # Opret tenants
    slug_til_id = opret_tenants_idempotent()
    if "tui" not in slug_til_id:
        print("❌ TUI-tenant kunne ikke oprettes — afbryder migration.")
        return
    tui_id = slug_til_id["tui"]

    # Backfill data
    backfill_dokumenter(tui_id)
    backfill_arkiv(tui_id)
    backfill_gemte_sager(tui_id)

    vis_summary()
    print()
    print("═" * 60)
    print(" Migration færdig.")
    print("═" * 60)


if __name__ == "__main__":
    main()
