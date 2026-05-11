#!/usr/bin/env bash
#
# Sætter Fly Cron-machine op der kører GDPR-anonymiseringspipelinen
# hver time. Idempotent — sletter eksisterende cron-machine først.
#
# Kør:
#   bash scripts/setup-gdpr-cron.sh
#
# Forudsætninger:
#   - flyctl installeret og logget ind (verificér: flyctl auth whoami)
#   - pax-juriitech-app skal være deployet (det er den allerede)
#   - ANTHROPIC_API_KEY + VOYAGE_API_KEY + DATABASE_URL skal være sat
#     som Fly secrets (det er de allerede — verificér: flyctl secrets list)
#
# Hvad scriptet gør:
#   1. Verificerer flyctl + app-eksistens
#   2. Lister eksisterende machines og spotter evt. gammel cron-machine
#   3. Stopper og fjerner gammel cron-machine (hvis nogen)
#   4. Opretter ny cron-machine der kører gdpr_cron_runner.py hver time
#   5. Verificerer at machine'en er oprettet
#
# Roll-back: bash scripts/stop-gdpr-cron.sh

set -euo pipefail

APP=pax-juriitech
IMAGE_TAG=latest
CRON_NAME=gdpr-cron

echo "═════════════════════════════════════════════════════════════════"
echo "  GDPR-cron setup for ${APP}"
echo "═════════════════════════════════════════════════════════════════"
echo ""

# Forudsætninger
command -v flyctl >/dev/null 2>&1 || {
    echo "FEJL: flyctl ikke installeret. Installer via 'brew install flyctl'"
    exit 1
}

CURRENT_USER=$(flyctl auth whoami 2>/dev/null || echo "<not logged in>")
echo "Flyctl-bruger: ${CURRENT_USER}"
[[ "${CURRENT_USER}" == "<not logged in>" ]] && {
    echo "FEJL: Ikke logget ind. Kør 'flyctl auth login' først."
    exit 1
}

echo ""
echo "1. Tjekker eksisterende machines i ${APP}..."
flyctl machine list --app "${APP}" 2>&1 | tail -20
echo ""

# Stop evt. eksisterende cron-machine (idempotent)
EXISTING=$(flyctl machine list --app "${APP}" --json 2>/dev/null \
    | python3 -c "import sys, json; ms=json.load(sys.stdin); print(' '.join(m['id'] for m in ms if 'cron' in (m.get('name') or '').lower() or 'gdpr' in (m.get('name') or '').lower()))" 2>/dev/null \
    || echo "")

if [[ -n "${EXISTING}" ]]; then
    echo "2. Stopper og fjerner eksisterende cron-machines: ${EXISTING}"
    for m in ${EXISTING}; do
        flyctl machine stop "${m}" --app "${APP}" 2>&1 || true
        flyctl machine destroy "${m}" --app "${APP}" --force 2>&1 || true
    done
else
    echo "2. Ingen eksisterende cron-machine fundet — fortsætter med fresh setup"
fi

echo ""
echo "3. Opretter ny cron-machine..."
flyctl machine run \
    "registry.fly.io/${APP}:${IMAGE_TAG}" \
    --app "${APP}" \
    --name "${CRON_NAME}" \
    --schedule hourly \
    --restart no \
    --vm-memory 1024 \
    python3 gdpr_cron_runner.py

echo ""
echo "4. Verificerer..."
flyctl machine list --app "${APP}" 2>&1 | grep -E "cron|gdpr" || true

echo ""
echo "═════════════════════════════════════════════════════════════════"
echo "  GDPR-cron sat op!"
echo "═════════════════════════════════════════════════════════════════"
echo ""
echo "Den kører nu hver time. Tjek logs efter første kørsel:"
echo ""
echo "  flyctl logs --app ${APP} --no-tail | grep gdpr"
echo ""
echo "Manuel kørsel (for at teste lige nu):"
echo ""
echo "  flyctl ssh console --app ${APP} -C 'python3 gdpr_cron_runner.py'"
echo ""
echo "Stop cron igen:"
echo ""
echo "  bash scripts/stop-gdpr-cron.sh"
echo ""
