"""
scraper_runner_vilkaar.py

Entry-point for månedlig auto-rescrape af alle tenants' rejsevilkår.
Itererer over alle tenants med rejsevilkaar_kilde_url sat og kører
vilkaar_scraper.scrape_vilkaar() for hver. Idempotent — eksisterende
URL'er (matchet via url_findes) skippes.

Bruges:
    python3 scraper_runner_vilkaar.py

Aktivering på Fly.io (manuel admin-handling):
    fly machine run \\
        --app pax-juriitech \\
        --schedule monthly \\
        --no-public-ips \\
        --region fra \\
        --name vilkaar-scraper-monthly \\
        --image registry.fly.io/pax-juriitech:latest \\
        python3 scraper_runner_vilkaar.py
"""

import json
import sys
from datetime import datetime

from database import hent_alle_tenants
from vilkaar_scraper import scrape_vilkaar


def main():
    print(
        f"=== Vilkår-rescrape kørt "
        f"{datetime.utcnow().isoformat()} UTC ==="
    )

    tenants = hent_alle_tenants()
    samlet = {
        "tenants_processed": 0,
        "tenants_skipped_no_url": 0,
        "tenants_with_errors": 0,
        "per_tenant": {},
    }

    for tenant in tenants:
        slug = tenant.get("slug")
        kilde = tenant.get("rejsevilkaar_kilde_url")

        if not kilde:
            print(f"SKIP: {slug} har ingen rejsevilkaar_kilde_url")
            samlet["tenants_skipped_no_url"] += 1
            continue

        print(f"--- Scraping {slug} fra {kilde} ---")
        try:
            result = scrape_vilkaar(
                tenant_id=tenant["id"],
                tenant_slug=slug,
                kilde_url=kilde,
            )
            print(json.dumps(result, indent=2, default=str))
            samlet["per_tenant"][slug] = result
            samlet["tenants_processed"] += 1
        except Exception as e:
            print(f"FEJL ved {slug}: {e}")
            import traceback
            traceback.print_exc()
            samlet["per_tenant"][slug] = {"fejl": str(e)}
            samlet["tenants_with_errors"] += 1

    print("=== SAMLET ===")
    print(json.dumps(samlet, indent=2, default=str))

    return 0 if samlet["tenants_with_errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
