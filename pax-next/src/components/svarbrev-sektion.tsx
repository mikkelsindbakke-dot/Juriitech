"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { toast } from "sonner";
import type { Tidsforhold } from "@/components/analyse-resultat";
import {
  postOgValider,
  sagsmetadataSchema,
  svarbrevSchema,
} from "@/lib/api-client";
import { useFejlBesked, useIsAdmin } from "@/lib/bruger-rolle";
import { useT } from "@/lib/i18n/client";

type SvarbrevRespons = {
  svarbrev: string;
  docx_base64?: string;
  docx_fejl?: string | null;
  paragraf_advarsler?: string[];
  metadata: {
    antal_filer: number;
    antal_instrukser: number;
    inkluder_kildehenvisninger: boolean;
    sagsnummer?: string;
    klagers_navn?: string;
    hoeringssvar_nr?: number;
    antal_bilag?: number;
    tegn: number;
  };
};

export type BilagItem = {
  bogstav: string;
  overskrift: string;
};

export function SvarbrevSektion({
  filer,
  klagepunkter,
  tidsforhold,
  bilagListe,
}: {
  filer: File[];
  klagepunkter?: string[];
  tidsforhold?: Tidsforhold;
  bilagListe?: BilagItem[];
}) {
  const t = useT();
  const isAdmin = useIsAdmin();
  const formatFejl = useFejlBesked();
  const [pending, startTransition] = useTransition();
  const [meta_pending, startMetaTransition] = useTransition();

  const [instrukser, sætInstrukser] = useState<string[]>([]);
  const [nyInstruks, sætNyInstruks] = useState("");
  const [kilder, sætKilder] = useState(false);

  // Brevhoved-felter (sektion: 13. Generer svarbrev til Nævnet)
  const [sagsnummer, sætSagsnummer] = useState("");
  const [klagersNavn, sætKlagersNavn] = useState("");
  const [hoeringssvarNr, sætHoeringssvarNr] = useState<1 | 2 | 3>(1);
  // Guard mod gentagne metadata-kald ved re-renders. useRef i stedet for
  // useState så vi ikke trigger en re-render når låsen sættes — og så
  // lint-reglen mod setState-i-effect ikke rammer.
  const metaHentet = useRef(false);

  const [svarbrev, sætSvarbrev] = useState<SvarbrevRespons | null>(null);

  // Auto-udtrækning af sagsnummer + klagers navn ved første render efter
  // filer er valgt. Cacher pr. fil-signatur så vi ikke kalder igen ved
  // hver re-render. Fejler stille — brugeren kan altid skrive selv.
  useEffect(() => {
    if (metaHentet.current || filer.length === 0) return;
    metaHentet.current = true;
    startMetaTransition(async () => {
      try {
        const formData = new FormData();
        for (const fil of filer) formData.append("filer", fil);
        // Kort kald (~3s). Færre retries — ingen grund til at brugeren
        // venter længere på et auto-udfyldt felt der bare kan rettes
        // manuelt.
        const data = await postOgValider(
          "/api/sagsmetadata",
          sagsmetadataSchema,
          { formData, retries: 2 },
        );
        if (data.sagsnummer && !sagsnummer) sætSagsnummer(data.sagsnummer);
        if (data.klagers_navn && !klagersNavn)
          sætKlagersNavn(data.klagers_navn);
      } catch (e) {
        console.warn("Auto-udtrækning af brevhoved fejlede:", e);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filer]);

  function tilfoejInstruks() {
    const v = nyInstruks.trim();
    if (!v) return;
    sætInstrukser((xs) => [...xs, v]);
    sætNyInstruks("");
  }

  function fjernInstruks(i: number) {
    sætInstrukser((xs) => xs.filter((_, idx) => idx !== i));
  }

  function generer() {
    if (filer.length === 0) {
      toast.error(t("svarbrev.vaelg_filer_foerst"));
      return;
    }
    startTransition(async () => {
      const formData = new FormData();
      for (const fil of filer) formData.append("filer", fil);
      formData.append("ekstra_instrukser_json", JSON.stringify(instrukser));
      formData.append("inkluder_kildehenvisninger", String(kilder));
      formData.append("sagsnummer", sagsnummer.trim());
      formData.append("klagers_navn", klagersNavn.trim());
      formData.append("hoeringssvar_nr", String(hoeringssvarNr));
      if (bilagListe && bilagListe.length > 0) {
        formData.append("bilag_liste_json", JSON.stringify(bilagListe));
      }
      if (klagepunkter) {
        formData.append(
          "verificerede_klagepunkter_json",
          JSON.stringify(klagepunkter),
        );
      }
      if (tidsforhold) {
        formData.append("tidsforhold_json", JSON.stringify(tidsforhold));
      }

      try {
        const data = (await postOgValider(
          "/api/svarbrev",
          svarbrevSchema,
          { formData, retries: 3 },
        )) as SvarbrevRespons;
        sætSvarbrev(data);
        toast.success(
          t("svarbrev.svarbrev_genereret_toast", { tegn: data.metadata.tegn }),
        );

        // Auto-arkivering FJERNET — vi gemmer ikke længere svarbreve
        // på siden af GDPR/datasikkerheds-grunde. Brugeren skal hente
        // DOCX-fil og selv arkivere lokalt.
      } catch (e) {
        toast.error(formatFejl(e));
      }
    });
  }

  function kopier() {
    if (!svarbrev) return;
    navigator.clipboard
      .writeText(svarbrev.svarbrev)
      .then(() => toast.success(t("svarbrev.kopieret_toast")))
      .catch(() => toast.error(t("svarbrev.kopi_fejl_toast")));
  }

  function downloadDocx() {
    if (!svarbrev?.docx_base64) {
      toast.error(t("svarbrev.docx_ikke_klar_toast"));
      return;
    }
    try {
      const binaer = atob(svarbrev.docx_base64);
      const buf = new Uint8Array(binaer.length);
      for (let i = 0; i < binaer.length; i++) buf[i] = binaer.charCodeAt(i);
      const blob = new Blob([buf], {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      });
      const klageFn = filer[0]?.name ?? "svarbrev";
      const filnavn = `svarbrev_${klageFn.replace(/\.[^.]+$/, "")}.docx`;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filnavn;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      toast.error(formatFejl(e));
    }
  }

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        {/* Særlige instrukser */}
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label>
              {t("svarbrev.saerlige_instrukser_label")}{" "}
              <span className="text-zinc-400">{t("svarbrev.valgfrit")}</span>
            </Label>
            <InfoTooltip>
              {t("svarbrev.saerlige_instrukser_tooltip")}
            </InfoTooltip>
          </div>
          <div className="flex gap-2">
            <Input
              value={nyInstruks}
              onChange={(e) => sætNyInstruks(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  tilfoejInstruks();
                }
              }}
              placeholder={t("svarbrev.instruks_placeholder")}
              disabled={pending}
            />
            <Button
              type="button"
              variant="secondary"
              size="default"
              onClick={tilfoejInstruks}
              disabled={pending || !nyInstruks.trim()}
            >
              {t("svarbrev.tilfoej_instruks")}
            </Button>
          </div>
          {instrukser.length > 0 && (
            <ul className="space-y-1 pt-1">
              {instrukser.map((instr, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-md bg-indigo-50 border-l-2 border-indigo-500 px-3 py-2 text-sm"
                >
                  <span className="font-semibold text-zinc-700">{i + 1}.</span>
                  <span className="flex-1 text-zinc-800">{instr}</span>
                  <button
                    type="button"
                    onClick={() => fjernInstruks(i)}
                    disabled={pending}
                    className="text-zinc-400 hover:text-red-700 text-sm leading-none"
                    aria-label={t("svarbrev.fjern_instruks_aria")}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Toggle: kildehenvisninger */}
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={kilder}
            onChange={(e) => sætKilder(e.target.checked)}
            disabled={pending}
          />
          <span className="text-sm font-medium">
            {t("svarbrev.kildehenvisninger_label")}
          </span>
          <InfoTooltip>
            {t("svarbrev.kildehenvisninger_tooltip_til")}
            <br />
            <br />
            {t("svarbrev.kildehenvisninger_tooltip_fra")}
          </InfoTooltip>
        </label>

        {/* Brevhoved */}
        <div className="space-y-3 pt-2 border-t border-zinc-200">
          <div className="flex items-center gap-1.5">
            <Label className="text-sm font-semibold">
              {t("svarbrev.brevhoved")}
            </Label>
            <InfoTooltip>{t("svarbrev.brevhoved_tooltip")}</InfoTooltip>
            {meta_pending && (
              <span className="text-xs italic text-indigo-600">
                {t("svarbrev.henter_sagsdata")}
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="sagsnummer" className="text-xs">
                {t("svarbrev.sagsnummer")}
              </Label>
              <Input
                id="sagsnummer"
                value={sagsnummer}
                onChange={(e) => sætSagsnummer(e.target.value)}
                placeholder={t("svarbrev.sagsnummer_placeholder")}
                disabled={pending}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="klagersnavn" className="text-xs">
                {t("svarbrev.klagers_navn")}
              </Label>
              <Input
                id="klagersnavn"
                value={klagersNavn}
                onChange={(e) => sætKlagersNavn(e.target.value)}
                placeholder={t("svarbrev.klagers_navn_placeholder")}
                disabled={pending}
              />
            </div>
          </div>

          {/* Høringssvar-nummer */}
          <div className="space-y-1">
            <div className="flex items-center gap-1.5">
              <Label className="text-xs">
                {t("svarbrev.hoeringssvar_nummer")}
              </Label>
              <InfoTooltip>{t("svarbrev.hoeringssvar_tooltip")}</InfoTooltip>
            </div>
            <div className="inline-flex rounded-md border border-zinc-300 bg-white p-0.5">
              {([1, 2, 3] as const).map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => sætHoeringssvarNr(n)}
                  disabled={pending}
                  className={`px-3 py-1.5 text-sm rounded-sm transition-colors disabled:opacity-50 ${
                    hoeringssvarNr === n
                      ? "bg-indigo-100 text-indigo-900 font-medium"
                      : "text-zinc-600 hover:bg-zinc-50"
                  }`}
                >
                  {t("svarbrev.hoeringssvar_knap", { n })}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Generér-knap */}
        <Button
          type="button"
          onClick={generer}
          disabled={pending || filer.length === 0}
          className="w-full h-12"
        >
          {pending
            ? t("svarbrev.skriver_svarbrev")
            : t("svarbrev.generer_udkast")}
        </Button>

        {pending && (
          <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-4 space-y-3">
            <p className="text-sm font-medium text-indigo-900">
              {t("svarbrev.progress_titel")}
            </p>
            <p className="text-xs text-indigo-700">
              {t("svarbrev.progress_tid")}
            </p>
            <div className="h-2 w-full overflow-hidden rounded-full bg-indigo-100">
              <div
                className="h-full w-full bg-gradient-to-r from-indigo-500 via-violet-500 via-sky-500 to-indigo-500 bg-[length:200%_100%]"
                style={{
                  animation: "pax-pulse 1.8s ease-in-out infinite",
                  backgroundSize: "200% 100%",
                }}
              />
            </div>
            <style>{`
              @keyframes pax-pulse {
                0%   { background-position:   0% 50%; opacity: 0.85; }
                50%  { background-position: 100% 50%; opacity: 1; }
                100% { background-position:   0% 50%; opacity: 0.85; }
              }
            `}</style>
          </div>
        )}

        {/* Resultat */}
        {svarbrev && (
          <div className="space-y-3 border-t border-zinc-200 pt-4">
            {/* Admin-only paragraf-hallucinations-advarsel — vises kun
                hvis AI har citeret §-referencer der ikke findes i
                pakkerejseloven. Brugere ser aldrig denne. */}
            {isAdmin &&
              svarbrev.paragraf_advarsler &&
              svarbrev.paragraf_advarsler.length > 0 && (
                <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
                  <p className="font-medium mb-1">
                    {t("svarbrev.admin_paragraf_titel")}
                  </p>
                  <p className="text-xs text-amber-800">
                    {t("svarbrev.admin_paragraf_beskrivelse")}{" "}
                    <span className="font-mono">
                      {svarbrev.paragraf_advarsler.join(", ")}
                    </span>
                  </p>
                </div>
              )}
            <div className="flex items-center justify-between flex-wrap gap-2">
              <p className="text-sm font-medium">
                {t("svarbrev.genereret_svarbrev")}
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="default"
                  size="sm"
                  onClick={downloadDocx}
                  disabled={!svarbrev.docx_base64}
                  title={
                    svarbrev.docx_fejl
                      ? isAdmin
                        ? t("svarbrev.word_export_fejl_admin", {
                            fejl: svarbrev.docx_fejl,
                          })
                        : t("svarbrev.word_export_fejl_bruger")
                      : undefined
                  }
                >
                  {t("svarbrev.download_word")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={kopier}
                >
                  {t("svarbrev.kopier")}
                </Button>
              </div>
            </div>
            <pre className="whitespace-pre-wrap rounded-md bg-zinc-50 p-4 text-sm text-zinc-800 font-sans leading-relaxed border border-zinc-200">
              {svarbrev.svarbrev}
            </pre>
            <p className="text-xs text-zinc-500">
              {t("svarbrev.metadata_tegn", { tegn: svarbrev.metadata.tegn })} ·{" "}
              {t("svarbrev.metadata_instrukser", {
                antal: svarbrev.metadata.antal_instrukser,
              })}{" "}
              ·{" "}
              {t("svarbrev.metadata_kilder", {
                vaerdi: svarbrev.metadata.inkluder_kildehenvisninger
                  ? t("svarbrev.ja")
                  : t("svarbrev.nej"),
              })}
              {svarbrev.metadata.sagsnummer && (
                <>
                  {" · "}
                  {t("svarbrev.metadata_sag", {
                    sagsnummer: svarbrev.metadata.sagsnummer,
                  })}
                </>
              )}
              {" · "}
              {t("svarbrev.metadata_hoeringssvar", {
                n: svarbrev.metadata.hoeringssvar_nr ?? 1,
              })}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
