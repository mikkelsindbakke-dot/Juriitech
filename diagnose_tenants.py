"""
Diagnostic + auto-fix for tenant_id-integritet.

Kører to ting:
  1. RAPPORT: viser den nuværende fordeling af tenant_id'er på tværs af
     mine_dokumenter, analyse_arkiv, gemte_sager. Identificerer hvis der
     er rækker der peger på en tenant_id der ikke længere findes
     ('orphaned').

  2. AUTO-FIX (kun hvis nødvendigt): hvis der findes orphaned rækker,
     reassigner dem til den nuværende TUI-tenant. Kører IKKE hvis alt
     ser rent ud.

KØRSEL:
    python3 diagnose_tenants.py

Sikker at re-køre — den ændrer kun rækker der har orphan-tenant_id, og
sætter ALDRIG TUI's data over på en anden tenant. Worst case: ingen
ændringer.

BAGGRUND:
Hvis migration_b1_tenants.py er blevet kørt flere gange, kan TUI-
tenant'en have fået forskellige id'er over tid. Ved samme lejlighed
kan eksisterende mine_dokumenter-rækker stadig pege på et gammelt
tenant_id der nu er 'forældreløs' (orphaned). Det betyder at en TUI-
bruger logger ind, filtrerer queries på den nuværende TUI-id, men
ingen data kommer op.
"""

from database import _connect, hent_tenant_by_slug


def main():
    print()
    print("═" * 60)
    print(" Tenant-integritet — diagnostic")
    print("═" * 60)

    # Find aktuelle TUI-tenant
    tui = hent_tenant_by_slug("tui")
    if not tui:
        print("❌ TUI-tenant findes IKKE i tenants-tabellen.")
        print("   Kør først: python3 migration_b1_tenants.py")
        return
    tui_id = tui["id"]
    print(f"\n  Den NUVÆRENDE TUI-tenant har id={tui_id}")

    conn = _connect()
    cur = conn.cursor()

    # Liste af gyldige tenant_ids
    cur.execute("SELECT id, slug, navn FROM tenants ORDER BY id")
    tenants = cur.fetchall()
    gyldige_ids = {r[0] for r in tenants}
    print(f"\n  Tenants i tenants-tabellen:")
    for tid, slug, navn in tenants:
        marker = "  ← TUI" if tid == tui_id else ""
        print(f"    id={tid:3d}  slug={slug:10s}  navn={navn}{marker}")

    # Tjek hver tabel for fordeling og orphans
    tabeller = ["mine_dokumenter", "analyse_arkiv", "gemte_sager"]
    samlet_orphan_antal = 0

    print(f"\n  Tenant-fordeling pr. tabel:")
    for tabel in tabeller:
        print(f"\n  {tabel}:")
        cur.execute(
            f"SELECT tenant_id, COUNT(*) FROM {tabel} "
            f"WHERE tenant_id IS NOT NULL "
            f"GROUP BY tenant_id ORDER BY tenant_id"
        )
        rows = cur.fetchall()
        if not rows:
            print(f"    (ingen rækker med tenant_id)")
        else:
            for tid, antal in rows:
                er_orphan = tid not in gyldige_ids
                marker = "  ❌ ORPHAN" if er_orphan else "  ✓"
                print(f"    tenant_id={tid:3d}: {antal:5d} rækker{marker}")
                if er_orphan:
                    samlet_orphan_antal += antal

        # Public-rækker (mine_dokumenter only)
        if tabel == "mine_dokumenter":
            cur.execute(
                "SELECT COUNT(*) FROM mine_dokumenter WHERE is_public = TRUE"
            )
            n_pub = cur.fetchone()[0]
            print(f"    public docs (is_public=TRUE): {n_pub} rækker")

    # Brugere
    print()
    print("  Brugere i users-tabellen:")
    cur.execute(
        "SELECT id, email, tenant_id, role, supabase_user_id "
        "FROM users ORDER BY id"
    )
    users = cur.fetchall()
    if not users:
        print("    (ingen brugere — kør bootstrap_admin.py)")
    else:
        for uid, email, tid, role, sup_id in users:
            tilknyttet = "OK" if tid in gyldige_ids else "❌ tenant findes ikke"
            linket = "linket" if sup_id else "ikke linket"
            print(
                f"    id={uid}  email={email:30s}  "
                f"tenant_id={tid} ({tilknyttet})  role={role}  {linket}"
            )

    # ========== AUTO-FIX ==========
    print()
    print("─" * 60)
    if samlet_orphan_antal == 0:
        print("  ✅ Ingen orphaned tenant_ids fundet — alt er konsistent.")
        print("─" * 60)
        return

    print(f"  ⚠️  Fundet {samlet_orphan_antal} orphaned rækker — fixer nu...")
    print("─" * 60)

    for tabel in tabeller:
        cur.execute(
            f"UPDATE {tabel} SET tenant_id = %s "
            f"WHERE tenant_id IS NOT NULL "
            f"AND tenant_id NOT IN (SELECT id FROM tenants)",
            (tui_id,),
        )
        n = cur.rowcount
        if n > 0:
            print(f"  {tabel}: {n} rækker reassignet → TUI (id={tui_id})")

    conn.commit()
    print()
    print("  ✅ Fix færdig. Re-kør scriptet for at verificere.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
