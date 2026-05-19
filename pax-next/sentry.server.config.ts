// Sentry-init for Node.js server-runtime (App Router server-components,
// route-handlers, server-actions).
//
// Samme PII-scrubber-mønster som client og FastAPI. Server-side har
// faktisk MERE PII-risiko fordi server-components kan logge DB-rækker
// med klage_tekst og fil_bytes direkte i frame-vars.
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

const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN || "";

if (dsn) {
  Sentry.init({
    dsn,
    sendDefaultPii: false,
    tracesSampleRate: 0.1,
    environment: process.env.SENTRY_ENV || "production",
    release: process.env.SENTRY_RELEASE || "pax-next@dev",
    beforeSend(event) {
      try {
        for (const exc of event.exception?.values || []) {
          for (const frame of exc.stacktrace?.frames || []) {
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
        console.warn("Sentry PII-scrubber fejlede:", e);
      }
      return event;
    },
  });
}
