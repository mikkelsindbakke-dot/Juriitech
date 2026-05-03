"""
gdpr_cron_runner.py

Entry-point for cron-jobbet der trigger auto-anonymiserings-pipelinen.
Designet til at blive kaldt hver time af Fly.io scheduled machines.

Bruges:
    python3 gdpr_cron_runner.py

Output skrives til stdout og fanges af Fly logs. Exit code 0 = OK,
1 = pipeline-fejl.

Aktivering på Fly.io (skal gøres manuelt af admin):
    fly machine run \\
        --app pax-juriitech \\
        --schedule hourly \\
        --no-public-ips \\
        --image registry.fly.io/pax-juriitech:latest \\
        python3 gdpr_cron_runner.py

Alternativt kan trigger_auto_anonymisering() kaldes direkte fra
admin-UI'en for manuel kørsel under test.
"""

import json
import sys
from datetime import datetime

from gdpr_pipeline import trigger_auto_anonymisering


def main():
    print(f"=== GDPR cron-runner kørt {datetime.utcnow().isoformat()} UTC ===")
    try:
        result = trigger_auto_anonymisering(maks_per_kørsel=20)
        print(json.dumps(result, indent=2, default=str))
        # Exit code 1 hvis nogle sager fejlede så Fly kan alerte
        if result.get("fejlede", 0) > 0:
            print(
                f"WARNING: {result['fejlede']} sager fejlede under "
                "anonymisering — tjek Sentry"
            )
            return 1
        return 0
    except Exception as e:
        print(f"FATAL: cron-runner crashede: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
