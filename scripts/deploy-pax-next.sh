#!/bin/bash
# Deploy pax-juriitech-next (Next.js + FastAPI).
#
# Henter NEXT_PUBLIC_* build-args automatisk fra pax-next/.env.local
# så vi ikke behøver indtaste dem manuelt hver gang.
#
# Kør fra projekt-roden:
#   bash scripts/deploy-pax-next.sh

set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="pax-next/.env.local"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "FEJL: $ENV_FILE findes ikke — opret den med NEXT_PUBLIC_SUPABASE_URL og NEXT_PUBLIC_SUPABASE_ANON_KEY"
    exit 1
fi

# Læs build-args fra .env.local
SUPA_URL=$(grep "^NEXT_PUBLIC_SUPABASE_URL=" "$ENV_FILE" | cut -d= -f2-)
SUPA_KEY=$(grep "^NEXT_PUBLIC_SUPABASE_ANON_KEY=" "$ENV_FILE" | cut -d= -f2-)
SENTRY_DSN=$(grep "^NEXT_PUBLIC_SENTRY_DSN=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "")

if [[ -z "$SUPA_URL" || -z "$SUPA_KEY" ]]; then
    echo "FEJL: NEXT_PUBLIC_SUPABASE_URL eller _ANON_KEY mangler i $ENV_FILE"
    exit 1
fi

# Sentry DSN er valgfri — hvis ikke sat i .env.local, brug den kendte prod-værdi.
# Dette er pax-next-projektet (JavaScript/Next.js platform). Det Python-projekt
# (FastAPI) bruger sin egen DSN via fly secret SENTRY_DSN.
if [[ -z "$SENTRY_DSN" ]]; then
    SENTRY_DSN="https://8a5905d41182da3c321c111a5e2072b9@o4511279259385856.ingest.de.sentry.io/4511383057924176"
fi

echo "Deployer pax-juriitech-next..."
echo "  Supabase URL: ${SUPA_URL:0:40}..."
echo "  Supabase key: ${SUPA_KEY:0:20}..."
echo "  Sentry DSN:   ${SENTRY_DSN:0:40}..."
echo ""

fly deploy \
    --config fly.next.toml \
    --dockerfile Dockerfile.next \
    --remote-only \
    --build-arg "NEXT_PUBLIC_SUPABASE_URL=$SUPA_URL" \
    --build-arg "NEXT_PUBLIC_SUPABASE_ANON_KEY=$SUPA_KEY" \
    --build-arg "NEXT_PUBLIC_SENTRY_DSN=$SENTRY_DSN"

echo ""
echo "✓ Next.js-deploy færdig"
