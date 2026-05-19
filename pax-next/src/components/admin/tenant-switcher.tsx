"use client";

// Admin-only: tenant-switcher dropdown der lader admin "se som" en
// anden tenant for debugging + kunde-support. Cookie sættes via
// /api/admin/switch-tenant — denne komponent er bare UI'en.
//
// Hvis admin har valgt en anden tenant end deres egen, vises en gul
// "advarsel"-bar så de ikke glemmer hvilken tenant de opererer på.

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { useT } from "@/lib/i18n/client";

type TenantOption = {
  id: number;
  slug: string;
  navn: string;
  land: string;
};

export function TenantSwitcher({
  tenants,
  egenTenantId,
  aktivTenantId,
}: {
  tenants: TenantOption[];
  egenTenantId: number;
  aktivTenantId: number;
}) {
  const t = useT();
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const harOverride = aktivTenantId !== egenTenantId;
  const aktivTenant = tenants.find((t) => t.id === aktivTenantId);

  function skiftTenant(nyId: number | null) {
    startTransition(async () => {
      try {
        const resp = await fetch("/api/admin/switch-tenant", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tenant_id: nyId }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          alert(`${t("admin.tenant_switcher.kunne_ikke_skifte")}: ${data.detail || resp.status}`);
          return;
        }
        // router.refresh() får alle server components til at re-renderes
        // med den nye cookie — uden full page reload.
        router.refresh();
      } catch (e) {
        alert(`${t("admin.tenant_switcher.netvaerksfejl")}: ${e instanceof Error ? e.message : "ukendt"}`);
      }
    });
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <label
          htmlFor="tenant-switcher"
          className="text-xs font-medium text-zinc-600 whitespace-nowrap"
        >
          {t("admin.tenant_switcher.label")}
        </label>
        <select
          id="tenant-switcher"
          value={aktivTenantId}
          disabled={pending}
          onChange={(e) => {
            const nyId = parseInt(e.target.value, 10);
            skiftTenant(nyId === egenTenantId ? null : nyId);
          }}
          className="flex-1 text-sm rounded-md border border-zinc-300 bg-white px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:opacity-50"
        >
          {tenants.map((tenant) => (
            <option key={tenant.id} value={tenant.id}>
              {tenant.navn} ({tenant.land})
              {tenant.id === egenTenantId ? ` — ${t("admin.tenant_switcher.min_egen")}` : ""}
            </option>
          ))}
        </select>
      </div>

      {harOverride && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 flex items-center justify-between gap-2">
          <span>
            {t("admin.tenant_switcher.advarsel_prefix")}{" "}
            <strong>{aktivTenant?.navn ?? t("admin.tenant_switcher.ukendt_tenant")}</strong>{" "}
            {t("admin.tenant_switcher.advarsel_suffix")}
          </span>
          <button
            type="button"
            onClick={() => skiftTenant(null)}
            disabled={pending}
            className="shrink-0 text-amber-900 underline underline-offset-2 hover:text-amber-700 disabled:opacity-50"
          >
            {t("admin.tenant_switcher.tilbage_til_min_egen")}
          </button>
        </div>
      )}
    </div>
  );
}
