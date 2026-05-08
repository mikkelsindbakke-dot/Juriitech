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
  oprettet_dato
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
};

export async function opretTenant(felter: TenantFelter): Promise<number | null> {
  const rows = await query<{ id: number }>(
    `
    INSERT INTO tenants
      (slug, navn, sagsbehandler, by, logo_filnavn,
       anonymisering_suffix, interne_team_navne,
       klageorgan_navn, klageorgan_url, rejsevilkaar_kilde_url,
       sprog, land, lov_navn)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
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
    ],
  );
  return rows[0]?.id ?? null;
}

export type TenantOpdater = Partial<Omit<TenantFelter, "slug">>;

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
