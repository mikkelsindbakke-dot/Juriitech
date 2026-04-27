"""
Migration-script: Neon → Supabase.

Kopierer alle data fra den eksisterende Neon-database til en ny
Supabase-database. Sikker, idempotent, og kan rulles tilbage ved at
pege DATABASE_URL tilbage til Neon.

Sådan bruger du scriptet:

  1. Opret en lokal .env-fil (eller sæt env vars) MED BEGGE URL'er:

     OLD_DATABASE_URL=postgresql://neondb_owner:...@neon.tech/...
     NEW_DATABASE_URL=postgresql://postgres.XXX:...@aws-0-eu-west-1.pooler.supabase.com:6543/postgres

  2. Kør scriptet:

     python3 migration_til_supabase.py

  3. Tjek output: scriptet viser antal rækker per tabel før/efter, så du
     kan verificere at migrationen er fuldført.

  4. Når alt er ok, opdater DATABASE_URL i Streamlit Cloud secrets til
     NEW_DATABASE_URL og redeploy. Lad Neon være urørt i 24-48 timer
     som rollback-buffer.
"""

import os
import sys
import time

import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv


load_dotenv()

# OLD_URL hentes automatisk fra DATABASE_URL i .env (samme værdi PAX bruger)
# Det betyder du ikke skal copy-paste din Neon-URL — den er allerede der.
OLD_URL = (
    os.getenv("OLD_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or ""
).strip()

NEW_URL = os.getenv("NEW_DATABASE_URL", "").strip()

if not OLD_URL:
    print("❌ Kunne ikke finde DATABASE_URL i .env-filen.")
    print("   Tjek at du står i den rigtige mappe og at .env eksisterer.")
    sys.exit(1)

# Hvis NEW_DATABASE_URL ikke er i .env, så spørg interaktivt
if not NEW_URL:
    print()
    print("=" * 70)
    print("Indsæt din Supabase-URL nu (med password indsat).")
    print("Den ser ud som:")
    print("  postgresql://postgres.XXXXX:[DIT-PASSWORD]@aws-0-eu-west-1."
          "pooler.supabase.com:6543/postgres")
    print()
    print("URL'en gemmes IKKE — den bruges kun i denne ene kørsel.")
    print("=" * 70)
    NEW_URL = input("\nSupabase URL: ").strip()
    if not NEW_URL:
        print("❌ Tom URL — afbrudt.")
        sys.exit(1)
    if "[YOUR-PASSWORD]" in NEW_URL or "[DIT-PASSWORD]" in NEW_URL:
        print("❌ Du har glemt at indsætte dit faktiske password i URL'en.")
        print("   Erstat [YOUR-PASSWORD] med dit Supabase database-password.")
        sys.exit(1)
    if "supabase" not in NEW_URL.lower():
        print("⚠️  URL'en ser ikke ud til at pege på Supabase. "
              "Sikker på det er den rigtige?")
        bekraeft = input("Fortsæt alligevel? (skriv 'ja' for at fortsætte): ")
        if bekraeft.lower().strip() != "ja":
            print("Afbrudt.")
            sys.exit(0)

# Sikkerhedsbekræftelse før destructiv operation
print()
print("=" * 70)
print("MIGRATION-OVERSIGT")
print("=" * 70)
print(f"FRA (gammel):  {OLD_URL[:60]}...")
print(f"TIL (ny):      {NEW_URL[:60]}...")
print()
print("Scriptet vil:")
print("  1. Læse alle data fra Neon (din nuværende database)")
print("  2. Oprette tabeller i Supabase")
print("  3. Kopiere alle data over")
print("  4. Verificere antal matcher")
print()
print("Neon-databasen rør IKKE — det er en kopi, ikke en flytning.")
print("Hvis noget går galt, er din originale data intakt.")
print("=" * 70)
bekraeft = input("\nKlar til at starte migration? (skriv 'ja' for at fortsætte): ")
if bekraeft.lower().strip() != "ja":
    print("Afbrudt.")
    sys.exit(0)
print()


def _connect(url, navn):
    print(f"🔌 Forbinder til {navn}...")
    conn = psycopg2.connect(url)
    try:
        register_vector(conn)
    except Exception:
        pass
    return conn


def opret_schema_paa_supabase(conn):
    """Opretter alle tabeller, extensions og indexes på den nye database."""
    cur = conn.cursor()
    print("📦 Opretter pgvector extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

    print("📦 Opretter mine_dokumenter-tabel...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mine_dokumenter (
            id SERIAL PRIMARY KEY,
            filnavn TEXT,
            indhold TEXT,
            oprettet_dato TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            dokumenttype TEXT DEFAULT 'afgoerelse',
            embedding vector(1024),
            kilde_url TEXT
        )
    """)

    print("📦 Opretter analyse_arkiv-tabel...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyse_arkiv (
            id SERIAL PRIMARY KEY,
            titel TEXT NOT NULL,
            type TEXT NOT NULL,
            klage_filnavn TEXT,
            spoergsmaal TEXT,
            sagsakter TEXT,
            ekstra_instrukser TEXT,
            indhold TEXT NOT NULL,
            oprettet_dato TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("📦 Opretter gemte_sager-tabel...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gemte_sager (
            id SERIAL PRIMARY KEY,
            user_id TEXT,
            titel TEXT NOT NULL,
            state_json TEXT NOT NULL,
            oprettet_dato TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            opdateret_dato TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # HNSW-indeks oprettes EFTER data er kopieret (bygger hurtigere på færdige data)
    print("✅ Schema oprettet")


def opret_index_paa_supabase(conn):
    """HNSW-indeks bygges efter data er indlæst — hurtigere end at gøre det først."""
    cur = conn.cursor()
    print("🔍 Bygger HNSW-indeks på embeddings (kan tage 30-90 sek)...")
    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mine_dokumenter_embedding
            ON mine_dokumenter
            USING hnsw (embedding vector_cosine_ops)
        """)
        conn.commit()
        print("✅ HNSW-indeks oprettet")
    except Exception as e:
        print(f"⚠️  HNSW-indeks kunne ikke oprettes (ikke kritisk): {e}")
        conn.rollback()


def antal_raekker(conn, tabel):
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {tabel}")
    n = cur.fetchone()[0]
    cur.close()
    return n


def kopier_mine_dokumenter(old_conn, new_conn):
    """Kopierer alle dokumenter inkl. embeddings."""
    print("\n📥 Læser mine_dokumenter fra Neon...")
    old_cur = old_conn.cursor()
    old_cur.execute("""
        SELECT filnavn, indhold, oprettet_dato, dokumenttype, embedding, kilde_url
        FROM mine_dokumenter
        ORDER BY id
    """)
    raekker = old_cur.fetchall()
    old_cur.close()
    print(f"   Hentede {len(raekker)} rækker")

    if not raekker:
        print("   (intet at kopiere)")
        return

    print(f"📤 Indsætter i Supabase i batches af 100...")
    new_cur = new_conn.cursor()

    # Indsæt i batches så vi ikke rammer parameter-limit
    BATCH = 100
    for i in range(0, len(raekker), BATCH):
        batch = raekker[i:i + BATCH]
        execute_values(
            new_cur,
            """
            INSERT INTO mine_dokumenter
                (filnavn, indhold, oprettet_dato, dokumenttype, embedding, kilde_url)
            VALUES %s
            """,
            batch,
        )
        new_conn.commit()
        print(f"   Indsat {min(i + BATCH, len(raekker))}/{len(raekker)}")

    new_cur.close()
    print("✅ mine_dokumenter migreret")


def kopier_analyse_arkiv(old_conn, new_conn):
    """Kopierer alle gemte analyser og svarbreve."""
    print("\n📥 Læser analyse_arkiv fra Neon...")
    old_cur = old_conn.cursor()
    try:
        old_cur.execute("""
            SELECT titel, type, klage_filnavn, spoergsmaal, sagsakter,
                   ekstra_instrukser, indhold, oprettet_dato
            FROM analyse_arkiv
            ORDER BY id
        """)
        raekker = old_cur.fetchall()
    except Exception as e:
        print(f"   ⚠️  Tabel findes ikke eller fejlede: {e}")
        old_conn.rollback()
        raekker = []
    old_cur.close()
    print(f"   Hentede {len(raekker)} rækker")

    if not raekker:
        print("   (intet at kopiere)")
        return

    new_cur = new_conn.cursor()
    execute_values(
        new_cur,
        """
        INSERT INTO analyse_arkiv
            (titel, type, klage_filnavn, spoergsmaal, sagsakter,
             ekstra_instrukser, indhold, oprettet_dato)
        VALUES %s
        """,
        raekker,
    )
    new_conn.commit()
    new_cur.close()
    print("✅ analyse_arkiv migreret")


def kopier_gemte_sager(old_conn, new_conn):
    """Kopierer alle gemte sagspakker (hele sag-state som JSON)."""
    print("\n📥 Læser gemte_sager fra Neon...")
    old_cur = old_conn.cursor()
    try:
        old_cur.execute("""
            SELECT user_id, titel, state_json, oprettet_dato, opdateret_dato
            FROM gemte_sager
            ORDER BY id
        """)
        raekker = old_cur.fetchall()
    except Exception as e:
        print(f"   ⚠️  Tabel findes ikke eller fejlede: {e}")
        old_conn.rollback()
        raekker = []
    old_cur.close()
    print(f"   Hentede {len(raekker)} rækker")

    if not raekker:
        print("   (intet at kopiere)")
        return

    new_cur = new_conn.cursor()
    execute_values(
        new_cur,
        """
        INSERT INTO gemte_sager
            (user_id, titel, state_json, oprettet_dato, opdateret_dato)
        VALUES %s
        """,
        raekker,
    )
    new_conn.commit()
    new_cur.close()
    print("✅ gemte_sager migreret")


def verificer(old_conn, new_conn):
    """Sammenligner antal rækker i hver tabel før/efter."""
    print("\n🔍 Verificerer migration...")
    print("=" * 60)
    print(f"{'Tabel':<25} {'Neon':>10} {'Supabase':>15} {'Match':>8}")
    print("=" * 60)

    alt_ok = True
    for tabel in ("mine_dokumenter", "analyse_arkiv", "gemte_sager"):
        try:
            n_old = antal_raekker(old_conn, tabel)
        except Exception:
            n_old = 0
            old_conn.rollback()
        try:
            n_new = antal_raekker(new_conn, tabel)
        except Exception:
            n_new = 0
            new_conn.rollback()
        match = "✅" if n_old == n_new else "❌"
        if n_old != n_new:
            alt_ok = False
        print(f"{tabel:<25} {n_old:>10} {n_new:>15} {match:>8}")

    print("=" * 60)
    if alt_ok:
        print("\n🎉 Migration fuldført uden tab af data!")
        print("\nNæste skridt:")
        print("  1. Opdater DATABASE_URL i Streamlit Cloud secrets til den nye URL")
        print("  2. Test PAX i 24-48 timer med Neon stadig kørende som backup")
        print("  3. Slet Neon-projektet når du er sikker på alt virker")
    else:
        print("\n⚠️  Antal rækker matcher ikke. Tjek output ovenfor.")
        print("   Migrationen kan være ufuldstændig — kontakt support inden næste skridt.")


def main():
    start = time.time()
    print("=" * 60)
    print("MIGRATION: Neon → Supabase")
    print("=" * 60)

    old_conn = _connect(OLD_URL, "Neon (gammel)")
    new_conn = _connect(NEW_URL, "Supabase (ny)")

    opret_schema_paa_supabase(new_conn)

    kopier_mine_dokumenter(old_conn, new_conn)
    kopier_analyse_arkiv(old_conn, new_conn)
    kopier_gemte_sager(old_conn, new_conn)

    opret_index_paa_supabase(new_conn)

    verificer(old_conn, new_conn)

    old_conn.close()
    new_conn.close()

    elapsed = time.time() - start
    print(f"\n⏱  Total tid: {elapsed:.1f} sekunder")


if __name__ == "__main__":
    main()
