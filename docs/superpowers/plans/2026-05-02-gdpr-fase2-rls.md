# GDPR Fase 2: Row-Level Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Aktivere Postgres Row-Level Security (RLS) som ekstra forsvarslinje på private tabeller. Hvis applikationskode ved en fejl glemmer en `tenant_id = X`-WHERE-clause, eller hvis en SQL-injection slipper igennem, vil RLS stadig blokere cross-tenant data-leakage.

**Architecture:** RLS-policies bruger en session-variable `app.current_tenant_id` der sættes per database-forbindelse i `_connect()`-funktionen efter `hent_aktiv_tenant_id()`. Policies tillader rækker hvor `tenant_id = current_setting('app.current_tenant_id')::INTEGER OR is_public = TRUE OR tenant_id IS NULL`. Service-role-forbindelser (admin-funktioner, scrapere) bypasser RLS via `BYPASSRLS`-attribut på en dedikeret rolle.

**Tech Stack:** Postgres 16 (Supabase), psycopg2 session-variabler.

**Risiko:** **HØJ.** Hvis policy-syntaks er forkert eller `app.current_tenant_id` ikke sættes korrekt, vil ALLE queries returnere 0 rækker eller fejle. Test grundigt mod et test-tenant FØR aktivering på prod.

**Status:** Ikke aktiveret. Klar til kørsel når brugeren har reviewet scriptet.

---

## Kritisk vurdering før kørsel

RLS er kompleks fordi:
1. Postgres' default policy = block all når RLS er aktiveret + ingen policy matcher
2. `current_setting()` med non-eksisterende variable kaster exception
3. Eksisterende admin-funktioner (scrapere, bootstrap_admin.py) bypasser tenant-context
4. Migration-scripts (migration_b1_tenants.py) skal også bypasse

Min anbefaling: **kør IKKE scriptet uden at have testet flowet manuelt mod test-tenant først**. Brugeren skal:
1. Reviewe RLS-scriptet
2. Læse "Pre-deploy tjekliste" nedenfor
3. Køre scriptet mod en test-DB hvis muligt
4. Først derefter mod prod

---

## File Structure

- **Create:** `gdpr_fase2_rls.sql` (SQL-script med policies, klar til kørsel)
- **Modify:** `database.py` (`_connect()` skal sætte session-variable)
- **Create:** `test_gdpr_fase2_rls.py` (verifikations-script)

## Pre-deploy tjekliste

Før `gdpr_fase2_rls.sql` køres mod prod:

- [ ] Reviewet at alle private tabeller er dækket (mine_dokumenter, analyse_arkiv, gemte_sager, chunks)
- [ ] Reviewet at offentlige rækker (is_public=TRUE eller tenant_id IS NULL) ikke blokeres af policies
- [ ] Reviewet at admin-funktioner (auth.admin_*, scrapere) bypasser RLS
- [ ] `_connect()` opdateret til at sætte `app.current_tenant_id` efter login
- [ ] Test mod prod-DB med ny tenant-bruger: kan se egne data + offentlige; kan IKKE se anden tenants data
- [ ] Backup af DB taget (Supabase auto-backup eller manuel pg_dump)

## Konkret SQL-script

Indhold er specificeret i Fase 2's RLS-script — se `gdpr_fase2_rls.sql` (oprettes i implementations-fasen). Det her plan-dokument er en INTROducktion. Selve scriptet vil indeholde:

- `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` for hver private tabel
- `CREATE POLICY tenant_isolation ON ... USING (...)`
- Bypass-rolle `juriitech_admin` med BYPASSRLS-attribut til admin-funktioner

## Implementation steps (når klar)

1. Brugeren reviewer dette plan-dokument + scriptet
2. Brugeren tager backup af prod-DB
3. Brugeren kører scriptet mod en test-DB (eller en kopi)
4. Brugeren verificerer at app virker med ny session-variable
5. Brugeren kører scriptet mod prod
6. Brugeren kører `test_gdpr_fase2_rls.py` for at verificere

## Eksplicit ude af scope

- Service-role separation (admin vs. user-rolle) — kommer som del af scriptet, men forfines i Fase 4
- RLS på `tenants`-tabellen og `users`-tabellen (admin-only, ikke tenant-specific)
- RLS på offentlige scrapede tabeller (vidensbank, lovgivning) — ikke nødvendigt
