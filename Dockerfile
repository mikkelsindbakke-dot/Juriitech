# juriitech PAX — produktions-container til Fly.io
#
# Bygger et slankt Python-image med Streamlit-appen og alle dens
# afhængigheder. Kører på port 8080 (Fly.io's standard internal port).

FROM python:3.11-slim

# Set environment variables for Python optimering
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_SERVER_PORT=8080 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false \
    STREAMLIT_SERVER_MAX_UPLOAD_SIZE=200

# System-afhængigheder:
# - libpq-dev: psycopg2 (Postgres-driver) skal bruge denne
# - gcc: nogle Python-pakker kompilerer C-kode under installation
# - curl: bruges til health checks
# - libfreetype6: reportlab har brug for det til PDF-fonts
# - fonts-dejavu: standard fonts til PDF-generering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    curl \
    libfreetype6 \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps først (separat layer for bedre Docker-caching —
# requirements.txt ændrer sig sjældent, så det layer genbruges på
# tværs af kode-ændringer)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Kopier resten af app-koden
COPY . .

# Expose Fly.io's interne port
EXPOSE 8080

# Health check så Fly.io ved, om appen kører eller skal genstartes
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl --fail http://localhost:8080/_stcore/health || exit 1

# Start Streamlit
CMD ["streamlit", "run", "app.py"]
