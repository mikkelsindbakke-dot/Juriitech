// POST /api/jobs/foerstevurdering
//
// Async submission for førstevurderings-analyse. Modtager filer +
// sagsakter, gemmer i Postgres, enqueue'r pg-boss-job, returnerer
// job_id straks (typisk inden for 200-500 ms).
//
// Klienten poller /api/jobs/[id] indtil status=completed eller failed.
//
// Idempotency: samme input (filer + sagsakter) inden for 1 time
// returnerer eksisterende job-ID i stedet for at oprette nyt.
//
// Hentes via aktiv_tenant fra FastAPI? NEJ — vi skal verificere auth
// direkte her, da vi IKKE proxier til FastAPI. Vi bruger samme
// pattern som /api/admin/audit-log (Supabase getUser + hentBrugerMedTenant).

import { NextRequest, NextResponse } from "next/server";
import { hentBrugerEllerNull } from "@/lib/auth/dual-auth";
import {
  opretJob,
  bygIdempotencyKey,
  type FilInput,
} from "@/lib/queries/analyse-jobs";
import { submitForstevurderingJob } from "@/lib/queue/pg-boss-client";
import * as Sentry from "@sentry/nextjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60; // ingen AI-arbejde her, kun upload+enqueue

export async function POST(req: NextRequest) {
  const dbBruger = await hentBrugerEllerNull(req);
  if (!dbBruger) {
    return NextResponse.json(
      { detail: "Ikke logget ind." },
      { status: 401 },
    );
  }

  // Parse multipart/form-data
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch (e) {
    return NextResponse.json(
      { detail: "Ugyldig multipart-form-data" },
      { status: 400 },
    );
  }

  const sagsakter = (formData.get("sagsakter") as string) || "";
  const filerEntries = formData.getAll("filer");

  if (filerEntries.length === 0) {
    return NextResponse.json(
      { detail: "Ingen filer vedhæftet" },
      { status: 400 },
    );
  }

  // Konverter til vores FilInput-form
  const filer: FilInput[] = [];
  for (const entry of filerEntries) {
    if (!(entry instanceof File)) continue;
    const bytes = Buffer.from(await entry.arrayBuffer());
    filer.push({
      filnavn: entry.name,
      bytes,
      mime_type: entry.type || "application/octet-stream",
    });
  }

  if (filer.length === 0) {
    return NextResponse.json(
      { detail: "Ingen gyldige filer fundet" },
      { status: 400 },
    );
  }

  // Sanity: max samlet input 50 MB. Hvis nogen sender større, afvis.
  const totalBytes = filer.reduce((sum, f) => sum + f.bytes.length, 0);
  if (totalBytes > 50 * 1024 * 1024) {
    return NextResponse.json(
      {
        detail: `Samlet upload (${(totalBytes / 1024 / 1024).toFixed(1)} MB) overstiger grænsen på 50 MB.`,
      },
      { status: 413 },
    );
  }

  const idempotencyKey = bygIdempotencyKey({
    tenantId: dbBruger.effektiv_tenant_id,
    userId: dbBruger.user_id,
    filer,
    sagsakter,
  });

  try {
    const { jobId, genbrugt } = await opretJob({
      tenantId: dbBruger.effektiv_tenant_id,
      userId: dbBruger.user_id,
      userEmail: dbBruger.email,
      filer,
      sagsakter,
      idempotencyKey,
    });

    // Hvis genbrugt: jobbet kører allerede (eller er færdigt). Ingen
    // grund til at enqueue'e igen.
    if (!genbrugt) {
      try {
        await submitForstevurderingJob(jobId);
      } catch (queueErr) {
        // Hvis queue fejler, har vi stadig jobbet i DB — markér som failed
        // så frontend ser fejlen og kan retry. Eller vi kan late-process via
        // en cron der scanner pending-rows. For nu: log+fejl.
        Sentry.captureException(queueErr, {
          tags: { source: "submitJob", jobId },
        });
        return NextResponse.json(
          {
            detail:
              "Kunne ikke planlægge analysen. Prøv igen om et øjeblik.",
          },
          { status: 503 },
        );
      }
    }

    return NextResponse.json({
      job_id: jobId,
      genbrugt,
      status: "pending",
    });
  } catch (e) {
    Sentry.captureException(e, {
      tags: { source: "opretJob" },
      contexts: {
        request: {
          antal_filer: filer.length,
          total_bytes: totalBytes,
        },
      },
    });
    return NextResponse.json(
      { detail: "Noget gik galt ved oprettelse af analyse-job." },
      { status: 500 },
    );
  }
}
