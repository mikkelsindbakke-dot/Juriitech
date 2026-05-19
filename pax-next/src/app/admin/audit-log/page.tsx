import Link from "next/link";
import { hentGdprAuditLog, type AuditRow, type AuditHandling } from "@/lib/queries/audit";
import { hentAlleTenants } from "@/lib/queries/tenants";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import { redirect } from "next/navigation";
import { lavT } from "@/lib/i18n/t";

// GDPR audit-log fremvisnings-side.
//
// Tabel med fem kolonner: dato, tidspunkt, selskab, bruger, handling.
// Admin er platform-bred og ser events på tværs af ALLE tenants — med
// valgfrit filter på selskab. Opfylder GDPR art. 30(2) + art. 32(1)(d).

const EMOJI_PR_HANDLING: Record<string, string> = {
  upload: "📤",
  analyse: "🔍",
  visning: "👁️",
  eksport: "📄",
  anonymisering: "🔒",
  sletning: "🗑️",
  cross_tenant_share: "📊",
  tilbage_kald: "↩️",
  login_success: "🔑",
  login_failed: "⛔",
  logout: "🚪",
  password_reset: "🔁",
  admin_user_oprettet: "👤",
  admin_user_slettet: "❌",
  admin_user_inviteret: "✉️",
  admin_tenant_oprettet: "🏢",
  admin_tenant_opdateret: "🛠️",
};

const GYLDIGE_HANDLINGER: AuditHandling[] = [
  "upload",
  "analyse",
  "visning",
  "eksport",
  "anonymisering",
  "sletning",
  "login_success",
  "login_failed",
  "logout",
  "admin_user_oprettet",
  "admin_user_slettet",
  "admin_user_inviteret",
  "admin_tenant_oprettet",
  "admin_tenant_opdateret",
];

function formatDato(iso: string, locale: string): string {
  try {
    const d = new Date(iso);
    const localeTag = locale === "no" ? "nb-NO" : "da-DK";
    return d.toLocaleDateString(localeTag, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatTidspunkt(iso: string, locale: string): string {
  try {
    const d = new Date(iso);
    const localeTag = locale === "no" ? "nb-NO" : "da-DK";
    return d.toLocaleTimeString(localeTag, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "";
  }
}

export default async function AuditLogPage(props: {
  searchParams: Promise<{ handling?: string; limit?: string; tenant?: string }>;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const dbBruger = await hentBrugerMedTenant(user.id);
  if (!dbBruger || dbBruger.role !== "admin") redirect("/");

  const locale = dbBruger.effektiv_sprog ?? "da";
  const t = lavT(locale);

  // Admin er platform-bred — hent alle selskaber så loggen kan vise
  // tenant-navn pr. række og tilbyde et selskabs-filter.
  const alleTenants = await hentAlleTenants();
  const tenantNavnPrId = new Map(alleTenants.map((tn) => [tn.id, tn.navn]));

  const sp = await props.searchParams;
  const valgtHandling = sp.handling && GYLDIGE_HANDLINGER.includes(sp.handling as AuditHandling)
    ? (sp.handling as AuditHandling)
    : null;
  const valgtTenantId =
    sp.tenant && tenantNavnPrId.has(Number(sp.tenant))
      ? Number(sp.tenant)
      : null;
  const limit = Math.max(10, Math.min(parseInt(sp.limit || "100", 10) || 100, 1000));

  // tenantId=null → ingen tenant-WHERE i query'en → events på tværs af
  // alle selskaber. Vælger admin et selskab, scopes loggen til det.
  const rows: AuditRow[] = await hentGdprAuditLog({
    tenantId: valgtTenantId,
    handling: valgtHandling,
    limit,
  });

  const eksportParams = new URLSearchParams();
  if (valgtHandling) eksportParams.set("handling", valgtHandling);
  if (valgtTenantId !== null) eksportParams.set("tenant", String(valgtTenantId));
  const eksportHref = eksportParams.toString()
    ? `/admin/audit-log/export?${eksportParams}`
    : `/admin/audit-log/export`;

  // Map handling-koder til oversatte labels via i18n
  function handlingLabel(handling: string): string {
    const key = `admin.audit_log.handling_${handling}`;
    const oversat = t(key);
    return oversat === key ? handling : oversat;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold mb-2">{t("admin.audit_log.titel")}</h2>
          <p className="text-sm text-zinc-600 max-w-3xl">
            {t("admin.audit_log.beskrivelse")}
          </p>
        </div>
        <a
          href={eksportHref}
          className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white rounded-md text-sm font-medium hover:bg-zinc-700 whitespace-nowrap"
          download
        >
          <span aria-hidden>⬇</span> {t("admin.audit_log.download_csv")}
        </a>
      </div>

      <div className="bg-white border border-zinc-200 rounded-lg p-4">
        <form className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-zinc-700">{t("admin.audit_log.filtrer_selskab_label")}</span>
            <select
              name="tenant"
              defaultValue={valgtTenantId !== null ? String(valgtTenantId) : ""}
              className="px-3 py-2 border border-zinc-300 rounded-md text-sm bg-white min-w-[14rem]"
            >
              <option value="">{t("admin.audit_log.alle_selskaber")}</option>
              {alleTenants.map((tn) => (
                <option key={tn.id} value={tn.id}>
                  {tn.navn}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-zinc-700">{t("admin.audit_log.filtrer_label")}</span>
            <select
              name="handling"
              defaultValue={valgtHandling ?? ""}
              className="px-3 py-2 border border-zinc-300 rounded-md text-sm bg-white min-w-[14rem]"
            >
              <option value="">{t("admin.audit_log.alle_handlinger")}</option>
              {GYLDIGE_HANDLINGER.map((h) => (
                <option key={h} value={h}>
                  {EMOJI_PR_HANDLING[h] ?? "•"} {handlingLabel(h)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-zinc-700">{t("admin.audit_log.maks_raekker")}</span>
            <select
              name="limit"
              defaultValue={String(limit)}
              className="px-3 py-2 border border-zinc-300 rounded-md text-sm bg-white"
            >
              <option value="50">50</option>
              <option value="100">100</option>
              <option value="200">200</option>
              <option value="500">500</option>
              <option value="1000">1000</option>
            </select>
          </label>
          <button
            type="submit"
            className="px-4 py-2 bg-zinc-900 text-white rounded-md text-sm font-medium hover:bg-zinc-700"
          >
            {t("admin.audit_log.anvend_filter")}
          </button>
          {(valgtHandling || valgtTenantId !== null) && (
            <Link
              href="/admin/audit-log"
              className="text-sm text-zinc-600 underline-offset-4 hover:underline"
            >
              {t("admin.audit_log.ryd_filter")}
            </Link>
          )}
        </form>
      </div>

      {rows.length === 0 ? (
        <div className="bg-white border border-zinc-200 rounded-lg p-8 text-center text-zinc-500">
          {t("admin.audit_log.ingen_events")}
        </div>
      ) : (
        <div className="bg-white border border-zinc-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 border-b border-zinc-200">
              <tr className="text-left text-xs uppercase tracking-wide text-zinc-500">
                <th className="px-4 py-3 font-medium">{t("admin.audit_log.kol_dato")}</th>
                <th className="px-4 py-3 font-medium">{t("admin.audit_log.kol_tidspunkt")}</th>
                <th className="px-4 py-3 font-medium">{t("admin.audit_log.kol_selskab")}</th>
                <th className="px-4 py-3 font-medium">{t("admin.audit_log.kol_bruger")}</th>
                <th className="px-4 py-3 font-medium">{t("admin.audit_log.kol_handling")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const emoji = EMOJI_PR_HANDLING[r.handling] ?? "•";
                const handlingTekst = handlingLabel(r.handling);
                return (
                  <tr key={r.id} className="border-b border-zinc-100 last:border-b-0 hover:bg-zinc-50">
                    <td className="px-4 py-3 text-zinc-700 whitespace-nowrap">
                      {formatDato(r.tidspunkt, locale)}
                    </td>
                    <td className="px-4 py-3 text-zinc-700 whitespace-nowrap font-mono text-xs">
                      {formatTidspunkt(r.tidspunkt, locale)}
                    </td>
                    <td className="px-4 py-3 text-zinc-700 whitespace-nowrap">
                      {tenantNavnPrId.get(r.tenant_id) ?? `#${r.tenant_id}`}
                    </td>
                    <td className="px-4 py-3 text-zinc-700">
                      {r.user_email ? (
                        <div>
                          <div className="font-medium">{r.user_email}</div>
                          {r.user_id && (
                            <div className="text-xs text-zinc-400">{t("admin.audit_log.id_label")}: {r.user_id}</div>
                          )}
                        </div>
                      ) : (
                        <span className="text-zinc-400 italic">{t("admin.audit_log.system")}</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1.5">
                        <span aria-hidden>{emoji}</span>
                        <span className="text-zinc-900">{handlingTekst}</span>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-zinc-500">
        {t("admin.audit_log.viser_raekker", {
          antal: rows.length,
          suffix: rows.length === 1 ? "" : (locale === "no" ? "er" : "r"),
          maks: limit,
        })}
      </p>
    </div>
  );
}
