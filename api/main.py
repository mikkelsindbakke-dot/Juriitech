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

from typing import List  # noqa: E402

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
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


@app.post("/api/parse-fil")
async def parse_fil(filer: List[UploadFile] = File(...)):
    """
    Tager én eller flere uploadede filer og returnerer struktureret
    parse-resultat per fil. Bruger eksisterende
    processor._laes_fra_bytes — samme funktion som Streamlit-PAX bruger
    bag scenen, så parse-output er bit-præcist det samme.

    Bytes i resultatet sendes IKKE tilbage i JSON (de kan være store).
    Vi returnerer kun:
      - filnavn, type, rolle, media_type, evt. aarsag
      - antal_bytes (størrelse-info så frontend kan vise)
      - tekst_uddrag (første 500 tegn til preview)
      - tekst_total_laengde (total antal tegn udtrukket)
    """
    from processor import _laes_fra_bytes  # lazy import for testbarhed

    resultater = []
    for fil in filer:
        data = await fil.read()
        result = _laes_fra_bytes(fil.filename or "ukendt", data)
        tekst = result.get("tekst") or ""
        resultater.append({
            "filnavn": result.get("filnavn"),
            "type": result.get("type"),
            "rolle": result.get("rolle"),
            "media_type": result.get("media_type"),
            "aarsag": result.get("aarsag"),
            "antal_bytes": len(data),
            "tekst_total_laengde": len(tekst),
            "tekst_uddrag": tekst[:500],
        })

    return {"filer": resultater, "antal": len(resultater)}


@app.post("/api/foerstevurdering")
async def foerstevurdering(
    filer: List[UploadFile] = File(...),
    sagsakter: str = Form(""),
):
    """
    Orkestrerer hele førstevurderings-flowet ved at kalde de eksisterende
    Python-funktioner uændret:

      1. processor._laes_fra_bytes — parse uploadede filer
      2. ai_engine.udled_alle_klagepunkter — verificeret klagepunkt-liste
      3. ai_engine.udled_tidsforhold — reklamationsrettidighed
      4. ai_engine.udled_foerstevurdering_struktureret — 6-sektion JSON-analyse
         (returnerer også relevante tidligere afgørelser via RAG)

    Returnerer alt i én JSON. Tager 30-90 sekunder pga. AI-kald +
    embedding-opslag i 500+ sager. Kalder mod prod-Supabase READ-ONLY
    (vidensbanken). Bruger Anthropic-credits.

    Bytes i sag-filerne sendes IKKE tilbage i JSON (kun metadata).
    """
    from processor import _laes_fra_bytes
    from ai_engine import (
        udled_alle_klagepunkter,
        udled_tidsforhold,
        udled_foerstevurdering_struktureret,
    )

    # ---------- 1. Parse files ----------
    parsed_filer = []
    for fil in filer:
        data = await fil.read()
        result = _laes_fra_bytes(fil.filename or "ukendt", data)
        parsed_filer.append(result)
    sag = {"filer": parsed_filer}

    # ---------- 2. Verified klagepunkter ----------
    try:
        klagepunkter = udled_alle_klagepunkter(
            sag=sag,
            sagsakter_tekst=sagsakter,
        ) or []
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"udled_alle_klagepunkter fejlede: {e}",
        )

    # ---------- 3. Tidsforhold (reklamationsrettidighed) ----------
    try:
        tidsforhold = udled_tidsforhold(
            sag=sag,
            sagsakter_tekst=sagsakter,
        ) or {}
    except Exception as e:
        print(f"DEBUG: udled_tidsforhold fejlede ({e}) — fortsætter uden")
        tidsforhold = {}

    # ---------- 4. Byg facit-blokke ----------
    klagepunkter_facit = ""
    if klagepunkter:
        klagepunkter_facit = (
            "VERIFICERET LISTE OVER ALLE KLAGEPUNKTER (udtrukket separat):\n"
            + "".join(f"  {i + 1}. {kp}\n" for i, kp in enumerate(klagepunkter))
            + f"\nTotal: {len(klagepunkter)} klagepunkter.\n\n"
        )

    tidsforhold_facit = ""
    if (
        tidsforhold
        and tidsforhold.get("har_problematisk_forsinkelse")
        and not tidsforhold.get("kunne_ikke_udledes")
    ):
        tidsforhold_facit = (
            "VERIFICERET TIDSFORHOLD — REKLAMATIONSRETTIDIGHED:\n"
            + (
                f"  Samlet: {tidsforhold.get('samlet_vurdering', '')}\n\n"
                if tidsforhold.get("samlet_vurdering")
                else ""
            )
            + "".join(
                f"  • {obs}\n"
                for obs in (tidsforhold.get("konkrete_observationer") or [])
            )
        )

    # ---------- 5. Hovedanalyse ----------
    try:
        analyse_dict, rel_sager = udled_foerstevurdering_struktureret(
            sag=sag,
            sagsakter=sagsakter,
            sagsakter_filer=[],
            klagepunkter_facit=klagepunkter_facit,
            tidsforhold_facit=tidsforhold_facit,
            klagepunkter_liste=klagepunkter,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"udled_foerstevurdering_struktureret fejlede: {e}",
        )

    if analyse_dict is None:
        raise HTTPException(
            status_code=502,
            detail="AI returnerede tom analyse (kan være credit-problem)",
        )

    # ---------- 6. Strip bytes/embedding fra rel_sager til JSON ----------
    rel_sager_clean = []
    for s in (rel_sager or [])[:5]:  # top 5 sager
        rel_sager_clean.append({
            k: v
            for k, v in s.items()
            if k not in ("embedding", "fil_bytes")
            and not isinstance(v, bytes)
        })

    return {
        "klagepunkter": klagepunkter,
        "tidsforhold": tidsforhold,
        "analyse": analyse_dict,
        "relevante_sager": rel_sager_clean,
        "metadata": {
            "antal_filer": len(parsed_filer),
            "antal_klagepunkter": len(klagepunkter),
            "antal_relevante_sager": len(rel_sager_clean),
        },
    }


@app.post("/api/svarbrev")
async def svarbrev(
    filer: List[UploadFile] = File(...),
    sagsakter: str = Form(""),
    ekstra_instrukser_json: str = Form("[]"),
    inkluder_kildehenvisninger: bool = Form(False),
    verificerede_klagepunkter_json: str = Form("null"),
    tidsforhold_json: str = Form("null"),
):
    """
    Genererer komplet udkast til svarbrev. Kalder eksisterende
    ai_engine.generer_svarbrev_til_sag uændret.

    Hvis verificerede_klagepunkter + tidsforhold sendes med (fra et
    tidligere /api/foerstevurdering-kald), genbruges de — det sparer
    2 AI-kald. Ellers udleder svarbrev-funktionen dem selv internt.

    Tager 30-60 sekunder pr. kald. Bruger Anthropic-credits.
    """
    import json

    from processor import _laes_fra_bytes
    from ai_engine import generer_svarbrev_til_sag

    # ---------- Parse files ----------
    parsed_filer = []
    for fil in filer:
        data = await fil.read()
        result = _laes_fra_bytes(fil.filename or "ukendt", data)
        parsed_filer.append(result)
    sag = {"filer": parsed_filer}

    # ---------- Decode JSON-Form-felter ----------
    try:
        ekstra_instrukser = json.loads(ekstra_instrukser_json) or []
        if not isinstance(ekstra_instrukser, list):
            ekstra_instrukser = []
    except Exception:
        ekstra_instrukser = []

    try:
        verificerede_klagepunkter = json.loads(verificerede_klagepunkter_json)
        if verificerede_klagepunkter and not isinstance(
            verificerede_klagepunkter, list
        ):
            verificerede_klagepunkter = None
    except Exception:
        verificerede_klagepunkter = None

    try:
        tidsforhold_dict = json.loads(tidsforhold_json)
        if tidsforhold_dict and not isinstance(tidsforhold_dict, dict):
            tidsforhold_dict = None
    except Exception:
        tidsforhold_dict = None

    # ---------- Byg ekstra_instrukser-tekst ----------
    instrukser_tekst = ""
    if ekstra_instrukser:
        instrukser_tekst = "\n".join(
            f"- {instr}" for instr in ekstra_instrukser if instr
        )

    # ---------- Generer svarbrev ----------
    try:
        svarbrev_tekst = generer_svarbrev_til_sag(
            sag=sag,
            sagsakter=sagsakter,
            ekstra_instrukser=instrukser_tekst or None,
            inkluder_kildehenvisninger=inkluder_kildehenvisninger,
            verificerede_klagepunkter=verificerede_klagepunkter,
            tidsforhold=tidsforhold_dict,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"generer_svarbrev_til_sag fejlede: {e}",
        )

    if not svarbrev_tekst or not svarbrev_tekst.strip():
        raise HTTPException(
            status_code=502,
            detail="AI returnerede tomt svarbrev (kan være credit-problem)",
        )

    return {
        "svarbrev": svarbrev_tekst,
        "metadata": {
            "antal_filer": len(parsed_filer),
            "antal_instrukser": len(ekstra_instrukser),
            "inkluder_kildehenvisninger": inkluder_kildehenvisninger,
            "tegn": len(svarbrev_tekst),
        },
    }
