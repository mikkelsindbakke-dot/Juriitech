"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import {
  ApiError,
  anonymiserSchema,
  postOgValider,
  sagsmetadataSchema,
} from "@/lib/api-client";

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
// Klagers navn auto-udledes fra klageskemaet via /api/sagsmetadata
// (samme endpoint som svarbrev-sektionen bruger). Tidligere havde vi
// en manuel "bekræft klager + medrejsende"-formular her — den er nu
// fjernet for at minimere brugerens manuelle arbejde. Hvis auto-
// udtrækning fejler, bliver klager_navne tom — og find_redaction_targets
// anonymiserer så ALLE personnavne, hvilket er en sikker fallback.
export function AnonymiserSektion({ filer }: { filer: File[] }) {
  const [pending, startTransition] = useTransition();
  const [klagersNavn, sætKlagersNavn] = useState<string>("");
  const [valgte, sætValgte] = useState<Record<string, boolean>>({});

  // Sync valgte-map med filer-prop. eslint-disable: prop-sync er det
  // legitime use case der ikke kan løses med derived state uden tab af
  // user-overrides.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
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

  // Auto-hent klagers navn ved første render efter filer er valgt.
  // Cacher pr. fil-signatur via useRef så vi ikke kalder igen ved hver
  // re-render. Fejler stille — anonymiseren har en sikker fallback hvis
  // listen er tom.
  const navnHentetRef = useRef<string>("");
  useEffect(() => {
    if (filer.length === 0) return;
    const filSig = filer.map((f) => f.name).sort().join("|");
    if (navnHentetRef.current === filSig) return;
    navnHentetRef.current = filSig;

    (async () => {
      try {
        const formData = new FormData();
        for (const fil of filer) formData.append("filer", fil);
        const data = await postOgValider(
          "/api/sagsmetadata",
          sagsmetadataSchema,
          { formData, retries: 2 },
        );
        if (data.klagers_navn) sætKlagersNavn(data.klagers_navn);
      } catch (e) {
        console.warn("Auto-udtrækning af klagers navn fejlede:", e);
      }
    })();
  }, [filer]);

  const [resultater, sætResultater] = useState<AnonymRespons | null>(null);

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
    const klagerNavneListe = klagersNavn.trim() ? [klagersNavn.trim()] : [];

    startTransition(async () => {
      const formData = new FormData();
      for (const fil of filerAtSende) formData.append("filer", fil);
      formData.append("klager_navne_json", JSON.stringify(klagerNavneListe));

      try {
        const data = (await postOgValider(
          "/api/anonymiser",
          anonymiserSchema,
          { formData, retries: 3 },
        )) as AnonymRespons;
        sætResultater(data);
        toast.success(
          `${data.metadata.antal_anonymiseret_ok} af ${data.metadata.antal_input} bilag anonymiseret.`,
        );
      } catch (e) {
        if (e instanceof ApiError) {
          toast.error(
            e.detalje ? `${e.message}: ${e.detalje.slice(0, 100)}` : e.message,
          );
        } else {
          toast.error(
            `Uventet fejl: ${e instanceof Error ? e.message : "ukendt"}`,
          );
        }
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

  const filerSorted = [...filer].sort((a, b) => a.name.localeCompare(b.name));

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        {/* Auto-udledt klager-info — vises som info-strip, ikke som form */}
        {klagersNavn && (
          <div className="rounded-md bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-900">
            <strong>Klagers navn auto-udledt:</strong> {klagersNavn} —
            bevares synligt i bilagene. Andre personnavne (medarbejdere,
            guider, eksterne partnere) sortmaskeres.
          </div>
        )}

        {/* Per-fil checkbox-liste */}
        <div className="space-y-2">
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
            sort-bjælke over følsomme felter (CPR, e-mails, telefon,
            interne medarbejdere og eksterne partnere).
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
