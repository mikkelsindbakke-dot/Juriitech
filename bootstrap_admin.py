"""
Engangs-script: opret eller verificér admin-bruger i users-tabellen.

Kør denne ÉN gang efter Phase B2 deploy for at sikre at
juriitech@juriitech.com har en row i vores users-tabel med
role='admin' og tenant_id=TUI. Brugeren skal allerede være oprettet
i Supabase Auth (via dashboard → Authentication → Users → Add User).

KØRSEL:
    python bootstrap_admin.py

Idempotent — du kan køre den igen uden problem. Hvis admin-row
allerede findes, sker der intet.

EFTER KØRSEL:
  Mikkel logger ind på pax.juriitech.com med juriitech@juriitech.com
  + det password han satte i Supabase. Login-flowet i auth.py vil:
    1. Verificere credentials hos Supabase
    2. Slå op via email i users-tabellen (matcher rækken vi opretter her)
    3. Opdatere rækken med Mikkels Supabase-UUID (linkning)
    4. Sætte session_state med tenant_id=TUI + role='admin'
"""

from database import (
    opret_tabeller,
    hent_tenant_by_slug,
    hent_user_by_email,
    opret_user,
)


ADMIN_EMAIL = "juriitech@juriitech.com"
ADMIN_TENANT_SLUG = "tui"  # admin tilknyttes TUI-tenant'en


def main():
    print()
    print("═" * 60)
    print("  Bootstrap admin-bruger")
    print("═" * 60)

    opret_tabeller()

    # Slå TUI-tenant op
    tui = hent_tenant_by_slug(ADMIN_TENANT_SLUG)
    if not tui:
        print(
            f"❌ Fejl: tenant '{ADMIN_TENANT_SLUG}' findes ikke i databasen.\n"
            "   Kør først: python migration_b1_tenants.py"
        )
        return
    tui_id = tui["id"]
    print(f"  TUI-tenant fundet: id={tui_id}")

    # Tjek om admin-row allerede findes
    eksisterende = hent_user_by_email(ADMIN_EMAIL)
    if eksisterende:
        print(f"  ✓  {ADMIN_EMAIL} findes allerede i users-tabellen:")
        print(f"      id={eksisterende['id']}")
        print(f"      tenant_id={eksisterende['tenant_id']}")
        print(f"      role={eksisterende['role']}")
        print(f"      supabase_user_id={eksisterende['supabase_user_id'] or '(ikke linket endnu)'}")
        if eksisterende["role"] != "admin":
            print()
            print(f"  ⚠️  ADVARSEL: rolle er '{eksisterende['role']}', ikke 'admin'!")
            print("      Manuel SQL-update kræves:")
            print(
                f"      UPDATE users SET role='admin' WHERE email='{ADMIN_EMAIL}';"
            )
        if eksisterende["tenant_id"] != tui_id:
            print()
            print(
                f"  ⚠️  ADVARSEL: tenant_id er {eksisterende['tenant_id']}, "
                f"forventet {tui_id} (TUI). Manuel fix kræves."
            )
        print()
        print("  Bootstrap er allerede gjort — intet at gøre.")
        print("═" * 60)
        return

    # Opret admin-row
    ny_id = opret_user(
        email=ADMIN_EMAIL,
        tenant_id=tui_id,
        role="admin",
        fulde_navn="Mikkel Sindbakke",
        supabase_user_id=None,  # Linkes ved første login
    )

    if ny_id:
        print(f"  ✅ {ADMIN_EMAIL} oprettet i users-tabellen (id={ny_id})")
        print(f"      tenant_id={tui_id}")
        print(f"      role=admin")
        print(f"      supabase_user_id=NULL (linkes ved første login)")
        print()
        print("  Næste skridt: Mikkel logger ind på pax.juriitech.com med")
        print(f"  email={ADMIN_EMAIL} + det password sat i Supabase Auth.")
        print()
        print("  Ved første login linkes supabase_user_id automatisk —")
        print("  fremtidige logins er hurtigere fordi vi ikke skal email-")
        print("  matche.")
    else:
        print(f"  ❌ Kunne IKKE oprette {ADMIN_EMAIL} i users-tabellen.")
        print("     Tjek DB-logs for detaljer.")

    print("═" * 60)


if __name__ == "__main__":
    main()
