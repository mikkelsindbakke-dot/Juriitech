import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import { hentGdprAuditLog, type AuditHandling } from "@/lib/queries/audit";

// CSV-eksport af audit-log på tværs af alle tenants (med valgfrit
// tenant-filter via ?tenant=). Strikt admin-only. Bruges når kundens
// DPO eller en ekstern revisor beder om en kopi de kan tage med sig.
// Output er valid Excel-CSV (UTF-8 + BOM så Excel gætter encodingen
// korrekt + komma-separator) — kunden kan åbne det direkte ved at
// dobbeltklikke.

const GYLDIGE_HANDLINGER = new Set<AuditHandling>([
  "upload",
  "analyse",
  "visning",
  "eksport",
  "anonymisering",
  "sletning",
  "cross_tenant_share",
  "tilbage_kald",
  "login_success",
  "login_failed",
  "logout",
  "password_reset",
  "admin_user_oprettet",
  "admin_user_slettet",
  "admin_user_inviteret",
  "admin_tenant_oprettet",
  "admin_tenant_opdateret",
]);

// CSV-escape: " → "", omslut feltet med " hvis det indeholder komma/
// anførselstegn/newline. Excel-kompatibel.
function csvCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export async function GET(req: NextRequest) {
  // ─── Adgangskontrol: kun admin ───
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ fejl: "Ikke logget ind" }, { status: 401 });
  }
  const dbBruger = await hentBrugerMedTenant(user.id);
  if (!dbBruger || dbBruger.role !== "admin") {
    return NextResponse.json({ fejl: "Kræver admin" }, { status: 403 });
  }

  // ─── Filtre fra query params ───
  const url = new URL(req.url);
  const handlingParam = url.searchParams.get("handling") ?? "";
  const handling =
    handlingParam && GYLDIGE_HANDLINGER.has(handlingParam as AuditHandling)
      ? (handlingParam as AuditHandling)
      : null;

  // Valgfrit selskabs-filter. Uden det eksporteres på tværs af alle tenants.
  const tenantParam = url.searchParams.get("tenant") ?? "";
  const tenantId = /^\d+$/.test(tenantParam) ? Number(tenantParam) : null;

  // Eksport tager max 5000 rækker pr. download for at undgå memory-blowup.
  // En typisk tenant har 50-200 events pr. dag — 5000 dækker 25-100 dage.
  // Hvis flere ønskes: filtrer på handling eller datointerval.
  const limit = Math.min(
    Math.max(parseInt(url.searchParams.get("limit") || "5000", 10) || 5000, 100),
    5000,
  );

  const rows = await hentGdprAuditLog({
    tenantId,
    handling,
    limit,
  });

  // ─── Byg CSV ───
  const header = [
    "tidspunkt",
    "handling",
    "user_email",
    "user_id",
    "sag_id",
    "ip_adresse",
    "tenant_id",
    "metadata_json",
  ];
  const linjer: string[] = [header.join(",")];
  for (const r of rows) {
    linjer.push(
      [
        r.tidspunkt,
        r.handling,
        r.user_email,
        r.user_id,
        r.sag_id,
        r.ip_adresse,
        r.tenant_id,
        r.metadata ? JSON.stringify(r.metadata) : "",
      ]
        .map(csvCell)
        .join(","),
    );
  }
  // BOM så Excel åbner UTF-8 korrekt
  const csv = "﻿" + linjer.join("\r\n") + "\r\n";

  // ─── Filnavn med dato + filtre for sporbarhed ───
  const dato = new Date().toISOString().slice(0, 10);
  const handlingSuffix = handling ? `_${handling}` : "";
  const tenantSuffix = tenantId !== null ? `_tenant-${tenantId}` : "";
  const filnavn = `gdpr-audit-log_${dbBruger.email.replace(/[^a-z0-9]/gi, "_")}_${dato}${tenantSuffix}${handlingSuffix}.csv`;

  return new NextResponse(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filnavn}"`,
      "Cache-Control": "no-store",
    },
  });
}
