import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import { hentAlleTenants } from "@/lib/queries/tenants";
import { TenantSwitcher } from "@/components/admin/tenant-switcher";
import { LocaleProvider } from "@/lib/i18n/client";
import { lavT } from "@/lib/i18n/t";

// Admin-layout: gater alle /admin/*-ruter på role='admin'.
// Adgangskontrol sker SERVER-SIDE — ingen ikke-admin kan få JSX'en
// dumpet, heller ikke ved at gætte URL'en. Sidemenu med tabs vises
// til alle admin-sider.
export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const dbBruger = await hentBrugerMedTenant(user.id);
  if (!dbBruger || dbBruger.role !== "admin") {
    redirect("/");
  }

  const locale = dbBruger.effektiv_sprog ?? "da";
  const t = lavT(locale);

  // Hent alle tenants så admin kan skifte mellem dem. Dette er en
  // tynd query (~10 rækker), så ingen perf-bekymring.
  const tenants = await hentAlleTenants();
  const switcherTenants = tenants.map((t) => ({
    id: t.id,
    slug: t.slug,
    navn: t.navn,
    land: t.land,
  }));

  return (
    <LocaleProvider locale={locale}>
    <main className="flex-1 bg-gradient-to-b from-zinc-50 to-zinc-100/60">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <div className="flex items-center justify-between mb-6 gap-4">
          <div>
            <h1 className="text-3xl font-serif font-medium tracking-tight text-zinc-900">
              {t("admin.layout.titel")}
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              {t("admin.layout.logget_ind_som")} <strong>{dbBruger.email}</strong> ({t("admin.layout.administrator")})
            </p>
          </div>
          <Link
            href="/"
            className="text-sm text-zinc-500 hover:text-zinc-900 underline-offset-4 hover:underline"
          >
            {t("admin.layout.tilbage_til_forsiden")}
          </Link>
        </div>

        {/* Tenant-switcher: kun for admin. Lader Mikkel se PAX som
            en anden tenant ville se den — nyttig til kunde-support
            og test af nye markeder (fx norsk PAX). */}
        <div className="mb-6 max-w-2xl">
          <TenantSwitcher
            tenants={switcherTenants}
            egenTenantId={dbBruger.tenant_id}
            aktivTenantId={dbBruger.effektiv_tenant_id}
          />
        </div>

        <nav className="flex gap-1 border-b border-zinc-200 mb-6">
          <AdminTabLink href="/admin">{t("admin.layout.tab_tenants")}</AdminTabLink>
          <AdminTabLink href="/admin/brugere">{t("admin.layout.tab_brugere")}</AdminTabLink>
          <AdminTabLink href="/admin/inviter">{t("admin.layout.tab_inviter")}</AdminTabLink>
          <AdminTabLink href="/admin/audit-log">{t("admin.layout.tab_audit_log")}</AdminTabLink>
          <AdminTabLink href="/admin/test-sager">{t("admin.layout.tab_test_sager")}</AdminTabLink>
        </nav>

        {children}
      </div>
    </main>
    </LocaleProvider>
  );
}

function AdminTabLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="px-4 py-2 text-sm font-medium text-zinc-600 hover:text-zinc-900 border-b-2 border-transparent hover:border-zinc-300 -mb-px"
    >
      {children}
    </Link>
  );
}
