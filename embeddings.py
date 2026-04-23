"""
Voyage AI embeddings-wrapper.

Bruges til at oversætte dansk juridisk tekst til 1024-dimensionelle vektorer,
så vi kan lave lynhurtig similarity-søgning i Postgres via pgvector.

Model: voyage-multilingual-2 (stærkeste multilingual embedding-model pr. 2025,
inkl. dansk). Output-dim: 1024.
"""

import os
from dotenv import load_dotenv
import voyageai

load_dotenv()

# Voyage-klienten læser VOYAGE_API_KEY fra miljøet automatisk,
# men vi initialiserer eksplicit for tydelighed og bedre fejlmeddelelser.
_API_KEY = os.getenv("VOYAGE_API_KEY")
if not _API_KEY:
    print("DEBUG: VOYAGE_API_KEY mangler i .env — embeddings vil fejle.")

_client = voyageai.Client(api_key=_API_KEY)

MODEL = "voyage-multilingual-2"
DIMENSIONS = 1024

# Voyage har en maksgrænse på ~32.000 tokens pr. input. De fleste
# afgørelser fylder under dette, men vi trunkerer defensivt for at undgå
# fejl på ekstremt lange dokumenter.
MAX_CHARS_PER_DOC = 120_000  # ~30.000 tokens for dansk tekst


def _truncate(text: str) -> str:
    if text is None:
        return ""
    if len(text) > MAX_CHARS_PER_DOC:
        return text[:MAX_CHARS_PER_DOC]
    return text


def embed_dokument(tekst: str):
    """
    Embedder én dokumenttekst (til lagring i databasen).
    Returnerer en liste af 1024 floats, eller None ved fejl.

    Bruger input_type='document' som Voyage anbefaler for ting
    der gemmes og senere søges imod.
    """
    if not tekst or not tekst.strip():
        return None
    try:
        result = _client.embed(
            [_truncate(tekst)],
            model=MODEL,
            input_type="document",
        )
        return result.embeddings[0]
    except Exception as e:
        print(f"DEBUG: Voyage embed_dokument fejlede: {e}")
        return None


def embed_sporgsmaal(tekst: str):
    """
    Embedder et brugerspørgsmål (til søgning mod dokumenter).
    Returnerer en liste af 1024 floats, eller None ved fejl.

    Bruger input_type='query' som Voyage anbefaler for søgekald —
    det giver bedre matches mellem korte spørgsmål og lange dokumenter.
    """
    if not tekst or not tekst.strip():
        return None
    try:
        result = _client.embed(
            [tekst],
            model=MODEL,
            input_type="query",
        )
        return result.embeddings[0]
    except Exception as e:
        print(f"DEBUG: Voyage embed_sporgsmaal fejlede: {e}")
        return None


def embed_batch(tekster: list):
    """
    Embedder flere dokumenter i ét kald (hurtigere og billigere ved bulk).
    Returnerer en liste af embedding-lister i samme rækkefølge som input.
    """
    if not tekster:
        return []
    try:
        result = _client.embed(
            [_truncate(t or "") for t in tekster],
            model=MODEL,
            input_type="document",
        )
        return result.embeddings
    except Exception as e:
        print(f"DEBUG: Voyage embed_batch fejlede: {e}")
        return [None] * len(tekster)
