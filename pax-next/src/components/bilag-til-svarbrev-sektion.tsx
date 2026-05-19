"use client";

import { useEffect, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { useT } from "@/lib/i18n/client";

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
function foreslaaOverskrift(
  filnavn: string,
  rolle: string | undefined,
  t: (noegle: string, args?: Record<string, string | number>) => string,
): string {
  const base = filnavn.replace(/\.[^.]+$/, "").replace(/_/g, " ");
  if (rolle === "klageskema" && /klageskema/i.test(base))
    return t("bilag.klageskema_overskrift");
  if (rolle === "klageskema") return base.replace(/^[Bb]ilag\s*\d+\s*/, "");
  if (rolle === "høring") return t("bilag.hoeringsbrev_overskrift");
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
  const t = useT();
  // Synkronisér valg-listen med de filer parent har valgt.
  //
  // KRITISK: vi MÅ IKKE re-bygge valg i filer-rækkefølge når sættet af
  // filnavne matcher — for så ville en brugers ↑/↓-swap straks blive
  // rullet tilbage. (Parent re-skaber filer-prop'en på hver render
  // med valgteFiler.map(...), så useEffekten fyrer ved hvert reorder.)
  //
  // Strategi:
  //   1. Hvis sættet af filnavne matcher det vi allerede har → ingenting.
  //      Brugerens rækkefølge bevares.
  //   2. Hvis filer faktisk er tilføjet/fjernet → behold de eksisterende
  //      i deres NUVÆRENDE rækkefølge, læg nye til sidst, fjern de
  //      forsvundne.
  useEffect(() => {
    if (filer.length === 0) {
      if (valg.length !== 0) onValgAendret([]);
      return;
    }
    const filerNavne = new Set(filer.map((f) => f.filnavn));
    const valgNavne = new Set(valg.map((v) => v.filnavn));
    const sammeSaet =
      filerNavne.size === valgNavne.size &&
      [...filerNavne].every((n) => valgNavne.has(n));
    if (sammeSaet) return; // bevar brugerens rækkefølge

    const eksisterende = new Map(valg.map((v) => [v.filnavn, v]));
    const bevaret = valg.filter((v) => filerNavne.has(v.filnavn));
    const nyeFiler: BilagValg[] = filer
      .filter((f) => !eksisterende.has(f.filnavn))
      .map((f) => ({
        filnavn: f.filnavn,
        inkluderet: false,
        overskrift: foreslaaOverskrift(f.filnavn, f.rolle, t),
      }));
    onValgAendret([...bevaret, ...nyeFiler]);
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

  // Flyt et inkluderet bilag op/ned i rækkefølgen.
  //
  // Vi swapper med den nærmeste INKLUDEREDE nabo — ikke bare med den
  // umiddelbart forrige/næste fil i valg-arrayet. Hvis vi swappede med
  // en u-tikket fil ville bogstav-tildelingen (E, F, G, ...) ikke ændre
  // sig overhovedet, fordi bogstaver kun gives til inkluderede bilag i
  // den rækkefølge de står — så brugeren ville klikke uden synlig effekt.
  function flyt(filnavn: string, retning: -1 | 1) {
    const i = valg.findIndex((v) => v.filnavn === filnavn);
    if (i < 0) return;
    let j = -1;
    if (retning === -1) {
      for (let k = i - 1; k >= 0; k--) {
        if (valg[k].inkluderet) {
          j = k;
          break;
        }
      }
    } else {
      for (let k = i + 1; k < valg.length; k++) {
        if (valg[k].inkluderet) {
          j = k;
          break;
        }
      }
    }
    if (j < 0) return; // ingen inkluderet nabo i den retning
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
          {t("bilag.svarbrev_altid_bilag", { bogstav: startUpper })}
          {antalInkluderede > 0 && (
            <>
              {" "}
              {t("bilag.valgt_antal")}{" "}
              <strong className="text-zinc-700">
                {t("bilag.valgt_antal_bilag", { antal: antalInkluderede })}
              </strong>
              .
            </>
          )}
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start">
          <div className="space-y-1">
            <Label htmlFor="startbogstav" className="text-xs">
              {t("bilag.startbogstav_label")}
            </Label>
            <Input
              id="startbogstav"
              value={startBogstav}
              onChange={(e) => {
                // BEMÆRK: maxLength=1 må IKKE sættes på dette felt.
                // Hvis feltet allerede har 'A' og brugeren skriver 'B',
                // ville browseren afvise det 2. tegn FØR onChange fyrer,
                // og feltet ville sidde fast på 'A'. Vi tillader derfor
                // flere tegn at passere ind, og tager kun det SIDST
                // skrevne (slice(-1)) som det nye start-bogstav.
                const upper = e.target.value.toUpperCase();
                const ny = upper.slice(-1);
                // Tomt input (efter Backspace) ignoreres — feltet bliver
                // bare ved med at vise det nuværende bogstav. Ikke-
                // bogstaver ignoreres også.
                if (/^[A-Z]$/.test(ny)) {
                  onStartBogstavAendret(ny);
                }
              }}
              onFocus={(e) => {
                // Marker det eksisterende bogstav når feltet får fokus,
                // så et enkelt tastetryk overskriver det — uden at
                // brugeren manuelt skal slette først.
                e.currentTarget.select();
              }}
              disabled={disabled}
              className="w-20"
            />
            <p className="text-xs text-zinc-500">
              {t("bilag.svarbrev_bliver_bilag", { bogstav: startUpper })}
            </p>
          </div>
        </div>

        <div className="space-y-1">
          <p className="text-xs text-zinc-500 italic">
            {t("bilag.klik_for_redigering")}
          </p>
          <ul className="divide-y divide-zinc-100 rounded-md border border-zinc-200">
            {valg.map((v, idx) => {
              const bogstav = tildelteBogstaver[v.filnavn];
              const erInkluderet = v.inkluderet;
              // Pile disables når der ikke er en inkluderet nabo i den
              // retning at swappe med — fx er den øverst-inkluderede
              // fil disabled på ↑, og den nederst-inkluderede på ↓.
              const harInkluderetFør = valg
                .slice(0, idx)
                .some((x) => x.inkluderet);
              const harInkluderetEfter = valg
                .slice(idx + 1)
                .some((x) => x.inkluderet);
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
                        {t("bilag.bilag_label", { bogstav })}
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
                        placeholder={t("bilag.beskrivelse_placeholder")}
                      />
                      <button
                        type="button"
                        onClick={() => flyt(v.filnavn, -1)}
                        disabled={disabled || !harInkluderetFør}
                        className="px-2 py-1 rounded border border-zinc-300 bg-white text-sm hover:bg-zinc-50 disabled:opacity-30 disabled:cursor-not-allowed"
                        aria-label={t("bilag.flyt_op_aria")}
                        title={t("bilag.flyt_op_aria")}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        onClick={() => flyt(v.filnavn, 1)}
                        disabled={disabled || !harInkluderetEfter}
                        className="px-2 py-1 rounded border border-zinc-300 bg-white text-sm hover:bg-zinc-50 disabled:opacity-30 disabled:cursor-not-allowed"
                        aria-label={t("bilag.flyt_ned_aria")}
                        title={t("bilag.flyt_ned_aria")}
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
            {t("bilag.afsluttende_note", {
              bogstav: startUpper,
              antal: antalInkluderede,
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Bygger BilagItem[] med svarbrevet som første bilag. `selskabBemaerkning`
// kan injiceres af kalderen for at lokalisere første-bilag-overskriften —
// hvis ikke sat, bruges dansk default. Kalderen er typisk
// upload-form.tsx der har adgang til useT()/lavT() og kan bygge stringen.
export function bilagValgTilListe(
  valg: BilagValg[],
  startBogstav: string,
  selskabBemaerkning = "rejseselskabets bemærkninger til sagen",
): BilagItem[] {
  const start = (startBogstav || "A").trim().toUpperCase().slice(0, 1) || "A";
  const startCode = start.charCodeAt(0);
  const liste: BilagItem[] = [
    {
      bogstav: start,
      overskrift: selskabBemaerkning,
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
