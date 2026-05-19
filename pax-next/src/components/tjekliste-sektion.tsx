"use client";

import { useState, useTransition } from "react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import { postOgValider, tjeklisteSchema } from "@/lib/api-client";
import { useFejlBesked } from "@/lib/bruger-rolle";
import { useT } from "@/lib/i18n/client";

type TjeklisteRespons = {
  tjekliste: string;
  metadata: {
    antal_filer: number;
    tegn: number;
  };
};

export function TjeklisteSektion({ filer }: { filer: File[] }) {
  const t = useT();
  const formatFejl = useFejlBesked();
  const [pending, startTransition] = useTransition();
  const [resultat, sætResultat] = useState<TjeklisteRespons | null>(null);

  function generer() {
    if (filer.length === 0) {
      toast.error(t("tjekliste.vaelg_filer_foerst"));
      return;
    }
    startTransition(async () => {
      const formData = new FormData();
      for (const fil of filer) formData.append("filer", fil);

      try {
        const data = (await postOgValider(
          "/api/tjekliste",
          tjeklisteSchema,
          { formData, retries: 3 },
        )) as TjeklisteRespons;
        sætResultat(data);
        toast.success(
          t("tjekliste.tjekliste_klar_toast", { tegn: data.metadata.tegn }),
        );

        // Auto-arkivering FJERNET — vi gemmer ikke længere tjeklister
        // på siden af GDPR/datasikkerheds-grunde.
      } catch (e) {
        toast.error(formatFejl(e));
      }
    });
  }

  function kopier() {
    if (!resultat) return;
    navigator.clipboard
      .writeText(resultat.tjekliste)
      .then(() => toast.success(t("tjekliste.kopieret_toast")))
      .catch(() => toast.error(t("tjekliste.kopi_fejl_toast")));
  }

  // Tæller status-bullets så vi kan vise summary-strip øverst.
  const statusTal = resultat
    ? tællStatus(resultat.tjekliste)
    : { dækket: 0, delvist: 0, mangler: 0 };

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <Button
          type="button"
          onClick={generer}
          disabled={pending || filer.length === 0}
          className="w-full"
        >
          {pending ? t("tjekliste.genererer") : t("tjekliste.generer")}
        </Button>

        {pending && (
          <div className="rounded-md bg-indigo-50 border border-indigo-200 p-3 text-sm text-indigo-900">
            {t("tjekliste.progress_besked")}
          </div>
        )}

        {resultat && (
          <div className="space-y-3 border-t border-zinc-200 pt-4">
            {/* Status-summary-strip */}
            {(statusTal.dækket + statusTal.delvist + statusTal.mangler) > 0 && (
              <div className="grid grid-cols-3 gap-2">
                <StatusKort
                  label={t("tjekliste.status_daekket")}
                  antal={statusTal.dækket}
                  bg="bg-emerald-50 border-emerald-200 text-emerald-900"
                  prik="bg-emerald-500"
                />
                <StatusKort
                  label={t("tjekliste.status_delvist")}
                  antal={statusTal.delvist}
                  bg="bg-amber-50 border-amber-200 text-amber-900"
                  prik="bg-amber-500"
                />
                <StatusKort
                  label={t("tjekliste.status_mangler")}
                  antal={statusTal.mangler}
                  bg="bg-red-50 border-red-200 text-red-900"
                  prik="bg-red-500"
                />
              </div>
            )}

            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">
                {t("tjekliste.tjekliste_fra_hoering")}
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={kopier}
              >
                {t("tjekliste.kopier")}
              </Button>
            </div>

            <div className="rounded-md border border-zinc-200 bg-white p-4">
              <div className="prose prose-sm max-w-none prose-headings:font-semibold prose-li:my-1 prose-strong:text-zinc-900">
                <ReactMarkdown
                  components={{
                    li: ({ children, ...props }) => {
                      // Detekter status-linjer ("Status: DÆKKET" osv.) og
                      // marker dem visuelt med farvet prik + baggrund så
                      // brugeren nemt kan scanne hvad der mangler.
                      const tekst = childrenTilTekst(children);
                      const status = parseStatus(tekst);
                      if (status) {
                        return (
                          <li
                            {...props}
                            className={`rounded px-2 py-0.5 ${status.bg} flex items-start gap-2`}
                          >
                            <span
                              className={`inline-block w-2.5 h-2.5 rounded-full mt-[0.45rem] flex-shrink-0 ${status.prik}`}
                              aria-hidden
                            />
                            <span className="flex-1">{children}</span>
                          </li>
                        );
                      }
                      return <li {...props}>{children}</li>;
                    },
                  }}
                >
                  {rensTjekliste(resultat.tjekliste)}
                </ReactMarkdown>
              </div>
            </div>

            <p className="text-xs text-zinc-500">
              {t("tjekliste.metadata_tegn", { tegn: resultat.metadata.tegn })} ·{" "}
              {t("tjekliste.metadata_filer", {
                antal: resultat.metadata.antal_filer,
              })}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StatusKort({
  label,
  antal,
  bg,
  prik,
}: {
  label: string;
  antal: number;
  bg: string;
  prik: string;
}) {
  return (
    <div className={`rounded-md border ${bg} p-3 text-center`}>
      <p className="text-xs uppercase tracking-wide opacity-75 flex items-center justify-center gap-1.5">
        <span
          className={`inline-block w-2 h-2 rounded-full ${prik}`}
          aria-hidden
        />
        {label}
      </p>
      <p className="text-2xl font-bold tabular-nums">{antal}</p>
    </div>
  );
}

function childrenTilTekst(children: React.ReactNode): string {
  if (typeof children === "string") return children;
  if (typeof children === "number") return String(children);
  if (!children) return "";
  if (Array.isArray(children)) return children.map(childrenTilTekst).join("");
  if (
    typeof children === "object" &&
    "props" in children &&
    children.props &&
    typeof children.props === "object" &&
    "children" in children.props
  ) {
    return childrenTilTekst(children.props.children as React.ReactNode);
  }
  return "";
}

type StatusInfo = { bg: string; prik: string };

// Fjerner status-emojis (✅/⚠️/❌/ℹ️) og sektion-header-emojis (📋/🎯)
// fra det rå AI-output. Emojier passer ikke ind i app'ens generelle
// farvecirkel-system — vi viser status med en lille farvet prik og
// baggrundsfarve i stedet. AI-prompten i ai_engine.py beder stadig om
// emojier (det er enklere end at re-tune prompten), så vi stripper dem
// her ved render-tid.
function rensTjekliste(markdown: string): string {
  return markdown
    .replace(/📋\s*/g, "")
    .replace(/🎯\s*/g, "")
    .replace(/✅\s*/g, "")
    .replace(/⚠️\s*/g, "")
    .replace(/⚠\s*/g, "")
    .replace(/❌\s*/g, "")
    .replace(/✕\s*/g, "")
    .replace(/ℹ️\s*/g, "")
    .replace(/ℹ\s*/g, "");
}

function parseStatus(tekst: string): StatusInfo | null {
  // Kun bullets der starter med "Status:" — undgår at fange almindelige
  // sætninger der tilfældigvis nævner "dækket" eller "mangler".
  if (!/status\s*[::]/i.test(tekst)) return null;
  // Tjek for "delvist" FØR "dækket" — "delvist dækket" indeholder begge.
  if (/delvist/i.test(tekst)) {
    return { bg: "bg-amber-50", prik: "bg-amber-500" };
  }
  if (/dækket/i.test(tekst)) {
    return { bg: "bg-emerald-50", prik: "bg-emerald-500" };
  }
  if (/mangler/i.test(tekst)) {
    return { bg: "bg-red-50", prik: "bg-red-500" };
  }
  if (/kræver/i.test(tekst)) {
    return { bg: "bg-zinc-100", prik: "bg-zinc-400" };
  }
  return null;
}

function tællStatus(markdown: string) {
  let dækket = 0;
  let delvist = 0;
  let mangler = 0;
  for (const linje of markdown.split("\n")) {
    if (!/status\s*[::]/i.test(linje)) continue;
    if (/delvist/i.test(linje)) delvist += 1;
    else if (/dækket/i.test(linje)) dækket += 1;
    else if (/mangler/i.test(linje)) mangler += 1;
  }
  return { dækket, delvist, mangler };
}
