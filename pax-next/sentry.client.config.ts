// Sentry-init for browser (client-side runtime).
//
// PII-scrubberen er bit-præcist samme felt-liste som Streamlit-PAX
// (app.py:_PII_FELT_NAVNE) og FastAPI-laget (api/main.py). Hvis vi
// utilsigtet logger en exception med klage-tekst eller klagers navn
// i en frame-var, fanger scrubberen det før det forlader browseren.
//
// DSN læses fra NEXT_PUBLIC_SENTRY_DSN (eksponeres til browseren).
// Hvis den mangler, init'eres ikke — appen fortsætter uden Sentry
// så lokal udvikling ikke kræver konfiguration.
import * as Sentry from "@sentry/nextjs";

const PII_FELT_NAVNE: ReadonlySet<string> = new Set([
  "aktuel_sag", "sagsakter", "sagsakter_filer", "filer",
  "fil_bytes", "bytes", "raw_bytes", "pdf_bytes",
  "tekst", "indhold", "klage", "klage_tekst", "sag_tekst",
  "klager_navn", "klagers_navn", "email", "fulde_navn",
  "auto_vurdering_tekst", "seneste_svarbrev", "seneste_anonymisering",
  "seneste_tjekliste", "sagsresume", "chat_historik",
  "state_json", "aktiv_sag_state", "snapshot",
  "spoergsmaal", "ekstra_instrukser",
  "password", "access_token", "refresh_token", "api_key",
  "data", "form", "body", "markdown",
]);

// Rekursiv PII-scrubber. Max-dybde 8 så vi ikke rammer rekursions-
// grænse på cykliske referencer.
function scrubPii(node: unknown, depth = 0): unknown {
  if (depth > 8) return "[REDACTED:max-depth]";
  if (node === null || node === undefined) return node;
  if (typeof node === "string") {
    if (node.length > 500) {
      return node.slice(0, 200) + `...[TRUNCATED len=${node.length}]`;
    }
    return node;
  }
  if (Array.isArray(node)) {
    return node.map((v) => scrubPii(v, depth + 1));
  }
  if (typeof node === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
      if (typeof k === "string" && PII_FELT_NAVNE.has(k.toLowerCase())) {
        out[k] = "[REDACTED]";
      } else {
        out[k] = scrubPii(v, depth + 1);
      }
    }
    return out;
  }
  return node;
}

const dsn =
  process.env.NEXT_PUBLIC_SENTRY_DSN || process.env.SENTRY_DSN || "";

if (dsn) {
  Sentry.init({
    dsn,
    sendDefaultPii: false,
    tracesSampleRate: 0.1,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENV || "production",
    release: process.env.NEXT_PUBLIC_SENTRY_RELEASE || "pax-next@dev",
    beforeSend(event) {
      try {
        // Stack-frame vars
        for (const exc of event.exception?.values || []) {
          for (const frame of exc.stacktrace?.frames || []) {
            // Frame.vars er Record<string, unknown> i Sentry's typer.
            const v = (frame as { vars?: Record<string, unknown> }).vars;
            if (v) {
              (frame as { vars?: Record<string, unknown> }).vars = scrubPii(
                v,
              ) as Record<string, unknown>;
            }
          }
        }
        if (event.extra) event.extra = scrubPii(event.extra) as typeof event.extra;
        if (event.contexts) {
          event.contexts = scrubPii(event.contexts) as typeof event.contexts;
        }
        if (event.request?.data) {
          event.request.data = scrubPii(event.request.data);
        }
      } catch (e) {
        // Fail-open: vi vil hellere sende et uscrubbed event end at
        // miste fejlen helt.
        console.warn("Sentry PII-scrubber fejlede:", e);
      }
      return event;
    },
  });
}
