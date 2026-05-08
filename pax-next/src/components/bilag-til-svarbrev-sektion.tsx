"use client";

import { useEffect, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";

// Sektion 11: Bilag til svarbrevet.
//
// Brugeren vælger hvilke uploadede filer der skal medsendes svarbrevet
// til Nævnet. Selve svarbrevet er altid Bilag A. Næste valgte fil bliver
// Bilag B osv. — fortløbende fra et valgbart start-bogstav.
//
// Output: en BilagItem[]-liste der sendes til /api/svarbrev som
// bilag_liste_json — bruges af eksport.svarbrev_til_docx til at bygge
// bilag-oversigten nederst i Word-filen.

export type BilagValg = {
  filnavn: string;
  inkluderet: boolean;
  overskrift: string; // editable beskrivelse
};

export type BilagItem = {
  bogstav: string;
  overskrift: string;
};

// Foreslår en kort beskrivelse til en fil baseret på filnavn + rolle.
// Kan altid overskrives af brugeren manuelt.
function foreslaaOverskrift(filnavn: string, rolle?: string): string {
  const base = filnavn.replace(/\.[^.]+$/, "").replace(/_/g, " ");
  if (rolle === "klageskema" && /klageskema/i.test(base))
    return "Klageskema indsendt til Pakkerejse-Ankenævnet";
  if (rolle === "klageskema") return base.replace(/^[Bb]ilag\s*\d+\s*/, "");
  if (rolle === "høring") return "Høringsbrev fra Pakkerejse-Ankenævnet";
  return base.replace(/^[Bb]ilag\s*\d+\s*/, "");
}

export function BilagTilSvarbrevSektion({
  filer,
  startBogstav,
  onStartBogstavAendret,
  valg,
  onValgAendret,
  disabled,
}: {
  filer: { filnavn: string; rolle?: string }[];
  startBogstav: string;
  onStartBogstavAendret: (s: string) => void;
  valg: BilagValg[];
  onValgAendret: (v: BilagValg[]) => void;
  disabled?: boolean;
}) {
  // Initialiser valg hvis listen er tom og vi har filer.
  // Default: alle filer er ikke-inkluderede; brugeren tikker dem til.
  // Filnavnene matches 1:1 — hvis brugeren tilføjer/fjerner filer,
  // synkroniseres listen.
  useEffect(() => {
    if (filer.length === 0) {
      if (valg.length !== 0) onValgAendret([]);
      return;
    }
    const eksisterende = new Map(valg.map((v) => [v.filnavn, v]));
    const ny: BilagValg[] = filer.map((f) => {
      const e = eksisterende.get(f.filnavn);
      if (e) return e;
      return {
        filnavn: f.filnavn,
        inkluderet: false,
        overskrift: foreslaaOverskrift(f.filnavn, f.rolle),
      };
    });
    // Kun opdatér hvis der er forskel — undgår infinite loop
    const samme =
      ny.length === valg.length &&
      ny.every((v, i) => v.filnavn === valg[i]?.filnavn);
    if (!samme) onValgAendret(ny);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filer]);

  const startUpper = (startBogstav || "A").trim().toUpperCase().slice(0, 1) || "A";
  const startCharCode = startUpper.charCodeAt(0);

  // Tildel bogstaver til de inkluderede bilag i den valgte rækkefølge.
  // Selve svarbrevet får start-bogstavet (A), første tjekkede fil får B osv.
  const tildelteBogstaver = useMemo(() => {
    let idx = 1;
    const map: Record<string, string> = {};
    for (const v of valg) {
      if (!v.inkluderet) continue;
      const code = startCharCode + idx;
      if (code > "Z".charCodeAt(0)) break;
      map[v.filnavn] = String.fromCharCode(code);
      idx += 1;
    }
    return map;
  }, [valg, startCharCode]);

  function toggle(filnavn: string) {
    onValgAendret(
      valg.map((v) =>
        v.filnavn === filnavn ? { ...v, inkluderet: !v.inkluderet } : v,
      ),
    );
  }

  function aendreOverskrift(filnavn: string, ny: string) {
    onValgAendret(
      valg.map((v) => (v.filnavn === filnavn ? { ...v, overskrift: ny } : v)),
    );
  }

  function flyt(filnavn: string, retning: -1 | 1) {
    const i = valg.findIndex((v) => v.filnavn === filnavn);
    if (i < 0) return;
    const j = i + retning;
    if (j < 0 || j >= valg.length) return;
    const ny = [...valg];
    [ny[i], ny[j]] = [ny[j], ny[i]];
    onValgAendret(ny);
  }

  if (filer.length === 0) return null;

  const antalInkluderede = valg.filter((v) => v.inkluderet).length;

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <p className="text-xs text-zinc-500">
          Selve svarbrevet er altid Bilag {startUpper}.
          {antalInkluderede > 0 && (
            <>
              {" "}
              Valgt: <strong className="text-zinc-700">{antalInkluderede} bilag</strong>.
            </>
          )}
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start">
          <div className="space-y-1">
            <Label htmlFor="startbogstav" className="text-xs">
              Start-bogstav
            </Label>
            <Input
              id="startbogstav"
              value={startBogstav}
              onChange={(e) =>
                onStartBogstavAendret(
                  e.target.value.toUpperCase().slice(0, 1) || "A",
                )
              }
              maxLength={1}
              disabled={disabled}
              className="w-20"
            />
            <p className="text-xs text-zinc-500">
              Selve svarbrevet bliver Bilag <strong>{startUpper}</strong>.
            </p>
          </div>
        </div>

        <div className="space-y-1">
          <p className="text-xs text-zinc-500 italic">
            Klik i feltet for at redigere den foreslåede titel.
          </p>
          <ul className="divide-y divide-zinc-100 rounded-md border border-zinc-200">
            {valg.map((v, idx) => {
              const bogstav = tildelteBogstaver[v.filnavn];
              const erInkluderet = v.inkluderet;
              return (
                <li
                  key={v.filnavn}
                  className={`p-3 ${erInkluderet ? "bg-zinc-50" : "bg-white"}`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={v.inkluderet}
                      onChange={() => toggle(v.filnavn)}
                      disabled={disabled}
                      className="mt-1"
                      id={`bilag-${idx}`}
                    />
                    <label
                      htmlFor={`bilag-${idx}`}
                      className="flex-1 cursor-pointer text-sm font-medium text-zinc-900"
                    >
                      {v.filnavn}
                    </label>
                    {erInkluderet && bogstav && (
                      <span className="text-amber-700 font-bold text-sm">
                        Bilag {bogstav}
                      </span>
                    )}
                  </div>
                  {erInkluderet && (
                    <div className="flex gap-2 mt-2 pl-7">
                      <Input
                        value={v.overskrift}
                        onChange={(e) =>
                          aendreOverskrift(v.filnavn, e.target.value)
                        }
                        disabled={disabled}
                        className="flex-1 text-sm"
                        placeholder="Beskrivelse af bilaget"
                      />
                      <button
                        type="button"
                        onClick={() => flyt(v.filnavn, -1)}
                        disabled={disabled || idx === 0}
                        className="px-2 py-1 rounded border border-zinc-300 bg-white text-sm hover:bg-zinc-50 disabled:opacity-30 disabled:cursor-not-allowed"
                        aria-label="Flyt op"
                        title="Flyt op"
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        onClick={() => flyt(v.filnavn, 1)}
                        disabled={disabled || idx === valg.length - 1}
                        className="px-2 py-1 rounded border border-zinc-300 bg-white text-sm hover:bg-zinc-50 disabled:opacity-30 disabled:cursor-not-allowed"
                        aria-label="Flyt ned"
                        title="Flyt ned"
                      >
                        ↓
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>

        {antalInkluderede > 0 && (
          <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-xs text-amber-900">
            Bilag-listen sendes til Word-filen når du genererer svarbrevet.
            Selve svarbrevet bliver Bilag {startUpper}; herefter følger{" "}
            {antalInkluderede} bilag i den rækkefølge du har valgt.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function bilagValgTilListe(
  valg: BilagValg[],
  startBogstav: string,
  selskabNavn = "rejseselskabet",
): BilagItem[] {
  const start = (startBogstav || "A").trim().toUpperCase().slice(0, 1) || "A";
  const startCode = start.charCodeAt(0);
  const liste: BilagItem[] = [
    {
      bogstav: start,
      overskrift: `${selskabNavn}s bemærkninger til sagen`,
    },
  ];
  let idx = 1;
  for (const v of valg) {
    if (!v.inkluderet) continue;
    const code = startCode + idx;
    if (code > "Z".charCodeAt(0)) break;
    liste.push({
      bogstav: String.fromCharCode(code),
      overskrift: v.overskrift.trim() || v.filnavn,
    });
    idx += 1;
  }
  return liste;
}
