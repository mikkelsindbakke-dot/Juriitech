"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export type Sandsynligheder = {
  fuld_medhold_til_klager?: number;
  delvist_medhold_til_klager?: number;
  afvisning_af_klagen?: number;
  begrundelse?: string;
};

export type Analyse = {
  klagens_kernepunkter?: string[];
  yderligere_klagepunkter_og_detaljer?: string[];
  rejseselskabets_stillingtagen_indtil_nu?: string;
  kort_juridisk_vurdering?: string;
  sandsynlighedsvurdering?: Sandsynligheder;
  konklusion_en_linje?: string;
};

export type Tidsforhold = {
  har_problematisk_forsinkelse?: boolean;
  kunne_ikke_udledes?: boolean;
  samlet_vurdering?: string;
  konkrete_observationer?: string[];
};

export type RelevantSag = {
  filnavn?: string;
  sag_id?: string | number;
  rerank_score?: number;
  similarity?: number;
  indhold?: string;
  kilde_url?: string;
};

export type MatchInfo = {
  sagsnummer?: string;
  titel?: string;
  rejsearrangoer?: string;
  klagers_krav?: string;
  tilkendt_beloeb?: string;
  udfald?: string;
  juridisk_relevant_match?: boolean;
  match_begrundelse?: string[];
};

export type FoerstevurderingsRespons = {
  klagepunkter: string[];
  tidsforhold: Tidsforhold;
  analyse: Analyse;
  relevante_sager: RelevantSag[];
  match_info?: MatchInfo[];
  metadata: {
    antal_filer: number;
    antal_klagepunkter: number;
    antal_relevante_sager: number;
  };
};

function ProcentBjælke({
  navn,
  vaerdi,
  farve,
}: {
  navn: string;
  vaerdi: number;
  farve: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-sm">
        <span className="text-zinc-700">{navn}</span>
        <span className="font-semibold tabular-nums">{vaerdi}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100">
        <div
          className={`h-full ${farve} transition-all`}
          style={{ width: `${vaerdi}%` }}
        />
      </div>
    </div>
  );
}

// Splitter et klagepunkt i (titel, rest) for at kunne vise titlen i fed.
// AI'en returnerer typisk "Klagepunkt N: [beskrivelse] [Bilag XX]" — vi
// stripper N-præfikset og bold'er den første sætning op til komma/dash/
// kolon, max ~55 tegn. Hvis ingen separator findes, bold'er vi de første
// ~5 ord. Hjælper jurister hurtigt at scanne hvad hvert punkt handler om.
function splitKlagepunkt(raw: string): { titel: string; rest: string } {
  let tekst = raw.trim();
  // Strip "Klagepunkt N:" / "Punkt N:" / "N." / "N:" præfikser
  tekst = tekst.replace(
    /^(?:klagepunkt\s*\d+\s*[:.\-]|punkt\s*\d+\s*[:.\-]|\d+\s*[:.\-])\s*/i,
    "",
  );

  const SEP = /[:,–—\-]/;
  const idx = tekst.search(SEP);
  if (idx > 0 && idx <= 55) {
    return {
      titel: tekst.slice(0, idx).trim(),
      rest: tekst.slice(idx + 1).trim(),
    };
  }
  // Ingen separator — tag de første 4 ord som titel
  const ord = tekst.split(/\s+/);
  if (ord.length <= 4) {
    return { titel: tekst, rest: "" };
  }
  return {
    titel: ord.slice(0, 4).join(" "),
    rest: ord.slice(4).join(" "),
  };
}

function KlagepunktItem({ punkt }: { punkt: string }) {
  const { titel, rest } = splitKlagepunkt(punkt);
  return (
    <li className="text-sm text-zinc-700">
      <strong className="font-semibold text-zinc-900">{titel}</strong>
      {rest && <span className="ml-1">— {rest}</span>}
    </li>
  );
}

function UdfaldsBadge({ udfald }: { udfald?: string }) {
  if (!udfald) return null;
  let label = udfald;
  let cls = "bg-zinc-100 text-zinc-700";
  if (udfald.includes("Fuld medhold")) {
    label = "Fuld medhold til klager";
    cls = "bg-red-100 text-red-800 border border-red-200";
  } else if (udfald.includes("Delvist")) {
    label = "Delvist medhold";
    cls = "bg-amber-100 text-amber-800 border border-amber-200";
  } else if (udfald === "Afvist") {
    label = "Afvist";
    cls = "bg-emerald-100 text-emerald-800 border border-emerald-200";
  }
  return (
    <span className={`inline-block text-xs rounded-full px-2 py-0.5 ${cls}`}>
      {label}
    </span>
  );
}

function MatchProcent({ procent }: { procent: number }) {
  let farve = "text-zinc-500";
  if (procent >= 70) farve = "text-emerald-600";
  else if (procent >= 55) farve = "text-amber-600";
  return (
    <div className="text-right">
      <div className={`text-2xl font-bold ${farve}`}>{procent}%</div>
      <div className="text-xs text-zinc-500">match</div>
    </div>
  );
}

function RelevantSagKort({
  sag,
  info,
  index,
}: {
  sag: RelevantSag;
  info: MatchInfo;
  index: number;
}) {
  const [aaben, sætAaben] = useState(false);
  const [visRaaTekst, sætVisRaaTekst] = useState(false);

  const sim = sag.similarity ?? 0;
  const simPct = Math.round(sim * 100);

  const sagsnummer =
    info.sagsnummer ||
    (sag.filnavn ?? `Sag ${sag.sag_id ?? ""}`)
      .replace(/\.[^.]+$/, "")
      .replace(/_/g, " ");

  const titel = info.titel || "";
  const klagersKrav = info.klagers_krav || "";
  const tilkendt = info.tilkendt_beloeb || "";
  const arrangoer = info.rejsearrangoer || "";
  const begrundelser = info.match_begrundelse ?? [];

  const harBeloeb = !!klagersKrav || !!tilkendt;
  const harBegrundelser = begrundelser.length > 0;

  const raaTekst = (sag.indhold ?? "").slice(0, 2000);

  return (
    <div className="rounded-md border border-zinc-200 bg-white">
      {/* Header */}
      <div className="flex items-start gap-3 p-4">
        <div className="flex-1 space-y-1">
          <p className="text-sm font-semibold text-zinc-900">
            {index}. Sagsnummer {sagsnummer}
            {titel && <span className="font-normal"> · {titel}</span>}
          </p>
          {arrangoer && arrangoer.toLowerCase() !== "ukendt" && (
            <p className="text-xs text-zinc-500">{arrangoer}</p>
          )}
          <div className="pt-0.5">
            <UdfaldsBadge udfald={info.udfald} />
          </div>
        </div>
        <MatchProcent procent={simPct} />
      </div>

      {/* Toggle "vis detaljer" */}
      {(harBeloeb || harBegrundelser || raaTekst) && (
        <button
          type="button"
          onClick={() => sætAaben((v) => !v)}
          className="w-full border-t border-zinc-100 px-4 py-2 text-left text-xs font-medium text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900"
        >
          {aaben ? "Skjul detaljer ▴" : "Se uddrag af afgørelsen ▾"}
        </button>
      )}

      {aaben && (
        <div className="space-y-4 border-t border-zinc-100 bg-zinc-50 px-4 py-4">
          {/* Beløb */}
          {harBeloeb && (
            <div>
              <p className="text-xs font-semibold text-zinc-700 uppercase tracking-wide mb-2">
                Beløb
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-md border border-zinc-200 bg-white p-3">
                  <p className="text-xs text-zinc-500 mb-1">Klageren krævede</p>
                  <p className="text-lg font-semibold text-zinc-900">
                    {klagersKrav || "ukendt"}
                  </p>
                </div>
                <div className="rounded-md border border-zinc-200 bg-white p-3">
                  <p className="text-xs text-zinc-500 mb-1">Nævnet tilkendte</p>
                  <p className="text-lg font-semibold text-zinc-900">
                    {tilkendt || "ukendt"}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Match-begrundelse */}
          {harBegrundelser && (
            <div>
              <p className="text-xs font-semibold text-zinc-700 uppercase tracking-wide mb-2">
                Hvorfor juriitech PAX ser det som et match
              </p>
              <ul className="space-y-1 text-sm text-zinc-700 list-disc pl-5">
                {begrundelser.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Rå tekst-uddrag */}
          {raaTekst && (
            <div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => sætVisRaaTekst((v) => !v)}
              >
                {visRaaTekst
                  ? "Skjul rå tekst"
                  : "Se rå tekst fra afgørelsen"}
              </Button>
              {visRaaTekst && (
                <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-200 bg-white p-3 text-xs text-zinc-700 font-sans leading-relaxed">
                  {raaTekst}
                  {(sag.indhold?.length ?? 0) > 2000 && "..."}
                </pre>
              )}
            </div>
          )}

          {/* Original-link */}
          {sag.kilde_url && (
            <a
              href={sag.kilde_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block text-xs text-blue-700 hover:text-blue-900 underline underline-offset-2"
            >
              Åbn original på pakkerejseankenaevnet.dk →
            </a>
          )}
        </div>
      )}
    </div>
  );
}

export function AnalyseResultat({
  data,
}: {
  data: FoerstevurderingsRespons;
}) {
  const a = data.analyse;
  const s = a.sandsynlighedsvurdering ?? {};
  const matchInfo = data.match_info ?? [];

  return (
    <div className="space-y-4">
      {/* Konklusion */}
      {a.konklusion_en_linje && (
        <Card className="border-emerald-200 bg-emerald-50">
          <CardHeader>
            <CardTitle className="text-base font-semibold text-emerald-900">
              Konklusion
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-emerald-900">
            {a.konklusion_en_linje}
          </CardContent>
        </Card>
      )}

      {/* Sandsynligheder */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">
            Sandsynlighedsvurdering
          </CardTitle>
          <CardDescription className="text-xs">
            AI&apos;ens vurdering af de tre mulige udfald.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <ProcentBjælke
            navn="Fuld medhold til klager"
            vaerdi={s.fuld_medhold_til_klager ?? 0}
            farve="bg-red-500"
          />
          <ProcentBjælke
            navn="Delvist medhold til klager"
            vaerdi={s.delvist_medhold_til_klager ?? 0}
            farve="bg-amber-500"
          />
          <ProcentBjælke
            navn="Afvisning af klagen"
            vaerdi={s.afvisning_af_klagen ?? 0}
            farve="bg-emerald-500"
          />
          {s.begrundelse && (
            <details className="pt-2 text-sm text-zinc-700">
              <summary className="cursor-pointer text-zinc-600 hover:text-zinc-900">
                Vis begrundelse
              </summary>
              <p className="mt-2 leading-relaxed">{s.begrundelse}</p>
            </details>
          )}
        </CardContent>
      </Card>

      {/* Klagens kernepunkter */}
      {a.klagens_kernepunkter && a.klagens_kernepunkter.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              Klagens kernepunkter
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 list-disc pl-5">
              {a.klagens_kernepunkter.map((punkt, i) => (
                <KlagepunktItem key={i} punkt={punkt} />
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Yderligere klagepunkter */}
      {a.yderligere_klagepunkter_og_detaljer &&
        a.yderligere_klagepunkter_og_detaljer.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-semibold">
                Yderligere klagepunkter og detaljer
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 list-disc pl-5">
                {a.yderligere_klagepunkter_og_detaljer.map((punkt, i) => (
                  <KlagepunktItem key={i} punkt={punkt} />
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

      {/* Tidsforhold */}
      {data.tidsforhold &&
        data.tidsforhold.har_problematisk_forsinkelse &&
        !data.tidsforhold.kunne_ikke_udledes && (
          <Card className="border-amber-200 bg-amber-50">
            <CardHeader>
              <CardTitle className="text-base font-semibold text-amber-900">
                Tidsforhold og rettidig kommunikation
              </CardTitle>
              <CardDescription className="text-xs text-amber-800">
                Pakkerejse-Ankenævnet vægter rettidig reklamation højt.
              </CardDescription>
            </CardHeader>
            <CardContent className="text-sm text-amber-900 space-y-2">
              {data.tidsforhold.samlet_vurdering && (
                <p>{data.tidsforhold.samlet_vurdering}</p>
              )}
              {data.tidsforhold.konkrete_observationer &&
                data.tidsforhold.konkrete_observationer.length > 0 && (
                  <ul className="list-disc pl-5 space-y-1">
                    {data.tidsforhold.konkrete_observationer.map((o, i) => (
                      <li key={i}>{o}</li>
                    ))}
                  </ul>
                )}
            </CardContent>
          </Card>
        )}

      {/* Rejseselskabets stillingtagen */}
      {a.rejseselskabets_stillingtagen_indtil_nu && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              Rejseselskabets stillingtagen indtil nu
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-zinc-700 whitespace-pre-wrap leading-relaxed">
            {a.rejseselskabets_stillingtagen_indtil_nu}
          </CardContent>
        </Card>
      )}

      {/* Juridisk vurdering */}
      {a.kort_juridisk_vurdering && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              Kort juridisk vurdering
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-zinc-700 whitespace-pre-wrap leading-relaxed">
            {a.kort_juridisk_vurdering}
          </CardContent>
        </Card>
      )}

      {/* Relevante sager — rige sagskort */}
      {data.relevante_sager && data.relevante_sager.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              Relevante tidligere afgørelser
            </CardTitle>
            <CardDescription className="text-xs">
              Tidligere afgørelser fra Pakkerejse-Ankenævnet som AI&apos;en har
              brugt som juridisk præcedens i vurderingen ovenfor. Klik på en
              sag for at se beløb, match-begrundelse og rå tekst-uddrag.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.relevante_sager.map((sag, i) => (
              <RelevantSagKort
                key={i}
                index={i + 1}
                sag={sag}
                info={matchInfo[i] ?? {}}
              />
            ))}
          </CardContent>
        </Card>
      )}

      {/* Verificeret klagepunkt-liste (debug-info) */}
      {data.klagepunkter && data.klagepunkter.length > 0 && (
        <details className="rounded-md bg-zinc-50 p-3 text-xs">
          <summary className="cursor-pointer text-zinc-600 hover:text-zinc-900">
            Verificeret klagepunkt-liste fra udled_alle_klagepunkter
            ({data.klagepunkter.length} punkter)
          </summary>
          <ol className="mt-2 list-decimal pl-5 space-y-1 text-zinc-700">
            {data.klagepunkter.map((kp, i) => (
              <li key={i}>{kp}</li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
