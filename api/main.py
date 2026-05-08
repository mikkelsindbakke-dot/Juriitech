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


async def _laes_uploads_med_zip_udpakning(filer: List[UploadFile]):
    """
    Læser uploads til (filnavn, bytes)-tupler og pakker zip-filer ud
    inline. Returnerer en flad liste — kalderen ser ingen forskel på
    om en fil kom direkte fra brugeren eller fra en zip.

    Bruger samme udpak_zip_til_filer-funktion som Streamlit-PAX, så
    udpaknings-adfærden er bit-præcist ens (springer __MACOSX, skjulte
    filer og mapper over).
    """
    from processor import udpak_zip_til_filer  # lazy import

    flad_liste = []  # liste af (filnavn, bytes)
    for fil in filer:
        navn = fil.filename or "ukendt"
        data = await fil.read()
        if navn.lower().endswith(".zip"):
            udpakket = udpak_zip_til_filer(data)
            for u_navn, u_data in udpakket:
                flad_liste.append((u_navn, u_data))
        else:
            flad_liste.append((navn, data))
    return flad_liste


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

    flade_filer = await _laes_uploads_med_zip_udpakning(filer)

    resultater = []
    for navn, data in flade_filer:
        result = _laes_fra_bytes(navn, data)
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
    flade_filer = await _laes_uploads_med_zip_udpakning(filer)
    parsed_filer = [_laes_fra_bytes(navn, data) for navn, data in flade_filer]
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
    flade_filer = await _laes_uploads_med_zip_udpakning(filer)
    parsed_filer = [_laes_fra_bytes(navn, data) for navn, data in flade_filer]
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


@app.post("/api/anonymiser")
async def anonymiser(
    filer: List[UploadFile] = File(...),
    klager_navne_json: str = Form("[]"),
):
    """
    Sort-bjælke-anonymisering af PDF-bilag. Kalder eksisterende
    anonymisering_pdf.anonymiser_pdf_fil uændret.

    Regler (defineret i Python-modulet):
      - Klagers navne (i klager_navne_json) bevares fuldt
      - Andre fornavne beholdes, efternavne sorbjælkes
      - Email: lokal del sorbjælkes, domæne bevares
      - Telefon: områdekode bevares, resten sorbjælkes
      - CPR: fuldt sorbjælkes
      - Adresse: gade+husnr sorbjælkes, postnr+by bevares

    Returnerer per fil:
      - status: 'ok' | 'scannet' | 'fejl_aaben' | 'fejl_redaktion'
      - anonymiseret_pdf_base64: base64-encoded redacted PDF (kun ved 'ok')
      - bemaerkning: forklarende tekst

    Bytes base64-encodes så de kan transporteres i JSON.
    """
    import base64
    import json

    from anonymisering_pdf import anonymiser_pdf_fil

    try:
        klager_navne = json.loads(klager_navne_json) or []
        if not isinstance(klager_navne, list):
            klager_navne = []
    except Exception:
        klager_navne = []

    flade_filer = await _laes_uploads_med_zip_udpakning(filer)

    resultater = []
    for filnavn, data in flade_filer:
        if not filnavn.lower().endswith(".pdf"):
            resultater.append({
                "filnavn": filnavn,
                "status": "ikke_pdf",
                "anonymiseret_pdf_base64": None,
                "antal_bytes_input": len(data),
                "antal_bytes_output": 0,
                "bemaerkning": "Kun PDF-filer understøttes af sort-bjælke-anonymisering",
            })
            continue

        try:
            output_pdf, status = anonymiser_pdf_fil(data, klager_navne)
        except Exception as e:
            resultater.append({
                "filnavn": filnavn,
                "status": "exception",
                "anonymiseret_pdf_base64": None,
                "antal_bytes_input": len(data),
                "antal_bytes_output": 0,
                "bemaerkning": f"{type(e).__name__}: {e}",
            })
            continue

        bemaerkning_map = {
            "ok": "Sort-bjælke-anonymiseret PDF med bevaret layout",
            "scannet": "Scannet PDF (intet tekst-lag) — sort-bjælke ikke muligt",
            "fejl_aaben": "PDF kunne ikke åbnes",
            "fejl_redaktion": "Redaction fejlede internt",
        }

        resultater.append({
            "filnavn": filnavn,
            "status": status,
            "anonymiseret_pdf_base64": (
                base64.b64encode(output_pdf).decode("ascii")
                if output_pdf and status == "ok"
                else None
            ),
            "antal_bytes_input": len(data),
            "antal_bytes_output": len(output_pdf) if output_pdf else 0,
            "bemaerkning": bemaerkning_map.get(status, status),
        })

    antal_ok = sum(1 for r in resultater if r["status"] == "ok")
    return {
        "filer": resultater,
        "metadata": {
            "antal_input": len(filer),
            "antal_anonymiseret_ok": antal_ok,
            "klager_navne": klager_navne,
        },
    }


@app.post("/api/tjekliste")
async def tjekliste(filer: List[UploadFile] = File(...)):
    """
    Genererer struktureret tjekliste over hvad Nævnet har bedt om i
    høringsbrevet, og hvad der er dækket/ikke dækket af de uploadede
    bilag. Kalder eksisterende ai_engine.generer_tjekliste uændret.

    Returnerer markdown-tekst som typisk indeholder:
      - Liste af ønskede oplysninger
      - Status per punkt (✓ dækket / ✗ mangler)
      - Konkrete bilag der dækker hvert punkt

    Tager ~30 sek. Bruger Anthropic-credits.
    """
    from processor import _laes_fra_bytes
    from ai_engine import generer_tjekliste

    flade_filer = await _laes_uploads_med_zip_udpakning(filer)
    parsed_filer = [_laes_fra_bytes(navn, data) for navn, data in flade_filer]
    sag = {"filer": parsed_filer}

    try:
        tjekliste_md = generer_tjekliste(sag=sag)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"generer_tjekliste fejlede: {e}",
        )

    if not tjekliste_md or not tjekliste_md.strip():
        raise HTTPException(
            status_code=502,
            detail="AI returnerede tom tjekliste",
        )

    return {
        "tjekliste": tjekliste_md,
        "metadata": {
            "antal_filer": len(parsed_filer),
            "tegn": len(tjekliste_md),
        },
    }
