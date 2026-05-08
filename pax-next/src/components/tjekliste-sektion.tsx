"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import { gemIArkivAction } from "@/app/arkiv/actions";
import { ApiError, postOgValider, tjeklisteSchema } from "@/lib/api-client";

type TjeklisteRespons = {
  tjekliste: string;
  metadata: {
    antal_filer: number;
    tegn: number;
  };
};

export function TjeklisteSektion({ filer }: { filer: File[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [resultat, sætResultat] = useState<TjeklisteRespons | null>(null);

  function generer() {
    if (filer.length === 0) {
      toast.error("Vælg filer først.");
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
        toast.success(`Tjekliste klar (${data.metadata.tegn} tegn).`);

        // Pre-warm /arkiv — auto-arkiverede tjeklister findes der.
        router.prefetch("/arkiv");

        const klageFn = filer[0]?.name ?? null;
        const arkivResultat = await gemIArkivAction({
          titel: klageFn ? `Tjekliste — ${klageFn}` : "Tjekliste",
          type: "tjekliste",
          indhold: data.tjekliste,
          klageFilnavn: klageFn,
        });
        if (!arkivResultat.ok) {
          console.warn("Auto-arkiv fejlede:", arkivResultat.fejl);
        }
      } catch (e) {
        if (e instanceof ApiError) {
          toast.error(
            e.detalje ? `${e.message}: ${e.detalje.slice(0, 100)}` : e.message,
          );
        } else {
          toast.error(
            `Uventet fejl: ${e instanceof Error ? e.message : "ukendt"}`,
          );
        }
      }
    });
  }

  function kopier() {
    if (!resultat) return;
    navigator.clipboard
      .writeText(resultat.tjekliste)
      .then(() => toast.success("Tjekliste kopieret"))
      .catch(() => toast.error("Kunne ikke kopiere"));
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
          {pending
            ? "Genererer tjekliste (~30 sek)..."
            : "Generer tjekliste"}
        </Button>

        {pending && (
          <div className="rounded-md bg-indigo-50 border border-indigo-200 p-3 text-sm text-indigo-900">
            juriitech PAX gennemgår sagen mod Nævnets høringsbrev —
            identificerer alle ønskede oplysninger og dokumenter…
          </div>
        )}

        {resultat && (
          <div className="space-y-3 border-t border-zinc-200 pt-4">
            {/* Status-summary-strip */}
            {(statusTal.dækket + statusTal.delvist + statusTal.mangler) > 0 && (
              <div className="grid grid-cols-3 gap-2">
                <StatusKort
                  label="Dækket"
                  antal={statusTal.dækket}
                  bg="bg-emerald-50 border-emerald-200 text-emerald-900"
                  ikon="✓"
                />
                <StatusKort
                  label="Delvist"
                  antal={statusTal.delvist}
                  bg="bg-amber-50 border-amber-200 text-amber-900"
                  ikon="⚠"
                />
                <StatusKort
                  label="Mangler"
                  antal={statusTal.mangler}
                  bg="bg-red-50 border-red-200 text-red-900"
                  ikon="✕"
                />
              </div>
            )}

            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">📋 Tjekliste fra høringsbrevet</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={kopier}
              >
                Kopiér
              </Button>
            </div>

            <div className="rounded-md border border-zinc-200 bg-white p-4">
              <div className="prose prose-sm max-w-none prose-headings:font-semibold prose-li:my-1 prose-strong:text-zinc-900">
                <ReactMarkdown
                  components={{
                    li: ({ children, ...props }) => {
                      // Detekter status-linjer ("Status: ✅ DÆKKET" osv.) og
                      // marker dem visuelt så det er nemt at scanne.
                      const tekst = childrenTilTekst(children);
                      const status = parseStatus(tekst);
                      if (status) {
                        return (
                          <li
                            {...props}
                            className={`rounded px-2 py-0.5 ${status.bg}`}
                          >
                            {children}
                          </li>
                        );
                      }
                      return <li {...props}>{children}</li>;
                    },
                  }}
                >
                  {resultat.tjekliste}
                </ReactMarkdown>
              </div>
            </div>

            <p className="text-xs text-zinc-500">
              {resultat.metadata.tegn} tegn ·{" "}
              {resultat.metadata.antal_filer} fil(er) gennemgået
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
  ikon,
}: {
  label: string;
  antal: number;
  bg: string;
  ikon: string;
}) {
  return (
    <div className={`rounded-md border ${bg} p-3 text-center`}>
      <p className="text-xs uppercase tracking-wide opacity-75">{label}</p>
      <p className="text-2xl font-bold tabular-nums">
        <span className="mr-1">{ikon}</span>
        {antal}
      </p>
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

type StatusInfo = { bg: string };

function parseStatus(tekst: string): StatusInfo | null {
  const lower = tekst.toLowerCase();
  if (
    /status\s*[::]/i.test(tekst) === false &&
    !lower.includes("dækket") &&
    !lower.includes("mangler")
  ) {
    return null;
  }
  if (/✅|✓|fuldt\s+dækket|fuld\s+dækket/i.test(tekst)) {
    return { bg: "bg-emerald-50" };
  }
  if (/⚠|delvist/i.test(tekst)) {
    return { bg: "bg-amber-50" };
  }
  if (/❌|✕|mangler/i.test(tekst)) {
    return { bg: "bg-red-50" };
  }
  return null;
}

function tællStatus(markdown: string) {
  let dækket = 0;
  let delvist = 0;
  let mangler = 0;
  for (const linje of markdown.split("\n")) {
    if (!/status\s*[::]/i.test(linje)) continue;
    if (/✅|fuldt?\s+dækket/i.test(linje)) dækket += 1;
    else if (/⚠|delvist/i.test(linje)) delvist += 1;
    else if (/❌|mangler/i.test(linje)) mangler += 1;
  }
  return { dækket, delvist, mangler };
}
