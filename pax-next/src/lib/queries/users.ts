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

export type UserRow = {
  id: number;
  email: string;
  fulde_navn: string;
  role: "admin" | "jurist";
  tenant_id: number;
  supabase_user_id: string | null;
};

export async function hentUserById(id: number): Promise<UserRow | null> {
  const rows = await query<UserRow>(
    `SELECT id, email, fulde_navn, role, tenant_id, supabase_user_id
       FROM users WHERE id=$1 LIMIT 1`,
    [id],
  );
  return rows[0] ?? null;
}

export async function hentUserByEmail(email: string): Promise<UserRow | null> {
  const rows = await query<UserRow>(
    `SELECT id, email, fulde_navn, role, tenant_id, supabase_user_id
       FROM users WHERE email=$1 LIMIT 1`,
    [email.trim().toLowerCase()],
  );
  return rows[0] ?? null;
}

export async function hentUsersForTenant(
  tenantId: number,
): Promise<UserRow[]> {
  return await query<UserRow>(
    `SELECT id, email, fulde_navn, role, tenant_id, supabase_user_id
       FROM users WHERE tenant_id=$1 ORDER BY role DESC, email ASC`,
    [tenantId],
  );
}

export async function opretUser(args: {
  email: string;
  tenantId: number;
  role: "admin" | "jurist";
  fuldeNavn?: string;
  supabaseUserId?: string | null;
}): Promise<number | null> {
  const rows = await query<{ id: number }>(
    `INSERT INTO users (email, tenant_id, role, fulde_navn, supabase_user_id)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING id`,
    [
      args.email.trim().toLowerCase(),
      args.tenantId,
      args.role,
      args.fuldeNavn ?? "",
      args.supabaseUserId ?? null,
    ],
  );
  return rows[0]?.id ?? null;
}

export async function sletUser(id: number): Promise<boolean> {
  const rows = await query<{ id: number }>(
    `DELETE FROM users WHERE id=$1 RETURNING id`,
    [id],
  );
  return rows.length === 1;
}

export async function taelAdmins(): Promise<number> {
  const rows = await query<{ count: string }>(
    `SELECT COUNT(*)::text AS count FROM users WHERE role='admin'`,
  );
  return Number(rows[0]?.count ?? 0);
}
