"""
Engangs/idempotent script: chunker alle eksisterende afgørelser og
embedder hver chunk for sig.

KØRSEL (fra terminalen, i projektmappen):
    python backfill_chunks.py

Hvad det gør:
  1. Sørger for at dokument_chunks-tabellen findes (idempotent).
  2. Finder alle afgørelser i mine_dokumenter der ENDNU IKKE har
     chunks i dokument_chunks-tabellen.
  3. For hver: splitter teksten med embeddings.chunk_tekst() og
     embedder hver chunk via Voyage.
  4. Gemmer chunks med embeddings i dokument_chunks-tabellen.

Idempotent: Du kan køre scriptet igen uden problem. Det rør kun
dokumenter der mangler chunks. Hvis du vil tvinge re-chunking af
ALLE dokumenter (fx hvis chunking-strategien ændres), skal du først
tømme dokument_chunks-tabellen manuelt:
    DELETE FROM dokument_chunks;
og så køre scriptet igen.

Kost-estimat: ~500 afgørelser × ~10 chunks × 700 tokens = 3,5M tokens.
Voyage tager $0,12/1M tokens, så ~$0,42 i ALT for hele backfillen.
"""

from database import (
    opret_tabeller,
    hent_dokumenter_uden_chunks,
    gem_chunks_for_dokument,
    antal_chunks_total,
)
from embeddings import chunk_tekst, embed_batch


# Hvor mange CHUNKS vi embedder pr. Voyage-kald. Voyage tillader op
# til 128, men 16 giver bedre fejl-isolation (én crash dropper kun
# 16 chunks, ikke 128) og tydelig progress-output.
EMBED_BATCH_SIZE = 16


def _embed_chunks_med_voyage(chunks):
    """
    Embedder en liste af chunk-dicts. Tilføjer 'embedding'-nøgle
    in-place på hver chunk. Returnerer antal succesfulde embeddings.
    """
    if not chunks:
        return 0

    ok = 0
    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i : i + EMBED_BATCH_SIZE]
        tekster = [c["indhold"] for c in batch]
        embeddings_resultat = embed_batch(tekster)
        for c, emb in zip(batch, embeddings_resultat):
            if emb is None:
                c["embedding"] = None
            else:
                c["embedding"] = emb
                ok += 1
    return ok


def main():
    print("=" * 60)
    print(" Backfill: chunking + embedding af afgørelser")
    print("=" * 60)
    print()

    # Sørg for at chunks-tabellen findes
    opret_tabeller()

    dokumenter = hent_dokumenter_uden_chunks(dokumenttype="afgoerelse")
    if not dokumenter:
        print("✅ Alle afgørelser har allerede chunks. Intet at gøre.")
        print(f"   Total chunks i databasen: {antal_chunks_total()}")
        return

    print(f"🔍 Fandt {len(dokumenter)} afgørelser uden chunks.")
    print(f"   Chunker og embedder...")
    print()

    total_chunks_oprettet = 0
    total_embeddings_ok = 0
    total_embeddings_fejl = 0
    dok_fejl = 0

    for nr, dok in enumerate(dokumenter, 1):
        filnavn = dok["filnavn"]
        indhold = dok["indhold"] or ""
        dok_id = dok["id"]

        try:
            chunks = chunk_tekst(indhold)
            if not chunks:
                print(f"   [{nr}/{len(dokumenter)}] {filnavn} — ⚠️  ingen chunks (tom tekst?)")
                continue

            ok = _embed_chunks_med_voyage(chunks)
            fejl = len(chunks) - ok
            total_embeddings_ok += ok
            total_embeddings_fejl += fejl

            antal_gemt = gem_chunks_for_dokument(dok_id, chunks)
            total_chunks_oprettet += antal_gemt

            status = "✅" if fejl == 0 else "⚠️ "
            print(
                f"   [{nr}/{len(dokumenter)}] {status} {filnavn} — "
                f"{antal_gemt} chunks ({ok} embeddet, {fejl} fejlede)"
            )
        except Exception as e:
            dok_fejl += 1
            print(f"   [{nr}/{len(dokumenter)}] ❌ {filnavn} — fejl: {e}")

    print()
    print("=" * 60)
    print(f" Færdig.")
    print(f"   Dokumenter behandlet: {len(dokumenter) - dok_fejl}")
    print(f"   Dokumenter fejlede:   {dok_fejl}")
    print(f"   Chunks oprettet:      {total_chunks_oprettet}")
    print(f"   Embeddings OK:        {total_embeddings_ok}")
    print(f"   Embeddings fejlede:   {total_embeddings_fejl}")
    print(f"   Total chunks i DB:    {antal_chunks_total()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
