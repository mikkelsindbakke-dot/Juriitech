import "server-only";
import { PgBoss } from "pg-boss";

// Singleton pg-boss instance pr. Node-proces. Bruger samme Postgres
// som vores andre queries (Supabase). pg-boss opretter sit eget skema
// (pgboss.*) ved første start — idempotent.

let _boss: PgBoss | null = null;
let _bossPromise: Promise<PgBoss> | null = null;

export const QUEUE_FOERSTEVURDERING = "foerstevurdering";

export async function getBoss(): Promise<PgBoss> {
  if (_boss) return _boss;
  if (_bossPromise) return _bossPromise;

  _bossPromise = (async () => {
    const url = process.env.DATABASE_URL;
    if (!url) {
      throw new Error("DATABASE_URL mangler — pg-boss kan ikke starte");
    }

    const boss = new PgBoss({
      connectionString: url,
      schema: "pgboss",
      // Vedligehold hver time (default er hyppigere men vi behøver det ikke)
      maintenanceIntervalSeconds: 60 * 60,
      // Per-queue policies (retry, archive osv.) sættes på createQueue
      // / send-niveau i v12 — vi bruger defaults for nu.
    });

    boss.on("error", (err: unknown) => {
      console.error("[pg-boss] fejl:", err);
      try {
        import("@sentry/nextjs").then((s) => {
          s.captureException(err, {
            tags: { source: "pg-boss" },
          });
        });
      } catch {
        // ignore
      }
    });

    await boss.start();
    _boss = boss;
    return boss;
  })();

  return _bossPromise;
}

export async function submitForstevurderingJob(jobDbId: string): Promise<void> {
  const boss = await getBoss();
  // jobDbId er vores analyse_jobs.id (UUID). pg-boss-jobben holder bare
  // en pegepind — input + resultat ligger i analyse_jobs-tabellen.
  await boss.send(QUEUE_FOERSTEVURDERING, { jobDbId });
}
