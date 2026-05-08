// Queries for analyse_arkiv-tabellen.
// Server-side ONLY (importerer db.ts som bruger DATABASE_URL).
//
// Tenant-isolation håndhæves i alle queries: cross-tenant read/write
// afvises i SQL-laget.
import "server-only";
import { query } from "@/lib/db";

export type ArkivType = "analyse" | "svarbrev" | "tjekliste";

export type ArkivRaekke = {
  id: number;
  titel: string;
  type: ArkivType;
  klage_filnavn: string | null;
  oprettet_dato: string;
};

export type ArkivRaekkeFuld = ArkivRaekke & {
  indhold: string;
  spoergsmaal: string | null;
  sagsakter: string | null;
  ekstra_instrukser: string | null;
};

export async function gemIArkiv(args: {
  titel: string;
  type: ArkivType;
  indhold: string;
  tenantId: number;
  klageFilnavn?: string | null;
  spoergsmaal?: string | null;
  sagsakter?: string | null;
  ekstraInstrukser?: string | null;
}): Promise<number | null> {
  const rows = await query<{ id: number }>(
    `
    INSERT INTO analyse_arkiv
      (titel, type, klage_filnavn, spoergsmaal, sagsakter,
       ekstra_instrukser, indhold, tenant_id)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    RETURNING id
    `,
    [
      args.titel,
      args.type,
      args.klageFilnavn ?? null,
      args.spoergsmaal ?? null,
      args.sagsakter ?? null,
      args.ekstraInstrukser ?? null,
      args.indhold,
      args.tenantId,
    ],
  );
  return rows[0]?.id ?? null;
}

export async function hentArkiv(
  tenantId: number,
  begraens: number = 50,
  filter?: ArkivType,
): Promise<ArkivRaekke[]> {
  if (filter) {
    return await query<ArkivRaekke>(
      `
      SELECT id, titel, type, klage_filnavn, oprettet_dato
        FROM analyse_arkiv
       WHERE tenant_id=$1 AND type=$2
       ORDER BY oprettet_dato DESC
       LIMIT $3
      `,
      [tenantId, filter, begraens],
    );
  }
  return await query<ArkivRaekke>(
    `
    SELECT id, titel, type, klage_filnavn, oprettet_dato
      FROM analyse_arkiv
     WHERE tenant_id=$1
     ORDER BY oprettet_dato DESC
     LIMIT $2
    `,
    [tenantId, begraens],
  );
}

export async function hentArkivById(
  id: number,
  tenantId: number,
): Promise<ArkivRaekkeFuld | null> {
  const rows = await query<ArkivRaekkeFuld>(
    `
    SELECT id, titel, type, klage_filnavn, spoergsmaal,
           sagsakter, ekstra_instrukser, indhold, oprettet_dato
      FROM analyse_arkiv
     WHERE id=$1 AND tenant_id=$2
     LIMIT 1
    `,
    [id, tenantId],
  );
  return rows[0] ?? null;
}

export async function sletFraArkiv(
  id: number,
  tenantId: number,
): Promise<boolean> {
  const rows = await query<{ id: number }>(
    `
    DELETE FROM analyse_arkiv
     WHERE id=$1 AND tenant_id=$2
    RETURNING id
    `,
    [id, tenantId],
  );
  return rows.length > 0;
}
