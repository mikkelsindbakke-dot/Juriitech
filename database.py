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

        # 5b. Chunks-tabel: hver afgørelse splittes i 5-15 paragraf-chunks
        #     der hver embeddes for sig. Det giver markant bedre RAG-præcision
        #     end at embedde et helt 30-siders dokument til én vektor.
        #     dokument_id = FK til mine_dokumenter.id (CASCADE delete så
        #     chunks ryger med hvis dokumentet slettes).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dokument_chunks (
                id SERIAL PRIMARY KEY,
                dokument_id INTEGER NOT NULL REFERENCES mine_dokumenter(id)
                    ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                overskrift TEXT,
                indhold TEXT NOT NULL,
                embedding vector(1024),
                oprettet_dato TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (dokument_id, chunk_index)
            )
        """)

        # 5c. HNSW-indeks på chunk-embeddings — kritisk for hurtig søgning
        try:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_dokument_chunks_embedding
                ON dokument_chunks
                USING hnsw (embedding vector_cosine_ops)
            """)
        except Exception as idx_err:
            print(f"DEBUG: HNSW-indeks for chunks kunne ikke oprettes (ikke kritisk): {idx_err}")
            conn.rollback()

        # 5d. Indeks til hurtig "find chunks for dokument" og keyword-søgning
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_dokument_chunks_dokument_id
            ON dokument_chunks (dokument_id)
        """)

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


# ---------- CHUNKS-FUNKTIONER (forbedret RAG) ----------

def hent_dokument_indhold(filnavn):
    """
    Henter den FULDE indhold-tekst for et dokument via filnavn.
    Bruges af regex-fallbacks når vi ellers kun har en chunk og
    har brug for at scanne hele afgørelsen (fx for at finde beløb
    der står i sektioner som chunken ikke indeholdt).

    Returnerer indhold som streng, eller tom streng hvis ikke fundet.
    """
    if not filnavn:
        return ""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT indhold FROM mine_dokumenter WHERE filnavn = %s LIMIT 1",
            (filnavn,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row and row[0] else ""
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente dokument-indhold for {filnavn}: {e}")
        return ""


def hent_dokument_id_fra_filnavn(filnavn):
    """Slår dokument-id op fra filnavn. Bruges af backfill-scriptet."""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM mine_dokumenter WHERE filnavn = %s LIMIT 1",
            (filnavn,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente dokument-id for {filnavn}: {e}")
        return None


def hent_dokumenter_uden_chunks(dokumenttype="afgoerelse"):
    """
    Returnerer alle dokumenter af en given type der ENDNU IKKE har
    chunks i dokument_chunks-tabellen. Bruges af backfill-scriptet
    så det er idempotent — kør det igen og igen, kun nye dokumenter
    bliver chunked.
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.id, m.filnavn, m.indhold
            FROM mine_dokumenter m
            LEFT JOIN dokument_chunks c ON c.dokument_id = m.id
            WHERE m.dokumenttype = %s
              AND c.id IS NULL
            ORDER BY m.id ASC
            """,
            (dokumenttype,),
        )
        raekker = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {"id": r[0], "filnavn": r[1], "indhold": r[2]}
            for r in raekker
        ]
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente dokumenter uden chunks: {e}")
        return []


def gem_chunks_for_dokument(dokument_id, chunks_med_embeddings):
    """
    Gemmer (eller erstatter) alle chunks for et dokument.
    chunks_med_embeddings er en liste af dicts:
        [{"chunk_index": int, "overskrift": str, "indhold": str,
          "embedding": list[float] | None}, ...]

    Sletter først eksisterende chunks for dokumentet, så funktionen
    kan re-køres uden duplikater (fx hvis chunking-strategien ændres).
    """
    if not chunks_med_embeddings:
        return 0
    try:
        conn = _connect()
        cur = conn.cursor()
        # Slet eksisterende chunks så vi kan re-køre uden duplikater
        cur.execute(
            "DELETE FROM dokument_chunks WHERE dokument_id = %s",
            (dokument_id,),
        )
        # Indsæt nye chunks
        antal_indsat = 0
        for c in chunks_med_embeddings:
            cur.execute(
                """
                INSERT INTO dokument_chunks
                  (dokument_id, chunk_index, overskrift, indhold, embedding)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    dokument_id,
                    c.get("chunk_index", 0),
                    c.get("overskrift") or "",
                    c.get("indhold") or "",
                    c.get("embedding"),
                ),
            )
            antal_indsat += 1
        conn.commit()
        cur.close()
        conn.close()
        return antal_indsat
    except Exception as e:
        print(f"DEBUG: Kunne ikke gemme chunks for dokument {dokument_id}: {e}")
        return 0


def antal_chunks_total():
    """Returnerer total antal chunks i databasen — bruges af diagnostik."""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dokument_chunks")
        antal = cur.fetchone()[0]
        cur.close()
        conn.close()
        return antal
    except Exception:
        return 0


def find_relevante_chunks(
    sporgsmaal_embedding,
    top_k=30,
    udeluk_dokument_id=None,
    dokumenttype="afgoerelse",
):
    """
    Chunk-baseret RAG-søgning. Returnerer de top_k mest relevante
    CHUNKS via cosine similarity, sammen med deres parent-dokument-
    metadata (filnavn, dato, kilde_url).

    Default top_k=30 fordi vi forventer at reranker'en skærer ned
    til 5-8 bagefter. Bedre at få mange kandidater til reranker'en.

    udeluk_dokument_id: hvis angivet, springes alle chunks fra det
                       dokument over (bruges så en klage der er
                       gemt automatisk ikke citerer sig selv).
    dokumenttype: filtrerer på parent-dokumentets type. Default
                  'afgoerelse' fordi chunking kun giver mening for
                  dem (vilkår + lovgivning er korte og bruges som hele
                  dokumenter).
    """
    if sporgsmaal_embedding is None:
        return []

    try:
        conn = _connect()
        cur = conn.cursor()

        where = [
            "c.embedding IS NOT NULL",
            "m.dokumenttype = %s",
        ]
        params = [dokumenttype, sporgsmaal_embedding]
        if udeluk_dokument_id:
            where.append("c.dokument_id <> %s")
            params.append(udeluk_dokument_id)
        params.append(sporgsmaal_embedding)
        params.append(top_k)

        sql = f"""
            SELECT
                c.id AS chunk_id,
                c.dokument_id,
                c.chunk_index,
                c.overskrift,
                c.indhold,
                m.filnavn,
                m.oprettet_dato,
                m.kilde_url,
                m.dokumenttype,
                1 - (c.embedding <=> %s::vector) AS similarity
            FROM dokument_chunks c
            JOIN mine_dokumenter m ON m.id = c.dokument_id
            WHERE {' AND '.join(where)}
            ORDER BY c.embedding <=> %s::vector ASC
            LIMIT %s
        """
        cur.execute(sql, params)
        raekker = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "chunk_id": r[0],
                "dokument_id": r[1],
                "chunk_index": r[2],
                "overskrift": r[3] or "",
                "indhold": r[4] or "",
                "filnavn": r[5],
                "oprettet_dato": r[6],
                "kilde_url": r[7],
                "dokumenttype": r[8] or "afgoerelse",
                "similarity": float(r[9]) if r[9] is not None else None,
            }
            for r in raekker
        ]
    except Exception as e:
        print(f"DEBUG: Kunne ikke finde relevante chunks: {e}")
        return []


def soeg_chunks_keyword(stikord, top_k=30, dokumenttype="afgoerelse"):
    """
    Stikord/keyword-søgning på chunks (ILIKE). Bruges til hybrid søgning
    sammen med find_relevante_chunks: keyword-resultater fanger sager
    hvor en specifik frase matcher næsten eksakt, men hvor embedding-
    similarity måske ikke ranglister højt nok.

    Returnerer samme dict-struktur som find_relevante_chunks (uden
    similarity-feltet — vi kan ikke sammenligne BM25-rank direkte med
    cosine).
    """
    if not stikord or not stikord.strip():
        return []
    try:
        conn = _connect()
        cur = conn.cursor()

        # Split på mellemrum og kræv at alle ord forekommer i samme chunk
        ord_liste = [o.strip() for o in stikord.split() if len(o.strip()) > 2]
        if not ord_liste:
            return []

        where = ["m.dokumenttype = %s"]
        params = [dokumenttype]
        for ord_ in ord_liste:
            where.append("c.indhold ILIKE %s")
            params.append(f"%{ord_}%")
        params.append(top_k)

        sql = f"""
            SELECT
                c.id AS chunk_id,
                c.dokument_id,
                c.chunk_index,
                c.overskrift,
                c.indhold,
                m.filnavn,
                m.oprettet_dato,
                m.kilde_url,
                m.dokumenttype
            FROM dokument_chunks c
            JOIN mine_dokumenter m ON m.id = c.dokument_id
            WHERE {' AND '.join(where)}
            ORDER BY m.oprettet_dato DESC
            LIMIT %s
        """
        cur.execute(sql, params)
        raekker = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "chunk_id": r[0],
                "dokument_id": r[1],
                "chunk_index": r[2],
                "overskrift": r[3] or "",
                "indhold": r[4] or "",
                "filnavn": r[5],
                "oprettet_dato": r[6],
                "kilde_url": r[7],
                "dokumenttype": r[8] or "afgoerelse",
                "similarity": None,  # ikke comparable med vector-similarity
            }
            for r in raekker
        ]
    except Exception as e:
        print(f"DEBUG: Kunne ikke keyword-søge chunks: {e}")
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
