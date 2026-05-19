// Query-funktioner relateret til brugere + tenants.
// Server-side ONLY (importerer db.ts som bruger DATABASE_URL).
import "server-only";
import { query } from "@/lib/db";
import { normaliserLocale, type Locale } from "@/lib/i18n/config";

// Cookie-navn til admin "view-as-tenant"-override. Når sat, læser
// hentBrugerMedTenant() dens værdi og sætter effektiv_tenant_id til
// override-tenant'en. Cookie er HTTP-only og sættes kun via det
// dedikerede /api/admin/switch-tenant endpoint (efter role-validering).
const ADMIN_VIEW_TENANT_COOKIE = "pax_admin_viewing_tenant";

export type BrugerMedTenant = {
  user_id: number;
  email: string;
  fulde_navn: string | null;
  role: "admin" | "jurist";
  // tenant_id: brugerens RIGTIGE/EJEDE tenant (fra users.tenant_id i DB).
  //   Bruges til identitet — "hvem er denne person", audit-log "who did
  //   this", og som default-værdi.
  tenant_id: number;
  // effektiv_tenant_id: hvilken tenant systemet SKAL OPERERE PÅ for
  //   denne request. For 99% af brugere (ikke-admins) er den ALTID
  //   identisk med tenant_id — ingen adfærdsforskel.
  //   For admins der har valgt "view as <tenant X>" via tenant-switcheren,
  //   er den sat til den valgte tenant. Bruges til data-viewing queries
  //   (arkiv, audit-log, sager, jobs).
  effektiv_tenant_id: number;
  tenant_slug: string;
  tenant_navn: string;
  // effektiv_sprog: locale for det EFFEKTIVE tenant (norsk tenant → 'no').
  //   Bruges til UI-oversættelse via i18n/t.ts. Falder tilbage til 'da'
  //   hvis tenant.sprog er null/ugyldig.
  effektiv_sprog: Locale;
};

// Slår en bruger op via Supabase Auth UUID og returnerer både
// user-row og tenant-info i ét hop. Returnerer null hvis brugeren
// ikke er linket i users-tabellen (det sker hvis brugeren er
// oprettet i Supabase Auth men ikke endnu inviteret i admin-UI'en).
//
// effektiv_tenant_id-håndtering:
// - Default: identisk med tenant_id (bit-identisk adfærd som før)
// - Hvis role='admin' OG en gyldig cookie sætter override: override-tenant
// - I alle andre tilfælde: tenant_id (sikker fallback)
export async function hentBrugerMedTenant(
  supabaseUserId: string,
): Promise<BrugerMedTenant | null> {
  type BaseRow = Omit<BrugerMedTenant, "effektiv_tenant_id" | "effektiv_sprog"> & {
    egen_sprog: string | null;
  };
  const rows = await query<BaseRow>(
    `
    SELECT
      u.id           AS user_id,
      u.email        AS email,
      u.fulde_navn   AS fulde_navn,
      u.role         AS role,
      t.id           AS tenant_id,
      t.slug         AS tenant_slug,
      t.navn         AS tenant_navn,
      t.sprog        AS egen_sprog
    FROM users u
    JOIN tenants t ON t.id = u.tenant_id
    WHERE u.supabase_user_id = $1
    LIMIT 1
    `,
    [supabaseUserId],
  );

  const base = rows[0];
  if (!base) return null;

  // Default: ingen override, effektiv === tenant_id (zero behavior change)
  const bruger: BrugerMedTenant = {
    user_id: base.user_id,
    email: base.email,
    fulde_navn: base.fulde_navn,
    role: base.role,
    tenant_id: base.tenant_id,
    tenant_slug: base.tenant_slug,
    tenant_navn: base.tenant_navn,
    effektiv_tenant_id: base.tenant_id,
    effektiv_sprog: normaliserLocale(base.egen_sprog),
  };

  // KUN admins kan have en override. Ikke-admins bruger ALTID deres egen
  // tenant — uanset om en cookie skulle være sat (defensiv vs cookie-tampering).
  if (bruger.role === "admin") {
    const override = await _laesAdminViewTenantOverride();
    if (override !== null && override !== bruger.tenant_id) {
      // Verificér at override-tenant faktisk findes — beskytter mod
      // stale cookies efter en tenant er blevet slettet.
      // Hent også sprog for override-tenant så UI også skifter.
      const exists = await query<{ id: number; sprog: string | null }>(
        `SELECT id, sprog FROM tenants WHERE id=$1 LIMIT 1`,
        [override],
      );
      if (exists.length === 1) {
        bruger.effektiv_tenant_id = override;
        bruger.effektiv_sprog = normaliserLocale(exists[0].sprog);
      }
    }
  }

  return bruger;
}

// Læser admin-view-as-tenant cookie via Next.js' cookies()-API.
// Returnerer parsed tenant-id eller null hvis ingen cookie, ugyldig
// værdi, eller funktionen kaldes uden for en Next.js request-context
// (fx fra scripts). Aldrig throw'er — fail safe = ingen override.
async function _laesAdminViewTenantOverride(): Promise<number | null> {
  try {
    // Lazy import så filen stadig kan importeres fra ikke-Next contexts
    // (fx test-scripts). I et server component/action/route er cookies()
    // tilgængelig; ellers throw'er den og vi fanger.
    const { cookies } = await import("next/headers");
    const cookieStore = await cookies();
    const raw = cookieStore.get(ADMIN_VIEW_TENANT_COOKIE)?.value;
    if (!raw) return null;
    const parsed = parseInt(raw, 10);
    if (!Number.isFinite(parsed) || parsed <= 0) return null;
    return parsed;
  } catch {
    return null;
  }
}

// Eksporteres så API-endpointet kan bruge samme cookie-navn — undgår
// silent drift mellem læser og skriver.
export const ADMIN_VIEW_TENANT_COOKIE_NAME = ADMIN_VIEW_TENANT_COOKIE;

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
