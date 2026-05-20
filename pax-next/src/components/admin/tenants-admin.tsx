"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import {
  opretTenantAction,
  opdaterTenantAction,
  konverterProeveTenantAction,
  forlængProeveTenantAction,
} from "@/app/admin/actions";
import type { Tenant } from "@/lib/queries/tenants";
import { useRouter } from "next/navigation";
import { useT } from "@/lib/i18n/client";

const SPROG = ["da", "sv", "no", "fi"] as const;
const LANDE = ["DK", "SE", "NO", "FI"] as const;

// Beregn YYYY-MM-DD-streng N dage fra i dag — i lokal tidszone.
// Bruges som default udløbsdato i prøve-tenant-formularen.
function omDageISODato(dage: number): string {
  const d = new Date();
  d.setDate(d.getDate() + dage);
  return d.toISOString().slice(0, 10);
}

// Konvertér en YYYY-MM-DD-streng (fra <input type="date">) til en
// ISO-streng der peger på slutningen af dagen (23:59:59) i lokal tid.
// Det betyder at trial "udløber 2026-06-03" gælder til og med kl. 23:59
// den dag, ikke ved midnat.
function datoInputTilISO(yyyy_mm_dd: string): string {
  const d = new Date(yyyy_mm_dd + "T23:59:59");
  return d.toISOString();
}

function dageFraNu(isoString: string | null): number | null {
  if (!isoString) return null;
  const ms = new Date(isoString).getTime() - Date.now();
  return Math.ceil(ms / (1000 * 60 * 60 * 24));
}

export function TenantsAdmin({ tenants }: { tenants: Tenant[] }) {
  const t = useT();
  const [editId, setEditId] = useState<number | null>(null);
  const [opretterNy, setOpretterNy] = useState(false);

  const aktivTenant = tenants.find((tenant) => tenant.id === editId) ?? null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">
            {t("admin.tenants.eksisterende_titel", { antal: tenants.length })}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {tenants.length === 0 ? (
            <p className="text-sm text-zinc-500">{t("admin.tenants.ingen_tenants")}</p>
          ) : (
            tenants.map((tenant) => (
              <div
                key={tenant.id}
                className="flex items-center justify-between rounded-md border border-zinc-200 px-4 py-3"
              >
                <div className="space-y-1">
                  <p className="font-medium text-sm flex flex-wrap items-center gap-2">
                    <span>{tenant.navn}</span>
                    <ProeveBadge tenant={tenant} />
                    <span className="text-zinc-400 font-normal">
                      · {t("admin.tenants.slug_label")}=<code className="text-xs">{tenant.slug}</code> · {t("admin.tenants.id_label")}={tenant.id}
                    </span>
                  </p>
                  <p className="text-xs text-zinc-500">
                    {tenant.by || "—"} · {tenant.sagsbehandler} · {tenant.land}/{tenant.sprog}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setEditId(tenant.id);
                    setOpretterNy(false);
                  }}
                >
                  {t("admin.tenants.rediger")}
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {!aktivTenant && !opretterNy && (
        <Button
          type="button"
          onClick={() => {
            setOpretterNy(true);
            setEditId(null);
          }}
        >
          {t("admin.tenants.opret_nyt")}
        </Button>
      )}

      {(aktivTenant || opretterNy) && (
        <TenantForm
          eksisterende={aktivTenant}
          onAfslut={() => {
            setEditId(null);
            setOpretterNy(false);
          }}
        />
      )}
    </div>
  );
}

function TenantForm({
  eksisterende,
  onAfslut,
}: {
  eksisterende: Tenant | null;
  onAfslut: () => void;
}) {
  const t = useT();
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const erRedigering = !!eksisterende;

  const [navn, sætNavn] = useState(eksisterende?.navn ?? "");
  const [slug, sætSlug] = useState(eksisterende?.slug ?? "");
  const [sagsbehandler, sætSagsbehandler] = useState(
    eksisterende?.sagsbehandler ?? "",
  );
  const [by, sætBy] = useState(eksisterende?.by ?? "");
  const [anonymSuffix, sætAnonymSuffix] = useState(
    eksisterende?.anonymisering_suffix ?? "",
  );
  const [teamNavne, sætTeamNavne] = useState(
    (eksisterende?.interne_team_navne ?? []).join("\n"),
  );
  const [klageorganNavn, sætKlageorganNavn] = useState(
    eksisterende?.klageorgan_navn ?? "Pakkerejse-Ankenævnet",
  );
  const [klageorganUrl, sætKlageorganUrl] = useState(
    eksisterende?.klageorgan_url ?? "https://www.pakkerejseankenaevnet.dk",
  );
  const [lovNavn, sætLovNavn] = useState(
    eksisterende?.lov_navn ?? "Pakkerejseloven",
  );
  const [rejsevilkaarUrl, sætRejsevilkaarUrl] = useState(
    eksisterende?.rejsevilkaar_kilde_url ?? "",
  );
  const [sprog, sætSprog] = useState<(typeof SPROG)[number]>(
    (eksisterende?.sprog as (typeof SPROG)[number]) ?? "da",
  );
  const [land, sætLand] = useState<(typeof LANDE)[number]>(
    (eksisterende?.land as (typeof LANDE)[number]) ?? "DK",
  );
  // Prøve-tenant state. Ved oprettelse default 14 dage frem; ved
  // redigering vises kun konvertér/forlæng-knapper (felterne kan
  // ikke ændres direkte fra formularen — admin skal eksplicit
  // forlænge med en knap, så audit-sporet er klart).
  const [erProeve, sætErProeve] = useState<boolean>(
    eksisterende?.is_trial ?? false,
  );
  const [proeveUdloeber, sætProeveUdloeber] = useState<string>(
    eksisterende?.trial_expires_at
      ? new Date(eksisterende.trial_expires_at).toISOString().slice(0, 10)
      : omDageISODato(14),
  );

  function gem() {
    const teamListe = teamNavne
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    const felter = {
      navn: navn.trim(),
      sagsbehandler: sagsbehandler.trim() || navn.trim(),
      by: by.trim(),
      anonymisering_suffix: anonymSuffix.trim() || navn.trim(),
      interne_team_navne: teamListe,
      klageorgan_navn: klageorganNavn.trim(),
      klageorgan_url: klageorganUrl.trim(),
      rejsevilkaar_kilde_url: rejsevilkaarUrl.trim(),
      sprog,
      land,
      lov_navn: lovNavn.trim(),
    };

    // Prøve-felter sendes KUN ved oprettelse. Ved redigering er
    // konvertér/forlæng dedikerede knapper (med audit-spor).
    const opretFelter = erProeve
      ? {
          ...felter,
          slug: slug.trim(),
          is_trial: true,
          trial_expires_at: datoInputTilISO(proeveUdloeber),
        }
      : { ...felter, slug: slug.trim() };

    startTransition(async () => {
      const r = erRedigering
        ? await opdaterTenantAction(eksisterende!.id, felter)
        : await opretTenantAction(opretFelter);
      if (r.ok) {
        toast.success(erRedigering ? t("admin.tenants.toast_opdateret") : t("admin.tenants.toast_oprettet"));
        onAfslut();
        router.refresh();
      } else {
        toast.error(r.fejl);
      }
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-semibold">
          {erRedigering
            ? t("admin.tenants.form_rediger_titel", { navn: eksisterende!.navn })
            : t("admin.tenants.form_opret_titel")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Felt label={t("admin.tenants.felt_navn")}>
            <Input
              value={navn}
              onChange={(e) => sætNavn(e.target.value)}
              placeholder={t("admin.tenants.felt_navn_placeholder")}
              disabled={pending}
            />
          </Felt>
          <Felt
            label={t("admin.tenants.felt_slug")}
            hjælp={
              erRedigering
                ? t("admin.tenants.felt_slug_hjaelp_rediger")
                : t("admin.tenants.felt_slug_hjaelp_opret")
            }
          >
            <Input
              value={slug}
              onChange={(e) => sætSlug(e.target.value.toLowerCase())}
              placeholder={t("admin.tenants.felt_slug_placeholder")}
              disabled={pending || erRedigering}
            />
          </Felt>
          <Felt label={t("admin.tenants.felt_sagsbehandler")} hjælp={t("admin.tenants.felt_sagsbehandler_hjaelp")}>
            <Input
              value={sagsbehandler}
              onChange={(e) => sætSagsbehandler(e.target.value)}
              placeholder={t("admin.tenants.felt_sagsbehandler_placeholder")}
              disabled={pending}
            />
          </Felt>
          <Felt label={t("admin.tenants.felt_by")}>
            <Input
              value={by}
              onChange={(e) => sætBy(e.target.value)}
              placeholder={t("admin.tenants.felt_by_placeholder")}
              disabled={pending}
            />
          </Felt>
          <Felt label={t("admin.tenants.felt_anonym_suffix")} hjælp={t("admin.tenants.felt_anonym_suffix_hjaelp")}>
            <Input
              value={anonymSuffix}
              onChange={(e) => sætAnonymSuffix(e.target.value)}
              placeholder={t("admin.tenants.felt_anonym_suffix_placeholder")}
              disabled={pending}
            />
          </Felt>
          <Felt label={t("admin.tenants.felt_lov_navn")}>
            <Input
              value={lovNavn}
              onChange={(e) => sætLovNavn(e.target.value)}
              disabled={pending}
            />
          </Felt>
        </div>

        <Felt
          label={t("admin.tenants.felt_team_navne")}
          hjælp={t("admin.tenants.felt_team_navne_hjaelp")}
        >
          <textarea
            value={teamNavne}
            onChange={(e) => sætTeamNavne(e.target.value)}
            placeholder={t("admin.tenants.felt_team_navne_placeholder")}
            disabled={pending}
            rows={3}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900 disabled:opacity-50"
          />
        </Felt>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Felt label={t("admin.tenants.felt_klageorgan_navn")}>
            <Input
              value={klageorganNavn}
              onChange={(e) => sætKlageorganNavn(e.target.value)}
              disabled={pending}
            />
          </Felt>
          <Felt label={t("admin.tenants.felt_klageorgan_url")}>
            <Input
              value={klageorganUrl}
              onChange={(e) => sætKlageorganUrl(e.target.value)}
              disabled={pending}
            />
          </Felt>
          <Felt label={t("admin.tenants.felt_sprog")}>
            <select
              value={sprog}
              onChange={(e) => sætSprog(e.target.value as (typeof SPROG)[number])}
              disabled={pending}
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
            >
              {SPROG.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Felt>
          <Felt label={t("admin.tenants.felt_land")}>
            <select
              value={land}
              onChange={(e) => sætLand(e.target.value as (typeof LANDE)[number])}
              disabled={pending}
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
            >
              {LANDE.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </Felt>
        </div>

        <Felt
          label={t("admin.tenants.felt_rejsevilkaar")}
          hjælp={t("admin.tenants.felt_rejsevilkaar_hjaelp")}
        >
          <Input
            value={rejsevilkaarUrl}
            onChange={(e) => sætRejsevilkaarUrl(e.target.value)}
            placeholder={t("admin.tenants.felt_rejsevilkaar_placeholder")}
            disabled={pending}
          />
        </Felt>

        {/* Prøve-tenant-sektion — vises kun ved oprettelse. Ved
            redigering bruges dedikerede knapper (konvertér/forlæng)
            længere nede. */}
        {!erRedigering && (
          <div className="rounded-md border border-amber-200 bg-amber-50/50 p-4 space-y-3">
            <div>
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={erProeve}
                  onChange={(e) => sætErProeve(e.target.checked)}
                  disabled={pending}
                  className="mt-0.5 h-4 w-4"
                />
                <div className="space-y-0.5">
                  <span className="text-sm font-medium text-zinc-900">
                    {t("admin.tenants.proeve_checkbox")}
                  </span>
                  <p className="text-xs text-zinc-600">
                    {t("admin.tenants.proeve_checkbox_hjaelp")}
                  </p>
                </div>
              </label>
            </div>
            {erProeve && (
              <Felt
                label={t("admin.tenants.proeve_udloeber_label")}
                hjælp={t("admin.tenants.proeve_udloeber_hjaelp")}
              >
                <Input
                  type="date"
                  value={proeveUdloeber}
                  min={omDageISODato(1)}
                  onChange={(e) => sætProeveUdloeber(e.target.value)}
                  disabled={pending}
                />
              </Felt>
            )}
          </div>
        )}

        {/* Konvertér + forlæng-knapper for eksisterende prøve-tenants */}
        {erRedigering && eksisterende?.is_trial && (
          <ProeveAktioner tenant={eksisterende} disabled={pending} />
        )}

        <div className="flex gap-2 pt-2 border-t border-zinc-200">
          <Button
            type="button"
            onClick={gem}
            disabled={pending || !navn.trim() || (!erRedigering && !slug.trim())}
          >
            {pending
              ? t("admin.tenants.knap_gemmer")
              : erRedigering
                ? t("admin.tenants.knap_gem_aendringer")
                : t("admin.tenants.knap_opret_tenant")}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={onAfslut}
            disabled={pending}
          >
            {t("admin.tenants.knap_annuller")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Knapper til konvertering + forlængelse af en eksisterende prøve-
 * tenant. Vises som dedikeret sektion i edit-formen så hver handling
 * får sit eget audit-spor.
 */
function ProeveAktioner({
  tenant,
  disabled,
}: {
  tenant: Tenant;
  disabled: boolean;
}) {
  const t = useT();
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  function konverter() {
    startTransition(async () => {
      const r = await konverterProeveTenantAction(tenant.id);
      if (r.ok) {
        toast.success(t("admin.tenants.toast_konverteret"));
        router.refresh();
      } else {
        toast.error(r.fejl);
      }
    });
  }

  function forlæng() {
    const nuværende = tenant.trial_expires_at
      ? new Date(tenant.trial_expires_at).toISOString().slice(0, 10)
      : omDageISODato(14);
    const svar = window.prompt(
      t("admin.tenants.forlaeng_prompt"),
      omDageISODato(14),
    );
    if (!svar || svar === nuværende) return;
    startTransition(async () => {
      const r = await forlængProeveTenantAction(
        tenant.id,
        datoInputTilISO(svar),
      );
      if (r.ok) {
        toast.success(t("admin.tenants.toast_forlaenget", { dato: svar }));
        router.refresh();
      } else {
        toast.error(r.fejl);
      }
    });
  }

  return (
    <div className="rounded-md border border-amber-300 bg-amber-50 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <ProeveBadge tenant={tenant} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={forlæng}
          disabled={disabled || pending}
        >
          {t("admin.tenants.knap_forlaeng_proeve")}
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={konverter}
          disabled={disabled || pending}
        >
          {t("admin.tenants.knap_konverter_til_kunde")}
        </Button>
      </div>
    </div>
  );
}

function Felt({
  label,
  hjælp,
  children,
}: {
  label: string;
  hjælp?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {hjælp && <p className="text-xs text-zinc-500">{hjælp}</p>}
    </div>
  );
}

/**
 * Visuel badge der signalerer prøve-tenant status:
 *   - aktiv prøveperiode → gul "🧪 PRØVE — udløber om X dage"
 *   - udløbet → rød "🧪 PRØVE — udløbet for X dage siden"
 *   - konverteret til kunde → grøn "✅ KONVERTERET"
 *   - almindelig betalende tenant → ingen badge (null)
 */
function ProeveBadge({ tenant }: { tenant: Tenant }) {
  const t = useT();
  if (tenant.trial_converted_at) {
    return (
      <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200">
        {t("admin.tenants.proeve_badge_konverteret")}
      </span>
    );
  }
  if (!tenant.is_trial) return null;
  const dage = dageFraNu(tenant.trial_expires_at);
  let label: string;
  let farve: string;
  if (dage === null) {
    label = t("admin.tenants.proeve_badge");
    farve = "bg-zinc-50 text-zinc-600 ring-zinc-200";
  } else if (dage > 0) {
    label = `${t("admin.tenants.proeve_badge")} — ${t("admin.tenants.proeve_badge_udløber_om", { dage })}`;
    farve = "bg-amber-50 text-amber-800 ring-amber-200";
  } else if (dage === 0) {
    label = `${t("admin.tenants.proeve_badge")} — ${t("admin.tenants.proeve_badge_udløbet_i_dag")}`;
    farve = "bg-amber-50 text-amber-800 ring-amber-200";
  } else {
    label = `${t("admin.tenants.proeve_badge")} — ${t("admin.tenants.proeve_badge_udløbet_for", { dage: Math.abs(dage) })}`;
    farve = "bg-rose-50 text-rose-700 ring-rose-200";
  }
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${farve}`}
    >
      {label}
    </span>
  );
}
