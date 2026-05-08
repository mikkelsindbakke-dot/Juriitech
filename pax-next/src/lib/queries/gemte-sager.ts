// Queries for gemte_sager-tabellen.
// Server-side ONLY (importerer db.ts som bruger DATABASE_URL).
//
// Tenant-isolation håndhæves i alle queries: cross-tenant read/write
// afvises i SQL-laget — vi stoler IKKE på application-laget alene.
import "server-only";
import { query } from "@/lib/db";

export type GemtSag = {
  id: number;
  titel: string;
  oprettet_dato: string;
  opdateret_dato: string;
};

export type GemtSagFuld = GemtSag & {
  state_json: string;
  user_id: string | null;
};

export async function gemSag(args: {
  titel: string;
  stateJson: string;
  userId: string;
  tenantId: number;
  sagId?: number;
}): Promise<number | null> {
  const { titel, stateJson, userId, tenantId, sagId } = args;

  if (sagId) {
    // Update — kun hvis sagen tilhører tenant'en (cross-tenant afvises)
    const rows = await query<{ id: number }>(
      `
      UPDATE gemte_sager
         SET titel=$1, state_json=$2, opdateret_dato=CURRENT_TIMESTAMP
       WHERE id=$3 AND tenant_id=$4
      RETURNING id
      `,
      [titel, stateJson, sagId, tenantId],
    );
    return rows[0]?.id ?? null;
  }

  // Insert
  const rows = await query<{ id: number }>(
    `
    INSERT INTO gemte_sager (user_id, titel, state_json, tenant_id)
    VALUES ($1, $2, $3, $4)
    RETURNING id
    `,
    [userId, titel, stateJson, tenantId],
  );
  return rows[0]?.id ?? null;
}

export async function hentGemteSager(
  tenantId: number,
  begraens: number = 50,
): Promise<GemtSag[]> {
  return await query<GemtSag>(
    `
    SELECT id, titel, oprettet_dato, opdateret_dato
      FROM gemte_sager
     WHERE tenant_id=$1
     ORDER BY opdateret_dato DESC
     LIMIT $2
    `,
    [tenantId, begraens],
  );
}

export async function hentSagById(
  id: number,
  tenantId: number,
): Promise<GemtSagFuld | null> {
  const rows = await query<GemtSagFuld>(
    `
    SELECT id, titel, state_json, user_id, oprettet_dato, opdateret_dato
      FROM gemte_sager
     WHERE id=$1 AND tenant_id=$2
     LIMIT 1
    `,
    [id, tenantId],
  );
  return rows[0] ?? null;
}

export async function sletSag(
  id: number,
  tenantId: number,
): Promise<boolean> {
  const rows = await query<{ id: number }>(
    `
    DELETE FROM gemte_sager
     WHERE id=$1 AND tenant_id=$2
    RETURNING id
    `,
    [id, tenantId],
  );
  return rows.length > 0;
}
