/**
 * Central API-klient til FastAPI-broen.
 *
 * Tre lag bygget oven på fetch:
 *   1. p-retry med eksponentielt backoff for 5xx-fejl. Anthropic-API
 *      flaker af og til, og lange AI-kald (60-90s) er for dyre at miste
 *      pga. transient infrastruktur-fejl. Vi retry'er KUN 5xx — 4xx er
 *      bruger-fejl der ikke fixes af gentagelse.
 *   2. Zod-validering af responsen så frontenden fanger shape-drift
 *      mellem FastAPI og Next.js på fetch-grænsen i stedet for længere
 *      nede i renderingen (hvor stack-trace bliver svær at finde).
 *   3. Fælles fejl-hierarki (ApiError) så kalderne kan skelne mellem
 *      "kunne ikke nå API'en" (netværks-fejl), "API svarede 4xx"
 *      (bruger-fejl) og "API svarede 5xx efter alle retries opbrugt"
 *      (server-fejl der eskaleres til brugeren).
 */
import pRetry, { AbortError } from "p-retry";
import { z, type ZodSchema } from "zod";
import { createClient } from "@/lib/supabase/client";

// ─────────── Auth-token henter ───────────
//
// Alle kald til FastAPI-broen kører multi-tenant routing — backenden
// læser Supabase JWT fra Authorization-headeren og slår brugerens
// tenant op i DB. Uden tokenet returnerer FastAPI 401, og uden
// tenant-lookup ville Apollo/Spies/test-brugere få TUI-branded svar.
//
// Vi henter sessionen via Supabase JS-klienten — den læser cookies
// og refresher tokenet automatisk hvis det er udløbet, så vi ikke
// behøver tracke expiry selv.
async function hentAuthToken(): Promise<string | null> {
  try {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  } catch {
    // Hvis Supabase ikke er konfigureret (lokal dev uden env), returnerer
    // vi null — FastAPI kører i AUTH_BYPASS-mode i den situation.
    return null;
  }
}

export class ApiError extends Error {
  status?: number;
  detalje?: string;

  constructor(besked: string, opts?: { status?: number; detalje?: string }) {
    super(besked);
    this.name = "ApiError";
    this.status = opts?.status;
    this.detalje = opts?.detalje;
  }
}

type FetchOptions = {
  // FormData posted as multipart/form-data. Vi bruger ikke JSON-body
  // fordi alle AI-endpoints tager fil-uploads.
  formData: FormData;
  // Total antal forsøg incl. det første. Default 3 — første forsøg +
  // 2 retries med eksponentielt backoff. For korte/lette kald (fx
  // sagsmetadata) brug retries=1 så brugeren ikke venter unødigt.
  retries?: number;
  // AbortSignal til at afbryde alle retry-forsøg på én gang.
  signal?: AbortSignal;
};

const STANDARD_RETRIES = 3;

/**
 * Hovedfunktion. Posts FormData til {NEXT_PUBLIC_API_URL}{path} og
 * validerer responsen mod schemaet.
 *
 * Smider ApiError ved alle fejl-tilstande. Kalderen skal håndtere
 * den (typisk via try/catch + toast).
 */
export async function postOgValider<T>(
  path: string,
  schema: ZodSchema<T>,
  opts: FetchOptions,
): Promise<T> {
  // Tom/manglende NEXT_PUBLIC_API_URL = same-origin (produktion). Sat
  // til 'http://localhost:8000' i pax-next/.env.local for lokal dev hvor
  // FastAPI kører separat. I produktion proxier Next.js rewrites
  // /api/*-stien til intern uvicorn så vi slipper for CORS + URL-bage.
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
  const url = `${baseUrl}${path}`;
  const retries = opts.retries ?? STANDARD_RETRIES;

  // Hent Supabase JWT én gang før første forsøg. Vi henter IKKE igen
  // mellem retries — hvis tokenet udløber midt i en retry-loop, er det
  // sandsynligvis kun millisekunder forskel, og at hente nyt token ved
  // hver retry ville fordoble Supabase-kald uden gevinst i normalt flow.
  const token = await hentAuthToken();

  const operation = async (): Promise<T> => {
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        body: opts.formData,
        headers,
        signal: opts.signal,
      });
    } catch (e) {
      // Netværks-fejl — værd at retry'e (DNS-flap, kortvarig forbindelses-
      // mistring osv.). Beskeden er KOMPLET BRUGER-VENLIG — endpoint-stien
      // havner i detalje-feltet og vises kun til admin via et expander.
      const tekniskDetalje = e instanceof Error ? e.message : String(e);
      throw new ApiError(
        "Forbindelsen til serveren blev kortvarigt afbrudt. Prøv igen.",
        { detalje: `endpoint=${path} · ${tekniskDetalje}` },
      );
    }

    if (!res.ok) {
      const fejlTekst = await res.text().catch(() => "");
      // FastAPI returnerer `{"detail": "..."}` ved HTTPException — pak
      // detail-strengen ud så brugervenlige beskeder ("Zip-filen er
      // krypteret — pak ud manuelt") vises som hoved-meddelelse og
      // ikke som "API svarede 422" + skjult JSON-blob.
      let besked = `API svarede ${res.status}`;
      let detalje: string | undefined = fejlTekst.slice(0, 500);
      try {
        const body = JSON.parse(fejlTekst);
        if (body && typeof body.detail === "string" && body.detail.length > 0) {
          besked = body.detail;
          detalje = undefined;
        }
      } catch {
        // Ikke JSON — behold fejlTekst som detalje
      }
      // 4xx: bruger-fejl. Stop retries — gentagelse løser ikke at
      // input er ugyldigt.
      if (res.status >= 400 && res.status < 500) {
        throw new AbortError(
          new ApiError(besked, { status: res.status, detalje }),
        );
      }
      // 5xx: lad p-retry prøve igen.
      throw new ApiError(besked, { status: res.status, detalje });
    }

    let raw: unknown;
    try {
      raw = await res.json();
    } catch (e) {
      // Ikke-JSON respons fra et endpoint der skulle returnere JSON.
      // Trumf-fejl — retry hjælper ikke. Wrap i AbortError.
      const detalje = e instanceof Error ? e.message : String(e);
      throw new AbortError(
        new ApiError(`API returnerede ugyldigt JSON`, { detalje }),
      );
    }

    // Long-poll keep-alive: api-proxy returnerer altid 200 for lange
    // endpoints og embedder den faktiske upstream-status i _proxy_status
    // for at undgå at Fly proxy lukker forbindelsen efter 60 sek. Vi
    // tjekker for feltet og eskalerer som om upstream svarede ÆGTE.
    const rawObj = raw as { _proxy_status?: number; detail?: string } | null;
    const proxyStatus =
      rawObj && typeof rawObj._proxy_status === "number"
        ? rawObj._proxy_status
        : null;
    if (proxyStatus !== null && proxyStatus >= 400) {
      const besked =
        typeof rawObj?.detail === "string" && rawObj.detail.length > 0
          ? rawObj.detail
          : `Server svarede ${proxyStatus}`;
      if (proxyStatus < 500) {
        throw new AbortError(
          new ApiError(besked, { status: proxyStatus }),
        );
      }
      throw new ApiError(besked, { status: proxyStatus });
    }

    const parsed = schema.safeParse(raw);
    if (!parsed.success) {
      // Schema-mismatch er programmer-fejl, ikke transient. Ingen retry.
      const issues = parsed.error.issues
        .slice(0, 3)
        .map((i) => `${i.path.join(".")}: ${i.message}`)
        .join("; ");
      throw new AbortError(
        new ApiError(`API-respons matcher ikke forventet form`, {
          detalje: issues,
        }),
      );
    }
    return parsed.data;
  };

  // Eksponentielt backoff: 1s, 2s, 4s mellem forsøg. minTimeout=1000
  // er bevidst — en transient Anthropic-overload tager typisk 1-3 sek
  // at clear'e, så at hammere igen efter 100ms hjælper ikke.
  return pRetry(operation, {
    retries: retries - 1, // p-retry tæller retries EFTER første forsøg
    minTimeout: 1000,
    maxTimeout: 8000,
    factor: 2,
  });
}

// ─────────── Schemas for FastAPI-responses ───────────
//
// Bevidst KONSERVATIVE — vi bruger .passthrough() og marker felter
// som .optional() når de ikke er kritiske, så små backend-tilføjelser
// (nye metadata-felter osv.) ikke breaker frontenden.

export const sagsmetadataSchema = z.object({
  sagsnummer: z.string().default(""),
  klagers_navn: z.string().default(""),
});
export type Sagsmetadata = z.infer<typeof sagsmetadataSchema>;

const begivenhedSchema = z
  .object({
    dato: z.string().optional(),
    tidspunkt: z.string().nullable().optional(),
    type: z.string().optional(),
    aktoer: z.string().optional(),
    beskrivelse: z.string().optional(),
    betydning: z.string().optional(),
  })
  .passthrough();

const tidsforholdSchema = z
  .object({
    rejseperiode: z.string().optional(),
    antal_naetter: z.number().optional(),
    har_problematisk_forsinkelse: z.boolean().optional(),
    kunne_ikke_udledes: z.boolean().optional(),
    samlet_vurdering: z.string().optional(),
    konkrete_observationer: z.array(z.string()).optional(),
    begivenheder: z.array(begivenhedSchema).optional(),
  })
  .passthrough();

const sandsynlighederSchema = z
  .object({
    fuld_medhold_til_klager: z.number().optional(),
    delvist_medhold_til_klager: z.number().optional(),
    afvisning_af_klagen: z.number().optional(),
    begrundelse: z.string().optional(),
  })
  .passthrough();

const analyseSchema = z
  .object({
    klagens_kernepunkter: z.array(z.string()).optional(),
    yderligere_klagepunkter_og_detaljer: z.array(z.string()).optional(),
    rejseselskabets_stillingtagen_indtil_nu: z.string().optional(),
    kort_juridisk_vurdering: z.string().optional(),
    sandsynlighedsvurdering: sandsynlighederSchema.optional(),
    konklusion_en_linje: z.string().optional(),
  })
  .passthrough();

const sagsresumeSchema = z
  .object({
    emne: z.string().optional(),
    klagepunkter: z.array(z.string()).optional(),
    krav: z.string().optional(),
    tui_handtering: z.string().optional(),
    forventet_udfald: z.string().optional(),
  })
  .passthrough();

export const ulaeseligFilSchema = z.object({
  filnavn: z.string(),
  aarsag: z.string(),
});
export type UlaeseligFil = z.infer<typeof ulaeseligFilSchema>;

export const foerstevurderingSchema = z
  .object({
    klagepunkter: z.array(z.string()),
    tidsforhold: tidsforholdSchema,
    analyse: analyseSchema,
    relevante_sager: z.array(z.unknown()),
    match_info: z.array(z.unknown()).optional(),
    // "god"   = ≥2 sager med rerank-score >= 0.30 (vises uden advarsel)
    // "begrænset" = 0-1 stærke matches, vi viser top 2 men markerer det
    // "ingen" = der findes ingen afgørelser overhovedet (edge case)
    match_kvalitet: z.enum(["god", "begrænset", "ingen"]).optional(),
    sagsresume: sagsresumeSchema.nullable().optional(),
    ulaeselige_filer: z.array(ulaeseligFilSchema).optional().default([]),
    paragraf_advarsler: z.array(z.string()).optional().default([]),
    metadata: z
      .object({
        antal_filer: z.number(),
        antal_klagepunkter: z.number(),
        antal_relevante_sager: z.number(),
      })
      .passthrough(),
  })
  .passthrough();
export type Foerstevurdering = z.infer<typeof foerstevurderingSchema>;

export const svarbrevSchema = z
  .object({
    svarbrev: z.string(),
    docx_base64: z.string().optional(),
    docx_fejl: z.string().nullable().optional(),
    paragraf_advarsler: z.array(z.string()).optional().default([]),
    metadata: z
      .object({
        antal_filer: z.number(),
        antal_instrukser: z.number(),
        inkluder_kildehenvisninger: z.boolean(),
        sagsnummer: z.string().optional(),
        klagers_navn: z.string().optional(),
        hoeringssvar_nr: z.number().optional(),
        antal_bilag: z.number().optional(),
        tegn: z.number(),
      })
      .passthrough(),
  })
  .passthrough();
export type Svarbrev = z.infer<typeof svarbrevSchema>;

export const tjeklisteSchema = z
  .object({
    tjekliste: z.string(),
    metadata: z
      .object({
        antal_filer: z.number(),
        tegn: z.number(),
      })
      .passthrough(),
  })
  .passthrough();
export type Tjekliste = z.infer<typeof tjeklisteSchema>;

const anonymResultatSchema = z
  .object({
    filnavn: z.string(),
    status: z.enum([
      "ok",
      "scannet",
      "fejl_aaben",
      "fejl_redaktion",
      "ikke_pdf",
      "ikke_understoettet",
      "exception",
    ]),
    anonymiseret_pdf_base64: z.string().nullable(),
    // 'pdf' | 'docx' — angiver hvilket format output_base64 indeholder.
    // Optional for backwards-compat med ældre API-svar (default 'pdf').
    output_extension: z.string().nullable().optional(),
    antal_bytes_input: z.number(),
    antal_bytes_output: z.number(),
    bemaerkning: z.string(),
  })
  .passthrough();

export const anonymiserSchema = z
  .object({
    filer: z.array(anonymResultatSchema),
    metadata: z
      .object({
        antal_input: z.number(),
        antal_anonymiseret_ok: z.number(),
        klager_navne: z.array(z.string()),
      })
      .passthrough(),
  })
  .passthrough();
export type AnonymRespons = z.infer<typeof anonymiserSchema>;

// ─────────── Analyse-eksport (DOCX / PDF) ───────────
//
// /api/analyse-eksport bruger JSON body i stedet for multipart fordi
// vi kun transporterer markdown-tekst + lidt metadata. Vi bruger derfor
// en separat postJson-helper i stedet for den eksisterende postOgValider.

export const analyseEksportSchema = z
  .object({
    filnavn: z.string(),
    mime: z.string(),
    base64: z.string(),
    metadata: z
      .object({
        format: z.string(),
        antal_bytes: z.number(),
        antal_tegn_markdown: z.number(),
      })
      .passthrough(),
  })
  .passthrough();
export type AnalyseEksport = z.infer<typeof analyseEksportSchema>;

/**
 * JSON-body variant af postOgValider. Samme retry + Zod + auth-token-
 * håndtering, men sender body som application/json.
 */
export async function postJsonOgValider<T>(
  path: string,
  schema: ZodSchema<T>,
  body: unknown,
  opts: { retries?: number; signal?: AbortSignal } = {},
): Promise<T> {
  // Tom/manglende NEXT_PUBLIC_API_URL = same-origin (produktion). Sat
  // til 'http://localhost:8000' i pax-next/.env.local for lokal dev hvor
  // FastAPI kører separat. I produktion proxier Next.js rewrites
  // /api/*-stien til intern uvicorn så vi slipper for CORS + URL-bage.
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
  const url = `${baseUrl}${path}`;
  const retries = opts.retries ?? 2; // Eksport er hurtigt — færre retries
  const token = await hentAuthToken();
  const bodyStr = JSON.stringify(body);

  const operation = async (): Promise<T> => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        headers,
        body: bodyStr,
        signal: opts.signal,
      });
    } catch (e) {
      const tekniskDetalje = e instanceof Error ? e.message : String(e);
      throw new ApiError(
        "Forbindelsen til serveren blev kortvarigt afbrudt. Prøv igen.",
        { detalje: `endpoint=${path} · ${tekniskDetalje}` },
      );
    }

    if (!res.ok) {
      const fejlTekst = await res.text().catch(() => "");
      let besked = `API svarede ${res.status}`;
      let detalje: string | undefined = fejlTekst.slice(0, 500);
      try {
        const body = JSON.parse(fejlTekst);
        if (body && typeof body.detail === "string" && body.detail.length > 0) {
          besked = body.detail;
          detalje = undefined;
        }
      } catch {
        // Ikke JSON
      }
      if (res.status >= 400 && res.status < 500) {
        throw new AbortError(
          new ApiError(besked, { status: res.status, detalje }),
        );
      }
      throw new ApiError(besked, { status: res.status, detalje });
    }

    let raw: unknown;
    try {
      raw = await res.json();
    } catch (e) {
      const detalje = e instanceof Error ? e.message : String(e);
      throw new AbortError(
        new ApiError(`API returnerede ugyldigt JSON`, { detalje }),
      );
    }

    const parsed = schema.safeParse(raw);
    if (!parsed.success) {
      const issues = parsed.error.issues
        .slice(0, 3)
        .map((i) => `${i.path.join(".")}: ${i.message}`)
        .join("; ");
      throw new AbortError(
        new ApiError(`API-respons matcher ikke forventet form`, {
          detalje: issues,
        }),
      );
    }
    return parsed.data;
  };

  return pRetry(operation, {
    retries: retries - 1,
    minTimeout: 1000,
    maxTimeout: 8000,
    factor: 2,
  });
}


// ─────────── Async job-flow (pg-boss queue) ───────────
//
// Erstatter den synkrone /api/foerstevurdering med:
//   1. POST /api/jobs/foerstevurdering → returnerer job_id (få hundrede ms)
//   2. GET /api/jobs/[id] hver POLL_INTERVAL_MS indtil completed/failed
//
// Fordele: ingen 5-min Node.js fetch timeout, ingen Fly proxy timeout,
// bruger kan lukke fane og komme tilbage (job kører videre i worker),
// systemet bliver "klar til rigtige kunder".

const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutter — generous til kø-ventetid

const submitJobSchema = z.object({
  job_id: z.string(),
  genbrugt: z.boolean().optional(),
  status: z.string().optional(),
});

const jobStatusSchema = z.object({
  job_id: z.string(),
  status: z.enum(["pending", "running", "completed", "failed"]),
  resultat: z.unknown().nullable().optional(),
  fejl_besked: z.string().nullable().optional(),
  fejl_kategori: z.string().nullable().optional(),
  forsoeg: z.number().optional(),
});

/**
 * Submit + poll wrapper. Returnerer validerede resultat-data når
 * jobbet er complete, eller kaster ApiError ved fejl/timeout.
 *
 * Brug fra komponenter med samme mønster som postOgValider:
 *
 *   const data = await kørAnalyseJob(
 *     formData,
 *     foerstevurderingSchema,
 *     { onStatusChange: (s) => sætFremgang(s) },
 *   );
 */
export async function kørAnalyseJob<T>(
  formData: FormData,
  resultatSchema: ZodSchema<T>,
  opts: {
    onStatusChange?: (status: string) => void;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  const token = await hentAuthToken();
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "";

  // ─── Step 1: submit ───
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let submitRes: Response;
  try {
    submitRes = await fetch(`${baseUrl}/api/jobs/foerstevurdering`, {
      method: "POST",
      body: formData,
      headers,
      signal: opts.signal,
    });
  } catch (e) {
    const detalje = e instanceof Error ? e.message : String(e);
    throw new ApiError(
      "Forbindelsen til serveren blev kortvarigt afbrudt. Prøv igen.",
      { detalje: `submit · ${detalje}` },
    );
  }

  if (!submitRes.ok) {
    const txt = await submitRes.text().catch(() => "");
    let besked = `Kunne ikke starte analysen (${submitRes.status})`;
    try {
      const body = JSON.parse(txt);
      if (typeof body.detail === "string") besked = body.detail;
    } catch {}
    throw new ApiError(besked, { status: submitRes.status });
  }

  const submitParsed = submitJobSchema.safeParse(await submitRes.json());
  if (!submitParsed.success) {
    throw new ApiError(
      "Serveren returnerede et uventet svar ved start af analyse.",
      { detalje: submitParsed.error.message.slice(0, 200) },
    );
  }
  const jobId = submitParsed.data.job_id;
  opts.onStatusChange?.("pending");

  // ─── Step 2: poll ───
  const startTid = Date.now();
  let sidsteStatus = "pending";

  while (Date.now() - startTid < POLL_TIMEOUT_MS) {
    if (opts.signal?.aborted) {
      throw new AbortError(new ApiError("Analysen blev afbrudt."));
    }

    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));

    let statusRes: Response;
    try {
      statusRes = await fetch(`${baseUrl}/api/jobs/${jobId}`, {
        method: "GET",
        headers,
        signal: opts.signal,
      });
    } catch {
      // Polling-fejl (fx kortvarig 5G-dropout) — fortsæt
      continue;
    }

    if (!statusRes.ok) {
      // 5xx eller midlertidig fejl — fortsæt med at polle
      if (statusRes.status >= 500) continue;
      const txt = await statusRes.text().catch(() => "");
      let besked = `Kunne ikke hente job-status (${statusRes.status})`;
      try {
        const body = JSON.parse(txt);
        if (typeof body.detail === "string") besked = body.detail;
      } catch {}
      throw new ApiError(besked, { status: statusRes.status });
    }

    const statusData = jobStatusSchema.safeParse(await statusRes.json());
    if (!statusData.success) {
      continue; // Ignorér ugyldigt svar, prøv igen
    }
    const s = statusData.data;
    if (s.status !== sidsteStatus) {
      sidsteStatus = s.status;
      opts.onStatusChange?.(s.status);
    }

    if (s.status === "completed") {
      if (s.resultat === null || s.resultat === undefined) {
        throw new ApiError(
          "Analysen er færdig men resultatet mangler. Prøv igen.",
          { detalje: "resultat=null" },
        );
      }
      const validated = resultatSchema.safeParse(s.resultat);
      if (!validated.success) {
        const issues = validated.error.issues
          .slice(0, 3)
          .map((i) => `${i.path.join(".")}: ${i.message}`)
          .join("; ");
        throw new ApiError(
          "Resultatet matchede ikke det forventede format.",
          { detalje: issues },
        );
      }
      return validated.data;
    }

    if (s.status === "failed") {
      throw new ApiError(
        s.fejl_besked ||
          "Analysen fejlede internt. Prøv igen om et øjeblik.",
        {
          detalje: s.fejl_kategori
            ? `kategori=${s.fejl_kategori}, forsøg=${s.forsoeg ?? 1}`
            : undefined,
        },
      );
    }

    // status === "pending" eller "running" → fortsæt med at polle
  }

  throw new ApiError(
    "Analysen tog længere end forventet. Prøv igen — dit job er gemt og kører måske stadig i baggrunden.",
    { detalje: `timeout efter ${POLL_TIMEOUT_MS / 1000}s` },
  );
}
