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

type AnonymResultat = {
  filnavn: string;
  status:
    | "ok"
    | "scannet"
    | "fejl_aaben"
    | "fejl_redaktion"
    | "ikke_pdf"
    | "exception";
  anonymiseret_pdf_base64: string | null;
  antal_bytes_input: number;
  antal_bytes_output: number;
  bemaerkning: string;
};

type AnonymRespons = {
  filer: AnonymResultat[];
  metadata: {
    antal_input: number;
    antal_anonymiseret_ok: number;
    klager_navne: string[];
  };
};

const statusFarve: Record<AnonymResultat["status"], string> = {
  ok: "bg-emerald-100 text-emerald-800",
  scannet: "bg-amber-100 text-amber-800",
  fejl_aaben: "bg-red-100 text-red-800",
  fejl_redaktion: "bg-red-100 text-red-800",
  ikke_pdf: "bg-zinc-100 text-zinc-700",
  exception: "bg-red-100 text-red-800",
};

function formatStr(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} kB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

// Konverter base64 til Blob så vi kan downloade
function base64TilBlob(b64: string, mime: string): Blob {
  const byteString = atob(b64);
  const arr = new Uint8Array(byteString.length);
  for (let i = 0; i < byteString.length; i++) {
    arr[i] = byteString.charCodeAt(i);
  }
  return new Blob([arr], { type: mime });
}

export function AnonymiserSektion({ filer }: { filer: File[] }) {
  const [pending, startTransition] = useTransition();
  const [klagerNavne, sætKlagerNavne] = useState<string[]>([]);
  const [nytNavn, sætNytNavn] = useState("");
  const [resultater, sætResultater] = useState<AnonymRespons | null>(null);

  function tilfoejNavn() {
    const v = nytNavn.trim();
    if (!v) return;
    sætKlagerNavne((xs) => [...xs, v]);
    sætNytNavn("");
  }

  function fjernNavn(i: number) {
    sætKlagerNavne((xs) => xs.filter((_, idx) => idx !== i));
  }

  function anonymiser() {
    const pdfFiler = filer.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfFiler.length === 0) {
      toast.error("Vælg mindst én PDF-fil. Sort-bjælke virker kun på PDF.");
      return;
    }
    startTransition(async () => {
      const url = process.env.NEXT_PUBLIC_API_URL;
      if (!url) {
        toast.error("NEXT_PUBLIC_API_URL ikke sat.");
        return;
      }
      const formData = new FormData();
      for (const fil of pdfFiler) formData.append("filer", fil);
      formData.append("klager_navne_json", JSON.stringify(klagerNavne));

      try {
        const res = await fetch(`${url}/api/anonymiser`, {
          method: "POST",
          body: formData,
        });
        if (!res.ok) {
          const fejl = await res.text();
          toast.error(`API svarede ${res.status}: ${fejl.slice(0, 200)}`);
          return;
        }
        const data = (await res.json()) as AnonymRespons;
        sætResultater(data);
        toast.success(
          `${data.metadata.antal_anonymiseret_ok} af ${data.metadata.antal_input} fil(er) anonymiseret.`,
        );
      } catch (e) {
        toast.error(
          `Kan ikke nå API: ${e instanceof Error ? e.message : "ukendt fejl"}.`,
        );
      }
    });
  }

  function download(r: AnonymResultat) {
    if (!r.anonymiseret_pdf_base64) return;
    const blob = base64TilBlob(r.anonymiseret_pdf_base64, "application/pdf");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = r.filnavn.replace(/\.pdf$/i, "") + "_anonymiseret.pdf";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-semibold">
          Anonymiser PDF-bilag (sort-bjælke)
        </CardTitle>
        <CardDescription className="text-xs">
          Bruger eksisterende anonymisering_pdf.py. Klagers navne bevares;
          andre navne, CPR, telefon, adresser sorbjælkes med bevaret layout.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Klager-navne */}
        <div className="space-y-2">
          <Label>Klagers navne (skal IKKE sorbjælkes)</Label>
          <div className="flex gap-2">
            <Input
              value={nytNavn}
              onChange={(e) => sætNytNavn(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  tilfoejNavn();
                }
              }}
              placeholder="fx 'Anders Andersen' eller 'Anders'"
              disabled={pending}
            />
            <Button
              type="button"
              variant="secondary"
              onClick={tilfoejNavn}
              disabled={pending || !nytNavn.trim()}
            >
              Tilføj
            </Button>
          </div>
          {klagerNavne.length > 0 && (
            <ul className="space-y-1 text-sm">
              {klagerNavne.map((n, i) => (
                <li
                  key={i}
                  className="flex items-center gap-2 rounded-md bg-zinc-50 px-3 py-2"
                >
                  <span className="flex-1 text-zinc-800">{n}</span>
                  <button
                    type="button"
                    onClick={() => fjernNavn(i)}
                    disabled={pending}
                    className="text-zinc-400 hover:text-red-700 text-xs"
                  >
                    fjern
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-zinc-500">
            Hvis listen er tom, anonymiseres ALLE personnavne (inkl. klagers).
          </p>
        </div>

        <Button
          type="button"
          onClick={anonymiser}
          disabled={pending || filer.length === 0}
          className="w-full"
        >
          {pending
            ? "Anonymiserer..."
            : `Anonymiser ${filer.filter((f) => f.name.toLowerCase().endsWith(".pdf")).length} PDF-fil(er)`}
        </Button>

        {/* Resultater */}
        {resultater && (
          <div className="space-y-3 border-t border-zinc-200 pt-4">
            <p className="text-sm font-medium text-zinc-900">
              Anonymiseringsresultat
            </p>
            {resultater.filer.map((r, i) => (
              <div
                key={i}
                className="rounded-md border border-zinc-200 bg-white p-3 space-y-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-sm">{r.filnavn}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${statusFarve[r.status]}`}
                  >
                    {r.status}
                  </span>
                </div>
                <p className="text-xs text-zinc-600">{r.bemaerkning}</p>
                {r.status === "ok" && (
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-zinc-500">
                      {formatStr(r.antal_bytes_input)} →{" "}
                      {formatStr(r.antal_bytes_output)}
                    </span>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => download(r)}
                    >
                      Download anonymiseret PDF
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
