// GET /api/jobs/[id]
//
// Polling-endpoint. Returnerer job-status + resultat hvis completed.
// Frontend kalder hver 2-3 sek mens analysen kører.
//
// Tenant-isoleret: returnerer kun jobs der tilhører caller's tenant.

import { NextRequest, NextResponse } from "next/server";
import { hentBrugerEllerNull } from "@/lib/auth/dual-auth";
import { hentJob } from "@/lib/queries/analyse-jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  // Sanity-check UUID-format
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
    return NextResponse.json({ detail: "Ugyldigt job-ID" }, { status: 400 });
  }

  const dbBruger = await hentBrugerEllerNull(req);
  if (!dbBruger) {
    return NextResponse.json({ detail: "Ikke logget ind." }, { status: 401 });
  }

  const job = await hentJob(id, dbBruger.effektiv_tenant_id);
  if (!job) {
    return NextResponse.json(
      { detail: "Job ikke fundet (eller ikke i din tenant)" },
      { status: 404 },
    );
  }

  // Vi sender input-filer-bytes IKKE tilbage (kan være store) — kun meta.
  return NextResponse.json({
    job_id: job.id,
    status: job.status,
    resultat: job.status === "completed" ? job.resultat : null,
    fejl_besked: job.status === "failed" ? job.fejl_besked : null,
    fejl_kategori: job.status === "failed" ? job.fejl_kategori : null,
    forsoeg: job.forsoeg,
    oprettet: job.oprettet,
    startet: job.startet,
    faerdig: job.faerdig,
    input_filer_meta: job.input_filer_meta,
  });
}
