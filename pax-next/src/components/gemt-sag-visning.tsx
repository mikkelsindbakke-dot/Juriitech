"use client";

// Visning af en gemt sag. State_json indeholder snapshot'et som blev
// gemt via GemSagKnap — som minimum 'analyse' + fil-metadata.
//
// MVP: vi viser AnalyseResultat-komponenten igen, plus en kort header
// med filer + gemt-dato. Re-upload af de oprindelige filer er IKKE
// inkluderet — brugeren skal uploade igen for at generere svarbrev
// eller tjekliste oven på denne analyse.
//
// Forwards-compat: hvis state_json mangler analyse-feltet (ældre
// gemmer-format), viser vi en pænt fejl-besked i stedet for at
// crashe.
import {
  AnalyseResultat,
  type FoerstevurderingsRespons,
} from "@/components/analyse-resultat";
import { useT } from "@/lib/i18n/client";

type GemtFilMeta = {
  navn?: string;
  antal_bytes?: number;
};

type GemtState = {
  analyse?: FoerstevurderingsRespons;
  bilag_start_bogstav?: string;
  bilag_valg?: Record<string, unknown>;
  filer?: GemtFilMeta[];
  gemt_dato?: string;
  // .passthrough — vi accepterer ekstra felter uden at fejle
  [key: string]: unknown;
};

type ParseResultat =
  | { ok: true; state: GemtState }
  | { ok: false; fejl: string };

function parseStateJson(
  raw: string,
  t: (n: string, args?: Record<string, string | number>) => string,
): ParseResultat {
  if (!raw || !raw.trim()) {
    return { ok: false, fejl: t("gemt_sag.ingen_data_fejl") };
  }
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) {
      return { ok: false, fejl: t("gemt_sag.uventet_format_fejl") };
    }
    return { ok: true, state: parsed as GemtState };
  } catch (e) {
    const detalje = e instanceof Error ? e.message : t("gemt_sag.ukendt_fejl");
    return {
      ok: false,
      fejl: t("gemt_sag.laese_fejl", { detalje }),
    };
  }
}

export function GemtSagVisning({ stateJson }: { stateJson: string }) {
  const t = useT();
  const resultat = parseStateJson(stateJson, t);

  if (!resultat.ok) {
    return (
      <div className="rounded-md bg-red-50 border border-red-200 p-4 text-sm text-red-800">
        {resultat.fejl}
      </div>
    );
  }

  const state = resultat.state;
  const analyse = state.analyse;
  const filer = state.filer ?? [];

  return (
    <div className="space-y-6">
      {/* Meta-header med filer og gemmedato */}
      <div className="rounded-md border border-zinc-200 bg-white p-4 space-y-3">
        {filer.length > 0 && (
          <div>
            <p className="text-xs uppercase tracking-wider text-zinc-500 mb-1.5 font-medium">
              {t("gemt_sag.oprindelige_filer")}
            </p>
            <ul className="text-sm text-zinc-700 space-y-0.5">
              {filer.map((f, i) => (
                <li key={i} className="font-mono text-xs">
                  {f.navn ?? t("gemt_sag.fil_fallback", { nr: i + 1 })}
                  {typeof f.antal_bytes === "number" && (
                    <span className="text-zinc-400 ml-2">
                      ({Math.round(f.antal_bytes / 1024)} KB)
                    </span>
                  )}
                </li>
              ))}
            </ul>
            <p className="text-xs text-zinc-500 italic mt-2">
              {t("gemt_sag.fil_indhold_ikke_gemt")}
            </p>
          </div>
        )}
      </div>

      {/* Selve analysen — genbrug af forsidens komponent */}
      {analyse ? (
        <AnalyseResultat data={analyse} />
      ) : (
        <div className="rounded-md bg-amber-50 border border-amber-200 p-4 text-sm text-amber-900">
          {t("gemt_sag.ingen_analyse")}
        </div>
      )}
    </div>
  );
}
