"""
Engangs-opsætning af Test-tenant + test-bruger til E2E-smoke-testen.

Køres ÉN gang lokalt med produktions-credentials i miljø-variabler:

    export DATABASE_URL="<fra fly secrets>"
    export SUPABASE_URL="<fra fly secrets>"
    export SUPABASE_ANON_KEY="<fra fly secrets>"
    export SUPABASE_SERVICE_KEY="<fra fly secrets>"
    python3 tests/e2e/setup_test_tenant.py

Output: skriver tests/.env.test med TEST_EMAIL og TEST_PASSWORD som
run_smoke.py læser. .env.test er gitignored.

Hvis Test-tenant og bruger allerede findes printes credentials uden
at oprette duplikater (idempotent).

Test-isolation: data brugeren opretter via PAX gemmes med tenant_id =
Test-tenant'en. Det betyder den ALDRIG kan ses af TUI/Spies/Apollo-
brugere — eksisterende tenant-isolation i database.py sikrer det.
"""
from __future__ import annotations

import os
import secrets
import string
import sys
from pathlib import Path

# Tilføj projekt-roden til Python-path så database/auth kan importeres
# uanset hvor scriptet køres fra.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


_TEST_TENANT_SLUG = "test-e2e"
_TEST_TENANT_NAVN = "Test (E2E smoke-test)"
_TEST_USER_EMAIL = "e2e-smoke@juriitech-pax.test"
_ENV_FILE = Path(__file__).parent.parent / ".env.test"


def _genererer_password(laengde=20):
    """Secure password til test-bruger."""
    alfabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabet) for _ in range(laengde))


def _sikr_tenant():
    """Opret Test-tenant hvis den ikke findes. Returnér tenant_id."""
    from database import hent_tenant_by_slug, opret_tenant

    eksisterende = hent_tenant_by_slug(_TEST_TENANT_SLUG)
    if eksisterende:
        print(
            f"OK: Test-tenant findes allerede (id={eksisterende['id']})"
        )
        return eksisterende["id"]

    tenant_id = opret_tenant(
        slug=_TEST_TENANT_SLUG,
        navn=_TEST_TENANT_NAVN,
        sagsbehandler="E2E Test Robot",
        by="Testby",
        anonymisering_suffix="Testselskabet",
        interne_team_navne=["test-team"],
        klageorgan_navn="Pakkerejse-Ankenævnet",
        rejsevilkaar_kilde_url="",
        sprog="da",
        land="DK",
        lov_navn="Pakkerejseloven",
    )
    if not tenant_id:
        raise SystemExit(
            "FEJL: Kunne ikke oprette Test-tenant. Tjek DB-forbindelse."
        )
    print(f"OK: Test-tenant oprettet (id={tenant_id})")
    return tenant_id


def _sikr_test_bruger(tenant_id):
    """
    Opret test-bruger hvis ikke findes. Returnér (email, password).
    Hvis brugeren findes læses passwordet fra .env.test (det vi
    gemte sidste gang). Hvis hverken bruger eller .env.test findes,
    opretter vi nyt.
    """
    from database import hent_user_by_email
    from auth import admin_create_user, _get_admin_client

    eksisterende_db = hent_user_by_email(_TEST_USER_EMAIL)

    if eksisterende_db and _ENV_FILE.exists():
        # Læs eksisterende password fra .env.test
        for linje in _ENV_FILE.read_text().splitlines():
            if linje.startswith("TEST_PASSWORD="):
                pw = linje.split("=", 1)[1].strip()
                if pw:
                    print(
                        f"OK: Test-bruger findes; bruger gemt password "
                        f"fra {_ENV_FILE.name}"
                    )
                    return _TEST_USER_EMAIL, pw

    if eksisterende_db:
        # DB har bruger men vi har intet password — slet og genopret
        print(
            "ADVARSEL: Test-bruger findes i DB men .env.test mangler "
            "password. Sletter og genopretter for at få nyt password."
        )
        admin_client = _get_admin_client()
        if admin_client:
            try:
                admin_client.auth.admin.delete_user(
                    eksisterende_db["supabase_user_id"]
                )
            except Exception as e:
                print(f"DEBUG: Sletning af Supabase-bruger fejlede: {e}")
        # Slet også vores DB-row
        try:
            from database import slet_user
            slet_user(eksisterende_db["id"])
        except Exception as e:
            print(f"DEBUG: Sletning af DB-bruger fejlede: {e}")

    # Opret ny bruger via eksisterende admin-flow
    ok, fejl, temp_pw = admin_create_user(
        email=_TEST_USER_EMAIL,
        tenant_id=tenant_id,
        role="jurist",
        fulde_navn="E2E Test Robot",
    )
    if not ok:
        raise SystemExit(
            f"FEJL: Kunne ikke oprette test-bruger: {fejl}"
        )

    # Brug et nyt secure password (vi genererer selv så vi ved hvad
    # det er — admin_create_user genererer sit eget men vi bruger
    # _generate_temp_password's output via temp_pw return).
    print(f"OK: Test-bruger oprettet ({_TEST_USER_EMAIL})")
    return _TEST_USER_EMAIL, temp_pw


def _gem_credentials_til_env_test(email, password):
    """Skriv .env.test med credentials run_smoke.py kan læse."""
    indhold = (
        "# Auto-genereret af tests/e2e/setup_test_tenant.py\n"
        "# Disse credentials bruges KUN af run_smoke.py mod live PAX.\n"
        "# Test-brugeren er isoleret i Test-tenant — ingen prod-data.\n"
        "# .env.test er gitignored.\n"
        f"TEST_EMAIL={email}\n"
        f"TEST_PASSWORD={password}\n"
        "TEST_BASE_URL=https://pax-juriitech.fly.dev\n"
    )
    _ENV_FILE.write_text(indhold)
    # Restriktive permissions så password ikke er world-readable
    os.chmod(_ENV_FILE, 0o600)
    print(f"OK: Credentials gemt i {_ENV_FILE}")


def main():
    # Verificér at de nødvendige miljø-variabler er sat
    paakraevet = [
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_KEY",
    ]
    mangler = [v for v in paakraevet if not os.getenv(v)]
    if mangler:
        print(
            "FEJL: Følgende miljø-variabler skal være sat:",
            file=sys.stderr,
        )
        for v in mangler:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nHent dem fra Fly: fly secrets list, og kopiér "
            "værdierne ind i din lokale shell.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("→ Opsætter Test-tenant + test-bruger til E2E-smoke-testen")
    tenant_id = _sikr_tenant()
    email, password = _sikr_test_bruger(tenant_id)
    _gem_credentials_til_env_test(email, password)

    print()
    print("Klar til at køre smoke-testen:")
    print("  python3 -m playwright install chromium  # første gang")
    print("  python3 tests/e2e/run_smoke.py")


if __name__ == "__main__":
    main()
