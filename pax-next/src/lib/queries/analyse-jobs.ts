import "server-only";
import { query, pool } from "@/lib/db";
import crypto from "node:crypto";

// Server-side DB-queries for analyse_jobs-tabellen. Job-koreografi
// håndteres af pg-boss; vi bruger denne tabel til input-bytes + final
// resultat (pg-boss data-felt er for lille til 16 MB filer).

export type JobStatus = "pending" | "running" | "completed" | "failed";

export type AnalyseJob = {
  id: string;
  tenant_id: number;
  user_id: number | null;
  user_email: string | null;
  status: JobStatus;
  idempotency_key: string | null;
  input_sagsakter: string | null;
  input_filer_meta: Record<string, unknown> | null;
  resultat: Record<string, unknown> | null;
  fejl_besked: string | null;
  fejl_kategori: string | null;
  forsoeg: number;
  oprettet: string;
  startet: string | null;
  faerdig: string | null;
};

export type FilInput = {
  filnavn: string;
  bytes: Buffer;
  mime_type: string;
};

/**
 * Bygger en idempotency-key fra input-filer + sagsakter.
 * Samme input → samme key → samme job (genbruges hvis < 1 time gammelt).
 */
export function bygIdempotencyKey(args: {
  tenantId: number;
  userId: number | null;
  filer: FilInput[];
  sagsakter: string;
}): string {
  const h = crypto.createHash("sha256");
  h.update(`tenant:${args.tenantId}|user:${args.userId ?? "none"}|`);
  // Filnavne + længde — vi hasher IKKE selve bytes pga. ydelse,
  // men filnavn+længde er nok til at fange dubletter inden for kort tid.
  const sorteret = [...args.filer].sort((a, b) =>
    a.filnavn.localeCompare(b.filnavn),
  );
  for (const f of sorteret) {
    h.update(`${f.filnavn}:${f.bytes.length}|`);
  }
  h.update(`sa:${args.sagsakter.length}`);
  return h.digest("hex").slice(0, 32);
}

/**
 * Opretter et nyt analyse-job + gemmer input-filer.
 * Returnerer job-ID. Idempotent: hvis samme idempotency_key findes
 * og er < 1 time gammel + ikke fejlet, returneres eksisterende job.
 */
export async function opretJob(args: {
  tenantId: number;
  userId: number | null;
  userEmail: string | null;
  filer: FilInput[];
  sagsakter: string;
  idempotencyKey: string;
}): Promise<{ jobId: string; genbrugt: boolean }> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    // Tjek for eksisterende job med samme idempotency_key
    const eksisterende = await client.query<{ id: string; status: JobStatus }>(
      `SELECT id, status FROM analyse_jobs
       WHERE idempotency_key = $1
         AND tenant_id = $2
         AND oprettet > NOW() - INTERVAL '1 hour'
         AND status IN ('pending', 'running', 'completed')
       ORDER BY oprettet DESC LIMIT 1`,
      [args.idempotencyKey, args.tenantId],
    );

    if (eksisterende.rows.length > 0) {
      await client.query("COMMIT");
      return { jobId: eksisterende.rows[0].id, genbrugt: true };
    }

    // Opret nyt job
    const filerMeta = args.filer.map((f) => ({
      filnavn: f.filnavn,
      bytes: f.bytes.length,
      mime_type: f.mime_type,
    }));

    const job = await client.query<{ id: string }>(
      `INSERT INTO analyse_jobs
         (tenant_id, user_id, user_email, idempotency_key,
          input_sagsakter, input_filer_meta, status)
       VALUES ($1, $2, $3, $4, $5, $6::jsonb, 'pending')
       RETURNING id`,
      [
        args.tenantId,
        args.userId,
        args.userEmail?.toLowerCase() ?? null,
        args.idempotencyKey,
        args.sagsakter,
        JSON.stringify(filerMeta),
      ],
    );
    const jobId = job.rows[0].id;

    // Gem fil-bytes
    for (const f of args.filer) {
      await client.query(
        `INSERT INTO analyse_job_filer (job_id, filnavn, bytes, mime_type)
         VALUES ($1, $2, $3, $4)`,
        [jobId, f.filnavn, f.bytes, f.mime_type],
      );
    }

    await client.query("COMMIT");
    return { jobId, genbrugt: false };
  } catch (e) {
    await client.query("ROLLBACK");
    throw e;
  } finally {
    client.release();
  }
}

/** Hent job-status til polling. */
export async function hentJob(
  jobId: string,
  tenantId: number,
): Promise<AnalyseJob | null> {
  const rows = await query<AnalyseJob>(
    `SELECT id::text, tenant_id, user_id, user_email, status,
            idempotency_key, input_sagsakter, input_filer_meta,
            resultat, fejl_besked, fejl_kategori, forsoeg,
            oprettet::text, startet::text, faerdig::text
     FROM analyse_jobs
     WHERE id = $1 AND tenant_id = $2`,
    [jobId, tenantId],
  );
  return rows[0] ?? null;
}

/** Hent input-filer som worker skal sende til FastAPI. */
export async function hentJobFiler(jobId: string): Promise<FilInput[]> {
  const rows = await query<{
    filnavn: string;
    bytes: Buffer;
    mime_type: string;
  }>(
    `SELECT filnavn, bytes, mime_type
     FROM analyse_job_filer
     WHERE job_id = $1
     ORDER BY id ASC`,
    [jobId],
  );
  return rows.map((r) => ({
    filnavn: r.filnavn,
    bytes: r.bytes,
    mime_type: r.mime_type,
  }));
}

/** Markér job som "running". Sætter startet-timestamp. */
export async function markérJobRunning(jobId: string): Promise<void> {
  await query(
    `UPDATE analyse_jobs
     SET status = 'running', startet = NOW(), forsoeg = forsoeg + 1
     WHERE id = $1 AND status IN ('pending', 'failed')`,
    [jobId],
  );
}

/** Markér job som "completed". Gemmer resultat-JSON. */
export async function markérJobCompleted(
  jobId: string,
  resultat: Record<string, unknown>,
  tokens?: { input?: number; output?: number },
): Promise<void> {
  await query(
    `UPDATE analyse_jobs
     SET status = 'completed',
         resultat = $2::jsonb,
         faerdig = NOW(),
         anthropic_tokens_input = $3,
         anthropic_tokens_output = $4
     WHERE id = $1`,
    [
      jobId,
      JSON.stringify(resultat),
      tokens?.input ?? null,
      tokens?.output ?? null,
    ],
  );
}

/** Markér job som "failed". Bevarer status='failed' så worker kan retry. */
export async function markérJobFailed(
  jobId: string,
  fejlBesked: string,
  fejlKategori?: string,
): Promise<void> {
  await query(
    `UPDATE analyse_jobs
     SET status = 'failed',
         fejl_besked = $2,
         fejl_kategori = $3,
         faerdig = NOW()
     WHERE id = $1`,
    [jobId, fejlBesked.slice(0, 2000), fejlKategori ?? null],
  );
}
