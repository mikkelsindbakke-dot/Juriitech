# Database.py patch til GDPR Fase 2 (RLS)

Denne ændring i `database.py` skal **køres SAMTIDIG med** `gdpr_fase2_rls.sql`. Hvis du kører SQL-scriptet uden denne patch, vil app-laget ikke sætte `app.current_tenant_id` per forbindelse, og ALLE queries vil returnere 0 private rækker.

## Hvor

I `database.py`, i `_connect()`-funktionen — efter `register_vector(conn)` og før `return conn`.

## Konkret edit

**Find:**

```python
def _connect():
    """
    Opretter en forbindelse til Supabase Postgres og registrerer
    pgvector-typen, så Python kan sende/modtage vector-kolonner som
    almindelige lister.
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
```

**Replace med:**

```python
def _connect():
    """
    Opretter en forbindelse til Supabase Postgres og registrerer
    pgvector-typen, så Python kan sende/modtage vector-kolonner som
    almindelige lister.

    Sætter også app.current_tenant_id session-variable så Postgres
    Row-Level Security (Fase 2) kan filtrere rækker per tenant uden
    at app-koden skal huske WHERE-clauses.
    """
    conn = psycopg2.connect(DB_URL)
    try:
        register_vector(conn)
    except Exception:
        # Hvis pgvector-extensionen ikke er oprettet endnu (første kørsel),
        # fejler register_vector. Vi ignorerer det — opret_tabeller() vil
        # aktivere extensionen, og næste forbindelse registrerer fint.
        pass

    # Sæt app.current_tenant_id for RLS-policies. Bruger samme funktion
    # som hent_aktiv_tenant_id() — returnerer aktiv tenant fra Streamlit-
    # session, eller None i ikke-Streamlit-kontekster (scrapere, scripts).
    # Hvis None: variablen sættes til tom streng, og current_tenant_id()
    # i SQL-laget returnerer NULL → kun offentlige rækker er synlige.
    try:
        tid = hent_aktiv_tenant_id()
        cur = conn.cursor()
        if tid is not None:
            cur.execute("SET app.current_tenant_id = %s", (str(tid),))
        else:
            cur.execute("SET app.current_tenant_id = ''")
        cur.close()
        conn.commit()
    except Exception as e:
        # Hvis variabel-sætning fejler (fx før hent_aktiv_tenant_id-imports
        # er klar), så fortsætter vi uden — RLS vil så blokere private
        # rækker, men det er sikrere end at kaste exception under boot.
        print(f"DEBUG: kunne ikke sætte app.current_tenant_id: {e}")

    return conn
```

## Tilbagekald (admin/scrapere skal bypasse RLS)

Scrapere og admin-scripts der kører UDEN tenant-context (fx `scraper.py`, `pakkerejselov_scraper.py`, `bootstrap_admin.py`) bruger superuser-rollen, der bypasser RLS automatisk pga. table ownership. Hvis Supabase-rolle er restricted, skal vi:

1. Oprette en separat database-rolle `juriitech_admin` med `BYPASSRLS`-attribut
2. Bruge den rolles connection-string i admin-scripts via en separat env-variabel `DB_URL_ADMIN`

Dette er ude af scope for Fase 2 og kan tilføjes hvis det viser sig nødvendigt.

## Test efter aktivering

Kør `test_gdpr_fase2_rls.py` (oprettes i Fase 2-implementering) der verificerer:
- Login som tenant A → kan læse egne sager + offentlige
- Login som tenant A → kan IKKE læse tenant B's sager (selv ved bevidst manipuleret WHERE-clause)
- Forsøg på INSERT med tenant_id der ikke matcher session → blokeres af WITH CHECK
