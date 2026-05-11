#!/usr/bin/env bash
#
# Stopper og fjerner GDPR-cron-machine. Sikker rollback hvis du vil
# pause anonymiseringen.
#
# Kør:  bash scripts/stop-gdpr-cron.sh
#
# Bemærk: data der ALLEREDE er anonymiseret kan IKKE gendannes — denne
# kommando stopper bare fremtidige kørsler.

set -euo pipefail

APP=pax-juriitech

echo "Finder GDPR-cron-machines..."
TARGETS=$(flyctl machine list --app "${APP}" --json 2>/dev/null \
    | python3 -c "import sys, json; ms=json.load(sys.stdin); print(' '.join(m['id'] for m in ms if 'cron' in (m.get('name') or '').lower() or 'gdpr' in (m.get('name') or '').lower()))" 2>/dev/null \
    || echo "")

if [[ -z "${TARGETS}" ]]; then
    echo "Ingen cron-machines fundet — intet at stoppe."
    exit 0
fi

for m in ${TARGETS}; do
    echo "Stopper machine ${m}..."
    flyctl machine stop "${m}" --app "${APP}" 2>&1 || true
    flyctl machine destroy "${m}" --app "${APP}" --force 2>&1 || true
done

echo "GDPR-cron stoppet og fjernet."
