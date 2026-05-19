import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

const nextConfig: NextConfig = {
  // standalone-output bundler kun de nødvendige node_modules ind i
  // .next/standalone/, så Fly-containeren bliver ~80% mindre. Kræves
  // for at FastAPI + Next.js kan køre i samme container uden at
  // image-størrelsen eksploderer.
  output: "standalone",

  // Proxy af /api/* sker via Route Handler i src/app/api/[...path]/route.ts
  // — IKKE via rewrites. Next.js-rewrites bruger undici med 30s body-
  // timeout, hvilket fejler vores AI-kald (60-90s). Route Handler kører
  // i Node-runtime uden timeout.

  // Hæver proxy-laget's body-limit fra default 10MB → 100MB. Sagsakter
  // kan være store ZIP-pakker (mail-tråde, screenshots, FileShare-dumps
  // m.m.) — vi har set 22MB+ i praksis. Uden denne setting truncerer
  // proxy'en body'en til 10MB og uvicorn modtager korrupte multipart-data
  // → 'fetch failed' fra Route Handler.
  //
  // @ts-expect-error — feltet eksisterer i Next.js 16-runtime-skemaet
  // (config-schema.js) men er endnu ikke i typedefinitionerne. Det
  // bruges af proxy-laget for at læse hele body'en igennem inden
  // request når Route Handler.
  middlewareClientMaxBodySize: "100mb",
  // Nyere navn i Next.js 16; findes i types — sættes som fremtidssikring.
  proxyClientMaxBodySize: "100mb",
};

// Sentry-wrapper. Build-time source-map-upload kræver SENTRY_AUTH_TOKEN
// + org/project — uden dem laver vi bare runtime-init via instrumentation.ts.
// Plugin er silent når miljøet ikke har auth-tokenet sat, så lokal build
// virker uden Sentry-konfiguration.
export default withSentryConfig(nextConfig, {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,

  // Skjul Sentry's build-output medmindre vi er i CI
  silent: !process.env.CI,

  widenClientFileUpload: true,
  reactComponentAnnotation: { enabled: true },

  // Slet source-maps fra public assets efter upload (sikkerhed —
  // ellers er kildekoden public via dev-tools).
  sourcemaps: { deleteSourcemapsAfterUpload: true },
  disableLogger: true,
});
