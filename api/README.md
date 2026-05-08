# juriitech PAX — FastAPI-bro

Bro mellem Next.js-frontend (`pax-next/`) og eksisterende
Python-AI-kode (`ai_engine.py`, `embeddings.py`, `processor.py`,
`anonymisering_pdf.py` m.fl.).

## Kør lokalt

Fra **projektets root-mappe** (ikke `api/`):

```bash
uvicorn api.main:app --reload --port 8000
```

Stop med Ctrl+C.

Kør parallelt med Next.js (`cd pax-next && npm run dev` på port 3000)
— så taler de to processer sammen via `http://localhost:8000`.

## Sundhedstjek

```bash
curl http://localhost:8000/api/health
```

Bør returnere `{"ok": true, ...}` med en liste af de Python-moduler
der er successfuldt importeret.

## Hvad denne service IKKE gør

- Ikke deployet til Fly.io. Kører kun lokalt under migration.
- Ikke en kopi af Python-koden. Den **importerer** eksisterende moduler
  fra parent-mappen via `sys.path`-hack øverst i `main.py`. Ingen
  duplikering, ingen risiko for divergens.

## Tilføj nye endpoints

Hvert endpoint i `main.py` tager imod data fra Next.js, kalder en
funktion i den eksisterende Python-kode og returnerer JSON.

Eksempel-mønster (kommer i step 6+):

```python
from ai_engine import generer_svarbrev_til_sag

@app.post("/api/svarbrev")
def lav_svarbrev(request: SvarbrevRequest):
    svar = generer_svarbrev_til_sag(
        sag=request.sag,
        sagsakter=request.sagsakter,
        # ...
    )
    return {"svarbrev": svar}
```
