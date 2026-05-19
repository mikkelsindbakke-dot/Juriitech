"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import {
  anonymiserSchema,
  postOgValider,
  sagsmetadataSchema,
} from "@/lib/api-client";
import { useFejlBesked, useIsAdmin } from "@/lib/bruger-rolle";
import { useT } from "@/lib/i18n/client";

type AnonymResultat = {
  filnavn: string;
  status:
    | "ok"
    | "scannet"
    | "fejl_aaben"
    | "fejl_redaktion"
    | "ikke_pdf"
    | "ikke_understoettet"
    | "exception";
  anonymiseret_pdf_base64: string | null;
  output_extension?: string | null;
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
  fejl_aaben: "bg-amber-100 text-amber-800",
  fejl_redaktion: "bg-amber-100 text-amber-800",
  ikke_pdf: "bg-zinc-100 text-zinc-700",
  ikke_understoettet: "bg-zinc-100 text-zinc-700",
  exception: "bg-amber-100 text-amber-800",
};

const ANONYM_UNDERSTOETTEDE_EXT = [".pdf", ".docx"];

function erAnonymiserbar(filnavn: string): boolean {
  const lower = filnavn.toLowerCase();
  return ANONYM_UNDERSTOETTEDE_EXT.some((ext) => lower.endsWith(ext));
}

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

type RolleKey = "hoering" | "vejledning" | "klageskema" | "bilag" | "fil";

function rolleAfFilnavn(filnavn: string): RolleKey {
  const navn = filnavn.toLowerCase();
  if (/høring|hoering/.test(navn)) return "hoering";
  if (/retningsl|vejledning/.test(navn)) return "vejledning";
  if (/klageskema/.test(navn)) return "klageskema";
  if (/bilag\s*0?[1-9]\d?/.test(navn)) return "bilag";
  return "fil";
}

// Sektion 10: Anonymisér bilag til Nævnet.
//
// Klagers navn auto-udledes fra klageskemaet via /api/sagsmetadata
// (samme endpoint som svarbrev-sektionen bruger). Tidligere havde vi
// en manuel "bekræft klager + medrejsende"-formular her — den er nu
// fjernet for at minimere brugerens manuelle arbejde. Hvis auto-
// udtrækning fejler, bliver klager_navne tom — og find_redaction_targets
// anonymiserer så ALLE personnavne, hvilket er en sikker fallback.
export function AnonymiserSektion({ filer }: { filer: File[] }) {
  const t = useT();
  const formatFejl = useFejlBesked();
  const isAdmin = useIsAdmin();

  const statusEtiket: Record<AnonymResultat["status"], string> = {
    ok: t("anonymiser.status_ok"),
    scannet: t("anonymiser.status_scannet"),
    fejl_aaben: t("anonymiser.status_fejl_aaben"),
    fejl_redaktion: t("anonymiser.status_fejl_redaktion"),
    ikke_pdf: t("anonymiser.status_ikke_pdf"),
    ikke_understoettet: t("anonymiser.status_ikke_understoettet"),
    exception: t("anonymiser.status_exception"),
  };

  const VENLIG_BEMAERKNING: Partial<Record<AnonymResultat["status"], string>> = {
    fejl_aaben: t("anonymiser.venlig_fejl_aaben"),
    fejl_redaktion: t("anonymiser.venlig_fejl_redaktion"),
    exception: t("anonymiser.venlig_exception"),
  };

  const rolleEtiket = (rolle: RolleKey): string => {
    switch (rolle) {
      case "hoering":
        return t("anonymiser.rolle_hoering");
      case "vejledning":
        return t("anonymiser.rolle_vejledning");
      case "klageskema":
        return t("anonymiser.rolle_klageskema");
      case "bilag":
        return t("anonymiser.rolle_bilag");
      case "fil":
        return t("anonymiser.rolle_fil");
    }
  };
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
        if (!erAnonymiserbar(f.name)) continue;
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
      toast.error(t("anonymiser.vaelg_mindst_en_toast"));
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
          t("anonymiser.anonymiseret_toast", {
            ok: data.metadata.antal_anonymiseret_ok,
            ialt: data.metadata.antal_input,
          }),
        );
      } catch (e) {
        toast.error(formatFejl(e));
      }
    });
  }

  function download(r: AnonymResultat) {
    if (!r.anonymiseret_pdf_base64) return;
    const ext = (r.output_extension || "pdf").toLowerCase();
    const mime =
      ext === "docx"
        ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        : "application/pdf";
    const blob = base64TilBlob(r.anonymiseret_pdf_base64, mime);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download =
      r.filnavn.replace(/\.(pdf|docx)$/i, "") + `_anonymiseret.${ext}`;
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
            <strong>{t("anonymiser.klager_auto_udledt")}</strong> {klagersNavn}{" "}
            — {t("anonymiser.klager_auto_udledt_beskrivelse")}
          </div>
        )}

        {/* Per-fil checkbox-liste */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-semibold">
              {t("anonymiser.vaelg_bilag_label")}
            </Label>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => toggleAlle(true)}
                disabled={pending}
                className="text-xs text-indigo-600 hover:text-indigo-800"
              >
                {t("anonymiser.vaelg_alle")}
              </button>
              <span className="text-xs text-zinc-300">·</span>
              <button
                type="button"
                onClick={() => toggleAlle(false)}
                disabled={pending}
                className="text-xs text-zinc-500 hover:text-zinc-800"
              >
                {t("anonymiser.ryd")}
              </button>
            </div>
          </div>
          <ul className="divide-y divide-zinc-100 rounded-md border border-zinc-200">
            {filerSorted.map((f, idx) => {
              const understoettet = erAnonymiserbar(f.name);
              const fraNaevnet = erFraNaevnet(f.name);
              const disabled = !understoettet || fraNaevnet || pending;
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
                  <span className="text-xs text-zinc-500">
                    {t("anonymiser.sag_rolle", { rolle: rolleEtiket(rolle) })}
                  </span>
                  {fraNaevnet && (
                    <span className="text-xs italic text-zinc-500">
                      {t("anonymiser.naevnet_note")}
                    </span>
                  )}
                  {!understoettet && !fraNaevnet && (
                    <span className="text-xs italic text-zinc-400">
                      {t("anonymiser.kun_pdf_docx")}
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
            ? t("anonymiser.anonymiserer_knap", { antal: antalValgte })
            : t("anonymiser.anonymiser_valgte_knap", { antal: antalValgte })}
        </Button>

        {pending && (
          <div className="rounded-md bg-indigo-50 border border-indigo-200 p-3 text-sm text-indigo-900">
            {t("anonymiser.progress_besked", { antal: antalValgte })}
          </div>
        )}

        {/* Resultater */}
        {resultater && (
          <div className="space-y-3 border-t border-zinc-200 pt-4">
            <div className="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-900">
              {t("anonymiser.resultat_oversigt", {
                ok: resultater.metadata.antal_anonymiseret_ok,
                ialt: resultater.metadata.antal_input,
              })}
            </div>
            <p className="text-sm font-semibold text-zinc-900">
              {t("anonymiser.klar_til_download")}
            </p>
            <p className="text-xs text-zinc-500">
              {t("anonymiser.manuel_tjek")}
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
                    {statusEtiket[r.status]}
                  </span>
                </div>
                <p className="text-xs text-zinc-600">
                  {isAdmin
                    ? r.bemaerkning
                    : VENLIG_BEMAERKNING[r.status] ?? r.bemaerkning}
                </p>
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
                      {t("anonymiser.download_anonymiseret", {
                        ext: (r.output_extension || "pdf").toUpperCase(),
                      })}
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
