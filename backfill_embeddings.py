"""
Engangs-script: embedder alle eksisterende sager i databasen der mangler
en embedding, og gemmer vektorerne tilbage.

Kørsel (fra terminalen, i projektmappen):
    python backfill_embeddings.py

Scriptet er idempotent — du kan køre det igen uden problem. Det rør kun
sager hvor embedding IS NULL, så allerede embeddede sager springes over.
"""

from database import (
    opret_tabeller,
    hent_sager_uden_embedding,
    opdater_embedding,
)
from embeddings import embed_batch


BATCH_SIZE = 8  # Voyage accepterer op til 128 pr. kald, men 8 er rigelig og giver tydelig progress


def main():
    # Sørg for at pgvector + kolonnen er sat op inden vi forsøger at skrive
    opret_tabeller()

    sager = hent_sager_uden_embedding()
    if not sager:
        print("✅ Alle sager har allerede en embedding. Intet at gøre.")
        return

    print(f"🔍 Fandt {len(sager)} sager der mangler embedding.")
    print("   Embedder i batches af", BATCH_SIZE, "...")

    ok = 0
    fejl = 0
    for i in range(0, len(sager), BATCH_SIZE):
        batch = sager[i : i + BATCH_SIZE]
        tekster = [s["indhold"] or "" for s in batch]

        embeddings = embed_batch(tekster)

        for sag, emb in zip(batch, embeddings):
            if emb is None:
                print(f"   ⚠️  Kunne ikke embedde {sag['filnavn']} — springer over")
                fejl += 1
                continue
            opdater_embedding(sag["filnavn"], emb)
            ok += 1
            print(f"   ✅ {sag['filnavn']} embeddet ({len(emb)} dimensioner)")

    print("")
    print(f"Færdig. {ok} sager embeddet, {fejl} fejlede.")


if __name__ == "__main__":
    main()
