// Sentry-init for Edge runtime (Next.js Edge functions, hvis vi
// nogensinde bruger dem). I PAX kører proxy.ts i Node-runtime og vi
// har INGEN edge routes pt., men Sentry-pakken kræver at filen findes
// så stacks instrumenters konsistent på tværs af runtimes.
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN || "";

if (dsn) {
  Sentry.init({
    dsn,
    sendDefaultPii: false,
    tracesSampleRate: 0.1,
    environment: process.env.SENTRY_ENV || "production",
    release: process.env.SENTRY_RELEASE || "pax-next@dev",
  });
}
