"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { useT } from "@/lib/i18n/client";

type Kilde = "naevnet" | "klager" | "selskab";
type Fil = { navn: string; titel: string; kilde: Kilde };
type Sag = {
  mappe: string;
  sagsnr: string;
  indklagede: string;
  klager: string;
  destination: string;
  rejseperiode: string;
  antal_rejsende: string;
  rejse_pris: string;
  filer: Fil[];
};

type TestBruger = {
  slug: string;
  navn: string;
  by: string;
  sagsbehandler: string;
  email: string;
  fulde_navn: string;
  matchende_test_sag: string;
};

type TestBrugereConfig = {
  test_password: string;
  brugere: TestBruger[];
};

const KILDE_BADGE_STYLE: Record<Kilde, string> = {
  naevnet: "bg-blue-50 text-blue-700 border-blue-200",
  klager: "bg-emerald-50 text-emerald-700 border-emerald-200",
  selskab: "bg-amber-50 text-amber-800 border-amber-200",
};

const KILDE_RAEKKEFOELGE: Kilde[] = ["naevnet", "klager", "selskab"];

export function TestSagDownloads({ sager }: { sager: Sag[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {sager.map((sag) => (
        <SagKort key={sag.mappe} sag={sag} />
      ))}
    </div>
  );
}

function SagKort({ sag }: { sag: Sag }) {
  const t = useT();
  const [henter, sætHenter] = useState(false);

  function kildeLabel(kilde: Kilde): string {
    return t(`admin.test_sager.kilde_${kilde}`);
  }

  async function hentSamletZip(s: Sag): Promise<void> {
    // Henter alle filer parallelt og pakker dem som en ZIP i browseren.
    // Bruger JSZip der dynamisk importeres (kun når brugeren rent
    // faktisk klikker på download-knappen — bundle bliver ikke større).
    const JSZip = (await import("jszip")).default;
    const zip = new JSZip();

    const filer = await Promise.all(
      s.filer.map(async (f) => {
        const res = await fetch(`/test-sager/${s.mappe}/${f.navn}`);
        if (!res.ok) throw new Error(t("admin.test_sager.toast_kunne_ikke_hente", { navn: f.navn }));
        const blob = await res.blob();
        return { navn: f.navn, blob };
      }),
    );

    for (const { navn, blob } of filer) {
      zip.file(navn, blob);
    }

    const ud = await zip.generateAsync({ type: "blob" });
    const url = URL.createObjectURL(ud);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${s.mappe}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function hentAlt() {
    sætHenter(true);
    try {
      await hentSamletZip(sag);
      toast.success(t("admin.test_sager.toast_zip_hentet", { navn: sag.indklagede }));
    } catch (e) {
      toast.error(
        e instanceof Error
          ? `${t("admin.test_sager.toast_zip_fejl_prefix")}: ${e.message}`
          : t("admin.test_sager.toast_zip_fejl_ukendt"),
      );
    } finally {
      sætHenter(false);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <CardTitle className="text-sm font-semibold leading-tight">
              {sag.indklagede}
            </CardTitle>
            <p className="text-xs text-zinc-500">
              {t("admin.test_sager.jnr_prefix")} {sag.sagsnr} · {sag.klager}
            </p>
          </div>
          <Button
            size="sm"
            variant="default"
            onClick={hentAlt}
            disabled={henter}
            className="shrink-0"
          >
            {henter
              ? t("admin.test_sager.knap_pakker")
              : t("admin.test_sager.knap_hent_zip")}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="text-xs space-y-1">
          <div className="flex gap-2">
            <dt className="text-zinc-500 w-20 shrink-0">
              {t("admin.test_sager.label_destination")}
            </dt>
            <dd className="text-zinc-700">{sag.destination}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-zinc-500 w-20 shrink-0">
              {t("admin.test_sager.label_periode")}
            </dt>
            <dd className="text-zinc-700">{sag.rejseperiode}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-zinc-500 w-20 shrink-0">
              {t("admin.test_sager.label_rejsende")}
            </dt>
            <dd className="text-zinc-700">{sag.antal_rejsende}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-zinc-500 w-20 shrink-0">
              {t("admin.test_sager.label_pris")}
            </dt>
            <dd className="text-zinc-700">{sag.rejse_pris}</dd>
          </div>
        </dl>

        <div className="pt-2 border-t border-zinc-100 space-y-3">
          <p className="text-xs font-medium text-zinc-600">
            {t("admin.test_sager.filer_antal", { antal: sag.filer.length })}
          </p>
          {KILDE_RAEKKEFOELGE.map((kilde) => {
            const filer = sag.filer.filter((f) => f.kilde === kilde);
            if (filer.length === 0) return null;
            return (
              <div key={kilde} className="space-y-1">
                <span
                  className={`inline-block text-[10px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded border ${KILDE_BADGE_STYLE[kilde]}`}
                >
                  {kildeLabel(kilde)} · {filer.length}
                </span>
                <ul className="space-y-0.5 ml-1">
                  {filer.map((f) => (
                    <li key={f.navn} className="text-xs">
                      <a
                        href={`/test-sager/${sag.mappe}/${f.navn}`}
                        download
                        className="text-blue-600 hover:text-blue-800 hover:underline inline-flex items-center gap-1"
                      >
                        <span aria-hidden>📄</span>
                        <span>{f.titel}</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}


export function TestBrugereOversigt({ config }: { config: TestBrugereConfig }) {
  const t = useT();

  async function kopier(tekst: string, label: string) {
    try {
      await navigator.clipboard.writeText(tekst);
      toast.success(t("admin.test_sager.toast_kopieret", { label }));
    } catch {
      toast.error(t("admin.test_sager.toast_kopier_fejl"));
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold">
          {t("admin.test_sager.test_logins_titel")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-zinc-600 leading-relaxed">
          {t("admin.test_sager.test_logins_beskrivelse_prefix")}{" "}
          <strong>{t("admin.test_sager.test_logins_beskrivelse_strong")}</strong>
          {t("admin.test_sager.test_logins_beskrivelse_suffix")}
        </p>

        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <strong>{t("admin.test_sager.obs_label")}</strong>{" "}
          {t("admin.test_sager.obs_tekst")}
        </div>

        <div className="flex items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2">
          <span className="text-xs font-medium text-zinc-500 shrink-0">
            {t("admin.test_sager.adgangskode_label")}
          </span>
          <code className="text-xs font-mono text-zinc-900 flex-1 truncate">
            {config.test_password}
          </code>
          <Button
            size="sm"
            variant="outline"
            onClick={() => kopier(config.test_password, t("admin.test_sager.label_adgangskode"))}
            className="h-7 px-2 text-xs shrink-0"
          >
            {t("admin.test_sager.knap_kopier")}
          </Button>
        </div>

        <div className="space-y-2">
          {config.brugere.map((b) => (
            <div
              key={b.email}
              className="flex items-center gap-3 rounded-md border border-zinc-200 px-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-zinc-900 truncate">
                  {b.navn}
                </p>
                <code className="text-xs font-mono text-zinc-600 block truncate">
                  {b.email}
                </code>
              </div>
              <span className="text-[10px] text-zinc-400 font-mono shrink-0 hidden sm:inline">
                → {b.matchende_test_sag}
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => kopier(b.email, t("admin.test_sager.label_email"))}
                className="h-7 px-2 text-xs shrink-0"
              >
                {t("admin.test_sager.knap_kopier_email")}
              </Button>
            </div>
          ))}
        </div>

        <p className="text-xs text-zinc-500">
          {t("admin.test_sager.fodnote_prefix")}{" "}
          <code className="bg-zinc-100 px-1 py-0.5 rounded text-[11px]">
            python3 scripts/opret_test_brugere.py
          </code>{" "}
          {t("admin.test_sager.fodnote_midte")}{" "}
          <code className="bg-zinc-100 px-1 py-0.5 rounded text-[11px]">
            --slet
          </code>{" "}
          {t("admin.test_sager.fodnote_suffix")}
        </p>
      </CardContent>
    </Card>
  );
}
