// Postgres-helper. Mirrorer eksisterende Python database.py's _connect:
// bruger samme DATABASE_URL og samme postgres-rolle.
//
// Pool er global (genbruges på tværs af requests) så vi ikke åbner
// nye connections ved hver SQL-kald — vigtigt for serverless deploy
// hvor cold-start ellers ville koste 50-100ms per request.
//
// Server-side ONLY: denne fil må ALDRIG importeres fra Client
// Components ('use client'). DATABASE_URL er en hemmelig nøgle og
// skal aldrig nå browseren.
import { Pool } from "pg";

declare global {
  var _pgPool: Pool | undefined;
}

function lavPool(): Pool {
  // Foretrækker TRANSACTION-pooler (port 6543) hvis tilgængelig — den
  // understøtter ~200 samtidige connections vs 15 i SESSION mode (5432).
  // Pg-boss kræver SESSION mode (LISTEN/NOTIFY), så den bruger fortsat
  // DATABASE_URL direkte; alle andre queries går via den her.
  const url =
    process.env.DATABASE_URL_TRANSACTION ?? process.env.DATABASE_URL;
  if (!url) {
    throw new Error("DATABASE_URL er ikke sat (tjek .env.local)");
  }
  return new Pool({
    connectionString: url,
    // Reduceret max — vi vil ikke ramme connection-limit selv ved
    // pludselige spike i load. Transaction-poolen håndterer
    // many-at-once internt.
    max: 5,
    idleTimeoutMillis: 10_000,
    // PgBouncer i transaction mode understøtter ikke prepared statements
    // automatisk — pg-pakken bruger ikke prepared statements som default,
    // så dette er en sikkerhedsforanstaltning hvis vi tilføjer det.
    statement_timeout: 30_000,
  });
}

// Genbrug pool på tværs af hot-reloads i development (Next.js
// re-importerer moduler ved hver gemt fil; uden global-cache ville
// vi lække connections).
export const pool: Pool = global._pgPool ?? lavPool();
if (process.env.NODE_ENV !== "production") {
  global._pgPool = pool;
}

// Convenience-wrapper: query<T>("SELECT ...", [params])
//   → returnerer rows som T[]
export async function query<T = Record<string, unknown>>(
  sql: string,
  params: unknown[] = [],
): Promise<T[]> {
  const result = await pool.query(sql, params);
  return result.rows as T[];
}
