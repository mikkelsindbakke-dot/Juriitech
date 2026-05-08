"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { toast } from "sonner";
import { gemIArkivAction } from "@/app/arkiv/actions";

type TjeklisteRespons = {
  tjekliste: string;
  metadata: {
    antal_filer: number;
    tegn: number;
  };
};

export function TjeklisteSektion({ filer }: { filer: File[] }) {
  const [pending, startTransition] = useTransition();
  const [resultat, sætResultat] = useState<TjeklisteRespons | null>(null);

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

      try {
        const res = await fetch(`${url}/api/tjekliste`, {
          method: "POST",
          body: formData,
        });
        if (!res.ok) {
          const fejl = await res.text();
          toast.error(`API svarede ${res.status}: ${fejl.slice(0, 200)}`);
          return;
        }
        const data = (await res.json()) as TjeklisteRespons;
        sætResultat(data);
        toast.success(`Tjekliste klar (${data.metadata.tegn} tegn).`);

        // Auto-save i arkiv
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
        toast.error(
          `Kan ikke nå API: ${e instanceof Error ? e.message : "ukendt fejl"}.`,
        );
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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-semibold">
          Tjekliste mod Nævnets høringsbrev
        </CardTitle>
        <CardDescription className="text-xs">
          AI'en gennemgår høringsbrevet og markerer hvilke ønskede
          oplysninger der er dækket af bilagene, og hvad der mangler.
          Kør den <strong>inden</strong> svarbrevet.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
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

        {resultat && (
          <div className="space-y-3 border-t border-zinc-200 pt-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">Tjekliste</p>
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
              {resultat.tjekliste}
            </pre>
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
