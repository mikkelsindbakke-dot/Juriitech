"use client";

import { useEffect, useState, useTransition } from "react";
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

function base64TilBlob(b64: string, mime: string): Blob {
  const byteString = atob(b64);
  const arr = new Uint8Array(byteString.length);
  for (let i = 0; i < byteString.length; i++) {
    arr[i] = byteString.charCodeAt(i);
  }
  return new Blob([arr], { type: mime });
}

// Heuristik: filer fra Nævnet (høringsbrev, retningslinjer, vejledninger)
// skal IKKE anonymiseres — de sendes ikke tilbage til Nævnet og er ikke
// følsomme. Vi disabler dem i checkbox-listen så brugeren ikke kommer til
// at anonymisere noget der allerede er offentligt fra Nævnet.
function erFraNaevnet(filnavn: string): boolean {
  const navn = filnavn.toLowerCase();
  return (
    /høring/.test(navn) ||
    /hoering/.test(navn) ||
    /retningsl/.test(navn) ||
    /vejledning/.test(navn)
  );
}

function rolleAfFilnavn(filnavn: string): string {
  const navn = filnavn.toLowerCase();
  if (/høring|hoering/.test(navn)) return "høring";
  if (/retningsl|vejledning/.test(navn)) return "vejledning";
  if (/klageskema/.test(navn)) return "klageskema";
  if (/bilag\s*0?[1-9]\d?/.test(navn)) return "bilag";
  return "fil";
}

const NAEVNET_NOTE = "Vejledning fra Nævnet — anonymiseres ikke";

// Sektion 10: Anonymisér bilag til Nævnet.
//
// Per-fil checkbox-valg + Klager(e) + Medrejsende inputs (begge bliver
// merget til klager_navne-listen API'et bruger — adskillelsen er kun
// visuel for at hjælpe brugeren med at huske at oplyse begge slags).
export function AnonymiserSektion({ filer }: { filer: File[] }) {
  const [pending, startTransition] = useTransition();

  const [klagerNavne, sætKlagerNavne] = useState<string[]>([]);
  const [klagerInput, sætKlagerInput] = useState("");
  const [medrejsende, sætMedrejsende] = useState<string[]>([]);
  const [medrejsendeInput, sætMedrejsendeInput] = useState("");

  // Per-fil checkbox-valg. Initialiseres til alle PDF'er der ikke er
  // fra Nævnet (klageskema, bilag) som default unchecked — brugeren
  // skal aktivt vælge hvad der skal anonymiseres.
  const [valgte, sætValgte] = useState<Record<string, boolean>>({});

  useEffect(() => {
    // Synkronisér valgte-map når filer ændres
    sætValgte((prev) => {
      const ny: Record<string, boolean> = {};
      for (const f of filer) {
        if (!f.name.toLowerCase().endsWith(".pdf")) continue;
        if (erFraNaevnet(f.name)) continue;
        ny[f.name] = prev[f.name] ?? false;
      }
      return ny;
    });
  }, [filer]);

  const [resultater, sætResultater] = useState<AnonymRespons | null>(null);

  function tilfoejTilListe(
    nyVerdi: string,
    sæt: React.Dispatch<React.SetStateAction<string[]>>,
    sætInput: (s: string) => void,
  ) {
    const v = nyVerdi.trim();
    if (!v) return;
    sæt((xs) => [...xs, v]);
    sætInput("");
  }

  function fjernFraListe(
    i: number,
    sæt: React.Dispatch<React.SetStateAction<string[]>>,
  ) {
    sæt((xs) => xs.filter((_, idx) => idx !== i));
  }

  function toggleAlle(vaerdi: boolean) {
    sætValgte((prev) => {
      const ny: Record<string, boolean> = {};
      for (const k of Object.keys(prev)) ny[k] = vaerdi;
      return ny;
    });
  }

  const valgteFilNavne = Object.entries(valgte)
    .filter(([, v]) => v)
    .map(([k]) => k);
  const antalValgte = valgteFilNavne.length;

  function anonymiser() {
    if (antalValgte === 0) {
      toast.error("Vælg mindst én fil at anonymisere.");
      return;
    }
    const filerAtSende = filer.filter((f) => valgte[f.name]);
    const alleNavne = [...klagerNavne, ...medrejsende];

    startTransition(async () => {
      const url = process.env.NEXT_PUBLIC_API_URL;
      if (!url) {
        toast.error("NEXT_PUBLIC_API_URL ikke sat.");
        return;
      }
      const formData = new FormData();
      for (const fil of filerAtSende) formData.append("filer", fil);
      formData.append("klager_navne_json", JSON.stringify(alleNavne));

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
          `${data.metadata.antal_anonymiseret_ok} af ${data.metadata.antal_input} bilag anonymiseret.`,
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

  // Filter til visning: vis alle filer (også non-PDF og fra-Nævnet) men
  // markér dem som disabled. Det matcher Streamlit-PAX' UI hvor fx
  // høringsbrev og vejledninger vises men er disabled med en note.
  const filerSorted = [...filer].sort((a, b) => a.name.localeCompare(b.name));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-semibold">
          10. Anonymisér bilag til Nævnet
        </CardTitle>
        <CardDescription className="text-xs">
          Vælg de bilag du ønsker at anonymisere — både sagsfiler og
          sagsakter du selv har uploadet. juriitech PAX producerer
          anonymiserede versioner efter Pakkerejse-Ankenævnets
          retningslinjer (Klager for klager, medrejsende for bipersoner,
          CPR-numre fjernes osv.).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Bekræft klager(e) + medrejsende */}
        <div className="space-y-2">
          <Label className="text-sm font-semibold">
            Bekræft klager(e) — bevares synlig i bilagene
          </Label>
          <p className="text-xs text-zinc-500">
            Disse navne bevares helt. Alle andre navne får sortmasket
            efternavn.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Klager(e)</Label>
              <div className="flex gap-1 mt-1">
                <Input
                  value={klagerInput}
                  onChange={(e) => sætKlagerInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      tilfoejTilListe(klagerInput, sætKlagerNavne, sætKlagerInput);
                    }
                  }}
                  placeholder="Anders Andersen"
                  disabled={pending}
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    tilfoejTilListe(klagerInput, sætKlagerNavne, sætKlagerInput)
                  }
                  disabled={pending || !klagerInput.trim()}
                >
                  +
                </Button>
              </div>
              {klagerNavne.length > 0 && (
                <ul className="space-y-1 text-xs mt-2">
                  {klagerNavne.map((n, i) => (
                    <li
                      key={i}
                      className="flex items-center gap-2 rounded-md bg-zinc-50 px-2 py-1"
                    >
                      <span className="flex-1 text-zinc-800">{n}</span>
                      <button
                        type="button"
                        onClick={() => fjernFraListe(i, sætKlagerNavne)}
                        disabled={pending}
                        className="text-zinc-400 hover:text-red-700"
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <Label className="text-xs">
                Medrejsende{" "}
                <span className="text-zinc-400">(valgfrit)</span>
              </Label>
              <div className="flex gap-1 mt-1">
                <Input
                  value={medrejsendeInput}
                  onChange={(e) => sætMedrejsendeInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      tilfoejTilListe(
                        medrejsendeInput,
                        sætMedrejsende,
                        sætMedrejsendeInput,
                      );
                    }
                  }}
                  placeholder="fx ægtefælle eller barn"
                  disabled={pending}
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    tilfoejTilListe(
                      medrejsendeInput,
                      sætMedrejsende,
                      sætMedrejsendeInput,
                    )
                  }
                  disabled={pending || !medrejsendeInput.trim()}
                >
                  +
                </Button>
              </div>
              {medrejsende.length > 0 && (
                <ul className="space-y-1 text-xs mt-2">
                  {medrejsende.map((n, i) => (
                    <li
                      key={i}
                      className="flex items-center gap-2 rounded-md bg-zinc-50 px-2 py-1"
                    >
                      <span className="flex-1 text-zinc-800">{n}</span>
                      <button
                        type="button"
                        onClick={() => fjernFraListe(i, sætMedrejsende)}
                        disabled={pending}
                        className="text-zinc-400 hover:text-red-700"
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          {klagerNavne.length === 0 && medrejsende.length === 0 && (
            <p className="text-xs text-amber-700 italic">
              Hvis listerne er tomme, anonymiseres ALLE personnavne (også
              klagers).
            </p>
          )}
        </div>

        {/* Per-fil checkbox-liste */}
        <div className="space-y-2 pt-2 border-t border-zinc-200">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-semibold">
              Vælg de bilag du ønsker at anonymisere
            </Label>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => toggleAlle(true)}
                disabled={pending}
                className="text-xs text-indigo-600 hover:text-indigo-800"
              >
                Vælg alle
              </button>
              <span className="text-xs text-zinc-300">·</span>
              <button
                type="button"
                onClick={() => toggleAlle(false)}
                disabled={pending}
                className="text-xs text-zinc-500 hover:text-zinc-800"
              >
                Ryd
              </button>
            </div>
          </div>
          <ul className="divide-y divide-zinc-100 rounded-md border border-zinc-200">
            {filerSorted.map((f, idx) => {
              const erPdf = f.name.toLowerCase().endsWith(".pdf");
              const fraNaevnet = erFraNaevnet(f.name);
              const disabled = !erPdf || fraNaevnet || pending;
              const rolle = rolleAfFilnavn(f.name);
              return (
                <li
                  key={f.name + idx}
                  className={`p-3 flex items-center gap-3 ${disabled ? "opacity-60" : ""}`}
                >
                  <input
                    type="checkbox"
                    id={`anonym-${idx}`}
                    checked={!!valgte[f.name]}
                    onChange={() =>
                      sætValgte((p) => ({ ...p, [f.name]: !p[f.name] }))
                    }
                    disabled={disabled}
                  />
                  <label
                    htmlFor={`anonym-${idx}`}
                    className={`flex-1 text-sm ${disabled ? "text-zinc-500" : "text-zinc-900 cursor-pointer"}`}
                  >
                    {f.name}
                  </label>
                  <span className="text-xs text-zinc-500">Sag · {rolle}</span>
                  {fraNaevnet && (
                    <span className="text-xs italic text-zinc-500">
                      {NAEVNET_NOTE}
                    </span>
                  )}
                  {!erPdf && !fraNaevnet && (
                    <span className="text-xs italic text-zinc-400">
                      kun PDF understøttes
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>

        <Button
          type="button"
          onClick={anonymiser}
          disabled={pending || antalValgte === 0}
          className="w-full"
        >
          {pending
            ? `Anonymiserer ${antalValgte} bilag…`
            : `Anonymisér valgte (${antalValgte})`}
        </Button>

        {pending && (
          <div className="rounded-md bg-indigo-50 border border-indigo-200 p-3 text-sm text-indigo-900">
            juriitech PAX anonymiserer {antalValgte} bilag — lægger
            sort-bjælke over følsomme felter i PDF&apos;er. Klagers fulde
            navn anonymiseres ikke, da det ikke er et krav.
          </div>
        )}

        {/* Resultater */}
        {resultater && (
          <div className="space-y-3 border-t border-zinc-200 pt-4">
            <div className="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-900">
              ✓ {resultater.metadata.antal_anonymiseret_ok} af{" "}
              {resultater.metadata.antal_input} bilag er anonymiseret.
              Gennemgå indholdet nedenunder og download som PDF når du er
              tilfreds.
            </div>
            <p className="text-sm font-semibold text-zinc-900">
              Anonymiserede bilag — klar til download
            </p>
            <p className="text-xs text-zinc-500">
              Tjek resultatet manuelt før du sender til Nævnet. AI-anonymisering
              er et hjælpeværktøj, ikke en garanti.
            </p>
            {resultater.filer.map((r, i) => (
              <div
                key={i}
                className="rounded-md border border-zinc-200 bg-white p-3 space-y-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-sm">
                    {r.status === "ok" ? "✓ " : "⚠ "}
                    {r.filnavn}
                  </span>
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
