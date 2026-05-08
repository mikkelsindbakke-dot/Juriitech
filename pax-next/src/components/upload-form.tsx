"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

type ParsedFil = {
  filnavn: string;
  type: string;
  rolle: string;
  media_type: string | null;
  aarsag?: string;
  antal_bytes: number;
  tekst_total_laengde: number;
  tekst_uddrag: string;
};

type ParseRespons = {
  filer: ParsedFil[];
  antal: number;
};

function formatStr(antalBytes: number): string {
  if (antalBytes < 1024) return `${antalBytes} B`;
  if (antalBytes < 1024 * 1024) return `${(antalBytes / 1024).toFixed(1)} kB`;
  return `${(antalBytes / 1024 / 1024).toFixed(1)} MB`;
}

const RolleEtiket: Record<string, string> = {
  klageskema: "Klageskema",
  klage: "Klage",
  vejledning: "Vejledning",
  høring: "Høring",
  bilag: "Bilag",
  ukendt: "Ukendt",
};

export function UploadForm() {
  const [pending, startTransition] = useTransition();
  const [resultater, sætResultater] = useState<ParsedFil[] | null>(null);
  const [valgteFiler, sætValgteFiler] = useState<File[]>([]);

  function håndterFilValg(e: React.ChangeEvent<HTMLInputElement>) {
    const filer = Array.from(e.target.files ?? []);
    sætValgteFiler(filer);
    sætResultater(null);
  }

  function håndterUpload() {
    if (valgteFiler.length === 0) {
      toast.error("Vælg mindst én fil først.");
      return;
    }
    startTransition(async () => {
      const url = process.env.NEXT_PUBLIC_API_URL;
      if (!url) {
        toast.error("NEXT_PUBLIC_API_URL ikke sat.");
        return;
      }

      const formData = new FormData();
      for (const fil of valgteFiler) {
        formData.append("filer", fil);
      }

      try {
        const res = await fetch(`${url}/api/parse-fil`, {
          method: "POST",
          body: formData,
        });
        if (!res.ok) {
          toast.error(`API svarede ${res.status}`);
          return;
        }
        const data = (await res.json()) as ParseRespons;
        sætResultater(data.filer);
        toast.success(`${data.antal} fil(er) parset.`);
      } catch (e) {
        toast.error(
          `Kunne ikke nå API: ${e instanceof Error ? e.message : "ukendt fejl"}. ` +
            `Husk at uvicorn kører på port 8000.`,
        );
      }
    });
  }

  return (
    <div className="space-y-6">
      {/* Fil-vælger */}
      <div className="space-y-3">
        <label
          htmlFor="filer-input"
          className="block w-full cursor-pointer rounded-lg border-2 border-dashed border-zinc-300 bg-zinc-50 p-8 text-center hover:border-zinc-400 hover:bg-zinc-100 transition-colors"
        >
          <div className="text-sm text-zinc-600">
            <span className="font-medium text-zinc-900">Klik for at vælge filer</span>
            <span className="block mt-1 text-xs">
              eller træk dem hertil. PDF, DOCX, PNG, JPG.
            </span>
          </div>
          <input
            id="filer-input"
            type="file"
            multiple
            accept=".pdf,.docx,.png,.jpg,.jpeg"
            onChange={håndterFilValg}
            className="sr-only"
          />
        </label>

        {valgteFiler.length > 0 && (
          <div className="rounded-md bg-zinc-50 p-3 text-xs">
            <p className="font-medium text-zinc-900 mb-1">
              {valgteFiler.length} fil(er) valgt:
            </p>
            <ul className="space-y-0.5 text-zinc-700">
              {valgteFiler.map((f, i) => (
                <li key={i}>
                  · {f.name} <span className="text-zinc-500">({formatStr(f.size)})</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <Button
        type="button"
        onClick={håndterUpload}
        disabled={pending || valgteFiler.length === 0}
        className="w-full"
      >
        {pending ? "Parser..." : "Upload + parse via FastAPI"}
      </Button>

      {/* Resultater */}
      {resultater && (
        <div className="space-y-3">
          <p className="text-sm font-medium text-zinc-900">
            Parse-resultat fra processor.py:
          </p>
          {resultater.map((r, i) => (
            <div
              key={i}
              className="rounded-md border border-zinc-200 bg-white p-3 space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm">{r.filnavn}</span>
                <span className="text-xs text-zinc-500">
                  {formatStr(r.antal_bytes)}
                </span>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-zinc-700">
                  type: <code>{r.type}</code>
                </span>
                <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-zinc-700">
                  rolle: {RolleEtiket[r.rolle] ?? r.rolle}
                </span>
                {r.tekst_total_laengde > 0 && (
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-800">
                    {r.tekst_total_laengde} tegn læst
                  </span>
                )}
                {r.media_type && (
                  <span className="rounded-full bg-blue-100 px-2 py-0.5 text-blue-800">
                    {r.media_type}
                  </span>
                )}
                {r.aarsag && (
                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-red-800">
                    {r.aarsag}
                  </span>
                )}
              </div>
              {r.tekst_uddrag && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-zinc-600 hover:text-zinc-900">
                    Vis tekst-uddrag (første 500 tegn)
                  </summary>
                  <pre className="mt-2 whitespace-pre-wrap rounded bg-zinc-50 p-2 text-zinc-800 max-h-40 overflow-auto">
                    {r.tekst_uddrag}
                  </pre>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
