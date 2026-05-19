#!/bin/bash
#
# Container-entrypoint for pax-next-deploymentet.
#
# Starter to processer i samme container:
#   1. uvicorn (FastAPI) på intern port 8000 — håndterer /api/*
#   2. node (Next.js standalone) på port 8080 — håndterer alt UI
#
# Next.js' rewrites-config proxier /api/* til localhost:8000, så klienten
# kalder same-origin og ingen CORS-headache.
#
# Signal-håndtering: hvis ét af processerne crasher, dræber vi det andet
# og exit'er med en non-zero kode så Fly genstarter machinen.

set -euo pipefail

# Alias Fly-secrets til de NEXT_PUBLIC_*-varianter som Next.js' server-side
# kode forventer. Fly secrets gemmes som SUPABASE_URL / SUPABASE_ANON_KEY
# (uden prefix — så de også deles med FastAPI/Python-laget). Uden denne
# aliasering crasher Next.js' server-render-lag med "Your project's URL
# and Key are required to create a Supabase client" på hver request.
#
# Client-side bundle har værdierne baked-in fra Dockerfile-build-args ved
# build-time, så aliaset er kun for SERVER-SIDE runtime.
export NEXT_PUBLIC_SUPABASE_URL="${NEXT_PUBLIC_SUPABASE_URL:-${SUPABASE_URL:-}}"
export NEXT_PUBLIC_SUPABASE_ANON_KEY="${NEXT_PUBLIC_SUPABASE_ANON_KEY:-${SUPABASE_ANON_KEY:-}}"

cleanup() {
    local exit_code=$?
    echo "[entrypoint] cleanup — dræber baggrunds-processer"
    if [[ -n "${UVICORN_PID:-}" ]]; then
        kill "$UVICORN_PID" 2>/dev/null || true
    fi
    if [[ -n "${NEXT_PID:-}" ]]; then
        kill "$NEXT_PID" 2>/dev/null || true
    fi
    exit "$exit_code"
}
trap cleanup SIGTERM SIGINT EXIT

echo "[entrypoint] Starter uvicorn (FastAPI) på port 8000..."
uvicorn api.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --log-level info \
    --no-access-log \
    &
UVICORN_PID=$!
echo "[entrypoint] uvicorn PID=$UVICORN_PID"

# Vent kort så uvicorn er klar inden Next.js tager imod requests og
# straks begynder at proxy /api/* — ellers får første brugere 502.
sleep 2

echo "[entrypoint] Starter Next.js (node server.js) på port 8080..."
cd /app/pax-next-runtime
node server.js &
NEXT_PID=$!
echo "[entrypoint] Next.js PID=$NEXT_PID"

# Vent på at en af processerne dør, så cleanup-traphandleren dræber resten
wait -n $UVICORN_PID $NEXT_PID
EXIT_CODE=$?
echo "[entrypoint] En proces døde med exit-code $EXIT_CODE"
exit $EXIT_CODE
