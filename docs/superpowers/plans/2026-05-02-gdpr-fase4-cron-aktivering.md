# GDPR Fase 4: Cron-aktivering + brugervendt UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans

**Goal:** Aktivere auto-anonymiserings-pipelinen i produktion ved at:
1. Tilføje cron-trigger der kalder `trigger_auto_anonymisering()` hver time
2. Sætte `anonymiseres_efter` på eksisterende 'aktiv' sager (migration)
3. Tilføje "Afslut sag"-knap der trigger 24-timers-vinduet
4. Tilføje admin-UI der viser GDPR-audit-log og anonymiserings-rapporter
5. Tilføje GDPR-tekst på disclaimer-siden (NU hvor pipelinen rent faktisk virker)

**Status:** Plan-fase. Kræver Fase 2 (RLS) + Fase 3 (pipeline) er aktiveret først.

**Risiko:** Mellem-høj. Når cron aktiveres, vil det automatisk anonymisere rigtige kundedata. Test grundigt på en test-sag først.

---

## Implementation steps (rækkefølge)

### 4.1 Tilføj "Afslut sag"-knap i UI

I forside.py (eller hvor sager vises): tilføj knap der sætter `anonymiseres_efter = NOW() + INTERVAL '24 hours'` på sagens dokument-rækker.

```python
def afslut_sag(sag_id, tenant_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE mine_dokumenter
        SET anonymiseres_efter = NOW() + INTERVAL '24 hours'
        WHERE id = %s
          AND tenant_id = %s
          AND anonymiserings_status = 'aktiv'
    """, (sag_id, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
```

### 4.2 Migration af eksisterende sager

Engangs-script `migration_gdpr_fase4_aktiver_pipeline.py`:

```python
"""
Markerer alle eksisterende 'aktiv' sager til anonymisering 24 timer
efter scriptet kører.

Kør én gang efter Fase 4 deploy:
    python3 migration_gdpr_fase4_aktiver_pipeline.py
"""
from database import _connect

conn = _connect()
cur = conn.cursor()
cur.execute("""
    UPDATE mine_dokumenter
    SET anonymiseres_efter = NOW() + INTERVAL '24 hours'
    WHERE anonymiserings_status = 'aktiv'
      AND is_public = FALSE
      AND anonymiseres_efter IS NULL
""")
print(f"Markerede {cur.rowcount} eksisterende sager til anonymisering om 24 timer")
conn.commit()
cur.close()
conn.close()
```

### 4.3 Cron-trigger på Fly.io

Tilføj til `fly.toml`:

```toml
[[scheduled_tasks]]
schedule = "0 * * * *"
command = 'python3 -c "from gdpr_pipeline import trigger_auto_anonymisering; print(trigger_auto_anonymisering())"'
```

### 4.4 Admin-UI: vis audit-log + rapporter

Tilføj ny tab i `admin.py`: "GDPR audit-log" der viser:
- Per-sag anonymiseringer med rapport
- Total counts: antal sager anonymiseret, antal delt til shared_patterns

### 4.5 GDPR-tekst på disclaimer-siden

Først NU — fordi nu er pipelinen aktiveret og påstandene er sande. Tilføj sektion til `disclaimer.py` med fakta om:
- 24-timers anonymisering (live)
- K-anonymitet (live)
- RLS (live)
- Audit-trail (live)

## Pre-deploy tjekliste

- [ ] Fase 2 (RLS) er aktiveret + verificeret
- [ ] Fase 3 pipeline er testet manuelt mod én test-sag
- [ ] Anthropic-credits er tilstrækkelige til pipelinen (rough estimate: $0.10-0.50 per sag)
- [ ] DPIA-dokument er finpudset af jurist
- [ ] Privatlivspolitik er publiceret på juriitech.com
- [ ] DPA-skabelon er klar til kunde-onboarding
