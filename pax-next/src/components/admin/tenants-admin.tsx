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

const SPROG = ["da", "sv", "no", "fi"] as const;
const LANDE = ["DK", "SE", "NO", "FI"] as const;

export function TenantsAdmin({ tenants }: { tenants: Tenant[] }) {
  const [editId, setEditId] = useState<number | null>(null);
  const [opretterNy, setOpretterNy] = useState(false);

  const aktivTenant = tenants.find((t) => t.id === editId) ?? null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">
            Eksisterende selskaber ({tenants.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {tenants.length === 0 ? (
            <p className="text-sm text-zinc-500">Ingen tenants oprettet endnu.</p>
          ) : (
            tenants.map((t) => (
              <div
                key={t.id}
                className="flex items-center justify-between rounded-md border border-zinc-200 px-4 py-3"
              >
                <div className="space-y-1">
                  <p className="font-medium text-sm">
                    {t.navn}{" "}
                    <span className="text-zinc-400 font-normal">
                      · slug=<code className="text-xs">{t.slug}</code> · id={t.id}
                    </span>
                  </p>
                  <p className="text-xs text-zinc-500">
                    {t.by || "—"} · {t.sagsbehandler} · {t.land}/{t.sprog}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setEditId(t.id);
                    setOpretterNy(false);
                  }}
                >
                  Rediger
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
          Opret nyt selskab
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
        toast.success(erRedigering ? "Tenant opdateret" : "Tenant oprettet");
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
          {erRedigering ? `Rediger ${eksisterende!.navn}` : "Opret nyt selskab"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Felt label="Selskabsnavn">
            <Input
              value={navn}
              onChange={(e) => sætNavn(e.target.value)}
              placeholder="fx 'Apollo'"
              disabled={pending}
            />
          </Felt>
          <Felt
            label="Slug"
            hjælp={
              erRedigering
                ? "Slug kan ikke ændres efter oprettelse."
                : "Små bogstaver, tal, bindestreger (fx 'apollo-dk')."
            }
          >
            <Input
              value={slug}
              onChange={(e) => sætSlug(e.target.value.toLowerCase())}
              placeholder="fx 'apollo'"
              disabled={pending || erRedigering}
            />
          </Felt>
          <Felt label="Sagsbehandler-signatur" hjælp="Default = selskabsnavnet.">
            <Input
              value={sagsbehandler}
              onChange={(e) => sætSagsbehandler(e.target.value)}
              placeholder="fx 'Apollo Kundeservice'"
              disabled={pending}
            />
          </Felt>
          <Felt label="By (datolinje)">
            <Input
              value={by}
              onChange={(e) => sætBy(e.target.value)}
              placeholder="fx 'København'"
              disabled={pending}
            />
          </Felt>
          <Felt label="Anonymiserings-suffix" hjælp="Default = selskabsnavnet.">
            <Input
              value={anonymSuffix}
              onChange={(e) => sætAnonymSuffix(e.target.value)}
              placeholder="fx 'Apollo'"
              disabled={pending}
            />
          </Felt>
          <Felt label="Lov-navn">
            <Input
              value={lovNavn}
              onChange={(e) => sætLovNavn(e.target.value)}
              disabled={pending}
            />
          </Felt>
        </div>

        <Felt
          label="Interne team-navne"
          hjælp="En pr. linje. Bruges af AI-anonymisering til at skelne interne medarbejdere fra eksterne."
        >
          <textarea
            value={teamNavne}
            onChange={(e) => sætTeamNavne(e.target.value)}
            placeholder="After Travel&#10;Kundeservice"
            disabled={pending}
            rows={3}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900 disabled:opacity-50"
          />
        </Felt>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Felt label="Klageorgan-navn">
            <Input
              value={klageorganNavn}
              onChange={(e) => sætKlageorganNavn(e.target.value)}
              disabled={pending}
            />
          </Felt>
          <Felt label="Klageorgan-URL">
            <Input
              value={klageorganUrl}
              onChange={(e) => sætKlageorganUrl(e.target.value)}
              disabled={pending}
            />
          </Felt>
          <Felt label="Sprog">
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
          <Felt label="Land">
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
          label="Rejsevilkår-kilde URL (valgfrit)"
          hjælp="Bruges til scraping af deres officielle rejsevilkår — gemmes på tenanten."
        >
          <Input
            value={rejsevilkaarUrl}
            onChange={(e) => sætRejsevilkaarUrl(e.target.value)}
            placeholder="https://www.apollorejser.dk/rejsevilkaar/"
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
              ? "Gemmer..."
              : erRedigering
                ? "Gem ændringer"
                : "Opret tenant"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={onAfslut}
            disabled={pending}
          >
            Annullér
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
