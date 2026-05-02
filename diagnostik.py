"""
Diagnostik-script: tjekker at RAG-opsætningen er korrekt på tværs af
pakker, database og Voyage API.

Kørsel (fra projektmappen):
    python diagnostik.py

Scriptet laver INGEN ændringer — det læser kun og rapporterer.
"""

import os
import sys

RESULTATER = []


def tjek(navn, ok, detalje=""):
    status = "✅" if ok else "❌"
    linje = f"{status} {navn}"
    if detalje:
        linje += f"  —  {detalje}"
    print(linje)
    RESULTATER.append(ok)


print("=" * 60)
print("JURIDISK ASSISTENT — RAG DIAGNOSTIK")
print("=" * 60)
print()

# --- 1. Pakker ---
print("1) Python-pakker")
try:
    import voyageai  # noqa: F401
    tjek("voyageai installeret", True, voyageai.__version__ if hasattr(voyageai, "__version__") else "")
except ImportError:
    tjek("voyageai installeret", False, "kør: pip install voyageai")

try:
    import pgvector  # noqa: F401
    tjek("pgvector installeret", True)
except ImportError:
    tjek("pgvector installeret", False, "kør: pip install pgvector")

try:
    import psycopg2  # noqa: F401
    tjek("psycopg2 installeret", True)
except ImportError:
    tjek("psycopg2 installeret", False, "kør: pip install psycopg2-binary")

try:
    import anthropic  # noqa: F401
    tjek("anthropic installeret", True)
except ImportError:
    tjek("anthropic installeret", False, "kør: pip install anthropic")

print()

# --- 2. .env-nøgler ---
print("2) API-nøgler i .env")
from dotenv import load_dotenv
load_dotenv()

tjek("DATABASE_URL sat", bool(os.getenv("DATABASE_URL")))
tjek("ANTHROPIC_API_KEY sat", bool(os.getenv("ANTHROPIC_API_KEY")))
tjek("VOYAGE_API_KEY sat", bool(os.getenv("VOYAGE_API_KEY")))

print()

# --- 3. Database-opsætning ---
print("3) Database (Supabase Postgres)")
try:
    import psycopg2
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    cur.execute("SELECT 1")
    tjek("Forbindelse til Supabase", True)

    cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    pgvec_aktiv = cur.fetchone() is not None
    tjek("pgvector-extension aktiveret", pgvec_aktiv)

    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='mine_dokumenter' AND column_name='embedding'"
    )
    emb_kolonne = cur.fetchone() is not None
    tjek("embedding-kolonne findes", emb_kolonne)

    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='mine_dokumenter' AND column_name='dokumenttype'"
    )
    dok_kolonne = cur.fetchone() is not None
    tjek("dokumenttype-kolonne findes", dok_kolonne)

    if emb_kolonne:
        cur.execute("SELECT COUNT(*) FROM mine_dokumenter")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM mine_dokumenter WHERE embedding IS NOT NULL")
        med_emb = cur.fetchone()[0]
        tjek(
            f"Sager med embedding: {med_emb} / {total}",
            med_emb == total and total > 0,
            "kør backfill_embeddings.py hvis ikke alle har embedding"
            if med_emb < total
            else "",
        )

    cur.close()
    conn.close()
except Exception as e:
    tjek("Forbindelse til Supabase", False, str(e))

print()

# --- 4. Voyage API ---
print("4) Voyage AI")
try:
    from embeddings import embed_sporgsmaal
    emb = embed_sporgsmaal("Test: forsinket fly pga. vejret")
    if emb and len(emb) == 1024:
        tjek("Voyage returnerer 1024-dim embedding", True, f"første 3 tal: {[round(x, 3) for x in emb[:3]]}")
    else:
        tjek("Voyage returnerer 1024-dim embedding", False, f"fik: {type(emb).__name__}")
except Exception as e:
    tjek("Voyage API-kald", False, str(e))

print()

# --- 5. End-to-end RAG-test ---
print("5) RAG ende-til-ende (stille test)")
try:
    from embeddings import embed_sporgsmaal
    from database import find_relevante_sager
    emb = embed_sporgsmaal("klage over forsinket fly")
    if emb:
        rel = find_relevante_sager(emb, top_k=3)
        if rel:
            tjek(
                f"RAG-søgning returnerer {len(rel)} relevante sager",
                True,
            )
            print("   Top 3 matches:")
            for i, s in enumerate(rel, 1):
                sim = s.get("similarity")
                sim_str = f"{sim:.3f}" if sim is not None else "n/a"
                print(f"     {i}. {s['filnavn']}  (relevans: {sim_str})")
        else:
            tjek("RAG-søgning returnerer relevante sager", False, "0 resultater — er backfill kørt?")
    else:
        tjek("RAG-søgning", False, "embedding fejlede")
except Exception as e:
    tjek("RAG-søgning", False, str(e))

print()
print("=" * 60)
if all(RESULTATER):
    print("🎉 ALT OK — RAG er klar til brug.")
else:
    n_fejl = sum(1 for r in RESULTATER if not r)
    print(f"⚠️  {n_fejl} tjek fejlede — se ovenstående.")
print("=" * 60)
