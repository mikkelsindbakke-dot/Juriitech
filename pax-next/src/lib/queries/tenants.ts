// Queries for tenants-tabellen + bruger-CRUD til admin-siden.
// Server-side ONLY — bruger DATABASE_URL via db.ts.
//
// ADMIN-OPERATIONER: tenant-CRUD og bruger-management har INGEN
// tenant_id-filter (admin opererer på tværs af alle selskaber).
// Adgangskontrollen håndhæves i app/admin/layout.tsx via role='admin'.
import "server-only";
import { query } from "@/lib/db";

export type Tenant = {
  id: number;
  slug: string;
  navn: string;
  sagsbehandler: string;
  by: string;
  logo_filnavn: string;
  anonymisering_suffix: string;
  interne_team_navne: string[];
  klageorgan_navn: string;
  klageorgan_url: string;
  rejsevilkaar_kilde_url: string;
  sprog: string;
  land: string;
  lov_navn: string;
  oprettet_dato: string;
  // Free-trial-felter — NULL for almindelige (betalende) tenants.
  // is_trial=TRUE + trial_expires_at < NOW() = brugere skal redirectes
  // til /proeve-udloebet af proxy-middleware.
  is_trial: boolean;
  trial_expires_at: string | null;
  trial_created_by: number | null;
  trial_converted_at: string | null;
  trial_data_purged_at: string | null;
};

type TenantRow = Omit<Tenant, "interne_team_navne"> & {
  interne_team_navne: string | string[] | null;
};

function parseTeamNavne(raw: string | string[] | null): string[] {
  if (Array.isArray(raw)) return raw;
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function rowTilTenant(row: TenantRow): Tenant {
  return { ...row, interne_team_navne: parseTeamNavne(row.interne_team_navne) };
}

const TENANT_KOLONNER = `
  id, slug, navn, sagsbehandler, by, logo_filnavn,
  anonymisering_suffix, interne_team_navne, klageorgan_navn,
  klageorgan_url, rejsevilkaar_kilde_url, sprog, land, lov_navn,
  oprettet_dato,
  is_trial, trial_expires_at, trial_created_by,
  trial_converted_at, trial_data_purged_at
`;

export async function hentAlleTenants(): Promise<Tenant[]> {
  const rows = await query<TenantRow>(
    `SELECT ${TENANT_KOLONNER} FROM tenants ORDER BY navn ASC`,
  );
  return rows.map(rowTilTenant);
}

export async function hentTenantById(id: number): Promise<Tenant | null> {
  const rows = await query<TenantRow>(
    `SELECT ${TENANT_KOLONNER} FROM tenants WHERE id=$1 LIMIT 1`,
    [id],
  );
  return rows[0] ? rowTilTenant(rows[0]) : null;
}

export async function hentTenantBySlug(slug: string): Promise<Tenant | null> {
  const rows = await query<TenantRow>(
    `SELECT ${TENANT_KOLONNER} FROM tenants WHERE slug=$1 LIMIT 1`,
    [slug],
  );
  return rows[0] ? rowTilTenant(rows[0]) : null;
}

export type TenantFelter = {
  slug: string;
  navn: string;
  sagsbehandler?: string;
  by?: string;
  anonymisering_suffix?: string;
  interne_team_navne?: string[];
  klageorgan_navn?: string;
  klageorgan_url?: string;
  rejsevilkaar_kilde_url?: string;
  sprog?: string;
  land?: string;
  lov_navn?: string;
  // Prøve-tenant: hvis is_trial=true MÅ trial_expires_at ikke være null
  is_trial?: boolean;
  trial_expires_at?: string | null; // ISO-string, fx '2026-06-03T00:00:00Z'
  trial_created_by?: number | null;
};

export async function opretTenant(felter: TenantFelter): Promise<number | null> {
  const rows = await query<{ id: number }>(
    `
    INSERT INTO tenants
      (slug, navn, sagsbehandler, by, logo_filnavn,
       anonymisering_suffix, interne_team_navne,
       klageorgan_navn, klageorgan_url, rejsevilkaar_kilde_url,
       sprog, land, lov_navn,
       is_trial, trial_expires_at, trial_created_by)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
            $14,$15,$16)
    RETURNING id
    `,
    [
      felter.slug,
      felter.navn,
      felter.sagsbehandler || felter.navn,
      felter.by ?? "",
      "",
      felter.anonymisering_suffix || felter.navn,
      JSON.stringify(felter.interne_team_navne ?? []),
      felter.klageorgan_navn ?? "Pakkerejse-Ankenævnet",
      felter.klageorgan_url ?? "https://www.pakkerejseankenaevnet.dk",
      felter.rejsevilkaar_kilde_url ?? "",
      felter.sprog ?? "da",
      felter.land ?? "DK",
      felter.lov_navn ?? "Pakkerejseloven",
      felter.is_trial ?? false,
      felter.trial_expires_at ?? null,
      felter.trial_created_by ?? null,
    ],
  );
  return rows[0]?.id ?? null;
}

export type TenantOpdater = Partial<Omit<TenantFelter, "slug">> & {
  trial_converted_at?: string | null;
  trial_data_purged_at?: string | null;
};

export async function opdaterTenant(
  id: number,
  felter: TenantOpdater,
): Promise<boolean> {
  const tilladt = new Set([
    "navn",
    "sagsbehandler",
    "by",
    "anonymisering_suffix",
    "interne_team_navne",
    "klageorgan_navn",
    "klageorgan_url",
    "rejsevilkaar_kilde_url",
    "sprog",
    "land",
    "lov_navn",
    "is_trial",
    "trial_expires_at",
    "trial_converted_at",
    "trial_data_purged_at",
  ]);
  const dele: string[] = [];
  const params: unknown[] = [];
  let i = 1;
  for (const [n, v] of Object.entries(felter)) {
    if (!tilladt.has(n)) continue;
    dele.push(`${n} = $${i++}`);
    params.push(n === "interne_team_navne" ? JSON.stringify(v ?? []) : v);
  }
  if (dele.length === 0) return true;
  params.push(id);
  const rows = await query<{ id: number }>(
    `UPDATE tenants SET ${dele.join(", ")} WHERE id=$${i} RETURNING id`,
    params,
  );
  return rows.length > 0;
}

/**
 * Konvertér en prøve-tenant til en betalende kunde.
 * Flipper is_trial=FALSE og rydder trial_expires_at, men beholder
 * trial_converted_at som audit-spor på at det oprindeligt var en prøve.
 */
export async function konverterProeveTenant(id: number): Promise<boolean> {
  const rows = await query<{ id: number }>(
    `UPDATE tenants
       SET is_trial = FALSE,
           trial_expires_at = NULL,
           trial_converted_at = NOW()
     WHERE id = $1 AND is_trial = TRUE
     RETURNING id`,
    [id],
  );
  return rows.length > 0;
}

/**
 * Forlæng en prøve-tenants udløbsdato. Tager en absolut ISO-dato
 * (ikke et antal dage), så admin har fuld kontrol over hvad de sætter.
 */
export async function forlængProeveTenant(
  id: number,
  nyUdløber: string,
): Promise<boolean> {
  const rows = await query<{ id: number }>(
    `UPDATE tenants
       SET trial_expires_at = $1
     WHERE id = $2 AND is_trial = TRUE
     RETURNING id`,
    [nyUdløber, id],
  );
  return rows.length > 0;
}
