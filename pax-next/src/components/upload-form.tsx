"use client";

import { useState, useTransition, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Pillar } from "@/components/ui/pillar";
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

// Grøn opsummerings-bar der viser "Sag klar til analyse: N filer (X læst,
// Y scannede PDF'er)" + en expandable fil-liste med rolle og tegn læst.
// Matcher Streamlit-PAX' status-bar lige under upload-zonen.
function SagKlarBar({ resultater }: { resultater: ParsedFil[] }) {
  const [aaben, sætAaben] = useState(false);
  const antal = resultater.length;
  const læst = resultater.filter((r) => r.tekst_total_laengde > 0).length;
  const scannet = resultater.filter(
    (r) => r.type === "scannet_pdf",
  ).length;
  const fejlet = resultater.filter((r) => r.aarsag).length;
  return (
    <div className="space-y-2">
      <div className="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-900">
        <strong>Sag klar til analyse:</strong> {antal} filer ({læst} læst
        {scannet > 0 && `, ${scannet} scannede PDF'er`}
        {fejlet > 0 && `, ${fejlet} fejlede`})
      </div>
      <button
        type="button"
        onClick={() => sætAaben((v) => !v)}
        className="w-full text-left text-sm text-zinc-600 hover:text-zinc-900 rounded-md border border-zinc-200 bg-white px-3 py-2"
      >
        <span className="text-zinc-400 mr-1">{aaben ? "▾" : "▸"}</span>
        {aaben ? `Skjul fil-listen` : `Se de ${antal} filer i sagen`}
      </button>
      {aaben && (
        <ol className="space-y-1 text-sm text-zinc-700 list-decimal pl-6">
          {resultater.map((r, i) => (
            <li key={i}>
              <strong className="font-semibold text-zinc-900">{r.filnavn}</strong>{" "}
              <em className="text-zinc-500">· {RolleEtiket[r.rolle] ?? r.rolle}</em>{" "}
              <span className="text-zinc-500">
                —{" "}
                {r.tekst_total_laengde > 0
                  ? `${r.tekst_total_laengde} tegn læst`
                  : r.aarsag
                    ? `fejl: ${r.aarsag}`
                    : "scannet PDF"}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// Lille timer der tæller op mens AI-kaldet kører. Renderes kun når
// analysen kører (parent gater på analysePending), så tilstanden
// auto-resettes via mount/unmount — derfor ingen reset i useEffect.
function Timer() {
  const [sek, sætSek] = useState(0);
  useEffect(() => {
    const id = setInterval(() => sætSek((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className="text-xs text-zinc-500 tabular-nums">
      {" "}
      ({sek}s — kan tage op til 90s)
    </span>
  );
}

// Progress-linje der tracker analyse-trinene tidsbaseret. Vi har ikke
// real-time feedback fra backenden (ét fetch-kald), så vi bruger
// estimerede varigheder pr. trin og animerer ud fra elapsed seconds.
// Matcher Streamlit-PAX' thinking_fullpage()-mønster.
//
// Renderes kun mens analysen kører (parent gater på analysePending), så
// tæller-tilstanden auto-resettes via mount/unmount.
function AnalyseProgress() {
  const [sek, sætSek] = useState(0);
  useEffect(() => {
    const id = setInterval(() => sætSek((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  // Estimerede varigheder (sekunder) pr. trin — baseret på faktiske
  // målinger af /api/foerstevurdering på en typisk sag.
  const trin = [
    { label: "Læser og parser sagsfiler", varighed: 4 },
    { label: "Udtrækker klagepunkter", varighed: 10 },
    { label: "Analyserer tidsforhold mellem rejse, klage og høring", varighed: 8 },
    { label: "Søger præcedens i vidensbank (500+ afgørelser)", varighed: 6 },
    { label: "Skriver juridisk førstevurdering med 6 sektioner", varighed: 30 },
    { label: "Sammenfatter resumé og konklusion", varighed: 10 },
  ];
  let cum = 0;
  const trinMedSlut = trin.map((t) => {
    cum += t.varighed;
    return { ...t, slut: cum };
  });
  const total = cum;

  // Progressen må aldrig nå 100% inden svaret er kommet — det får brugeren
  // til at tro at noget hænger fast. Vi capper ved 90% i estimerings-
  // perioden, og kryber langsomt mod 98% bagefter (asymptote).
  let pct: number;
  if (sek <= total) {
    pct = Math.min(90, (sek / total) * 90);
  } else {
    // Efter estimatet: kryb fra 90% mod 98% over de næste 90 sek.
    const efter = sek - total;
    pct = Math.min(98, 90 + (efter / 90) * 8);
  }

  // Når vi er forbi estimatet er sidste trin stadig "aktivt" (vi kan
  // ikke vide hvilken AI-fase der hænger fast — typisk er det dog det
  // tunge skrivetrin).
  let aktivIdx = trinMedSlut.findIndex((t) => sek < t.slut);
  if (aktivIdx === -1) aktivIdx = trin.length - 1;

  const overTid = sek > total;

  return (
    <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-5 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-indigo-900">
            juriitech PAX laver en grundig analyse af din sag
          </p>
          <p className="text-xs text-indigo-700 mt-0.5 max-w-md">
            Kvalitet tager tid. En typisk sag tager 60-90 sek; større
            sager med +10 dokumenter kan tage 2-3 min.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span
            className={`inline-block w-2.5 h-2.5 rounded-full animate-pulse ${
              overTid ? "bg-amber-500" : "bg-indigo-500"
            }`}
          />
          <span
            className={`text-sm font-mono tabular-nums font-semibold ${
              overTid ? "text-amber-900" : "text-indigo-900"
            }`}
          >
            {sek}s
          </span>
        </div>
      </div>

      {/* Progress-bar */}
      <div className="h-2 w-full bg-indigo-100 rounded-full overflow-hidden">
        <div
          className={`h-full transition-all duration-700 ease-out ${
            overTid
              ? "bg-gradient-to-r from-amber-400 to-amber-600"
              : "bg-gradient-to-r from-indigo-500 to-indigo-700"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Trin-liste */}
      <ol className="space-y-1.5">
        {trinMedSlut.map((t, i) => {
          const erFærdig = i < aktivIdx;
          const erAktiv = i === aktivIdx;
          return (
            <li
              key={i}
              className={`flex items-center gap-3 text-sm transition-colors ${
                erFærdig
                  ? "text-emerald-700"
                  : erAktiv
                    ? overTid
                      ? "text-amber-900 font-medium"
                      : "text-indigo-900 font-medium"
                    : "text-indigo-400"
              }`}
            >
              <span className="w-5 inline-flex justify-center items-center">
                {erFærdig ? (
                  <span className="text-emerald-600">✓</span>
                ) : erAktiv ? (
                  <span
                    className={`inline-block w-3 h-3 border-2 ${overTid ? "border-amber-500" : "border-indigo-500"} border-t-transparent rounded-full animate-spin`}
                  />
                ) : (
                  <span className="text-indigo-300">○</span>
                )}
              </span>
              <span>{t.label}</span>
            </li>
          );
        })}
      </ol>

      {overTid && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          <strong>Det tager længere end forventet</strong> — store sager med
          mange bilag kan tage 2-3 minutter. juriitech PAX arbejder
          stadig; forlad ikke siden.
        </p>
      )}
    </div>
  );
}

type AnalyseFejl = { besked: string; detalje?: string; status?: number };

export function UploadForm() {
  const [parsePending, startParseTransition] = useTransition();
  const [analysePending, startAnalyseTransition] = useTransition();
  const [resultater, sætResultater] = useState<ParsedFil[] | null>(null);
  const [analyse, sætAnalyse] = useState<FoerstevurderingsRespons | null>(
    null,
  );
  const [valgteFiler, sætValgteFiler] = useState<File[]>([]);

  // Persistent fejl-state — vises som banner i stedet for at forsvinde
  // som toast. Brugeren skal vide hvad der gik galt og kunne prøve igen
  // uden at miste filerne.
  const [analyseFejl, sætAnalyseFejl] = useState<AnalyseFejl | null>(null);

  // Sektion 9: Sagsakter (fri tekst med ekstra kontekst).
  const [sagsakter, sætSagsakter] = useState("");

  // Sektion 11: Bilag til svarbrevet (letter assignment + reorder).
  const [bilagStartBogstav, sætBilagStartBogstav] = useState("A");
  const [bilagValg, sætBilagValg] = useState<BilagValg[]>([]);

  // Advar brugeren hvis de prøver at lukke siden mens analysen kører —
  // ellers kan de tro de blev "smidt tilbage" til upload (i virkeligheden
  // bare en page-refresh der dræbte fetch'en).
  useEffect(() => {
    if (!analysePending && !parsePending) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "Analysen kører stadig — er du sikker på du vil forlade siden?";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [analysePending, parsePending]);

  function håndterFilValg(e: React.ChangeEvent<HTMLInputElement>) {
    const filer = Array.from(e.target.files ?? []);
    sætValgteFiler(filer);
    sætResultater(null);
    sætAnalyse(null);
    sætAnalyseFejl(null);
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
    sætAnalyseFejl(null); // ryd evt. tidligere fejl
    startAnalyseTransition(async () => {
      const url = process.env.NEXT_PUBLIC_API_URL;
      if (!url) {
        const fejl: AnalyseFejl = {
          besked: "NEXT_PUBLIC_API_URL er ikke sat",
          detalje: "Kontakt en administrator — environment-variablen mangler.",
        };
        sætAnalyseFejl(fejl);
        toast.error(fejl.besked);
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
          const fejlTekst = await res.text().catch(() => "");
          const fejl: AnalyseFejl = {
            besked: `API svarede ${res.status} ${res.statusText || ""}`.trim(),
            detalje: fejlTekst.slice(0, 500),
            status: res.status,
          };
          console.error("[foerstevurdering] non-ok:", fejl);
          sætAnalyseFejl(fejl);
          toast.error(fejl.besked);
          return;
        }
        const data = (await res.json()) as FoerstevurderingsRespons;
        sætAnalyse(data);
        sætAnalyseFejl(null);
        toast.success(
          `Analyse færdig — ${data.metadata.antal_klagepunkter} klagepunkter, ` +
            `${data.metadata.antal_relevante_sager} præcedens-matches.`,
        );
      } catch (e) {
        const detalje = e instanceof Error ? e.message : String(e);
        console.error("[foerstevurdering] fetch fejl:", e);
        const fejl: AnalyseFejl = {
          besked: "Kan ikke nå analyse-API'en",
          detalje,
        };
        sætAnalyseFejl(fejl);
        toast.error(`${fejl.besked}: ${detalje}`);
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
              Analyserer<Timer />
            </>
          ) : sagsakterAendretEfterAnalyse ? (
            "Re-kør førstevurdering med ny kontekst"
          ) : (
            "2. Kør førstevurdering (AI)"
          )}
        </Button>
      </div>

      {/* Progress-linje med trin der animerer mens analysen kører */}
      {analysePending && <AnalyseProgress />}

      {/* Persistent fejl-banner — vises hvis API-kaldet fejlede.
          Forsvinder ikke som toast, og giver brugeren en retry-knap så
          filerne ikke skal genvælges. */}
      {analyseFejl && !analysePending && (
        <div className="rounded-md border border-red-300 bg-red-50 p-4 space-y-3">
          <div className="flex items-start gap-3">
            <span className="text-lg leading-none">⚠</span>
            <div className="flex-1 space-y-1">
              <p className="text-sm font-semibold text-red-900">
                Analysen fejlede — dine filer er bevaret
              </p>
              <p className="text-sm text-red-800">{analyseFejl.besked}</p>
              {analyseFejl.detalje && (
                <details className="text-xs text-red-700">
                  <summary className="cursor-pointer hover:text-red-900">
                    Tekniske detaljer
                  </summary>
                  <pre className="mt-1 whitespace-pre-wrap font-mono">
                    {analyseFejl.detalje}
                  </pre>
                </details>
              )}
              {analyseFejl.status && analyseFejl.status >= 500 && (
                <p className="text-xs text-red-700 italic">
                  5xx-fejl indikerer et server-problem (typisk timeout eller
                  Anthropic-credits løbet tør). Prøv igen om et par sekunder.
                </p>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              onClick={håndterAnalyse}
              disabled={valgteFiler.length === 0}
            >
              Prøv igen
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => sætAnalyseFejl(null)}
            >
              Luk
            </Button>
          </div>
        </div>
      )}

      {/* Sag klar til analyse — opsummerings-bar (vises før + under analyse) */}
      {!analyse && resultater && resultater.length > 0 && (
        <SagKlarBar resultater={resultater} />
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

      {/* Sektion 9-13 vises FØRST når analysen er kørt — ellers kan
          brugeren risikere at udfylde sagsakter, vælge bilag osv.
          før der er noget at re-analysere imod.

          Hver sektion får en farvet Apple Health-pillar som "header"
          (titel + beskrivelse) over selve form-indholdet. */}

      {/* Sektion 9: Sagsakter */}
      {analyse && (
        <div className="space-y-4">
          <Pillar
            farve="lavender"
            nummer={9}
            titel="Sagsakter til denne sag"
            beskrivelse={
              <>
                Her kan du uploade yderligere filer om sagen, såsom
                mailkorrespondancer, tekstbeskeder, bookingdetaljer,
                screenshots m.m. — altså information som juriitech PAX
                ikke automatisk har adgang til.
                <br />
                <br />
                Når du tilføjer sagsakter, genberegnes analysen automatisk,
                så vurderingen tager højde for ny information.
              </>
            }
          />
          <SagsakterSektion
            vaerdi={sagsakter}
            onAendret={sætSagsakter}
            disabled={analysePending || parsePending}
          />
        </div>
      )}

      {/* Anonymiser-sektion (10) */}
      {analyse && (
        <div className="space-y-4">
          <Pillar
            farve="rose"
            nummer={10}
            titel="Anonymisér bilag til Nævnet"
            beskrivelse={
              <>
                Vælg de bilag du ønsker at anonymisere — både sagsfiler og
                sagsakter du selv har uploadet. juriitech PAX producerer
                anonymiserede versioner efter Pakkerejse-Ankenævnets
                retningslinjer (Klager for klager, medrejsende for
                bipersoner, CPR-numre fjernes osv.).
                <br />
                <br />
                Nye sagsakter du uploader dukker automatisk op i listen
                herunder.
              </>
            }
          />
          <AnonymiserSektion filer={valgteFiler} />
        </div>
      )}

      {/* Sektion 11: Bilag til svarbrevet */}
      {analyse && (
        <div className="space-y-4">
          <Pillar
            farve="amber"
            nummer={11}
            titel="Bilag til svarbrevet"
            beskrivelse="Vælg hvilke bilag der skal medsendes svarbrevet til Nævnet. Selve svarbrevet er altid første bilag. Beskrivelserne er auto-foreslået af PAX — ret dem hvis de skal være anderledes."
          />
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
      {analyse && (
        <div className="space-y-4">
          <Pillar
            farve="indigo"
            nummer={12}
            titel="Tjekliste mod høringsbrev"
            beskrivelse="AI'en gennemgår høringsbrevet og markerer hvilke ønskede oplysninger der er dækket af bilagene, og hvad der mangler. Kør den inden svarbrevet — så du ved hvad du skal hente fra rejseselskabets systemer først."
          />
          <TjeklisteSektion filer={valgteFiler} />
        </div>
      )}

      {/* Svarbrev-sektion (13) */}
      {analyse && (
        <div className="space-y-4">
          <Pillar
            farve="emerald"
            nummer={13}
            titel="Generér svarbrev"
            beskrivelse="juriitech PAX skriver et færdigformateret svarbrev på baggrund af analysen, klagepunkterne og tidsforholdene. Du kan downloade resultatet som Word-fil og rette manuelt før afsendelse."
          />
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
