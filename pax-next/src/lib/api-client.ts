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
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) {
    throw new ApiError("NEXT_PUBLIC_API_URL er ikke sat", {
      detalje: "Kontakt en administrator — environment-variablen mangler.",
    });
  }
  const url = `${baseUrl}${path}`;
  const retries = opts.retries ?? STANDARD_RETRIES;

  const operation = async (): Promise<T> => {
    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        body: opts.formData,
        signal: opts.signal,
      });
    } catch (e) {
      // Netværks-fejl — værd at retry'e (DNS-flap, kortvarig forbindelses-
      // mistring osv.).
      const detalje = e instanceof Error ? e.message : String(e);
      throw new ApiError(`Kan ikke nå ${path}`, { detalje });
    }

    if (!res.ok) {
      const fejlTekst = await res.text().catch(() => "");
      // 4xx: bruger-fejl. Stop retries — gentagelse løser ikke at
      // input er ugyldigt.
      if (res.status >= 400 && res.status < 500) {
        throw new AbortError(
          new ApiError(`API svarede ${res.status}`, {
            status: res.status,
            detalje: fejlTekst.slice(0, 500),
          }),
        );
      }
      // 5xx: lad p-retry prøve igen.
      throw new ApiError(`API svarede ${res.status}`, {
        status: res.status,
        detalje: fejlTekst.slice(0, 500),
      });
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

const tidsforholdSchema = z
  .object({
    har_problematisk_forsinkelse: z.boolean().optional(),
    kunne_ikke_udledes: z.boolean().optional(),
    samlet_vurdering: z.string().optional(),
    konkrete_observationer: z.array(z.string()).optional(),
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

export const foerstevurderingSchema = z
  .object({
    klagepunkter: z.array(z.string()),
    tidsforhold: tidsforholdSchema,
    analyse: analyseSchema,
    relevante_sager: z.array(z.unknown()),
    match_info: z.array(z.unknown()).optional(),
    sagsresume: sagsresumeSchema.nullable().optional(),
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
      "exception",
    ]),
    anonymiseret_pdf_base64: z.string().nullable(),
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
