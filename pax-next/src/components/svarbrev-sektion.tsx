"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { toast } from "sonner";
import type {
  Tidsforhold,
} from "@/components/analyse-resultat";
import { gemIArkivAction } from "@/app/arkiv/actions";

type SvarbrevRespons = {
  svarbrev: string;
  metadata: {
    antal_filer: number;
    antal_instrukser: number;
    inkluder_kildehenvisninger: boolean;
    tegn: number;
  };
};

export function SvarbrevSektion({
  filer,
  klagepunkter,
  tidsforhold,
}: {
  filer: File[];
  klagepunkter?: string[];
  tidsforhold?: Tidsforhold;
}) {
  const [pending, startTransition] = useTransition();
  const [instrukser, sætInstrukser] = useState<string[]>([]);
  const [nyInstruks, sætNyInstruks] = useState("");
  const [kilder, sætKilder] = useState(false);
  const [svarbrev, sætSvarbrev] = useState<SvarbrevRespons | null>(null);

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
      toast.error("Vælg filer først.");
      return;
    }
    startTransition(async () => {
      const url = process.env.NEXT_PUBLIC_API_URL;
      if (!url) {
        toast.error("NEXT_PUBLIC_API_URL ikke sat.");
        return;
      }
      const formData = new FormData();
      for (const fil of filer) formData.append("filer", fil);
      formData.append("ekstra_instrukser_json", JSON.stringify(instrukser));
      formData.append("inkluder_kildehenvisninger", String(kilder));
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
        const res = await fetch(`${url}/api/svarbrev`, {
          method: "POST",
          body: formData,
        });
        if (!res.ok) {
          const fejl = await res.text();
          toast.error(`API svarede ${res.status}: ${fejl.slice(0, 200)}`);
          return;
        }
        const data = (await res.json()) as SvarbrevRespons;
        sætSvarbrev(data);
        toast.success(`Svarbrev genereret (${data.metadata.tegn} tegn).`);

        // Auto-save i arkiv (parity med Streamlit-PAX)
        const klageFn = filer[0]?.name ?? null;
        const arkivResultat = await gemIArkivAction({
          titel: klageFn ? `Svarbrev — ${klageFn}` : "Svarbrev",
          type: "svarbrev",
          indhold: data.svarbrev,
          klageFilnavn: klageFn,
          ekstraInstrukser:
            instrukser.length > 0 ? instrukser.join("\n") : null,
        });
        if (!arkivResultat.ok) {
          console.warn("Auto-arkiv fejlede:", arkivResultat.fejl);
        }
      } catch (e) {
        toast.error(
          `Kan ikke nå API: ${e instanceof Error ? e.message : "ukendt fejl"}.`,
        );
      }
    });
  }

  function kopier() {
    if (!svarbrev) return;
    navigator.clipboard
      .writeText(svarbrev.svarbrev)
      .then(() => toast.success("Svarbrev kopieret til udklipsholder"))
      .catch(() => toast.error("Kunne ikke kopiere"));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-semibold">
          Generer svarbrev
        </CardTitle>
        <CardDescription className="text-xs">
          {klagepunkter && tidsforhold
            ? "Bruger verificerede klagepunkter + tidsforhold fra førstevurderingen — sparer 2 AI-kald."
            : "Vil udlede klagepunkter + tidsforhold internt (~30s ekstra)."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Særlige instrukser */}
        <div className="space-y-2">
          <Label>Særlige instrukser (valgfrit)</Label>
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
              placeholder="fx 'læg vægt på force majeure-forbeholdet'"
              disabled={pending}
            />
            <Button
              type="button"
              variant="secondary"
              size="default"
              onClick={tilfoejInstruks}
              disabled={pending || !nyInstruks.trim()}
            >
              Tilføj
            </Button>
          </div>
          {instrukser.length > 0 && (
            <ul className="space-y-1 text-sm">
              {instrukser.map((instr, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-md bg-zinc-50 px-3 py-2"
                >
                  <span className="text-zinc-500 tabular-nums">
                    {i + 1}.
                  </span>
                  <span className="flex-1 text-zinc-800">{instr}</span>
                  <button
                    type="button"
                    onClick={() => fjernInstruks(i)}
                    disabled={pending}
                    className="text-zinc-400 hover:text-red-700 text-xs"
                  >
                    fjern
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Toggle: kildehenvisninger */}
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={kilder}
            onChange={(e) => sætKilder(e.target.checked)}
            disabled={pending}
            className="mt-1"
          />
          <span className="text-sm">
            <span className="font-medium">Inkluder kildehenvisninger</span>
            <span className="block text-xs text-zinc-500">
              Eksplicitte henvisninger til bilag, vilkår og lovparagraffer.
              Default: fra (mere flydende sprog).
            </span>
          </span>
        </label>

        {/* Generér-knap */}
        <Button
          type="button"
          onClick={generer}
          disabled={pending || filer.length === 0}
          className="w-full"
        >
          {pending ? "Genererer svarbrev (30-90 sek)..." : "Generer svarbrev"}
        </Button>

        {pending && (
          <div className="rounded-md bg-blue-50 border border-blue-200 p-3 text-sm text-blue-900">
            AI'en bygger svarbrev: indledning → faktum → juridisk vurdering →
            stillingtagen → konklusion. Forbudte ord (beklager, anerkender,
            bestrider osv.) bliver auto-fjernet i post-processing.
          </div>
        )}

        {/* Resultat */}
        {svarbrev && (
          <div className="space-y-3 border-t border-zinc-200 pt-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">Genereret svarbrev</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={kopier}
              >
                Kopier
              </Button>
            </div>
            <pre className="whitespace-pre-wrap rounded-md bg-zinc-50 p-4 text-sm text-zinc-800 font-sans leading-relaxed border border-zinc-200">
              {svarbrev.svarbrev}
            </pre>
            <p className="text-xs text-zinc-500">
              {svarbrev.metadata.tegn} tegn ·{" "}
              {svarbrev.metadata.antal_instrukser} særlig(e) instrukser ·
              kildehenvisninger:{" "}
              {svarbrev.metadata.inkluder_kildehenvisninger ? "ja" : "nej"}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
