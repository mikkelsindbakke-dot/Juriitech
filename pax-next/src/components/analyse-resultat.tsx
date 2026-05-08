"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

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
};

export type FoerstevurderingsRespons = {
  klagepunkter: string[];
  tidsforhold: Tidsforhold;
  analyse: Analyse;
  relevante_sager: RelevantSag[];
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

export function AnalyseResultat({
  data,
}: {
  data: FoerstevurderingsRespons;
}) {
  const a = data.analyse;
  const s = a.sandsynlighedsvurdering ?? {};

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
            AI'ens vurdering af de tre mulige udfald.
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
            <ul className="space-y-1.5 text-sm text-zinc-700 list-disc pl-5">
              {a.klagens_kernepunkter.map((punkt, i) => (
                <li key={i}>{punkt}</li>
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
              <ul className="space-y-1.5 text-sm text-zinc-700 list-disc pl-5">
                {a.yderligere_klagepunkter_og_detaljer.map((punkt, i) => (
                  <li key={i}>{punkt}</li>
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

      {/* Relevante sager */}
      {data.relevante_sager && data.relevante_sager.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              Relevante tidligere afgørelser
            </CardTitle>
            <CardDescription className="text-xs">
              Top {data.relevante_sager.length} fundet via RAG-søgning i
              vidensbanken.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {data.relevante_sager.map((sag, i) => (
                <li
                  key={i}
                  className="flex items-baseline justify-between gap-3 rounded-md bg-zinc-50 px-3 py-2"
                >
                  <span className="font-mono text-zinc-700">
                    {sag.filnavn ?? `Sag ${sag.sag_id}`}
                  </span>
                  {sag.rerank_score !== undefined && (
                    <span className="text-xs tabular-nums text-zinc-500">
                      score: {sag.rerank_score.toFixed(2)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
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
