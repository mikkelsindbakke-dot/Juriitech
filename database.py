import os
import psycopg2
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv

# Læs database-URL fra .env (ikke hardcoded)
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")


def _connect():
    """
    Opretter en forbindelse til Neon og registrerer pgvector-typen,
    så Python kan sende/modtage vector-kolonner som almindelige lister.
    """
    conn = psycopg2.connect(DB_URL)
    try:
        register_vector(conn)
    except Exception:
        # Hvis pgvector-extensionen ikke er oprettet endnu (første kørsel),
        # fejler register_vector. Vi ignorerer det — opret_tabeller() vil
        # aktivere extensionen, og næste forbindelse registrerer fint.
        pass
    return conn


def opret_tabeller():
    """
    Opretter tabellen hvis den ikke findes, sørger for at alle kolonner
    (dokumenttype, embedding) er til stede, og aktiverer pgvector-extensionen.
    Kører idempotent — det er sikkert at kalde ved hver opstart.
    """
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        # 1. Aktivér pgvector-extension (kræves før vector-kolonnen kan oprettes)
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # 2. Basistabel
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mine_dokumenter (
                id SERIAL PRIMARY KEY,
                filnavn TEXT,
                indhold TEXT,
                oprettet_dato TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. Dokumenttype-kolonne (bagudkompatibel; eksisterende rækker får 'afgoerelse')
        cur.execute("""
            ALTER TABLE mine_dokumenter
            ADD COLUMN IF NOT EXISTS dokumenttype TEXT DEFAULT 'afgoerelse'
        """)

        # 4. Embedding-kolonne til vektor-søgning (1024 dim = voyage-multilingual-2)
        cur.execute("""
            ALTER TABLE mine_dokumenter
            ADD COLUMN IF NOT EXISTS embedding vector(1024)
        """)

        # 4b. kilde_url-kolonne — bruges til at spore hvor en sag kom fra
        #     (fx scraperen) og til dedup på URL frem for filnavn.
        cur.execute("""
            ALTER TABLE mine_dokumenter
            ADD COLUMN IF NOT EXISTS kilde_url TEXT
        """)

        # 5. HNSW-indeks til hurtig cosine-søgning. HNSW er robust selv på
        #    små/tomme tabeller og skalerer godt til millioner af rækker.
        #    Hvis pgvector-versionen ikke understøtter HNSW, springer vi over.
        try:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_mine_dokumenter_embedding
                ON mine_dokumenter
                USING hnsw (embedding vector_cosine_ops)
            """)
        except Exception as idx_err:
            print(f"DEBUG: HNSW-indeks kunne ikke oprettes (ikke kritisk): {idx_err}")
            conn.rollback()

        # 6. Arkiv-tabel til gemte analyser og svarbreve. Hver række er én
        #    analyse/ét brev som juristen har fået lavet og vil kunne finde
        #    igen uden at køre AI'en om.
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

        # 7. Gemte sager-tabel — hele sagens state (sag + sagsakter + vurdering)
        #    gemmes som JSON så brugeren kan genoptage arbejde senere.
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
        cur.close()
        conn.close()
        print("DEBUG: Databaseforbindelse oprettet succesfuldt!")
    except Exception as e:
        print(f"DEBUG: Fejl ved oprettelse af tabel: {e}")


def gem_sag_i_db(filnavn, tekst, dokumenttype="afgoerelse", embedding=None, kilde_url=None):
    """
    Gemmer en sag i databasen.
    dokumenttype skal være enten 'afgoerelse' (tidligere kendelse) eller 'klage'
    (indkommen klage, endnu ikke afgjort).

    embedding er valgfri — hvis den er None, gemmes sagen uden, og
    backfill_embeddings() kan fylde den på bagefter.

    kilde_url er valgfri — bruges af scraperen til at spore hvor sagen kom fra
    og undgå dubletter på næste kørsel.
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO mine_dokumenter (filnavn, indhold, dokumenttype, embedding, kilde_url) "
            "VALUES (%s, %s, %s, %s, %s)",
            (filnavn, tekst, dokumenttype, embedding, kilde_url),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"DEBUG: Kunne ikke gemme fil i databasen: {e}")


def url_findes(kilde_url):
    """
    Returnerer True hvis en sag med denne kilde_url allerede findes i databasen.
    Bruges af scraperen til at undgå at re-downloade samme PDF.
    """
    if not kilde_url:
        return False
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM mine_dokumenter WHERE kilde_url = %s LIMIT 1",
            (kilde_url,),
        )
        findes = cur.fetchone() is not None
        cur.close()
        conn.close()
        return findes
    except Exception as e:
        print(f"DEBUG: Kunne ikke tjekke om URL findes: {e}")
        return False


def opdater_embedding(filnavn, embedding):
    """
    Sætter/opdaterer embeddingen for en allerede gemt sag.
    Bruges af backfill-flowet og når en ny klage auto-gemmes uden embedding først.
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE mine_dokumenter SET embedding = %s WHERE filnavn = %s",
            (embedding, filnavn),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"DEBUG: Kunne ikke opdatere embedding: {e}")


def sag_findes(filnavn):
    """
    Returnerer True hvis en sag med det angivne filnavn allerede findes i databasen.
    Bruges til at undgå dubletter når klager gemmes automatisk ved upload.
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM mine_dokumenter WHERE filnavn = %s LIMIT 1",
            (filnavn,),
        )
        findes = cur.fetchone() is not None
        cur.close()
        conn.close()
        return findes
    except Exception as e:
        print(f"DEBUG: Kunne ikke tjekke om sag findes: {e}")
        return False


def hent_antal_sager():
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mine_dokumenter")
        antal = cur.fetchone()[0]
        cur.close()
        conn.close()
        return antal
    except Exception:
        return 0


def antal_af_type(dokumenttype):
    """Returnerer antal dokumenter af en given type (fx 'lovgivning')."""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM mine_dokumenter WHERE dokumenttype = %s",
            (dokumenttype,),
        )
        antal = cur.fetchone()[0]
        cur.close()
        conn.close()
        return antal
    except Exception:
        return 0


def hent_sager_uden_embedding():
    """
    Returnerer sager der mangler embedding — bruges af backfill-scriptet.
    Hver række er en dict med filnavn + indhold.
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT filnavn, indhold FROM mine_dokumenter "
            "WHERE embedding IS NULL"
        )
        raekker = cur.fetchall()
        cur.close()
        conn.close()
        return [{"filnavn": r[0], "indhold": r[1]} for r in raekker]
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente sager uden embedding: {e}")
        return []


def hent_alle_sager():
    """
    Returnerer alle sager i databasen som en liste af dicts:
    [{"filnavn": ..., "indhold": ..., "oprettet_dato": ..., "dokumenttype": ...}, ...]

    Bevaret til backwards compatibility — bruges stadig af fallback-flowet
    når en embedding ikke kan genereres.
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT filnavn, indhold, oprettet_dato, dokumenttype "
            "FROM mine_dokumenter "
            "ORDER BY oprettet_dato DESC"
        )
        raekker = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "filnavn": r[0],
                "indhold": r[1],
                "oprettet_dato": r[2],
                "dokumenttype": r[3] or "afgoerelse",
            }
            for r in raekker
        ]
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente sager: {e}")
        return []


def hent_sager_af_type(dokumenttype, limit=None):
    """
    Returnerer alle dokumenter af en given dokumenttype.

    Bruges bl.a. til at hente ALLE anonymiseringsregler som fast kontekst
    til anonymiseringsopgaver (i modsætning til RAG-baseret topp-k-søgning).
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        if limit is not None:
            cur.execute(
                "SELECT filnavn, indhold, kilde_url FROM mine_dokumenter "
                "WHERE dokumenttype = %s "
                "ORDER BY filnavn ASC LIMIT %s",
                (dokumenttype, int(limit)),
            )
        else:
            cur.execute(
                "SELECT filnavn, indhold, kilde_url FROM mine_dokumenter "
                "WHERE dokumenttype = %s "
                "ORDER BY filnavn ASC",
                (dokumenttype,),
            )
        raekker = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "filnavn": r[0],
                "indhold": r[1],
                "kilde_url": r[2] if len(r) > 2 else None,
            }
            for r in raekker
        ]
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente sager af type {dokumenttype}: {e}")
        return []


# ---------- ARKIV-FUNKTIONER ----------

def gem_i_arkiv(
    titel,
    type_,
    indhold,
    klage_filnavn=None,
    spoergsmaal=None,
    sagsakter=None,
    ekstra_instrukser=None,
):
    """
    Gemmer en analyse eller et svarbrev i arkiv-tabellen.
    type_ skal være enten 'analyse' eller 'svarbrev'.
    Returnerer id på den nye række, eller None ved fejl.
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO analyse_arkiv
              (titel, type, klage_filnavn, spoergsmaal, sagsakter,
               ekstra_instrukser, indhold)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (titel, type_, klage_filnavn, spoergsmaal, sagsakter,
             ekstra_instrukser, indhold),
        )
        ny_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return ny_id
    except Exception as e:
        print(f"DEBUG: Kunne ikke gemme i arkiv: {e}")
        return None


def hent_arkiv(begraens=50):
    """
    Henter de seneste arkiv-indgange sorteret efter dato (nyeste først).
    Returnerer liste af dicts.
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, titel, type, klage_filnavn, spoergsmaal,
                   oprettet_dato, indhold, sagsakter, ekstra_instrukser
            FROM analyse_arkiv
            ORDER BY oprettet_dato DESC
            LIMIT %s
            """,
            (begraens,),
        )
        raekker = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "id": r[0],
                "titel": r[1],
                "type": r[2],
                "klage_filnavn": r[3],
                "spoergsmaal": r[4],
                "oprettet_dato": r[5],
                "indhold": r[6],
                "sagsakter": r[7],
                "ekstra_instrukser": r[8],
            }
            for r in raekker
        ]
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente arkiv: {e}")
        return []


def slet_arkiv_entry(entry_id):
    """Sletter en arkiv-indgang. Bruges hvis juristen vil rydde op."""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM analyse_arkiv WHERE id = %s", (entry_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"DEBUG: Kunne ikke slette arkiv-indgang: {e}")
        return False


# ---------- GEMTE SAGER ----------

def gem_sag_state(titel, state_json, user_id=None, sag_id=None):
    """
    Gemmer hele sagens state som JSON i gemte_sager-tabellen.
    Hvis sag_id er angivet, opdateres en eksisterende række.
    Ellers oprettes en ny.
    Returnerer id'et på rækken.
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        if sag_id is not None:
            cur.execute(
                "UPDATE gemte_sager SET titel=%s, state_json=%s, "
                "opdateret_dato=CURRENT_TIMESTAMP WHERE id=%s RETURNING id",
                (titel, state_json, sag_id),
            )
            row = cur.fetchone()
            ny_id = row[0] if row else None
        else:
            cur.execute(
                "INSERT INTO gemte_sager (user_id, titel, state_json) "
                "VALUES (%s, %s, %s) RETURNING id",
                (user_id, titel, state_json),
            )
            ny_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return ny_id
    except Exception as e:
        print(f"DEBUG: Kunne ikke gemme sag-state: {e}")
        return None


def hent_gemte_sager(user_id=None, begraens=50):
    """
    Returnerer listen af gemte sager sorteret efter opdateringsdato.
    Hvis user_id=None returneres alle (til simpel brug indtil login indføres).
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        if user_id is None:
            cur.execute(
                "SELECT id, titel, oprettet_dato, opdateret_dato "
                "FROM gemte_sager ORDER BY opdateret_dato DESC LIMIT %s",
                (begraens,),
            )
        else:
            cur.execute(
                "SELECT id, titel, oprettet_dato, opdateret_dato "
                "FROM gemte_sager WHERE user_id=%s "
                "ORDER BY opdateret_dato DESC LIMIT %s",
                (user_id, begraens),
            )
        raekker = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "id": r[0],
                "titel": r[1],
                "oprettet_dato": r[2],
                "opdateret_dato": r[3],
            }
            for r in raekker
        ]
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente gemte sager: {e}")
        return []


def hent_gemt_sag(sag_id):
    """Returnerer en gemt sag inklusive dens state-JSON, eller None."""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, titel, state_json, oprettet_dato, opdateret_dato "
            "FROM gemte_sager WHERE id=%s",
            (sag_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "titel": row[1],
            "state_json": row[2],
            "oprettet_dato": row[3],
            "opdateret_dato": row[4],
        }
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente gemt sag: {e}")
        return None


def slet_gemt_sag(sag_id):
    """Sletter en gemt sag permanent."""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM gemte_sager WHERE id=%s", (sag_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"DEBUG: Kunne ikke slette gemt sag: {e}")
        return False


# ---------- RAG-SØGNING ----------

def soeg_i_arkiv(stikord=None, dokumenttype=None, begraens=50):
    """
    Stikordssøgning i vidensbanken.
    - stikord: hvis angivet, filtreres der på tekstindhold (ILIKE match)
    - dokumenttype: 'afgoerelse' / 'klage' / 'vilkaar' eller None for alle
    - begraens: max antal resultater

    Returnerer liste af dicts med fil-metadata + indhold.
    """
    try:
        conn = _connect()
        cur = conn.cursor()

        where = []
        params = []
        if stikord and stikord.strip():
            # Split på mellemrum og kræv at alle ord forekommer (case-insensitive)
            ord_liste = [o.strip() for o in stikord.split() if o.strip()]
            for ord_ in ord_liste:
                where.append("indhold ILIKE %s")
                params.append(f"%{ord_}%")
        if dokumenttype:
            where.append("dokumenttype = %s")
            params.append(dokumenttype)

        where_klausul = (" WHERE " + " AND ".join(where)) if where else ""
        params.append(begraens)

        sql = f"""
            SELECT filnavn, indhold, oprettet_dato, dokumenttype, kilde_url
            FROM mine_dokumenter
            {where_klausul}
            ORDER BY oprettet_dato DESC
            LIMIT %s
        """
        cur.execute(sql, params)
        raekker = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "filnavn": r[0],
                "indhold": r[1],
                "oprettet_dato": r[2],
                "dokumenttype": r[3] or "afgoerelse",
                "kilde_url": r[4],
            }
            for r in raekker
        ]
    except Exception as e:
        print(f"DEBUG: Kunne ikke søge i arkiv: {e}")
        return []


def find_relevante_sager(
    sporgsmaal_embedding,
    top_k=5,
    udeluk_filnavn=None,
    dokumenttype=None,
):
    """
    Kernen i RAG: find de top_k mest relevante sager via cosine similarity.

    sporgsmaal_embedding: 1024-dim liste genereret af embeddings.embed_sporgsmaal().
    top_k: antal sager der returneres (default 5).
    udeluk_filnavn: hvis angivet, udelades denne sag (bruges så en klage der
                    er gemt automatisk ikke citerer sig selv).
    dokumenttype: hvis angivet, begrænses søgningen til denne type
                  ('afgoerelse', 'klage', 'vilkaar'). Default = alle.

    I pgvector betyder '<=>' cosine-distance (0 = identisk, 2 = modsat).
    Vi sorterer ASC så de mest relevante kommer først, og returnerer også
    similarity-scoren (1 - distance) så vi kan vise den i UI'en hvis ønsket.
    """
    if sporgsmaal_embedding is None:
        return []

    try:
        conn = _connect()
        cur = conn.cursor()

        # Byg WHERE-klausulen dynamisk
        where = ["embedding IS NOT NULL"]
        params = [sporgsmaal_embedding]
        if udeluk_filnavn:
            where.append("filnavn <> %s")
            params.append(udeluk_filnavn)
        if dokumenttype:
            where.append("dokumenttype = %s")
            params.append(dokumenttype)
        params.append(sporgsmaal_embedding)
        params.append(top_k)

        sql = f"""
            SELECT filnavn, indhold, oprettet_dato, dokumenttype, kilde_url,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM mine_dokumenter
            WHERE {' AND '.join(where)}
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s
        """
        cur.execute(sql, params)
        raekker = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "filnavn": r[0],
                "indhold": r[1],
                "oprettet_dato": r[2],
                "dokumenttype": r[3] or "afgoerelse",
                "kilde_url": r[4],
                "similarity": float(r[5]) if r[5] is not None else None,
            }
            for r in raekker
        ]
    except Exception as e:
        print(f"DEBUG: Kunne ikke finde relevante sager: {e}")
        return []
