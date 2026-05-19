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
} from "@/app/admin/actions";
import type { Tenant } from "@/lib/queries/tenants";
import { useRouter } from "next/navigation";
import { useT } from "@/lib/i18n/client";

const SPROG = ["da", "sv", "no", "fi"] as const;
const LANDE = ["DK", "SE", "NO", "FI"] as const;

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
                  <p className="font-medium text-sm">
                    {tenant.navn}{" "}
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

    startTransition(async () => {
      const r = erRedigering
        ? await opdaterTenantAction(eksisterende!.id, felter)
        : await opretTenantAction({ ...felter, slug: slug.trim() });
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
