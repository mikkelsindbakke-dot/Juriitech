// Worker-process der trækker førstevurderings-jobs fra pg-boss-køen
// og udfører dem ved at kalde FastAPI internt.
//
// Designprincipper:
//   1. Idempotent: hvis vi crasher midt i et job, kan vi genstarte
//      uden at dobbeltkøre dyre Anthropic-kald. analyse_jobs.status
//      holder progress; vi tjekker den før hvert trin.
//   2. Concurrency-kontrolleret: kun N samtidige jobs pr. worker
//      (default 2, justérbar via PAX_WORKER_CONCURRENCY).
//   3. Retry med exponential backoff på 5xx fra FastAPI eller
//      Anthropic-overload — KUN hvis det er sikkert at retry'e
//      (ingen partial side-effects).
//   4. Sentry-context på hver fejl: tenant, user, job-id, trin.
//
// Worker startes via entrypoint-next.sh som "node dist/worker.js"
// eller direkte via tsx i dev.

import "server-only";
import type { Job } from "pg-boss";
import { Buffer } from "node:buffer";
import { setTimeout as sleep } from "node:timers/promises";
import { Agent, setGlobalDispatcher } from "undici";
import * as Sentry from "@sentry/nextjs";
import {
  getBoss,
  QUEUE_FOERSTEVURDERING,
} from "@/lib/queue/pg-boss-client";
import {
  hentJobFiler,
  markérJobRunning,
  markérJobCompleted,
  markérJobFailed,
} from "@/lib/queries/analyse-jobs";

// FastAPI på localhost (samme container).
const FASTAPI_URL = process.env.PAX_FASTAPI_URL || "http://127.0.0.1:8000";

// Hvor mange jobs worker'en må processere samtidig. Holder vi lav (2)
// så FastAPI ikke overbelastes som i den første load-test (5 = OOM).
// Når Fly scales op kan vi tweake.
const WORKER_CONCURRENCY = parseInt(
  process.env.PAX_WORKER_CONCURRENCY || "2",
  10,
);

// Max retries pr. job. Med exponential backoff: 1s, 2s, 4s — total
// max ekstra ventetid ~7s. Hvis disse mislykkes er det permanent.
const MAX_RETRIES = 3;

// Hvor mange sekunder vi venter på FastAPI-svar pr. retry-forsøg.
// 10 min er rigeligt: én analyse tager ~3 min, men under load (3
// concurrent) kan en analyse strækkes til 5-8 min pga. ressourcedeling.
const FETCH_TIMEOUT_MS = 600_000;

// Node.js' undici (default fetch-impl) har 300s default headers/body-
// timeouts der overrider AbortController. Vi sætter dem til 10 min så
// lange AI-kald ikke crasher med "fetch failed". Global dispatcher
// gælder alle fetch-kald i worker-processen — det er fint, vi har kun
// ét sted vi laver lange fetches.
setGlobalDispatcher(
  new Agent({
    headersTimeout: FETCH_TIMEOUT_MS,
    bodyTimeout: FETCH_TIMEOUT_MS,
  }),
);


type JobPayload = { jobDbId: string };

function vent_med_backoff(forsoeg: number): Promise<void> {
  // 1s, 2s, 4s, 8s ... men cap'et på 30s
  const ms = Math.min(1000 * 2 ** forsoeg, 30_000);
  return sleep(ms);
}

function kategoriser_fastapi_fejl(status: number, body: string): string {
  if (status === 503) return "overload_eller_proxy";
  if (status === 422) return "validation";
  if (status === 401 || status === 403) return "auth";
  if (status >= 500) return "server_error";
  if (status >= 400) return "client_error";
  if (body.toLowerCase().includes("overload")) return "overload";
  if (body.toLowerCase().includes("rate")) return "rate_limit";
  return "other";
}

/**
 * Eksekverer ÉN førstevurdering ved at kalde FastAPI internt.
 * Returnerer resultat-JSON eller kaster ved fejl.
 */
async function kør_foerstevurdering(jobDbId: string): Promise<{
  resultat: Record<string, unknown>;
}> {
  const filer = await hentJobFiler(jobDbId);
  const sagsakter = await hent_input_sagsakter(jobDbId);

  // Byg multipart form-data identisk med hvad upload-form ville sende
  const form = new FormData();
  for (const f of filer) {
    const blob = new Blob([f.bytes as BlobPart], { type: f.mime_type });
    form.append("filer", blob, f.filnavn);
  }
  form.append("sagsakter", sagsakter ?? "");

  // For at undgå at gå gennem vores egen api-proxy (cirkulær), kalder
  // worker'en FastAPI direkte på localhost:8000.
  const url = `${FASTAPI_URL}/api/foerstevurdering`;

  // Auth: worker er server-side og har service_role_key. Vi minter en
  // worker-JWT via service_role_key? NEJ — simpler: bypass auth ved at
  // sende en intern header som FastAPI checker. Men det kræver
  // ændringer i FastAPI. Alternativt: hent en gyldig JWT fra Supabase
  // admin API for job-ejeren.
  const auth = await mint_jwt_for_job(jobDbId);
  if (!auth || !auth.jwt) {
    throw new Error("Kunne ikke minte JWT til worker");
  }

  // Tenant-override-cookie: når admin har uploadet via "view as"-flow er
  // job.tenant_id != JWT-ejerens egen tenant. FastAPI's aktiv_tenant-dep
  // honorerer cookien KUN for admin-rolle (silently ignoreret ellers),
  // så vi sender den altid med — det er trygt for non-admin og kritisk
  // for admin-impersoneret upload (uden den ville aktiv_tenant returnere
  // admins egen tenant og hele sprog/RAG/branding ryger forkert).
  const cookieHeader =
    auth.tenantId != null
      ? `pax_admin_viewing_tenant=${auth.tenantId}`
      : "";

  // Med timeout via AbortController
  const ctrl = new AbortController();
  const timeoutId = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);

  let resp: Response;
  try {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${auth.jwt}`,
    };
    if (cookieHeader) headers["Cookie"] = cookieHeader;
    resp = await fetch(url, {
      method: "POST",
      headers,
      body: form,
      signal: ctrl.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }

  if (!resp.ok) {
    const txt = await resp.text().catch(() => "");
    const fejlKat = kategoriser_fastapi_fejl(resp.status, txt);
    const err = new Error(
      `FastAPI returnerede ${resp.status}: ${txt.slice(0, 200)}`,
    );
    (err as Error & { statusKode?: number; kategori?: string }).statusKode =
      resp.status;
    (err as Error & { statusKode?: number; kategori?: string }).kategori =
      fejlKat;
    throw err;
  }

  const resultat = (await resp.json()) as Record<string, unknown>;
  return { resultat };
}

async function hent_input_sagsakter(jobDbId: string): Promise<string | null> {
  const { query } = await import("@/lib/db");
  const rows = await query<{ input_sagsakter: string | null }>(
    "SELECT input_sagsakter FROM analyse_jobs WHERE id = $1",
    [jobDbId],
  );
  return rows[0]?.input_sagsakter ?? null;
}

/**
 * Genererer en kortvarig JWT for job-ejeren via Supabase admin API.
 * Worker'en kører ikke som en specifik bruger, men FastAPI's
 * aktiv_tenant-dependency kræver en gyldig JWT. Vi laver en magic-link
 * for ejer-emailen og forløser den straks.
 *
 * Returnerer både JWT og job.tenant_id så kalderen kan sætte
 * pax_admin_viewing_tenant-cookien — det er den der sikrer at FastAPI
 * bruger job'ets tenant (ikke admin'ens egen) ved admin-impersoneret
 * upload. Tidligere logik der ledte efter en alt-bruger i job.tenant_id
 * fejlede for tenants uden brugere (fx TUI hvor admin er den eneste).
 *
 * Race-condition: Supabase invaliderer tidligere OTP når en ny genereres
 * for samme email. Når samme bruger submitter 2 jobs samtidig kan worker
 * A's OTP blive ugyldiggjort af worker B's generate_link før A's verify.
 * Vi retry'er én gang på otp_expired — den genererer en helt fersk OTP
 * der typisk vinder ræset næste gang.
 *
 * KUN brugbart server-side; kræver SUPABASE_SERVICE_KEY.
 */
async function mint_jwt_for_job(
  jobDbId: string,
): Promise<{ jwt: string; tenantId: number | null } | null> {
  const { query } = await import("@/lib/db");

  const rows = await query<{
    user_email: string | null;
    tenant_id: number | null;
  }>(
    "SELECT user_email, tenant_id FROM analyse_jobs WHERE id = $1",
    [jobDbId],
  );
  const jobUserEmail = rows[0]?.user_email;
  const jobTenantId = rows[0]?.tenant_id ?? null;

  const email = jobUserEmail;
  if (!email) return null;

  const supUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const serviceKey = process.env.SUPABASE_SERVICE_KEY;
  if (!supUrl || !anonKey || !serviceKey) {
    throw new Error(
      "Supabase env-vars mangler — kan ikke minte worker-JWT",
    );
  }

  for (let forsoeg = 1; forsoeg <= 2; forsoeg++) {
    // 1. Generér magic-link — returnerer både email_otp og hashed_token.
    const linkResp = await fetch(`${supUrl}/auth/v1/admin/generate_link`, {
      method: "POST",
      headers: {
        apikey: serviceKey,
        Authorization: `Bearer ${serviceKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ type: "magiclink", email }),
    });
    if (!linkResp.ok) {
      throw new Error(
        `generate_link fejlede (${linkResp.status}): ${(await linkResp.text()).slice(0, 200)}`,
      );
    }
    const linkData = (await linkResp.json()) as {
      email_otp?: string;
      hashed_token?: string;
    };
    const otp = linkData.email_otp;
    if (!otp) {
      throw new Error("email_otp mangler i generate_link-svar");
    }

    // 2. Verificér OTP via POST /verify — returnerer session som JSON.
    const verifyResp = await fetch(`${supUrl}/auth/v1/verify`, {
      method: "POST",
      headers: {
        apikey: anonKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        type: "magiclink",
        token: otp,
        email,
      }),
    });

    if (verifyResp.ok) {
      const verifyData = (await verifyResp.json()) as {
        access_token?: string;
      };
      if (!verifyData.access_token) {
        throw new Error("access_token mangler i verify-svar");
      }
      console.log(
        `[worker] mint_jwt_for_job: job=${jobDbId} user='${email}' ` +
          `tenant_override=${jobTenantId ?? "(none)"}`,
      );
      return { jwt: verifyData.access_token, tenantId: jobTenantId };
    }

    const fejlTekst = (await verifyResp.text()).slice(0, 300);
    const erOtpExpired =
      verifyResp.status === 403 && fejlTekst.includes("otp_expired");

    // Kun otp_expired retries — andre fejl er ikke race-relateret.
    if (!erOtpExpired || forsoeg === 2) {
      throw new Error(`verify fejlede (${verifyResp.status}): ${fejlTekst}`);
    }

    console.log(
      `[worker] OTP race detekteret for ${email} (forsøg ${forsoeg}) — genererer ny`,
    );
    // Lille jitter så samtidige workers ikke retry'er synkront.
    await new Promise((r) => setTimeout(r, 100 + Math.random() * 400));
  }

  // Uopnåelig, men TypeScript kræver eksplicit returværdi.
  return null;
}

/**
 * Hovedhåndterer for et job.
 * Idempotent: tjekker status før den arbejder, så et restart ikke
 * dobbeltkører.
 */
async function håndter_job(payload: JobPayload): Promise<void> {
  const { jobDbId } = payload;
  console.log(`[worker] Modtog job ${jobDbId}`);

  // Idempotency-tjek: er jobbet allerede færdigt?
  const { query } = await import("@/lib/db");
  const eksisterende = await query<{ status: string; forsoeg: number }>(
    "SELECT status, forsoeg FROM analyse_jobs WHERE id = $1",
    [jobDbId],
  );
  if (eksisterende.length === 0) {
    console.warn(`[worker] Job ${jobDbId} findes ikke i DB — skipper`);
    return;
  }
  const status = eksisterende[0].status;
  if (status === "completed") {
    console.log(`[worker] Job ${jobDbId} allerede completed — skipper`);
    return;
  }

  // Markér som running (transactional)
  await markérJobRunning(jobDbId);

  // Eksekvér med exponential backoff retry
  let sidsteFejl: unknown = null;
  for (let forsoeg = 0; forsoeg < MAX_RETRIES; forsoeg++) {
    try {
      const { resultat } = await kør_foerstevurdering(jobDbId);

      // Pluk token-forbrug hvis FastAPI returnerer det (kan udvides)
      await markérJobCompleted(jobDbId, resultat);
      console.log(`[worker] Job ${jobDbId} completed efter ${forsoeg + 1} forsøg`);
      return;
    } catch (e) {
      sidsteFejl = e;
      const kat =
        (e as { kategori?: string }).kategori ??
        (e instanceof Error ? e.name : "unknown");
      const skalRetry =
        kat === "overload" ||
        kat === "rate_limit" ||
        kat === "overload_eller_proxy" ||
        kat === "server_error";
      if (!skalRetry || forsoeg === MAX_RETRIES - 1) {
        // Permanent fejl — markér failed
        const besked = e instanceof Error ? e.message : String(e);
        Sentry.captureException(e, {
          tags: { source: "worker.foerstevurdering", jobId: jobDbId, kategori: kat },
        });
        await markérJobFailed(jobDbId, besked, kat);
        console.error(
          `[worker] Job ${jobDbId} FAILED efter ${forsoeg + 1} forsøg: ${besked}`,
        );
        return;
      }
      console.warn(
        `[worker] Job ${jobDbId} fejlede (${kat}), retry ${forsoeg + 1}/${MAX_RETRIES}`,
      );
      await vent_med_backoff(forsoeg);
    }
  }

  // Burde aldrig ramme her, men for completeness:
  const besked = sidsteFejl instanceof Error ? sidsteFejl.message : String(sidsteFejl);
  await markérJobFailed(jobDbId, besked, "max_retries");
}

/**
 * Starter worker-loopet. Kører indtil processen dræbes.
 */
export async function startWorker(): Promise<void> {
  console.log(
    `[worker] Starter pg-boss worker (concurrency=${WORKER_CONCURRENCY})`,
  );
  const boss = await getBoss();

  // pg-boss v12 API: createQueue + work(queueName, handler)
  await boss.createQueue(QUEUE_FOERSTEVURDERING);
  await boss.work<JobPayload>(
    QUEUE_FOERSTEVURDERING,
    {
      // batchSize: max samtidige jobs denne worker-instans håndterer
      batchSize: WORKER_CONCURRENCY,
      pollingIntervalSeconds: 1,
    },
    async (jobs: Job<JobPayload>[]) => {
      // pg-boss v12 leverer batch — vi processer parallelt op til batchSize
      await Promise.all(
        jobs.map(async (job: Job<JobPayload>) => {
          try {
            await håndter_job(job.data);
          } catch (e) {
            // Burde aldrig hænde fordi håndter_job catches alt selv,
            // men sikkerheds-net.
            Sentry.captureException(e, {
              tags: { source: "worker.batch", jobId: job.id },
            });
            console.error(`[worker] Uventet fejl i job ${job.id}:`, e);
          }
        }),
      );
    },
  );

  console.log("[worker] Tilmeldt kø — venter på jobs");
}
