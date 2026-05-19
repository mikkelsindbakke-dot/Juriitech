"""
opret_test_brugere.py

Opretter 5 test-tenants + test-brugere matchende de fiktive sager i
pax-next/public/test-sager. Idempotent — kan køres igen uden duplikater.

KØRSEL:
    python3 scripts/opret_test_brugere.py           # opret/synk
    python3 scripts/opret_test_brugere.py --vis     # vis kun credentials
    python3 scripts/opret_test_brugere.py --slet    # fjern alle test-data

KONFIGURATION:
    test-brugere-config.json i repo-roden definerer brugerne.

SIKKERHED:
- Test-brugere har SAMME password (kun til lokal/staging-test).
- Test-tenants har slug-prefix 'test-' så de er nemme at filtrere.
- Test-brugere har role='jurist' — ikke admin.
- Test-tenants har INGEN reel data — de er adskilt fra rigtige tenants.
- KØR IKKE --slet i produktion uden at vide hvad der skylles.
"""

import argparse
import json
import os
import sys

ROD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROD)

CONFIG_PATH = os.path.join(ROD, "test-brugere-config.json")

# Load env: .env (DB, ENCRYPTION_KEY) + pax-next/.env.local (Supabase keys)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(ROD, ".env"))
load_dotenv(os.path.join(ROD, "pax-next", ".env.local"), override=False)

# Next.js bruger NEXT_PUBLIC_-prefix for SUPABASE_URL/ANON_KEY; auth.py
# i Python forventer det uden prefix. Aliasér så begge fungerer.
for _src, _dst in (
    ("NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_URL"),
    ("NEXT_PUBLIC_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY"),
):
    if os.getenv(_src) and not os.getenv(_dst):
        os.environ[_dst] = os.getenv(_src)

from database import (  # noqa: E402
    _connect,
    hent_tenant_by_slug,
    opret_tenant,
    hent_user_by_email,
    opret_user,
    slet_user,
)
from auth import _get_admin_client  # noqa: E402


def _load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _opret_eller_hent_tenant(slug, navn, by, sagsbehandler,
                              land="DK", sprog="da",
                              klageorgan_navn=None,
                              klageorgan_url=None,
                              lov_navn=None):
    """Returnerer (tenant_id, oprettet_nu: bool).

    Default-værdier er danske (Pakkerejse-Ankenævnet). For test-tenants
    i andre lande (Norge, Sverige osv.) skal land/sprog samt klage-
    organ-info angives eksplicit.
    """
    eksisterende = hent_tenant_by_slug(slug)
    if eksisterende:
        return eksisterende["id"], False
    # Land-specifikke defaults
    if land == "NO":
        klageorgan_navn = klageorgan_navn or "Pakkereisenemnda"
        klageorgan_url = klageorgan_url or "https://reiselivsforum.no"
        lov_navn = lov_navn or "Pakkereiseloven"
    elif land == "SE":
        klageorgan_navn = klageorgan_navn or "Allmänna reklamationsnämnden"
        klageorgan_url = klageorgan_url or "https://www.arn.se"
        lov_navn = lov_navn or "Paketreselagen"
    else:
        # DK / default
        klageorgan_navn = klageorgan_navn or "Pakkerejse-Ankenævnet"
        klageorgan_url = klageorgan_url or "https://www.pakkerejseankenaevnet.dk"
        lov_navn = lov_navn or "Pakkerejseloven"

    ny_id = opret_tenant(
        slug=slug,
        navn=navn,
        sagsbehandler=sagsbehandler,
        by=by,
        anonymisering_suffix=navn,
        klageorgan_navn=klageorgan_navn,
        klageorgan_url=klageorgan_url,
        sprog=sprog,
        land=land,
        lov_navn=lov_navn,
    )
    return ny_id, True


def _find_supabase_user_by_email(admin_client, email):
    """
    Returnér Supabase User-objekt eller None.
    list_users paginerer — vi går alle sider igennem indtil match.
    """
    page = 1
    per_page = 200
    while True:
        try:
            result = admin_client.auth.admin.list_users(
                page=page, per_page=per_page
            )
        except TypeError:
            # Ældre supabase-py uden page-args
            result = admin_client.auth.admin.list_users()
            for u in result:
                if (getattr(u, "email", "") or "").lower() == email.lower():
                    return u
            return None

        # Nyere klient: list[User]
        if not result:
            return None
        for u in result:
            if (getattr(u, "email", "") or "").lower() == email.lower():
                return u
        if len(result) < per_page:
            return None
        page += 1


def _opret_eller_opdater_supabase(admin_client, email, password, fulde_navn):
    """
    Opretter Supabase Auth-bruger eller opdaterer password på eksisterende.
    Returnerer (supabase_user_id, oprettet_nu: bool).
    """
    existing = _find_supabase_user_by_email(admin_client, email)
    if existing:
        admin_client.auth.admin.update_user_by_id(
            existing.id,
            {"password": password, "user_metadata": {"full_name": fulde_navn}},
        )
        return existing.id, False

    result = admin_client.auth.admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"full_name": fulde_navn},
    })
    sup_user = result.user
    sup_id = getattr(sup_user, "id", None) or sup_user.get("id")
    return sup_id, True


def _slet_tenant_med_slug(slug):
    """
    DELETE FROM tenants WHERE slug = %s. Fejler hvis tenanten stadig
    har FK-referencer (RESTRICT). Returnerer (ok, fejl).
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM tenants WHERE slug = %s", (slug,))
        antal = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return antal > 0, None
    except Exception as e:
        return False, str(e)


def main_opret():
    cfg = _load_config()
    pw = cfg["test_password"]
    brugere = cfg["brugere"]

    admin_client = _get_admin_client()
    if not admin_client:
        print(
            "FEJL: SUPABASE_SERVICE_KEY mangler i miljøet. "
            "Sæt i .env eller via 'fly secrets set'."
        )
        return 1

    print(f"=== Opretter/synkroniserer {len(brugere)} test-brugere ===")
    print()

    for entry in brugere:
        slug = entry["slug"]
        navn = entry["navn"]
        email = entry["email"]

        # 1. Tenant
        tenant_id, tenant_ny = _opret_eller_hent_tenant(
            slug, navn, entry["by"], entry["sagsbehandler"],
            land=entry.get("land", "DK"),
            sprog=entry.get("sprog", "da"),
        )
        if tenant_id is None:
            print(f"  ✗ Tenant {slug} — kunne ikke oprettes (slå op i logs)")
            continue
        tag = "ny" if tenant_ny else "findes"
        print(f"  Tenant {slug:30s} id={tenant_id:<4} [{tag}]")

        # 2. Supabase Auth-bruger
        try:
            sup_id, sup_ny = _opret_eller_opdater_supabase(
                admin_client, email, pw, entry["fulde_navn"]
            )
            tag = "ny" if sup_ny else "pw opdateret"
            print(f"  Supabase {email:45s} [{tag}]")
        except Exception as e:
            print(f"  ✗ Supabase {email} — fejl: {e}")
            continue

        # 3. DB users-row
        db_user = hent_user_by_email(email)
        if db_user:
            # Sikre supabase_user_id er sat (kan have været None før)
            if db_user.get("supabase_user_id") != sup_id:
                conn = _connect()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE users SET supabase_user_id = %s WHERE id = %s",
                    (sup_id, db_user["id"]),
                )
                conn.commit()
                cur.close()
                conn.close()
                print(f"  DB user  {email:45s} [link opdateret]")
            else:
                print(f"  DB user  {email:45s} [findes]")
        else:
            new_id = opret_user(
                email=email,
                tenant_id=tenant_id,
                role="jurist",
                fulde_navn=entry["fulde_navn"],
                supabase_user_id=sup_id,
            )
            if new_id:
                print(f"  DB user  {email:45s} [ny id={new_id}]")
            else:
                print(f"  ✗ DB user {email} — kunne ikke oprettes")

        print()

    print()
    print("=== Færdig ===")
    print(f"Adgangskode (samme for alle):  {pw}")
    print()
    print("Test-brugere:")
    for entry in brugere:
        print(f"  {entry['email']:45s}  →  {entry['navn']}")
    print()
    print("Log ind via pax-next/forsiden eller Streamlit-/login-siden.")
    print("Brug 'python3 scripts/opret_test_brugere.py --slet' for at fjerne.")
    return 0


def main_slet():
    cfg = _load_config()
    brugere = cfg["brugere"]
    admin_client = _get_admin_client()

    print(f"=== Sletter {len(brugere)} test-brugere + test-tenants ===")
    print()

    for entry in brugere:
        email = entry["email"]
        slug = entry["slug"]

        # 1. Slet i Supabase Auth (hvis findes)
        if admin_client:
            try:
                existing = _find_supabase_user_by_email(admin_client, email)
                if existing:
                    admin_client.auth.admin.delete_user(existing.id)
                    print(f"  Supabase  {email:45s} [slettet]")
                else:
                    print(f"  Supabase  {email:45s} [findes ikke]")
            except Exception as e:
                print(f"  ✗ Supabase {email} — fejl: {e}")

        # 2. Slet i vores users-tabel
        db_user = hent_user_by_email(email)
        if db_user:
            ok = slet_user(db_user["id"])
            tag = "slettet" if ok else "fejl"
            print(f"  DB user   {email:45s} [{tag}]")
        else:
            print(f"  DB user   {email:45s} [findes ikke]")

        # 3. Slet tenant
        ok, fejl = _slet_tenant_med_slug(slug)
        if ok:
            print(f"  Tenant    {slug:45s} [slettet]")
        elif fejl:
            print(f"  ✗ Tenant  {slug:45s} [fejl: {fejl}]")
        else:
            print(f"  Tenant    {slug:45s} [findes ikke]")
        print()

    print("=== Færdig ===")
    return 0


def main_vis():
    cfg = _load_config()
    print(f"Adgangskode (samme for alle):  {cfg['test_password']}")
    print()
    print("Brugere:")
    for entry in cfg["brugere"]:
        print(f"  {entry['email']:45s}  →  {entry['navn']}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Test-brugere management")
    g = ap.add_mutually_exclusive_group()
    g.add_argument(
        "--slet", action="store_true",
        help="Slet alle test-brugere + test-tenants",
    )
    g.add_argument(
        "--vis", action="store_true",
        help="Vis kun credentials, opret intet",
    )
    args = ap.parse_args()

    if args.slet:
        return main_slet()
    if args.vis:
        return main_vis()
    return main_opret()


if __name__ == "__main__":
    sys.exit(main())
