// Next.js instrumentation hook — kører ved app-opstart i hver runtime.
// Bruges af @sentry/nextjs til at registrere sentry.server.config.ts
// og sentry.edge.config.ts i de korrekte runtimes.
//
// Reference: https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("../sentry.server.config");

    // pg-boss worker starter automatisk når Next.js booter, hvis
    // PAX_ENABLE_WORKER=1 er sat. Dette er gated så lokal `next dev`
    // ikke uventet starter en worker mod prod-DB'en.
    //
    // Worker kører i samme proces som Next.js-server — hvis processen
    // crasher, dør worker'en også, hvilket er det vi vil (Fly genstarter
    // hele containeren og worker'en plukker uafsluttede jobs op igen).
    if (process.env.PAX_ENABLE_WORKER === "1") {
      try {
        const { startWorker } = await import("./lib/queue/worker");
        // Vi await'er IKKE — worker.work() resolves når subscription er
        // sat op, og fortsætter at lytte efter jobs i baggrunden.
        startWorker().catch((err) => {
          console.error("[instrumentation] worker start fejlede:", err);
        });
      } catch (e) {
        console.error("[instrumentation] kunne ikke loade worker:", e);
      }
    }
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("../sentry.edge.config");
  }
}

// Next.js's onRequestError-hook der videregives til Sentry så
// uncaught request-fejl rapporteres automatisk.
export { captureRequestError as onRequestError } from "@sentry/nextjs";
