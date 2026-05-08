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

function formatStr(antalBytes: number): string {
  if (antalBytes < 1024) return `${antalBytes} B`;
  if (antalBytes < 1024 * 1024) return `${(antalBytes / 1024).toFixed(1)} kB`;
  return `${(antalBytes / 1024 / 1024).toFixed(1)} MB`;
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

// Aktivitets-indikator: en strisslerende farve-bjælke der bevæger sig
// fra side til side mens AI'en arbejder. Vi har ikke real-time feedback
// fra backenden, så enhver tids-baseret progress-bar ville lyve. I
// stedet kommunikerer vi BARE liveness via animation — brugeren ser at
// noget sker, uden at få et falsk estimat for hvor lang tid der er
// tilbage.
//
// Renderes kun mens analysen kører (parent gater på analysePending).
function AnalyseProgress() {
  return (
    <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-5 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-indigo-900">
            juriitech PAX scanner din sag
          </p>
          <p className="text-xs text-indigo-700 mt-0.5 max-w-md">
            Analyserer klagepunkter, tidsforhold og søger præcedens i
            500+ afgørelser. En typisk sag tager 60-90 sek; større
            sager med mange bilag op til 2-3 min.
          </p>
        </div>
      </div>

      {/* Aktivitets-bjælke: cyklisk farve-shift mellem indigo/violet/sky
          så brugeren visuelt kan se at programmet arbejder. Bruger
          background-position-animationen i Tailwind via et large
          background-size for kontinuerlig bevægelse. */}
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
  );
}

type AnalyseFejl = { besked: string; detalje?: string; status?: number };

export function UploadForm() {
  const [analysePending, startAnalyseTransition] = useTransition();
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
    if (!analysePending) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "Analysen kører stadig — er du sikker på du vil forlade siden?";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [analysePending]);

  function håndterFilValg(e: React.ChangeEvent<HTMLInputElement>) {
    const filer = Array.from(e.target.files ?? []);
    sætValgteFiler(filer);
    sætAnalyse(null);
    sætAnalyseFejl(null);
    sætBilagValg([]); // ny fil-set → reset bilag-valg
  }

  // Tilføj flere filer (fra sagsakter-sektionen) uden at nulstille
  // den eksisterende sagsstand. Filerne lægges blot i hat-listen,
  // og brugeren kan re-scanne med "Scan igen".
  function tilfoejFiler(nyeFiler: File[]) {
    if (nyeFiler.length === 0) return;
    sætValgteFiler((prev) => {
      const eksisterendeNavne = new Set(prev.map((f) => f.name));
      const tilfoejet = nyeFiler.filter((f) => !eksisterendeNavne.has(f.name));
      return [...prev, ...tilfoejet];
    });
    sætBilagValg([]); // bilag-listen skal regenereres med nye filer
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

      {/* Én stor Scan-knap. Parse-preview er fjernet — brugeren skal
          ikke vælge mellem hurtig fil-tjek og AI-analyse, de vil bare
          scanne sagen og komme videre. */}
      <Button
        type="button"
        size="lg"
        onClick={håndterAnalyse}
        disabled={analysePending || valgteFiler.length === 0}
        className="w-full h-14 text-base"
      >
        {analysePending ? (
          <>
            Scanner sag<Timer />
          </>
        ) : sagsakterAendretEfterAnalyse ? (
          "Scan igen med ny kontekst"
        ) : (
          "Scan filer"
        )}
      </Button>

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
            onFilerTilfoejet={tilfoejFiler}
            disabled={analysePending}
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
                Vælg bilag der skal anonymiseres før de sendes til Nævnet.
                juriitech PAX følger Pakkerejse-Ankenævnets retningslinjer:
                <strong className="text-zinc-900"> klagers og medrejsendes navne bevares</strong>,
                men CPR-numre, e-mails, telefonnumre samt navne på interne
                medarbejdere/guider og eksterne samarbejdspartnere
                (hotel-staff, læger, vidner) sortmaskeres.
                <br />
                <br />
                Klagers navn udledes automatisk fra klageskemaet — ingen
                manuel indtastning.
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
