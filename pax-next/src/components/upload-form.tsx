"use client";

import { useState, useTransition, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  AnalyseResultat,
  type FoerstevurderingsRespons,
} from "@/components/analyse-resultat";
import { SvarbrevSektion } from "@/components/svarbrev-sektion";
import { AnonymiserSektion } from "@/components/anonymiser-sektion";
import { TjeklisteSektion } from "@/components/tjekliste-sektion";
import { GemSagKnap } from "@/components/gem-sag-knap";
import { SagsakterSektion } from "@/components/sagsakter-sektion";
import {
  BilagTilSvarbrevSektion,
  bilagValgTilListe,
  type BilagValg,
} from "@/components/bilag-til-svarbrev-sektion";

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

// Lille timer der tæller op mens AI-kaldet kører.
function Timer({ kører }: { kører: boolean }) {
  const [sek, sætSek] = useState(0);
  useEffect(() => {
    if (!kører) {
      sætSek(0);
      return;
    }
    const id = setInterval(() => sætSek((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [kører]);
  if (!kører) return null;
  return (
    <span className="text-xs text-zinc-500 tabular-nums">
      {" "}
      ({sek}s — kan tage op til 90s)
    </span>
  );
}

export function UploadForm() {
  const [parsePending, startParseTransition] = useTransition();
  const [analysePending, startAnalyseTransition] = useTransition();
  const [resultater, sætResultater] = useState<ParsedFil[] | null>(null);
  const [analyse, sætAnalyse] = useState<FoerstevurderingsRespons | null>(
    null,
  );
  const [valgteFiler, sætValgteFiler] = useState<File[]>([]);

  // Sektion 9: Sagsakter (fri tekst med ekstra kontekst).
  // Medsendes alle AI-kald så vurderingen tager højde for ny information.
  const [sagsakter, sætSagsakter] = useState("");

  // Sektion 11: Bilag til svarbrevet (letter assignment + reorder).
  const [bilagStartBogstav, sætBilagStartBogstav] = useState("A");
  const [bilagValg, sætBilagValg] = useState<BilagValg[]>([]);

  function håndterFilValg(e: React.ChangeEvent<HTMLInputElement>) {
    const filer = Array.from(e.target.files ?? []);
    sætValgteFiler(filer);
    sætResultater(null);
    sætAnalyse(null);
    sætBilagValg([]); // ny fil-set → reset bilag-valg
  }

  function håndterParse() {
    if (valgteFiler.length === 0) {
      toast.error("Vælg mindst én fil først.");
      return;
    }
    startParseTransition(async () => {
      const url = process.env.NEXT_PUBLIC_API_URL;
      if (!url) {
        toast.error("NEXT_PUBLIC_API_URL ikke sat.");
        return;
      }
      const formData = new FormData();
      for (const fil of valgteFiler) formData.append("filer", fil);
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
          `Kan ikke nå API: ${e instanceof Error ? e.message : "ukendt fejl"}.`,
        );
      }
    });
  }

  function håndterAnalyse() {
    if (valgteFiler.length === 0) {
      toast.error("Vælg mindst én fil først.");
      return;
    }
    startAnalyseTransition(async () => {
      const url = process.env.NEXT_PUBLIC_API_URL;
      if (!url) {
        toast.error("NEXT_PUBLIC_API_URL ikke sat.");
        return;
      }
      const formData = new FormData();
      for (const fil of valgteFiler) formData.append("filer", fil);
      if (sagsakter.trim()) formData.append("sagsakter", sagsakter);
      try {
        const res = await fetch(`${url}/api/foerstevurdering`, {
          method: "POST",
          body: formData,
        });
        if (!res.ok) {
          const fejl = await res.text();
          toast.error(`API svarede ${res.status}: ${fejl.slice(0, 200)}`);
          return;
        }
        const data = (await res.json()) as FoerstevurderingsRespons;
        sætAnalyse(data);
        toast.success(
          `Analyse færdig — ${data.metadata.antal_klagepunkter} klagepunkter, ` +
            `${data.metadata.antal_relevante_sager} præcedens-matches.`,
        );
      } catch (e) {
        toast.error(
          `Kan ikke nå API: ${e instanceof Error ? e.message : "ukendt fejl"}.`,
        );
      }
    });
  }

  // Bygger bilag-listen der sendes til /api/svarbrev så Word-filen får
  // den korrekte bilag-oversigt nederst.
  const bilagListeTilDocx = bilagValgTilListe(bilagValg, bilagStartBogstav);

  // Tilbyd analyse-trigger igen hvis sagsakter ændres efter første analyse —
  // så brugeren kan re-køre med ekstra kontekst.
  const sagsakterAendretEfterAnalyse =
    analyse !== null && sagsakter.trim().length > 0;

  return (
    <div className="space-y-6">
      {/* Fil-vælger */}
      <div className="space-y-3">
        <label
          htmlFor="filer-input"
          className="block w-full cursor-pointer rounded-lg border-2 border-dashed border-zinc-300 bg-zinc-50 p-8 text-center hover:border-zinc-400 hover:bg-zinc-100 transition-colors"
        >
          <div className="text-sm text-zinc-600">
            <span className="font-medium text-zinc-900">
              Klik for at vælge filer
            </span>
            <span className="block mt-1 text-xs">
              eller træk dem hertil. PDF, DOCX, PNG, JPG, ZIP.
            </span>
          </div>
          <input
            id="filer-input"
            type="file"
            multiple
            accept=".pdf,.docx,.png,.jpg,.jpeg,.zip"
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
                  · {f.name}{" "}
                  <span className="text-zinc-500">({formatStr(f.size)})</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* To-knap-rækken: parse (gratis, sec) vs analyse (AI, dyrt) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <Button
          type="button"
          variant="secondary"
          onClick={håndterParse}
          disabled={parsePending || analysePending || valgteFiler.length === 0}
        >
          {parsePending ? "Parser..." : "1. Parse-preview"}
        </Button>
        <Button
          type="button"
          onClick={håndterAnalyse}
          disabled={parsePending || analysePending || valgteFiler.length === 0}
        >
          {analysePending ? (
            <>
              Analyserer<Timer kører={analysePending} />
            </>
          ) : sagsakterAendretEfterAnalyse ? (
            "Re-kør førstevurdering med ny kontekst"
          ) : (
            "2. Kør førstevurdering (AI)"
          )}
        </Button>
      </div>

      {analysePending && (
        <div className="rounded-md bg-blue-50 border border-blue-200 p-3 text-sm text-blue-900">
          AI&apos;en arbejder: udtrækker klagepunkter → finder præcedens via
          RAG → genererer 6-sektion juridisk analyse. Forlad ikke siden.
        </div>
      )}

      {/* Parse-resultater */}
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

      {/* Analyse-resultat */}
      {analyse && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold tracking-tight border-t border-zinc-200 pt-4">
            Førstevurdering
          </h2>
          <AnalyseResultat data={analyse} />
        </div>
      )}

      {/* Sektion 9: Sagsakter (vises altid når der er filer) */}
      {valgteFiler.length > 0 && (
        <div className="border-t border-zinc-200 pt-4">
          <SagsakterSektion
            vaerdi={sagsakter}
            onAendret={sætSagsakter}
            disabled={analysePending || parsePending}
          />
        </div>
      )}

      {/* Anonymiser-sektion (10) */}
      {valgteFiler.length > 0 && (
        <div className="space-y-3 border-t border-zinc-200 pt-4">
          <AnonymiserSektion filer={valgteFiler} />
        </div>
      )}

      {/* Sektion 11: Bilag til svarbrevet — output bruges i sektion 13 */}
      {valgteFiler.length > 0 && (
        <div className="border-t border-zinc-200 pt-4">
          <BilagTilSvarbrevSektion
            filer={valgteFiler.map((f) => ({ filnavn: f.name }))}
            startBogstav={bilagStartBogstav}
            onStartBogstavAendret={sætBilagStartBogstav}
            valg={bilagValg}
            onValgAendret={sætBilagValg}
          />
        </div>
      )}

      {/* Tjekliste-sektion (12) */}
      {valgteFiler.length > 0 && (
        <div className="space-y-3 border-t border-zinc-200 pt-4">
          <TjeklisteSektion filer={valgteFiler} />
        </div>
      )}

      {/* Svarbrev-sektion (13) — modtager bilag-listen fra sektion 11 */}
      {valgteFiler.length > 0 && (
        <div className="space-y-3 border-t border-zinc-200 pt-4">
          <SvarbrevSektion
            filer={valgteFiler}
            klagepunkter={analyse?.klagepunkter}
            tidsforhold={analyse?.tidsforhold}
            bilagListe={bilagListeTilDocx}
          />
        </div>
      )}

      {/* Sektion 14: Gem din sagsbehandling */}
      {analyse && (
        <div className="border-t border-zinc-200 pt-4">
          <GemSagKnap
            state={{
              analyse,
              sagsakter,
              bilag_start_bogstav: bilagStartBogstav,
              bilag_valg: bilagValg,
              filer: valgteFiler.map((f) => ({
                navn: f.name,
                antal_bytes: f.size,
              })),
              gemt_dato: new Date().toISOString(),
            }}
            defaultTitel={
              valgteFiler[0]?.name?.replace(/\.(pdf|docx)$/i, "") ?? ""
            }
          />
        </div>
      )}
    </div>
  );
}
