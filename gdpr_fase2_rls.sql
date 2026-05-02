-- ============================================================================
-- GDPR Fase 2: Row-Level Security (RLS) policies
-- ============================================================================
--
-- ADVARSEL: KØR IKKE DIREKTE MOD PROD UDEN AT HAVE LÆST PLAN-DOKUMENTET
--   docs/superpowers/plans/2026-05-02-gdpr-fase2-rls.md
--
-- Hvis app-laget ikke sætter `app.current_tenant_id` per forbindelse, vil
-- ALLE queries blive blokeret af RLS-policies efter dette script kører.
-- Sørg for at database._connect() er opdateret til at sætte session-variablen
-- FØR scriptet køres.
--
-- Test-rækkefølge:
-- 1. Tag backup af DB
-- 2. Sørg for database.py er opdateret (separat patch)
-- 3. Test mod test-DB hvis muligt
-- 4. Først derefter mod prod
--
-- Rollback: Hvis noget går galt, kør ROLLBACK_gdpr_fase2_rls.sql (genereres
-- af kommentarer nedenfor — eller manuelt: ALTER TABLE ... DISABLE ROW LEVEL
-- SECURITY for hver tabel + DROP POLICY tenant_isolation ON ...).
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Aktivér RLS på private tabeller
-- ----------------------------------------------------------------------------
-- Bemærk: ENABLE ROW LEVEL SECURITY uden FORCE betyder at table owner
-- (typisk 'postgres'-superuser) bypasser RLS. Det er hvad vi vil — admin-
-- forbindelser uden tenant-context skal kunne læse alt. Application-rollen
-- (anon-key i Supabase, eller den connection-string vi bruger fra Fly.io)
-- vil derimod være underlagt RLS.

ALTER TABLE mine_dokumenter ENABLE ROW LEVEL SECURITY;
ALTER TABLE analyse_arkiv   ENABLE ROW LEVEL SECURITY;
ALTER TABLE gemte_sager     ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks          ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------------------------------------------
-- 2. Helper-funktion: hent current_tenant_id sikkert
-- ----------------------------------------------------------------------------
-- Hvis app.current_tenant_id ikke er sat (fx ved scraper-kørsel uden login),
-- returnerer funktionen NULL. Policies tjekker så IS NOT NULL og blokerer
-- private rækker for ikke-loggede sessioner. Offentlige rækker (is_public=TRUE)
-- forbliver synlige.

CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS INTEGER AS $$
BEGIN
    -- current_setting med 'true' som andet argument returnerer NULL hvis
    -- variablen ikke er sat (i stedet for at kaste exception)
    RETURN NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- ----------------------------------------------------------------------------
-- 3. RLS-policies
-- ----------------------------------------------------------------------------

-- mine_dokumenter:
--   - Offentlige dokumenter (is_public=TRUE) er synlige for alle
--   - Tenant-private dokumenter er kun synlige for matching tenant
--   - Rækker uden tenant_id (ældgamle eller offentlige scrapede) er synlige
DROP POLICY IF EXISTS tenant_isolation ON mine_dokumenter;
CREATE POLICY tenant_isolation ON mine_dokumenter
    USING (
        is_public = TRUE
        OR tenant_id IS NULL
        OR tenant_id = current_tenant_id()
    )
    WITH CHECK (
        -- INSERT/UPDATE: kun tilladt hvis ny række matcher tenant-kontekst
        is_public = TRUE
        OR tenant_id IS NULL
        OR tenant_id = current_tenant_id()
    );

-- analyse_arkiv: ALTID tenant-private (ingen offentlige analyser)
DROP POLICY IF EXISTS tenant_isolation ON analyse_arkiv;
CREATE POLICY tenant_isolation ON analyse_arkiv
    USING (
        tenant_id = current_tenant_id()
    )
    WITH CHECK (
        tenant_id = current_tenant_id()
    );

-- gemte_sager: ALTID tenant-private
DROP POLICY IF EXISTS tenant_isolation ON gemte_sager;
CREATE POLICY tenant_isolation ON gemte_sager
    USING (
        tenant_id = current_tenant_id()
    )
    WITH CHECK (
        tenant_id = current_tenant_id()
    );

-- chunks: følger parent-dokument
--   chunks har dokument_id der peger på mine_dokumenter, så vi kan ikke
--   filtrere direkte på tenant_id. Vi joiner via en EXISTS-subquery.
DROP POLICY IF EXISTS tenant_isolation ON chunks;
CREATE POLICY tenant_isolation ON chunks
    USING (
        EXISTS (
            SELECT 1 FROM mine_dokumenter md
            WHERE md.id = chunks.dokument_id
              AND (
                md.is_public = TRUE
                OR md.tenant_id IS NULL
                OR md.tenant_id = current_tenant_id()
              )
        )
    );
-- chunks WITH CHECK undlades — chunks oprettes via INSERT INTO ... SELECT
-- og parent-dokumentets tenant_id allerede er valideret.

-- ----------------------------------------------------------------------------
-- 4. Verifikation efter kørsel
-- ----------------------------------------------------------------------------
-- Disse SELECTs skal returnere de rigtige rækker når scriptet er kørt:
--
-- 1. Som superuser (uden RLS):
--      SELECT COUNT(*) FROM mine_dokumenter; -- alle rækker
--
-- 2. Som application-rolle med tenant_id sat:
--      SET app.current_tenant_id = '1';
--      SELECT COUNT(*) FROM mine_dokumenter;
--      -- = offentlige + tenant 1's private
--
-- 3. Som application-rolle med forkert tenant_id:
--      SET app.current_tenant_id = '999';
--      SELECT COUNT(*) FROM analyse_arkiv;
--      -- = 0 (ingen analyser tilhører tenant 999)
--
-- ----------------------------------------------------------------------------

COMMIT;

-- ============================================================================
-- ROLLBACK-SCRIPT (kør hvis noget går galt — kommentér ud BEGIN/COMMIT først)
-- ============================================================================
--
-- BEGIN;
-- DROP POLICY IF EXISTS tenant_isolation ON mine_dokumenter;
-- DROP POLICY IF EXISTS tenant_isolation ON analyse_arkiv;
-- DROP POLICY IF EXISTS tenant_isolation ON gemte_sager;
-- DROP POLICY IF EXISTS tenant_isolation ON chunks;
-- ALTER TABLE mine_dokumenter DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE analyse_arkiv   DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE gemte_sager     DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE chunks          DISABLE ROW LEVEL SECURITY;
-- DROP FUNCTION IF EXISTS current_tenant_id();
-- COMMIT;
