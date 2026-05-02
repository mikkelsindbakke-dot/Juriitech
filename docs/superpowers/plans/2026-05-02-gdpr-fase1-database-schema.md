# GDPR Fase 1: Database schema + audit-log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tilføj database-fundamentet for GDPR-pipelinen — nye kolonner på `mine_dokumenter`, ny `gdpr_audit_log`-tabel og ny `shared_patterns`-tabel — uden at ændre app-adfærd. Senere planer (RLS, pipeline-modul, cron) bygger oven på dette fundament.

**Architecture:** Schema-ændringerne gøres idempotente via `CREATE TABLE IF NOT EXISTS` + `ADD COLUMN IF NOT EXISTS` i `database.opret_tabeller()` (samme mønster som B1 + B2). Eksisterende rækker får sikre default-værdier (`anonymiserings_status='pending'`). Ingen kode-stier ændres, ingen queries flyttes — kun fundamentet lægges.

**Tech Stack:** Postgres 16 (Supabase), psycopg2, pgvector 0.8.0, Python 3.11.

**Test-strategi:** Projektet har ingen pytest-suite (jf. CLAUDE.md). Vi laver et standalone test-script `test_gdpr_fase1_schema.py` (matcher eksisterende `test_b1_isolation.py`-mønster) der verificerer schema-ændringer + at appen stadig starter + at eksisterende sager stadig kan oprettes/hentes.

---

## File Structure

- **Modify:** `database.py:140-310` (i `opret_tabeller()` — tilføj nye tabeller + kolonner, idempotent)
- **Create:** `test_gdpr_fase1_schema.py` (verifikations-script — kører mod prod-DB med tom-tenant)

Ingen ny modul nødvendig endnu — pipelinen kommer i Fase 3.

---

### Task 1: Tilføj `anonymiserings_status` + `anonymiseres_efter` kolonner til `mine_dokumenter`

**Why:** Pipelinen (Fase 3) skal kunne identificere hvilke sager der skal anonymiseres og hvornår. Vi tilføjer to kolonner: en status-enum og et tidsstempel-trigger.

**Files:**
- Modify: `/Users/mikkelhansen/Desktop/juridisk_assistent/database.py` (i `opret_tabeller()`-funktionen)

- [ ] **Step 1: Find indsætningspunkt i `opret_tabeller()`**

Kør:
```bash
grep -n "ADD COLUMN IF NOT EXISTS is_public" /Users/mikkelhansen/Desktop/juridisk_assistent/database.py
```

Forventet: én linje, der er enden af de eksisterende B1-kolonne-tilføjelser. Vi indsætter de to nye kolonner lige efter den eksisterende `is_public`-blok.

- [ ] **Step 2: Tilføj de to nye kolonner**

Edit `database.py` — find blokken der ender med `is_public BOOLEAN DEFAULT FALSE` på `mine_dokumenter`. Lige efter den blok, INDSÆT:

```python
        # 10b. GDPR Fase 1: anonymiserings_status + anonymiseres_efter
        # på mine_dokumenter. Pipeline (Fase 3) bruger disse til at
        # identificere sager der skal anonymiseres.
        # Status-enum:
        #   'pending'       — ikke startet behandling endnu (default for nye sager)
        #   'aktiv'         — sag er aktiv, persondata findes som nødvendigt
        #   'anonymiseret'  — pipeline har kørt, original-data slettet
        #   'public'        — offentlig afgørelse (matcher is_public=TRUE),
        #                     skal aldrig anonymiseres
        cur.execute("""
            ALTER TABLE mine_dokumenter
            ADD COLUMN IF NOT EXISTS anonymiserings_status TEXT
            DEFAULT 'pending'
        """)
        # CHECK-constraint adderes separat så det er idempotent
        # (CONSTRAINT IF NOT EXISTS findes ikke før Postgres 17)
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.constraint_column_usage
                    WHERE table_name = 'mine_dokumenter'
                      AND constraint_name = 'mine_dokumenter_anon_status_check'
                ) THEN
                    ALTER TABLE mine_dokumenter
                    ADD CONSTRAINT mine_dokumenter_anon_status_check
                    CHECK (anonymiserings_status IN
                        ('pending', 'aktiv', 'anonymiseret', 'public'));
                END IF;
            END$$
        """)
        cur.execute("""
            ALTER TABLE mine_dokumenter
            ADD COLUMN IF NOT EXISTS anonymiseres_efter TIMESTAMPTZ
        """)
        # Index så Fase-3-cron kan hurtigt finde rækker der skal
        # anonymiseres. Filtrerer eksplicit is_public=FALSE — offentlige
        # afgørelser fra Pakkerejse-Ankenævnet er allerede pseudonymiseret
        # af kilden og må ALDRIG røres.
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mine_dok_anonym_pending
            ON mine_dokumenter (anonymiseres_efter)
            WHERE anonymiserings_status = 'aktiv'
              AND is_public = FALSE
        """)

```

- [ ] **Step 3: Opdatér eksisterende rækker så de har korrekt status**

I samme `opret_tabeller()`, EFTER kolonne-tilføjelsen, tilføj en backfill-blok:

```python
        # Backfill: eksisterende offentlige afgørelser → 'public',
        # eksisterende private dokumenter (klage-sager) → 'aktiv'
        # (de er allerede uploadet, så pipelinen ville ellers tro de
        # var i 'pending' og aldrig trigge dem).
        cur.execute("""
            UPDATE mine_dokumenter
            SET anonymiserings_status = 'public'
            WHERE is_public = TRUE
              AND anonymiserings_status = 'pending'
        """)
        cur.execute("""
            UPDATE mine_dokumenter
            SET anonymiserings_status = 'aktiv'
            WHERE is_public = FALSE
              AND anonymiserings_status = 'pending'
              AND tenant_id IS NOT NULL
        """)
        # Bemærk: anonymiseres_efter SÆTTES IKKE her. Det betyder
        # eksisterende sager bliver liggende i 'aktiv' indefinitely
        # indtil Fase 3 deploys og en bevidst migration trigger på
        # dem. Det er bevidst — vi vil ikke pludseligt anonymisere
        # alt eksisterende data uden test.

```

- [ ] **Step 4: Verificer Python-syntaks**

Kør:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python3 -c "
import ast
with open('database.py') as f: ast.parse(f.read())
print('SYNTAX OK')
"
```

Forventet: `SYNTAX OK`

- [ ] **Step 5: Kør `opret_tabeller()` mod prod-DB og verificer at kolonner findes**

Kør:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python3 -c "
from database import opret_tabeller, get_conn
opret_tabeller()
conn = get_conn()
cur = conn.cursor()
cur.execute('''
    SELECT column_name, data_type, column_default
    FROM information_schema.columns
    WHERE table_name='mine_dokumenter'
      AND column_name IN ('anonymiserings_status', 'anonymiseres_efter')
    ORDER BY column_name
''')
for r in cur.fetchall(): print(r)
cur.close()
conn.close()
"
```

Forventet output:
```
('anonymiserings_status', 'text', "'pending'::text")
('anonymiseres_efter', 'timestamp with time zone', None)
```

Hvis output mangler én eller begge rækker → opret_tabeller() har fejlet, læs traceback og fix.

- [ ] **Step 6: Verificer at eksisterende rækker har fået korrekt status-backfill**

Kør:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python3 -c "
from database import get_conn
conn = get_conn()
cur = conn.cursor()
cur.execute('''
    SELECT anonymiserings_status, is_public, COUNT(*) AS antal
    FROM mine_dokumenter
    GROUP BY anonymiserings_status, is_public
    ORDER BY anonymiserings_status, is_public
''')
for r in cur.fetchall(): print(r)
cur.close()
conn.close()
"
```

Forventet output (rækker afhænger af aktuel data, men mønstret skal matche):
```
('aktiv', False, <antal private rækker>)
('public', True, <antal offentlige afgørelser>)
```

Der må IKKE være rækker med `('pending', ...)` — alle eksisterende rækker er backfilled til enten 'aktiv' eller 'public'.

- [ ] **Step 7: Commit**

```bash
git add database.py
git commit -m "$(cat <<'EOF'
GDPR Fase 1.1: anonymiserings_status + anonymiseres_efter på mine_dokumenter

Tilføjer to kolonner som fundament for kommende auto-anonymiserings-
pipeline (Fase 3). Idempotent migration via ADD COLUMN IF NOT EXISTS.
Eksisterende rækker backfilles: is_public=TRUE → 'public', private
sager → 'aktiv'. Index på anonymiseres_efter (filtreret
WHERE is_public=FALSE) så pipeline-cron kan hurtigt finde sager
til anonymisering uden at scanne offentlige afgørelser.

Ingen app-adfærd ændres — kun schema-fundament lægges.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Opret `gdpr_audit_log`-tabel

**Why:** Audit-log er et selvstændigt krav fra GDPR (Art. 30: register over behandlinger). Vi skal kunne dokumentere PER sag hvad der skete og hvornår — særligt sletninger. Pipeline (Fase 3) skriver til denne tabel; admin-side (Fase 4) viser den til kunden.

**Files:**
- Modify: `/Users/mikkelhansen/Desktop/juridisk_assistent/database.py` (i `opret_tabeller()`)

- [ ] **Step 1: Tilføj tabel-oprettelse i `opret_tabeller()`**

I `database.py` — efter Task 1's kolonne-tilføjelser, INDSÆT:

```python
        # GDPR Fase 1.2: Audit-log tabel
        # Per-sag historik over GDPR-relevante handlinger:
        # upload, analyse-start, anonymisering, original-sletning,
        # cross-tenant share. Skal kunne fremvises ved kunde-revision.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gdpr_audit_log (
                id SERIAL PRIMARY KEY,
                sag_id TEXT NOT NULL,
                tenant_id INTEGER NOT NULL
                    REFERENCES tenants(id) ON DELETE RESTRICT,
                handling TEXT NOT NULL,
                tidspunkt TIMESTAMPTZ DEFAULT NOW(),
                metadata JSONB
            )
        """)
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.constraint_column_usage
                    WHERE table_name = 'gdpr_audit_log'
                      AND constraint_name = 'gdpr_audit_log_handling_check'
                ) THEN
                    ALTER TABLE gdpr_audit_log
                    ADD CONSTRAINT gdpr_audit_log_handling_check
                    CHECK (handling IN (
                        'upload', 'analyse', 'anonymisering',
                        'sletning', 'cross_tenant_share',
                        'tilbage_kald'
                    ));
                END IF;
            END$$
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gdpr_audit_tenant_sag
            ON gdpr_audit_log (tenant_id, sag_id, tidspunkt DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_gdpr_audit_tidspunkt
            ON gdpr_audit_log (tidspunkt DESC)
        """)

```

- [ ] **Step 2: Verificer syntaks**

Kør:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python3 -c "
import ast
with open('database.py') as f: ast.parse(f.read())
print('SYNTAX OK')
"
```

Forventet: `SYNTAX OK`

- [ ] **Step 3: Kør `opret_tabeller()` og verificer tabellen findes**

Kør:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python3 -c "
from database import opret_tabeller, get_conn
opret_tabeller()
conn = get_conn()
cur = conn.cursor()
cur.execute('''
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name='gdpr_audit_log'
    ORDER BY ordinal_position
''')
for r in cur.fetchall(): print(r)
cur.close()
conn.close()
"
```

Forventet output:
```
('id', 'integer', 'NO')
('sag_id', 'text', 'NO')
('tenant_id', 'integer', 'NO')
('handling', 'text', 'NO')
('tidspunkt', 'timestamp with time zone', 'YES')
('metadata', 'jsonb', 'YES')
```

- [ ] **Step 4: Test at vi kan indsætte + hente en row**

Kør:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python3 -c "
from database import get_conn
import json
conn = get_conn()
cur = conn.cursor()
# Hent en gyldig tenant_id
cur.execute('SELECT id FROM tenants LIMIT 1')
tid = cur.fetchone()[0]
# Insert test-row
cur.execute('''
    INSERT INTO gdpr_audit_log (sag_id, tenant_id, handling, metadata)
    VALUES (%s, %s, %s, %s::jsonb)
    RETURNING id
''', ('test-sag-fase1', tid, 'upload', json.dumps({'test': True})))
inserted_id = cur.fetchone()[0]
# Hent rækken
cur.execute('SELECT sag_id, handling, metadata FROM gdpr_audit_log WHERE id = %s',
            (inserted_id,))
print('Inserted row:', cur.fetchone())
# Ryd op
cur.execute('DELETE FROM gdpr_audit_log WHERE id = %s', (inserted_id,))
conn.commit()
print('Cleanup OK')
cur.close()
conn.close()
"
```

Forventet output:
```
Inserted row: ('test-sag-fase1', 'upload', {'test': True})
Cleanup OK
```

- [ ] **Step 5: Commit**

```bash
git add database.py
git commit -m "$(cat <<'EOF'
GDPR Fase 1.2: gdpr_audit_log-tabel

Audit-trail for GDPR-relevante handlinger pr. sag (upload, analyse,
anonymisering, sletning, cross_tenant_share, tilbage_kald). FK til
tenants med ON DELETE RESTRICT så audit-historik aldrig forsvinder
før eksplicit handling.

Indeks på (tenant_id, sag_id, tidspunkt DESC) for hurtig per-sag
historik-opslag og på (tidspunkt DESC) for kronologisk visning.

Pipelinen i Fase 3 skriver til tabellen; Fase 4 tilføjer admin-UI
til at vise loggen til kunden.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Opret `shared_patterns`-tabel

**Why:** Den fælles cross-tenant pulje af anonymiserede mønstre fra (iii) i designet. Tabellen har INGEN `tenant_id` — det er fysisk umuligt at lække tenant-info via SQL fra denne tabel. Pipeline (Fase 3) skriver hertil når k-anonymitet (k≥5) er opfyldt; RAG-laget (Fase 3.b) bruger den som lærings-kilde for ALLE tenants.

**Files:**
- Modify: `/Users/mikkelhansen/Desktop/juridisk_assistent/database.py` (i `opret_tabeller()`)

- [ ] **Step 1: Tilføj tabel-oprettelse i `opret_tabeller()`**

I `database.py` — efter Task 2, INDSÆT:

```python
        # GDPR Fase 1.3: shared_patterns — cross-tenant anonymiseret pulje
        # Designprincip: INGEN tenant_id-kolonne her. Det er fysisk umuligt
        # at lække tenant-info via SQL fra denne tabel. K-anonymitet
        # (k_count ≥ 5) håndhæves af pipelinen i Fase 3 — kun mønstre
        # der allerede har 4+ lignende kandidater må gemmes her.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shared_patterns (
                id SERIAL PRIMARY KEY,
                tilfojet_dato TIMESTAMPTZ DEFAULT NOW(),
                sag_kategori TEXT NOT NULL,
                udfald_kategori TEXT NOT NULL,
                region TEXT,
                anonymiseret_tekst TEXT NOT NULL,
                embedding vector(1024),
                k_count INTEGER NOT NULL DEFAULT 1
            )
        """)
        # CHECK-constraint på k_count så ingen pipeline-fejl skriver
        # k=0 eller negative værdier
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.constraint_column_usage
                    WHERE table_name = 'shared_patterns'
                      AND constraint_name = 'shared_patterns_k_count_check'
                ) THEN
                    ALTER TABLE shared_patterns
                    ADD CONSTRAINT shared_patterns_k_count_check
                    CHECK (k_count >= 5);
                END IF;
            END$$
        """)
        # Index på kategori-kombi (sagstype + udfald + region) for
        # hurtig matching af nye sager mod eksisterende mønstre
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_shared_patterns_kategori
            ON shared_patterns (sag_kategori, udfald_kategori, region)
        """)
        # HNSW-index på embedding for cosine-similarity-søgning
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_shared_patterns_embedding
            ON shared_patterns USING hnsw (embedding vector_cosine_ops)
        """)

```

- [ ] **Step 2: Verificer syntaks**

Kør:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python3 -c "
import ast
with open('database.py') as f: ast.parse(f.read())
print('SYNTAX OK')
"
```

Forventet: `SYNTAX OK`

- [ ] **Step 3: Kør `opret_tabeller()` og verificer tabellen findes med korrekt struktur**

Kør:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python3 -c "
from database import opret_tabeller, get_conn
opret_tabeller()
conn = get_conn()
cur = conn.cursor()
cur.execute('''
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name='shared_patterns'
    ORDER BY ordinal_position
''')
for r in cur.fetchall(): print(r)
# Verificer tabellen IKKE har tenant_id
cur.execute('''
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_name='shared_patterns' AND column_name='tenant_id'
''')
assert cur.fetchone()[0] == 0, 'BUG: shared_patterns har tenant_id — designprincip brudt'
print('OK: shared_patterns har INGEN tenant_id')
cur.close()
conn.close()
"
```

Forventet output (data-types skal matche):
```
('id', 'integer')
('tilfojet_dato', 'timestamp with time zone')
('sag_kategori', 'text')
('udfald_kategori', 'text')
('region', 'text')
('anonymiseret_tekst', 'text')
('embedding', 'USER-DEFINED')
('k_count', 'integer')
OK: shared_patterns har INGEN tenant_id
```

- [ ] **Step 4: Test CHECK-constraint på k_count blokerer k<5**

Kør:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python3 -c "
from database import get_conn
import psycopg2
conn = get_conn()
cur = conn.cursor()
# Forsøg insert med k_count=3 — skal fejle
try:
    cur.execute('''
        INSERT INTO shared_patterns
        (sag_kategori, udfald_kategori, region, anonymiseret_tekst, k_count)
        VALUES (%s, %s, %s, %s, %s)
    ''', ('test', 'test', 'test', 'test', 3))
    conn.commit()
    print('BUG: insert med k_count=3 lykkedes — constraint virker IKKE')
except psycopg2.errors.CheckViolation:
    conn.rollback()
    print('OK: k_count=3 blokeret af CHECK-constraint')
cur.close()
conn.close()
"
```

Forventet output:
```
OK: k_count=3 blokeret af CHECK-constraint
```

- [ ] **Step 5: Commit**

```bash
git add database.py
git commit -m "$(cat <<'EOF'
GDPR Fase 1.3: shared_patterns-tabel (cross-tenant pulje)

Den fælles pulje af anonymiserede mønstre fra (iii) i GDPR-designet.

Designprincip: INGEN tenant_id-kolonne. Det er fysisk umuligt at lække
tenant-info via SQL fra denne tabel. K-anonymitet (k_count ≥ 5)
håndhæves både i pipeline-laget (Fase 3) og som CHECK-constraint
i database — defense in depth.

HNSW-index på embedding (vector_cosine_ops) for hurtig
cosine-similarity-søgning, matchende mønster fra public-vidensbank.

RAG-laget i Fase 3 vil bruge denne pulje som lærings-kilde for ALLE
tenants — det er den primære cross-tenant lærings-mekanisme.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Verifikations-script `test_gdpr_fase1_schema.py`

**Why:** Vi skal kunne re-køre verifikation efter Fase 2-4-deploys uden at huske de manuelle steps. Et standalone script samler alle tjek fra Task 1-3 + verificerer at app stadig starter (ingen kode-paths brokken af schema-ændringerne).

**Files:**
- Create: `/Users/mikkelhansen/Desktop/juridisk_assistent/test_gdpr_fase1_schema.py`

- [ ] **Step 1: Skriv scriptet**

Create file `/Users/mikkelhansen/Desktop/juridisk_assistent/test_gdpr_fase1_schema.py`:

```python
"""
test_gdpr_fase1_schema.py

Verifikations-script for GDPR Fase 1 schema-ændringer.
Kører mod produktions-DB (via .env).

Bruges:
    python3 test_gdpr_fase1_schema.py

Exit code 0 = alle tjek bestået. 1 = mindst ét tjek fejlet.

Følger samme mønster som test_b1_isolation.py.
"""

import json
import sys
import psycopg2

from database import get_conn, opret_tabeller


def _green(s):
    return f"\033[32m{s}\033[0m"


def _red(s):
    return f"\033[31m{s}\033[0m"


def tjek(navn, betingelse, fejl_hint=""):
    """Print resultat af et tjek. Raises hvis fejlet — kalder accepterer
    via try/except hvis test ikke skal stoppe ved første fejl."""
    if betingelse:
        print(f"  {_green('✓')} {navn}")
        return True
    else:
        print(f"  {_red('✗')} {navn}")
        if fejl_hint:
            print(f"      hint: {fejl_hint}")
        return False


def hovedtest():
    print("\n=== GDPR Fase 1 schema-verifikation ===\n")
    conn = get_conn()
    cur = conn.cursor()
    fejl = 0

    # ---- Task 1: anonymiserings_status + anonymiseres_efter ----
    print("Task 1 — mine_dokumenter kolonner:")
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='mine_dokumenter'
          AND column_name IN ('anonymiserings_status', 'anonymiseres_efter')
    """)
    fundet = {r[0] for r in cur.fetchall()}
    if not tjek("anonymiserings_status findes",
                "anonymiserings_status" in fundet):
        fejl += 1
    if not tjek("anonymiseres_efter findes",
                "anonymiseres_efter" in fundet):
        fejl += 1

    # CHECK-constraint
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.check_constraints
        WHERE constraint_name='mine_dokumenter_anon_status_check'
    """)
    if not tjek("CHECK-constraint på status-værdier findes",
                cur.fetchone()[0] >= 1):
        fejl += 1

    # Backfill: ingen 'pending' rækker
    cur.execute("""
        SELECT COUNT(*) FROM mine_dokumenter
        WHERE anonymiserings_status='pending'
    """)
    pending_antal = cur.fetchone()[0]
    if not tjek(
        "Ingen rækker har status='pending' (backfill virkede)",
        pending_antal == 0,
        f"{pending_antal} rækker har 'pending' — kør opret_tabeller() igen"
    ):
        fejl += 1

    # ---- Task 2: gdpr_audit_log ----
    print("\nTask 2 — gdpr_audit_log tabel:")
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name='gdpr_audit_log'
    """)
    if not tjek("Tabel findes", cur.fetchone()[0] == 1):
        fejl += 1

    # Insert + delete-cyklus
    try:
        cur.execute("SELECT id FROM tenants LIMIT 1")
        tid = cur.fetchone()
        if tid is None:
            tjek("Mindst én tenant findes (forudsætning)", False,
                 "kør migration_b1_tenants.py først")
            fejl += 1
        else:
            tid = tid[0]
            cur.execute("""
                INSERT INTO gdpr_audit_log
                (sag_id, tenant_id, handling, metadata)
                VALUES (%s, %s, %s, %s::jsonb)
                RETURNING id
            """, ("schema-test", tid, "upload",
                  json.dumps({"verifikation": True})))
            ins_id = cur.fetchone()[0]
            cur.execute(
                "DELETE FROM gdpr_audit_log WHERE id=%s", (ins_id,))
            conn.commit()
            tjek("Insert + delete-cyklus virker", True)
    except Exception as e:
        conn.rollback()
        tjek("Insert + delete-cyklus virker", False, str(e))
        fejl += 1

    # CHECK-constraint på handling
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.check_constraints
        WHERE constraint_name='gdpr_audit_log_handling_check'
    """)
    if not tjek("CHECK-constraint på handling-værdier findes",
                cur.fetchone()[0] >= 1):
        fejl += 1

    # ---- Task 3: shared_patterns ----
    print("\nTask 3 — shared_patterns tabel:")
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name='shared_patterns'
    """)
    if not tjek("Tabel findes", cur.fetchone()[0] == 1):
        fejl += 1

    cur.execute("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name='shared_patterns' AND column_name='tenant_id'
    """)
    if not tjek("Tabel har INGEN tenant_id (designprincip)",
                cur.fetchone()[0] == 0,
                "tenant_id må ALDRIG findes på shared_patterns"):
        fejl += 1

    # CHECK-constraint blokerer k_count<5
    try:
        cur.execute("""
            INSERT INTO shared_patterns
            (sag_kategori, udfald_kategori, region,
             anonymiseret_tekst, k_count)
            VALUES (%s, %s, %s, %s, %s)
        """, ("test", "test", "test", "test", 4))
        conn.commit()
        tjek("k_count<5 blokeret af CHECK-constraint", False,
             "k_count=4 burde have fejlet, men insert lykkedes")
        fejl += 1
        # Cleanup
        cur.execute("""
            DELETE FROM shared_patterns
            WHERE sag_kategori='test' AND k_count=4
        """)
        conn.commit()
    except psycopg2.errors.CheckViolation:
        conn.rollback()
        tjek("k_count<5 blokeret af CHECK-constraint", True)

    # HNSW-index findes
    cur.execute("""
        SELECT COUNT(*) FROM pg_indexes
        WHERE tablename='shared_patterns'
          AND indexname='idx_shared_patterns_embedding'
    """)
    if not tjek("HNSW-index på embedding findes",
                cur.fetchone()[0] >= 1):
        fejl += 1

    # ---- Resultat ----
    print()
    cur.close()
    conn.close()
    if fejl == 0:
        print(_green("=== ALLE TJEK BESTÅET ==="))
        return 0
    else:
        print(_red(f"=== {fejl} TJEK FEJLET ==="))
        return 1


if __name__ == "__main__":
    sys.exit(hovedtest())
```

- [ ] **Step 2: Kør scriptet og bekræft alle tjek består**

Kør:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && python3 test_gdpr_fase1_schema.py
```

Forventet output (sidste linje = grøn):
```
=== GDPR Fase 1 schema-verifikation ===

Task 1 — mine_dokumenter kolonner:
  ✓ anonymiserings_status findes
  ✓ anonymiseres_efter findes
  ✓ CHECK-constraint på status-værdier findes
  ✓ Ingen rækker har status='pending' (backfill virkede)

Task 2 — gdpr_audit_log tabel:
  ✓ Tabel findes
  ✓ Insert + delete-cyklus virker
  ✓ CHECK-constraint på handling-værdier findes

Task 3 — shared_patterns tabel:
  ✓ Tabel findes
  ✓ Tabel har INGEN tenant_id (designprincip)
  ✓ k_count<5 blokeret af CHECK-constraint
  ✓ HNSW-index på embedding findes

=== ALLE TJEK BESTÅET ===
```

Hvis nogen tjek fejler → læs hint, fix opret_tabeller(), kør igen.

- [ ] **Step 3: Commit**

```bash
git add test_gdpr_fase1_schema.py
git commit -m "$(cat <<'EOF'
GDPR Fase 1.4: verifikations-script test_gdpr_fase1_schema.py

Standalone smoke-test der verificerer alle Fase 1 schema-ændringer
mod produktions-DB. Kan re-køres efter Fase 2-4 deploys for at
sikre fundamentet stadig er intakt.

Følger samme mønster som test_b1_isolation.py — exit code 0 = OK,
1 = mindst ét tjek fejlet.

Tjek dækker:
- mine_dokumenter har anonymiserings_status + anonymiseres_efter
- CHECK-constraint på status-værdier
- Ingen rækker har 'pending' efter backfill
- gdpr_audit_log virker (insert+delete cycle)
- shared_patterns har INGEN tenant_id
- CHECK-constraint blokerer k_count<5
- HNSW-index på embedding findes

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Smoke-test at appen stadig starter + virker

**Why:** Schema-ændringer kan i teorien bryde noget der ikke fanges af verifikations-scriptet. Vi vil sikre at appens normale flow stadig virker — login, upload-side, arkiv-side, gemte sager.

**Files:** Ingen ændringer — kun manuel verifikation.

- [ ] **Step 1: Deploy til Fly.io**

Kør:
```bash
cd /Users/mikkelhansen/Desktop/juridisk_assistent && fly deploy 2>&1 | tail -10
```

Forventet: Deploy succeeds, exit code 0, "Visit your newly deployed app at https://pax-juriitech.fly.dev/".

- [ ] **Step 2: Tjek logs for opstart-fejl**

Kør:
```bash
fly logs --no-tail 2>&1 | grep -E "ERROR|Traceback|opret_tabeller" | tail -20
```

Forventet: Ingen `Traceback`-linjer. Eventuelt en `DEBUG: opret_tabeller`-linje er fint.

- [ ] **Step 3: Manuel browser-smoke-test**

Åbn `https://pax.juriitech.com` i en INKOGNITO-fane. Login som admin. Tjek:

1. **Forsiden** loader uden fejl. Sidebar viser navigation. Ingen røde fejl-bokse.
2. **Søg i arkivet** loader, viser eksisterende afgørelser, søgning virker.
3. **Gemte sager** loader, viser eksisterende sager (hvis nogen), åbn én af dem.
4. **Disclaimer** loader, viser tekst.
5. **Admin** loader, viser tenants-liste, viser brugere-liste.

Hvis ALT virker → Fase 1 er klar til at lukke. Hvis NOGET fejler → læs Fly logs, identificer rod-årsag, fix, gendepla.

- [ ] **Step 4: Markér Fase 1 som færdig**

Når smoke-test er bestået, opdatér todos:

```bash
echo "GDPR Fase 1: Database schema FÆRDIG $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> docs/superpowers/STATUS.md 2>/dev/null || true
git add docs/superpowers/STATUS.md 2>/dev/null && git commit -m "Markér GDPR Fase 1 færdig" 2>/dev/null || echo "Ingen STATUS.md at committe"
```

(Optional — bare for at have en log over progression. Springes over hvis filen ikke findes.)

---

## Done når

- `mine_dokumenter.anonymiserings_status` + `anonymiseres_efter` kolonner findes med korrekte default-værdier
- `gdpr_audit_log`-tabel oprettet, insert/delete-cyklus virker, CHECK-constraint blokerer ugyldige handling-værdier
- `shared_patterns`-tabel oprettet UDEN tenant_id-kolonne, CHECK-constraint blokerer k_count<5, HNSW-index på embedding findes
- `test_gdpr_fase1_schema.py` kører og rapporterer "ALLE TJEK BESTÅET"
- App-deploy lykkes, alle 5 sider loader uden fejl, eksisterende funktionalitet uændret

## Eksplicit ude af scope

- Pipeline-modul der faktisk anonymiserer (kommer i Fase 3)
- Cron-trigger der trigger pipeline (kommer i Fase 4)
- RLS-policies på Supabase (kommer i Fase 2)
- Privatlivspolitik på juriitech.com (kommer i Fase 4)
- DPIA-dokument (kommer i Fase 4)
- Disclaimer-tekst om GDPR (kommer i Fase 4 efter pipelinen rent faktisk virker)
