import "server-only";
import { query } from "@/lib/db";
import { headers } from "next/headers";

// GDPR audit-logging. Skriver direkte til gdpr_audit_log via samme
// Postgres-pool som de øvrige queries — én roundtrip pr. handling,
// ingen FastAPI-hop. Schemaet matcher Python-siden, så audit-rows
// fra Next.js-admin og fra api/main.py-endpoints er identiske formatet.
//
// Fail-safe: ALLE fejl swallowes. En admin-handling må ALDRIG fejle
// fordi audit-logning fejlede. Sentry vil fange evt. underliggende
// DB-problemer separat hvis der er tale om noget systemisk.

export type AuditHandling =
  | "upload"
  | "analyse"
  | "visning"
  | "eksport"
  | "anonymisering"
  | "sletning"
  | "cross_tenant_share"
  | "tilbage_kald"
  | "login_success"
  | "login_failed"
  | "logout"
  | "password_reset"
  | "admin_user_oprettet"
  | "admin_user_slettet"
  | "admin_user_inviteret"
  | "admin_tenant_oprettet"
  | "admin_tenant_opdateret"
  | "admin_proeve_tenant_oprettet"
  | "admin_proeve_tenant_konverteret"
  | "admin_proeve_tenant_forlaenget"
  | "admin_proeve_tenant_data_purged";

export type AuditInput = {
  handling: AuditHandling;
  tenantId: number;
  sagId?: string | number | null;
  userId?: number | null;
  userEmail?: string | null;
  metadata?: Record<string, unknown> | null;
};

// Henter klientens IP-adresse fra request-headers. Fly proxy sender
// ægte client-IP i Fly-Client-IP; ellers falder vi tilbage til
// x-forwarded-for (første hop). Hvis ingen header er sat (lokal dev
// uden proxy), returneres null.
async function hentIp(): Promise<string | null> {
  try {
    const h = await headers();
    return (
      h.get("fly-client-ip") ||
      h.get("x-forwarded-for")?.split(",")[0]?.trim() ||
      h.get("x-real-ip") ||
      null
    );
  } catch {
    return null;
  }
}

/**
 * Skriv én række til gdpr_audit_log. Fail-safe — sluger alle fejl
 * og logger dem til stderr så de fanges af Fly logs + Sentry.
 *
 * Eksempel:
 *   await skrivGdprAudit({
 *     handling: "admin_user_inviteret",
 *     tenantId: 1,
 *     userId: aktuelAdmin.user_id,
 *     userEmail: aktuelAdmin.email,
 *     sagId: nyBrugerEmail,
 *     metadata: { ny_bruger_role: "jurist" },
 *   });
 */
export async function skrivGdprAudit(input: AuditInput): Promise<void> {
  try {
    const ip = await hentIp();
    await query(
      `
      INSERT INTO gdpr_audit_log
        (sag_id, tenant_id, handling, metadata,
         user_id, user_email, ip_adresse)
      VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7::inet)
      `,
      [
        input.sagId === null || input.sagId === undefined ? "n/a" : String(input.sagId),
        input.tenantId,
        input.handling,
        JSON.stringify(input.metadata ?? {}),
        input.userId ?? null,
        input.userEmail?.toLowerCase() ?? null,
        ip,
      ],
    );
  } catch (e) {
    console.error("skrivGdprAudit fejlede (ikke kritisk):", e);
  }
}


// ─────────── HENT (læse-vej for admin-UI) ───────────

export type AuditRow = {
  id: number;
  tidspunkt: string;
  handling: AuditHandling;
  sag_id: string;
  tenant_id: number;
  user_id: number | null;
  user_email: string | null;
  ip_adresse: string | null;
  metadata: Record<string, unknown> | null;
};

export type AuditFilter = {
  tenantId?: number | null;
  userId?: number | null;
  sagId?: string | null;
  handling?: AuditHandling | null;
  limit?: number;
};

/**
 * Hent rækker fra gdpr_audit_log med filter. Kun til admin-brug —
 * caller skal selv håndhæve role-check + tenant-scoping.
 *
 * Returnerer nyeste først. Maks 2000 rækker pr. query (clamped).
 */
export async function hentGdprAuditLog(
  filter: AuditFilter = {},
): Promise<AuditRow[]> {
  const where: string[] = [];
  const params: unknown[] = [];

  if (filter.tenantId !== undefined && filter.tenantId !== null) {
    params.push(filter.tenantId);
    where.push(`tenant_id = $${params.length}`);
  }
  if (filter.userId !== undefined && filter.userId !== null) {
    params.push(filter.userId);
    where.push(`user_id = $${params.length}`);
  }
  if (filter.sagId) {
    params.push(filter.sagId);
    where.push(`sag_id = $${params.length}`);
  }
  if (filter.handling) {
    params.push(filter.handling);
    where.push(`handling = $${params.length}`);
  }

  const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";
  const limit = Math.min(Math.max(filter.limit ?? 200, 1), 2000);
  params.push(limit);

  const rows = await query<{
    id: number;
    tidspunkt: Date;
    handling: AuditHandling;
    sag_id: string;
    tenant_id: number;
    user_id: number | null;
    user_email: string | null;
    ip_adresse: string | null;
    metadata: Record<string, unknown> | null;
  }>(
    `SELECT id, tidspunkt, handling, sag_id, tenant_id,
            user_id, user_email, ip_adresse::text AS ip_adresse, metadata
       FROM gdpr_audit_log
       ${whereSql}
       ORDER BY tidspunkt DESC
       LIMIT $${params.length}`,
    params,
  );

  return rows.map((r) => ({
    ...r,
    tidspunkt: r.tidspunkt instanceof Date ? r.tidspunkt.toISOString() : String(r.tidspunkt),
    ip_adresse: r.ip_adresse,
  }));
}
