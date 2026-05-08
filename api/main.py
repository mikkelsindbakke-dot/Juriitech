"""
FastAPI-bro til eksisterende Python-PAX-kode.

Denne service eksponerer ai_engine.py, embeddings.py, processor.py,
anonymisering_pdf.py m.fl. som HTTP-endpoints, så Next.js-versionen
af PAX (i pax-next/) kan kalde dem uden at vi skal port'e den
juridiske domæne-logik til TypeScript.

Designprincipper:
  - INGEN ændring af eksisterende Python-kode (ai_engine.py m.fl.).
  - Kun lokalt under migration. IKKE deployet til Fly.io.
  - Importerer fra parent-mappen via sys.path-hack øverst i filen.
  - CORS tillader kun localhost:3000 (Next.js dev-server).

Kør lokalt:
  cd /Users/mikkelhansen/Desktop/Projekter/juridisk_assistent
  uvicorn api.main:app --reload --port 8000
"""

import os
import sys

# Tilføj parent-mappen til sys.path så vi kan importere ai_engine,
# embeddings, processor m.fl. uden at flytte dem.
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app = FastAPI(
    title="juriitech PAX API",
    description="Bro mellem Next.js-frontend og eksisterende Python-AI-kode.",
    version="0.1.0",
)

# CORS: tillad kun Next.js dev-serveren at kalde os under udvikling.
# Når vi deployer rigtigt (step 8+), opdateres denne liste.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    """
    Sundhedstjek. Verificerer at FastAPI kører OG at den faktisk
    kan importere de eksisterende AI-moduler — så vi tidligt fanger
    path- eller dependency-problemer.
    """
    moduler_status = {}
    for navn in ["ai_engine", "embeddings", "processor", "anonymisering_pdf",
                 "database", "selskab_profiler"]:
        try:
            __import__(navn)
            moduler_status[navn] = "ok"
        except Exception as e:
            moduler_status[navn] = f"FEJL: {type(e).__name__}: {e}"

    alle_ok = all(v == "ok" for v in moduler_status.values())
    return {
        "ok": alle_ok,
        "service": "juriitech-pax-api",
        "version": "0.1.0",
        "python_path_root": _PARENT,
        "moduler": moduler_status,
    }
