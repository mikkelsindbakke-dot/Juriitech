// POST /api/admin/switch-tenant
//
// Lader admin-brugere skifte hvilken tenant de "ser som" — bruges til
// debugging og kunde-support. Sætter en HTTP-only cookie der læses af
// hentBrugerMedTenant() og populeres som effektiv_tenant_id.
//
// SIKKERHED:
// - KUN admin-brugere kan sætte cookien (role-check FØR cookie sættes)
// - Cookien er HTTP-only + secure + sameSite=lax → kan ikke læses/manipuleres
//   fra klient-side JavaScript
// - Tenant-id'en valideres mod databasen før den accepteres
// - Hvis brugeren senere fjerner sin admin-rolle, ignoreres cookien
//   automatisk i hentBrugerMedTenant() (kun admin-rolle læser den)

import { NextRequest, NextResponse } from "next/server";
import { hentBrugerEllerNull } from "@/lib/auth/dual-auth";
import { hentTenantById } from "@/lib/queries/tenants";
import { ADMIN_VIEW_TENANT_COOKIE_NAME } from "@/lib/queries/users";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const dbBruger = await hentBrugerEllerNull(req);
  if (!dbBruger) {
    return NextResponse.json({ detail: "Ikke logget ind." }, { status: 401 });
  }
  if (dbBruger.role !== "admin") {
    return NextResponse.json(
      { detail: "Kun administratorer kan skifte tenant." },
      { status: 403 },
    );
  }

  let body: { tenant_id?: number | string | null };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { detail: "Ugyldig JSON i request body." },
      { status: 400 },
    );
  }

  const raw = body.tenant_id;

  // null → ryd cookie (admin "vender tilbage til sin egen tenant")
  if (raw === null || raw === undefined || raw === "") {
    const res = NextResponse.json({ ok: true, aktiv_tenant_id: null });
    res.cookies.delete(ADMIN_VIEW_TENANT_COOKIE_NAME);
    return res;
  }

  const id = typeof raw === "number" ? raw : parseInt(String(raw), 10);
  if (!Number.isFinite(id) || id <= 0) {
    return NextResponse.json(
      { detail: "Ugyldig tenant_id." },
      { status: 400 },
    );
  }

  const tenant = await hentTenantById(id);
  if (!tenant) {
    return NextResponse.json(
      { detail: "Tenant findes ikke." },
      { status: 404 },
    );
  }

  const res = NextResponse.json({
    ok: true,
    aktiv_tenant_id: id,
    tenant_slug: tenant.slug,
    tenant_navn: tenant.navn,
  });
  res.cookies.set(ADMIN_VIEW_TENANT_COOKIE_NAME, String(id), {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    // 7 dages levetid — admin behøver ikke at re-vælge tenant ved hver
    // session. Hvis tenant slettes mellem cookie-set og næste request,
    // ignoreres cookien (validering i hentBrugerMedTenant).
    maxAge: 60 * 60 * 24 * 7,
  });
  return res;
}
