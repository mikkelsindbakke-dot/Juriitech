# GDPR Fase 2 — RLS status

**Dato:** 2026-05-03
**Status:** Aktiveret men IKKE effektiv mod nuværende app-rolle

## Hvad der er gjort

- RLS aktiveret + FORCE'et på `mine_dokumenter`, `analyse_arkiv`, `gemte_sager`, `dokument_chunks`
- Policies oprettet: `tenant_isolation` på alle 4 tabeller
- Helper-funktion `current_tenant_id()` oprettet i Postgres
- App-laget patchet (`_connect()` sætter `app.current_tenant_id`)

## Hvorfor RLS ikke virker mod app i dag

Vores `DATABASE_URL` bruger `postgres`-rollen, som i Supabase har `rolbypassrls=true`. Det betyder at RLS-policies bliver ignoreret når app-laget kører queries — selv med FORCE ROW LEVEL SECURITY.

```
 rolname  | rolsuper | rolbypassrls
----------+----------+--------------
 postgres | f        | t
```

## Konsekvens

- **Tenant-isolation er IKKE brudt.** Det virker fortsat via WHERE-clauses i app-koden (`tenant_id = hent_aktiv_tenant_id()`) — testet i `test_b1_isolation.py`.
- **RLS er klar til aktivering.** Når vi skifter rolle, vil policies straks træde i kraft uden yderligere ændringer.
- **Vi mister "defense in depth".** Hvis app-koden glemmer en WHERE-clause, vil RLS ikke fange det. Det er bekymrende men ikke katastrofalt — vi har systematiske tests.

## Hvad der mangler for ægte RLS (Fase 2.b — udskudt)

1. `CREATE ROLE juriitech_app LOGIN PASSWORD '<ny>' NOBYPASSRLS;`
2. `GRANT USAGE ON SCHEMA public TO juriitech_app;`
3. `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO juriitech_app;`
4. `GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO juriitech_app;`
5. `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ...` (så fremtidige tabeller også er tilgængelige)
6. Bygge ny connection-string: `postgresql://juriitech_app:<password>@<host>/postgres`
7. Skifte `DATABASE_URL` i Fly secrets
8. Test at appen virker — særligt scrapere og admin-funktioner
9. Eventuelt oprette `juriitech_admin LOGIN BYPASSRLS` til admin-scripts der må læse alt

Estimeret tid: 1-2 timer fokuseret arbejde med rollback-plan.

## Beslutning 2026-05-03

Udskydes. Tenant-isolation er sikret via app-laget + tests. Cross-tenant via shared_patterns har CHECK-constraint i DB (k_count≥5) som ekstra forsvar. Vi prioriterer Fase 4 (faktisk GDPR-løfter: auto-anonymisering, "Afslut sag"-knap, cron, audit-UI) der har større kommerciel og juridisk værdi.
