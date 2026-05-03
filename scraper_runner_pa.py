"""
scraper_runner_pa.py

Entry-point for månedlig auto-scrape af Pakkerejse-Ankenævnets afgørelser.
Designet til at blive kaldt af Fly.io scheduled machine.

Bruges:
    python3 scraper_runner_pa.py

Output skrives til stdout og fanges af Fly logs.

Aktivering på Fly.io (manuel admin-handling):
    fly machine run \\
        --app pax-juriitech \\
        --schedule monthly \\
        --no-public-ips \\
        --region fra \\
        --name pa-scraper-monthly \\
        --image registry.fly.io/pax-juriitech:latest \\
        python3 scraper_runner_pa.py
"""

import json
import sys
from datetime import datetime

from scraper import scrape_nye_sager


def main():
    print(
        f"=== PA-scraper kørt {datetime.utcnow().isoformat()} UTC ==="
    )
    try:
        result = scrape_nye_sager(max_sager=100)
        print(json.dumps(result, indent=2, default=str))
        return 0
    except Exception as e:
        print(f"FATAL: PA-scraper crashede: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
