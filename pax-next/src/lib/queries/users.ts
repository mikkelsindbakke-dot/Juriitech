// Query-funktioner relateret til brugere + tenants.
// Server-side ONLY (importerer db.ts som bruger DATABASE_URL).
import "server-only";
import { query } from "@/lib/db";

export type BrugerMedTenant = {
  user_id: number;
  email: string;
  fulde_navn: string | null;
  role: "admin" | "jurist";
  tenant_id: number;
  tenant_slug: string;
  tenant_navn: string;
};

// Slår en bruger op via Supabase Auth UUID og returnerer både
// user-row og tenant-info i ét hop. Returnerer null hvis brugeren
// ikke er linket i users-tabellen (det sker hvis brugeren er
// oprettet i Supabase Auth men ikke endnu inviteret i admin-UI'en).
export async function hentBrugerMedTenant(
  supabaseUserId: string,
): Promise<BrugerMedTenant | null> {
  const rows = await query<BrugerMedTenant>(
    `
    SELECT
      u.id           AS user_id,
      u.email        AS email,
      u.fulde_navn   AS fulde_navn,
      u.role         AS role,
      t.id           AS tenant_id,
      t.slug         AS tenant_slug,
      t.navn         AS tenant_navn
    FROM users u
    JOIN tenants t ON t.id = u.tenant_id
    WHERE u.supabase_user_id = $1
    LIMIT 1
    `,
    [supabaseUserId],
  );

  return rows[0] ?? null;
}
