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

        # ═════════════════════════════════════════════════════════════
        # B1: MULTI-TENANT TABELLER
        # ═════════════════════════════════════════════════════════════
        # Phase B af multi-tenant rollout. Disse to tabeller + tenant_id-
        # kolonnerne nedenfor er fundamentet for at hver kunde-organisation
        # (TUI, Spies, Apollo osv.) ser KUN deres egne sager og analyser.
        #
        # Sikkerhedsprincip: Alle queries der rør private data SKAL
        # filtrere på tenant_id. Public data (Pakkerejse-Ankenævn-
        # afgørelser, lovgivning) markeres med is_public=TRUE og er
        # synlige for alle tenants som juridisk præcedens.

        # 8. tenants — én række per kunde-organisation
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id SERIAL PRIMARY KEY,
                slug TEXT UNIQUE NOT NULL,
                navn TEXT NOT NULL,
                sagsbehandler TEXT,
                by TEXT,
                logo_filnavn TEXT,
                anonymisering_suffix TEXT,
                interne_team_navne TEXT,
                klageorgan_navn TEXT DEFAULT 'Pakkerejse-Ankenævnet',
                klageorgan_url TEXT DEFAULT 'https://www.pakkerejseankenaevnet.dk',
                rejsevilkaar_kilde_url TEXT,
                sprog TEXT DEFAULT 'da',
                land TEXT DEFAULT 'DK',
                lov_navn TEXT DEFAULT 'Pakkerejseloven',
                oprettet_dato TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 9. users — én række per autentificeret bruger
        # supabase_user_id er UUID'en fra Supabase Auth (vi bruger Supabase
        # som auth-leverandør i B2). Vi gemmer ikke password — det er
        # Supabase's ansvar.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                supabase_user_id UUID UNIQUE,
                tenant_id INTEGER NOT NULL REFERENCES tenants(id)
                    ON DELETE RESTRICT,
                email TEXT NOT NULL UNIQUE,
                fulde_navn TEXT,
                role TEXT NOT NULL DEFAULT 'jurist'
                    CHECK (role IN ('admin', 'jurist')),
                oprettet_dato TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_supabase_id
            ON users (supabase_user_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_tenant_id
            ON users (tenant_id)
        """)

        # 10. tenant_id + is_public på eksisterende tabeller
        # mine_dokumenter: tenant_id kan være NULL for offentlige dokumenter
        # (Ankenævn-afgørelser, lovgivning). is_public=TRUE gør dokumentet
        # synligt for alle tenants.
        cur.execute("""
            ALTER TABLE mine_dokumenter
            ADD COLUMN IF NOT EXISTS tenant_id INTEGER
                REFERENCES tenants(id) ON DELETE RESTRICT
        """)
        cur.execute("""
            ALTER TABLE mine_dokumenter
            ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mine_dokumenter_tenant_id
            ON mine_dokumenter (tenant_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mine_dokumenter_is_public
            ON mine_dokumenter (is_public)
            WHERE is_public = TRUE
        """)

        # analyse_arkiv: tenant_id altid sat (analyser er ALTID private)
        cur.execute("""
            ALTER TABLE analyse_arkiv
            ADD COLUMN IF NOT EXISTS tenant_id INTEGER
                REFERENCES tenants(id) ON DELETE RESTRICT
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyse_arkiv_tenant_id
            ON analyse_arkiv (tenant_id)
        """)

        # gemte_sager: tenant_id altid sat (sag-state er ALTID private)
        cur.execute("""
            ALTER TABLE gemte_sager
            ADD COLUMN IF NOT EXISTS tenant_id INTEGER
                REFERENCES tenants(id) ON DELETE RESTRICT
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gemte_sager_tenant_id
            ON gemte_sager (tenant_id)
        """)

        conn.commit()
        cur.close()
        conn.close()
        print("DEBUG: Databaseforbindelse oprettet succesfuldt!")
    except Exception as e:
        print(f"DEBUG: Fejl ved oprettelse af tabel: {e}")


# ═══════════════════════════════════════════════════════════════
# TENANT + USER CRUD (Phase B1)
# ═══════════════════════════════════════════════════════════════
# Disse funktioner er fundamentet for multi-tenant. Tenants oprettes
# typisk én gang via admin-siden (Phase B4). Users oprettes når en
# kunde inviteres via Supabase magic-link og registrerer sig (Phase B2).

def hent_alle_tenants():
    """Returnerer alle tenants som liste af dicts. Bruges i admin-UI."""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, slug, navn, sagsbehandler, by, logo_filnavn, "
            "anonymisering_suffix, interne_team_navne, klageorgan_navn, "
            "klageorgan_url, rejsevilkaar_kilde_url, sprog, land, "
            "lov_navn, oprettet_dato "
            "FROM tenants ORDER BY navn ASC"
        )
        raekker = cur.fetchall()
        cur.close()
        conn.close()
        return [_row_to_tenant_dict(r) for r in raekker]
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente tenants: {e}")
        return []


def hent_tenant_by_id(tenant_id):
    """Slå tenant op på id. Returnerer dict eller None."""
    if tenant_id is None:
        return None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, slug, navn, sagsbehandler, by, logo_filnavn, "
            "anonymisering_suffix, interne_team_navne, klageorgan_navn, "
            "klageorgan_url, rejsevilkaar_kilde_url, sprog, land, "
            "lov_navn, oprettet_dato "
            "FROM tenants WHERE id = %s",
            (int(tenant_id),),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return _row_to_tenant_dict(row) if row else None
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente tenant {tenant_id}: {e}")
        return None


def hent_tenant_by_slug(slug):
    """
    Slå tenant op på slug ('tui', 'spies', 'apollo'). Returnerer dict
    eller None. Bruges af selskab_profiler.py som primær lookup.
    """
    if not slug:
        return None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, slug, navn, sagsbehandler, by, logo_filnavn, "
            "anonymisering_suffix, interne_team_navne, klageorgan_navn, "
            "klageorgan_url, rejsevilkaar_kilde_url, sprog, land, "
            "lov_navn, oprettet_dato "
            "FROM tenants WHERE slug = %s",
            (slug,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return _row_to_tenant_dict(row) if row else None
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente tenant {slug}: {e}")
        return None


def opret_tenant(
    slug, navn, sagsbehandler=None, by=None, logo_filnavn=None,
    anonymisering_suffix=None, interne_team_navne=None,
    klageorgan_navn="Pakkerejse-Ankenævnet",
    klageorgan_url="https://www.pakkerejseankenaevnet.dk",
    rejsevilkaar_kilde_url=None, sprog="da", land="DK",
    lov_navn="Pakkerejseloven",
):
    """
    Opretter en ny tenant. interne_team_navne er en liste — gemmes
    som JSON-string i DB. Returnerer den nye tenant's id, eller None
    ved fejl (fx hvis slug allerede findes).
    """
    import json as _json
    try:
        conn = _connect()
        cur = conn.cursor()
        team_json = _json.dumps(interne_team_navne or [])
        cur.execute(
            """
            INSERT INTO tenants
              (slug, navn, sagsbehandler, by, logo_filnavn,
               anonymisering_suffix, interne_team_navne,
               klageorgan_navn, klageorgan_url, rejsevilkaar_kilde_url,
               sprog, land, lov_navn)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                slug, navn, sagsbehandler or navn, by or "",
                logo_filnavn or "",
                anonymisering_suffix or navn, team_json,
                klageorgan_navn, klageorgan_url,
                rejsevilkaar_kilde_url or "",
                sprog, land, lov_navn,
            ),
        )
        ny_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return ny_id
    except Exception as e:
        print(f"DEBUG: Kunne ikke oprette tenant {slug}: {e}")
        return None


def opdater_tenant(tenant_id, **felter):
    """
    Opdaterer specifikke felter på en tenant. Tager keyword arguments
    der svarer til kolonne-navne. interne_team_navne accepteres som liste
    og gemmes som JSON.
    """
    import json as _json
    if not felter:
        return True
    tilladt = {
        "navn", "sagsbehandler", "by", "logo_filnavn",
        "anonymisering_suffix", "interne_team_navne",
        "klageorgan_navn", "klageorgan_url",
        "rejsevilkaar_kilde_url", "sprog", "land", "lov_navn",
    }
    sat_dele = []
    params = []
    for nøgle, værdi in felter.items():
        if nøgle not in tilladt:
            continue
        if nøgle == "interne_team_navne" and isinstance(værdi, (list, tuple)):
            værdi = _json.dumps(list(værdi))
        sat_dele.append(f"{nøgle} = %s")
        params.append(værdi)
    if not sat_dele:
        return True
    params.append(int(tenant_id))
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE tenants SET {', '.join(sat_dele)} WHERE id = %s",
            params,
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"DEBUG: Kunne ikke opdatere tenant {tenant_id}: {e}")
        return False


def _row_to_tenant_dict(row):
    """Konverterer en tenant-row fra SELECT til dict, med team_navne parsed."""
    if not row:
        return None
    import json as _json
    try:
        team_navne = _json.loads(row[7]) if row[7] else []
    except Exception:
        team_navne = []
    return {
        "id": row[0],
        "slug": row[1],
        "navn": row[2],
        "sagsbehandler": row[3] or row[2],  # default til navn
        "by": row[4] or "",
        "logo_filnavn": row[5] or "",
        "anonymisering_suffix": row[6] or row[2],  # default til navn
        "interne_team_navne": team_navne,
        "klageorgan_navn": row[8] or "Pakkerejse-Ankenævnet",
        "klageorgan_url": row[9] or "",
        "rejsevilkaar_kilde_url": row[10] or "",
        "sprog": row[11] or "da",
        "land": row[12] or "DK",
        "lov_navn": row[13] or "Pakkerejseloven",
        "oprettet_dato": row[14],
    }


# ─── USERS ───

def hent_user_by_supabase_id(supabase_user_id):
    """
    Slå en bruger op på Supabase Auth UUID. Returnerer dict med
    user_id + tenant_id + role + email + fulde_navn, eller None.
    Bruges efter login til at hente den autentificerede brugers tenant.
    """
    if not supabase_user_id:
        return None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, supabase_user_id, tenant_id, email, fulde_navn, "
            "role, oprettet_dato FROM users WHERE supabase_user_id = %s",
            (str(supabase_user_id),),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "supabase_user_id": str(row[1]),
            "tenant_id": row[2],
            "email": row[3],
            "fulde_navn": row[4] or "",
            "role": row[5],
            "oprettet_dato": row[6],
        }
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente user {supabase_user_id}: {e}")
        return None


def hent_user_by_email(email):
    """Slå bruger op på email (bruges af admin-side til at se eksisterende invitationer)."""
    if not email:
        return None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, supabase_user_id, tenant_id, email, fulde_navn, "
            "role, oprettet_dato FROM users WHERE email = %s",
            (email.lower().strip(),),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "supabase_user_id": str(row[1]) if row[1] else None,
            "tenant_id": row[2],
            "email": row[3],
            "fulde_navn": row[4] or "",
            "role": row[5],
            "oprettet_dato": row[6],
        }
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente user {email}: {e}")
        return None


def opret_user(email, tenant_id, role="jurist", fulde_navn=None,
               supabase_user_id=None):
    """
    Opretter en bruger. Kaldes typisk i to situationer:
    (1) Admin inviterer en ny bruger — opret række UDEN supabase_user_id
        (sættes når brugeren rent faktisk registrerer sig via magic-link).
    (2) Bruger registrerer sig — supabase_user_id sættes til Auth-UUID.

    Returnerer det nye user-id eller None ved fejl.
    """
    if not email:
        return None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users
              (email, tenant_id, role, fulde_navn, supabase_user_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                email.lower().strip(),
                int(tenant_id),
                role,
                fulde_navn or "",
                str(supabase_user_id) if supabase_user_id else None,
            ),
        )
        ny_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return ny_id
    except Exception as e:
        print(f"DEBUG: Kunne ikke oprette user {email}: {e}")
        return None


def opdater_user_supabase_id(user_id, supabase_user_id):
    """
    Sætter supabase_user_id på en eksisterende bruger-række. Bruges når
    en inviteret bruger registrerer sig via magic-link og vi får deres
    UUID fra Supabase Auth.
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET supabase_user_id = %s WHERE id = %s",
            (str(supabase_user_id), int(user_id)),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"DEBUG: Kunne ikke opdatere user {user_id}: {e}")
        return False


def hent_users_for_tenant(tenant_id):
    """Returnerer alle brugere for en tenant (admin-side)."""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, supabase_user_id, tenant_id, email, fulde_navn, "
            "role, oprettet_dato FROM users WHERE tenant_id = %s "
            "ORDER BY oprettet_dato DESC",
            (int(tenant_id),),
        )
        raekker = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "id": r[0],
                "supabase_user_id": str(r[1]) if r[1] else None,
                "tenant_id": r[2],
                "email": r[3],
                "fulde_navn": r[4] or "",
                "role": r[5],
                "oprettet_dato": r[6],
            }
            for r in raekker
        ]
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente users for tenant {tenant_id}: {e}")
        return []


# ─── AKTIV TENANT ───
# Denne helper er hjertet af multi-tenant lookup. I B1 returnerer den
# bare TUI's id (hardcoded fallback), så systemet opfører sig præcis
# som før. I B3 (efter login) udvides den til at læse fra
# st.session_state.user.tenant_id.

def hent_aktiv_tenant_id():
    """
    Returnerer id'et på den aktuelle aktive tenant.

    Lookup-rækkefølge:
      1. Streamlit session: st.session_state.user.tenant_id (efter login)
      2. Fallback: TUI's id (hardcoded — bruges i scripts/backfills hvor
         der ikke er en logged-in user, fx migration_b1_tenants.py).

    I Streamlit-kontekst BØR fallback'en aldrig ramme — auth-gate i
    app.py forhindrer ikke-loggede brugere i at nå queries. Hvis
    fallback rammes mens Streamlit kører, er det et tegn på en bug
    (auth-gate er omgået, eller user-objektet i session er korrupt).
    Vi printer en WARNING så det opdages tidligt.
    """
    # Lazy import for at undgå at Streamlit-import sker når database.py
    # bruges fra ikke-Streamlit kontekst (fx backfill-scripts).
    streamlit_aktiv = False
    try:
        import streamlit as st
        # Tjek om vi faktisk kører inde i en Streamlit-runtime — ikke
        # bare har streamlit installeret som package.
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            streamlit_aktiv = get_script_run_ctx() is not None
        except Exception:
            streamlit_aktiv = False

        user = st.session_state.get("user")
        if user and user.get("tenant_id"):
            return int(user["tenant_id"])
    except Exception:
        pass

    # Fallback: TUI som default
    if streamlit_aktiv:
        # Bekymrende: vi kører i Streamlit men ingen user — auth-gate
        # er omgået, eller session er tom på et sted hvor den ikke burde.
        print(
            "WARNING: hent_aktiv_tenant_id() faldt tilbage til TUI under "
            "Streamlit-session — auth-gate kan være omgået eller session.user "
            "er tom uventet. Tjek at app.py's auth-check kører før queries."
        )

    tui = hent_tenant_by_slug("tui")
    return tui["id"] if tui else None


def gem_sag_i_db(filnavn, tekst, dokumenttype="afgoerelse", embedding=None,
                 kilde_url=None, tenant_id=None, is_public=None):
    """
    Gemmer en sag i databasen.
    dokumenttype skal være enten 'afgoerelse' (tidligere kendelse), 'klage'
    (indkommen klage, endnu ikke afgjort), 'vilkaar', 'lovgivning' eller
    'anonymisering_regler'.

    embedding er valgfri — hvis den er None, gemmes sagen uden, og
    backfill_embeddings() kan fylde den på bagefter.

    kilde_url er valgfri — bruges af scraperen til at spore hvor sagen kom fra
    og undgå dubletter på næste kørsel.

    tenant_id og is_public bestemmer hvem der kan se dokumentet:
      - is_public=True (typisk afgoerelse, lovgivning, anonymisering_regler):
        synlig for alle tenants. tenant_id bør være None.
      - tenant_id sat (typisk klage, vilkaar): kun synlig for den tenant.
        Bruger hent_aktiv_tenant_id() som default hvis intet er angivet.
    """
    # Defaults: hvis ikke specificeret, så afgør baseret på dokumenttype
    if tenant_id is None and is_public is None:
        if dokumenttype in ("afgoerelse", "lovgivning", "anonymisering_regler"):
            is_public = True
        else:
            tenant_id = hent_aktiv_tenant_id()
            is_public = False
    elif is_public is None:
        is_public = False

    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO mine_dokumenter "
            "(filnavn, indhold, dokumenttype, embedding, kilde_url, "
            " tenant_id, is_public) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (filnavn, tekst, dokumenttype, embedding, kilde_url,
             tenant_id, bool(is_public)),
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


def hent_alle_sager(tenant_id=None):
    """
    Returnerer alle sager der er synlige for den aktive tenant:
    public docs (is_public=TRUE) PLUS tenant-private docs.

    tenant_id default = aktiv tenant (TUI i B1, logged-in bruger i B3).
    Sættes til 0 eller negativ for kun at få public docs.
    """
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT filnavn, indhold, oprettet_dato, dokumenttype "
            "FROM mine_dokumenter "
            "WHERE is_public = TRUE OR tenant_id = %s "
            "ORDER BY oprettet_dato DESC",
            (tenant_id,),
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


def hent_sager_af_type(dokumenttype, limit=None, tenant_id=None):
    """
    Returnerer alle dokumenter af en given dokumenttype, filtreret så
    man kun ser public docs + den aktive tenant's private docs.

    Bruges bl.a. til at hente ALLE anonymiseringsregler som fast kontekst
    til anonymiseringsopgaver (i modsætning til RAG-baseret topp-k-søgning).
    """
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()
    try:
        conn = _connect()
        cur = conn.cursor()
        base_sql = (
            "SELECT filnavn, indhold, kilde_url FROM mine_dokumenter "
            "WHERE dokumenttype = %s "
            "AND (is_public = TRUE OR tenant_id = %s) "
            "ORDER BY filnavn ASC"
        )
        if limit is not None:
            cur.execute(base_sql + " LIMIT %s",
                        (dokumenttype, tenant_id, int(limit)))
        else:
            cur.execute(base_sql, (dokumenttype, tenant_id))
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
    tenant_id=None,
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
    tenant_id: tenant-isolation. Default = aktiv tenant. Returnerer
               public docs (Ankenævn-afgørelser) PLUS denne tenant's
               private docs.
    """
    if sporgsmaal_embedding is None:
        return []
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()

    try:
        conn = _connect()
        cur = conn.cursor()

        where = [
            "c.embedding IS NOT NULL",
            "m.dokumenttype = %s",
            "(m.is_public = TRUE OR m.tenant_id = %s)",
        ]
        # Params i SAMME rækkefølge som %s-placeholderne i SQL'en:
        #   1. SELECT vector for similarity
        #   2. WHERE dokumenttype
        #   3. WHERE tenant_id
        #   4. (optional) WHERE udeluk_dokument_id
        #   5. ORDER BY vector
        #   6. LIMIT
        # OBS: tidligere version havde ordering-bug der betød at chunk-
        # pipelinen returnerede [] silently og altid faldt tilbage til
        # hele-dokument-RAG. Det er fixet her.
        params = [sporgsmaal_embedding, dokumenttype, tenant_id]
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


def soeg_chunks_keyword(stikord, top_k=30, dokumenttype="afgoerelse",
                        tenant_id=None):
    """
    Stikord/keyword-søgning på chunks (ILIKE). Bruges til hybrid søgning
    sammen med find_relevante_chunks: keyword-resultater fanger sager
    hvor en specifik frase matcher næsten eksakt, men hvor embedding-
    similarity måske ikke ranglister højt nok.

    tenant_id: tenant-isolation. Default = aktiv tenant. Returnerer
               public docs PLUS denne tenant's private docs.

    Returnerer samme dict-struktur som find_relevante_chunks (uden
    similarity-feltet — vi kan ikke sammenligne BM25-rank direkte med
    cosine).
    """
    if not stikord or not stikord.strip():
        return []
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()
    try:
        conn = _connect()
        cur = conn.cursor()

        # Split på mellemrum og kræv at alle ord forekommer i samme chunk
        ord_liste = [o.strip() for o in stikord.split() if len(o.strip()) > 2]
        if not ord_liste:
            return []

        where = [
            "m.dokumenttype = %s",
            "(m.is_public = TRUE OR m.tenant_id = %s)",
        ]
        params = [dokumenttype, tenant_id]
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
    tenant_id=None,
):
    """
    Gemmer en analyse eller et svarbrev i arkiv-tabellen.
    type_ skal være enten 'analyse' eller 'svarbrev'.
    tenant_id default = aktiv tenant. Hvis None og ingen aktiv tenant,
    returneres None (vi nægter at gemme uden tenant for at forhindre
    "orphan" arkiv-indgange).
    Returnerer id på den nye række, eller None ved fejl.
    """
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()
    if not tenant_id:
        print("DEBUG: gem_i_arkiv afvist — ingen tenant_id (krævet)")
        return None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO analyse_arkiv
              (titel, type, klage_filnavn, spoergsmaal, sagsakter,
               ekstra_instrukser, indhold, tenant_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (titel, type_, klage_filnavn, spoergsmaal, sagsakter,
             ekstra_instrukser, indhold, tenant_id),
        )
        ny_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return ny_id
    except Exception as e:
        print(f"DEBUG: Kunne ikke gemme i arkiv: {e}")
        return None


def hent_arkiv(begraens=50, tenant_id=None):
    """
    Henter de seneste arkiv-indgange sorteret efter dato (nyeste først).
    Filtreres ALTID på tenant_id — arkiv-indgange er per definition
    private. Returnerer liste af dicts.
    """
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()
    if not tenant_id:
        return []
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, titel, type, klage_filnavn, spoergsmaal,
                   oprettet_dato, indhold, sagsakter, ekstra_instrukser
            FROM analyse_arkiv
            WHERE tenant_id = %s
            ORDER BY oprettet_dato DESC
            LIMIT %s
            """,
            (tenant_id, begraens),
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


def slet_arkiv_entry(entry_id, tenant_id=None):
    """
    Sletter en arkiv-indgang — KUN hvis den tilhører den aktive tenant.
    Returnerer True hvis sletning lykkedes; False hvis entry_id ikke
    findes ELLER tilhører en anden tenant.
    """
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()
    if not tenant_id:
        return False
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM analyse_arkiv WHERE id = %s AND tenant_id = %s",
            (entry_id, tenant_id),
        )
        slettet = cur.rowcount > 0
        conn.commit()
        cur.close()
        conn.close()
        return slettet
    except Exception as e:
        print(f"DEBUG: Kunne ikke slette arkiv-indgang: {e}")
        return False


# ---------- GEMTE SAGER ----------

def gem_sag_state(titel, state_json, user_id=None, sag_id=None,
                  tenant_id=None):
    """
    Gemmer hele sagens state som JSON i gemte_sager-tabellen.
    Hvis sag_id er angivet, opdateres en eksisterende række (men kun
    hvis den tilhører den aktive tenant — cross-tenant edit afvises).
    Ellers oprettes en ny.
    Returnerer id'et på rækken eller None ved fejl/cross-tenant-forsøg.
    """
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()
    if not tenant_id:
        print("DEBUG: gem_sag_state afvist — ingen tenant_id (krævet)")
        return None
    try:
        conn = _connect()
        cur = conn.cursor()
        if sag_id is not None:
            # Verificér tenant-ejerskab før update
            cur.execute(
                "UPDATE gemte_sager SET titel=%s, state_json=%s, "
                "opdateret_dato=CURRENT_TIMESTAMP "
                "WHERE id=%s AND tenant_id=%s RETURNING id",
                (titel, state_json, sag_id, tenant_id),
            )
            row = cur.fetchone()
            ny_id = row[0] if row else None
            if ny_id is None:
                print(
                    f"DEBUG: gem_sag_state afvist — sag {sag_id} tilhører "
                    f"ikke tenant {tenant_id}"
                )
        else:
            cur.execute(
                "INSERT INTO gemte_sager (user_id, titel, state_json, tenant_id) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (user_id, titel, state_json, tenant_id),
            )
            ny_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return ny_id
    except Exception as e:
        print(f"DEBUG: Kunne ikke gemme sag-state: {e}")
        return None


def hent_gemte_sager(user_id=None, begraens=50, tenant_id=None):
    """
    Returnerer listen af gemte sager sorteret efter opdateringsdato.
    Filtreres ALTID på tenant_id — gemte sager er per definition private.
    user_id er reservet til fremtidig per-bruger-filtrering inden for
    samme tenant (i dag deler alle brugere i en tenant arkivet).
    """
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()
    if not tenant_id:
        return []
    try:
        conn = _connect()
        cur = conn.cursor()
        if user_id is None:
            cur.execute(
                "SELECT id, titel, oprettet_dato, opdateret_dato "
                "FROM gemte_sager WHERE tenant_id=%s "
                "ORDER BY opdateret_dato DESC LIMIT %s",
                (tenant_id, begraens),
            )
        else:
            cur.execute(
                "SELECT id, titel, oprettet_dato, opdateret_dato "
                "FROM gemte_sager WHERE user_id=%s AND tenant_id=%s "
                "ORDER BY opdateret_dato DESC LIMIT %s",
                (user_id, tenant_id, begraens),
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


def hent_gemt_sag(sag_id, tenant_id=None):
    """
    Returnerer en gemt sag — KUN hvis den tilhører den aktive tenant.
    Returnerer None hvis sag_id ikke findes ELLER tilhører anden tenant.
    """
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()
    if not tenant_id:
        return None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, titel, state_json, oprettet_dato, opdateret_dato "
            "FROM gemte_sager WHERE id=%s AND tenant_id=%s",
            (sag_id, tenant_id),
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


def slet_gemt_sag(sag_id, tenant_id=None):
    """
    Sletter en gemt sag — KUN hvis den tilhører den aktive tenant.
    Returnerer True hvis sletning lykkedes.
    """
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()
    if not tenant_id:
        return False
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM gemte_sager WHERE id=%s AND tenant_id=%s",
            (sag_id, tenant_id),
        )
        slettet = cur.rowcount > 0
        conn.commit()
        cur.close()
        conn.close()
        return slettet
    except Exception as e:
        print(f"DEBUG: Kunne ikke slette gemt sag: {e}")
        return False


# ---------- RAG-SØGNING ----------

def soeg_i_arkiv(stikord=None, dokumenttype=None, begraens=50, tenant_id=None):
    """
    Stikordssøgning i vidensbanken.
    - stikord: hvis angivet, filtreres der på tekstindhold (ILIKE match)
    - dokumenttype: 'afgoerelse' / 'klage' / 'vilkaar' eller None for alle
    - begraens: max antal resultater
    - tenant_id: tenant-isolation. Default = aktiv tenant.

    Returnerer liste af dicts med fil-metadata + indhold.
    """
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()
    try:
        conn = _connect()
        cur = conn.cursor()

        # Tenant-filter er ALTID med — public docs eller denne tenant's
        # private docs. Ingen anden tenant's private docs.
        where = ["(is_public = TRUE OR tenant_id = %s)"]
        params = [tenant_id]
        if stikord and stikord.strip():
            # Split på mellemrum og kræv at alle ord forekommer (case-insensitive)
            ord_liste = [o.strip() for o in stikord.split() if o.strip()]
            for ord_ in ord_liste:
                where.append("indhold ILIKE %s")
                params.append(f"%{ord_}%")
        if dokumenttype:
            where.append("dokumenttype = %s")
            params.append(dokumenttype)

        where_klausul = " WHERE " + " AND ".join(where)
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
    tenant_id=None,
):
    """
    Kernen i RAG: find de top_k mest relevante sager via cosine similarity.

    sporgsmaal_embedding: 1024-dim liste genereret af embeddings.embed_sporgsmaal().
    top_k: antal sager der returneres (default 5).
    udeluk_filnavn: hvis angivet, udelades denne sag (bruges så en klage der
                    er gemt automatisk ikke citerer sig selv).
    dokumenttype: hvis angivet, begrænses søgningen til denne type
                  ('afgoerelse', 'klage', 'vilkaar'). Default = alle.
    tenant_id:   tenant-isolation. Default = aktiv tenant. Returnerer
                 public docs PLUS denne tenant's private docs.

    I pgvector betyder '<=>' cosine-distance (0 = identisk, 2 = modsat).
    Vi sorterer ASC så de mest relevante kommer først, og returnerer også
    similarity-scoren (1 - distance) så vi kan vise den i UI'en hvis ønsket.
    """
    if sporgsmaal_embedding is None:
        return []
    if tenant_id is None:
        tenant_id = hent_aktiv_tenant_id()

    try:
        conn = _connect()
        cur = conn.cursor()

        # Byg WHERE-klausulen dynamisk
        where = [
            "embedding IS NOT NULL",
            "(is_public = TRUE OR tenant_id = %s)",
        ]
        params = [sporgsmaal_embedding, tenant_id]
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
