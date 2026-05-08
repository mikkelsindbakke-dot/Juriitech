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

export type Sagsresume = {
  emne?: string;
  klagepunkter?: string[];
  krav?: string;
  tui_handtering?: string;
  forventet_udfald?: string;
};

export type FoerstevurderingsRespons = {
  klagepunkter: string[];
  tidsforhold: Tidsforhold;
  analyse: Analyse;
  relevante_sager: RelevantSag[];
  match_info?: MatchInfo[];
  sagsresume?: Sagsresume | null;
  metadata: {
    antal_filer: number;
    antal_klagepunkter: number;
    antal_relevante_sager: number;
  };
};

// ─────────── Bilag-pille parsing ───────────
//
// AI-output indeholder ofte fragmenter som "[Bilag 12, s. 1]" eller
// "[Afgørelse 24-288 (2025)]". Vi vil rendere dem som små hvide
// afrundede pille-badges i stedet for kantet-bracket-tekst — det er
// markant lettere at scanne og matcher Streamlit-PAX.
const BILAG_RE = /\[(Bilag\s+[^\]]*|Afgørelse\s+[^\]]*|Klageskema[^\]]*|Høring[^\]]*)\]/gi;

function renderTekstMedBilagPiller(tekst: string): React.ReactNode[] {
  if (!tekst) return [];
  const dele: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  BILAG_RE.lastIndex = 0;
  while ((match = BILAG_RE.exec(tekst)) !== null) {
    if (match.index > lastIndex) {
      dele.push(tekst.slice(lastIndex, match.index));
    }
    dele.push(
      <span
        key={`pille-${match.index}`}
        className="inline-block rounded-full border border-zinc-300 bg-white px-1.5 py-0.5 text-[0.7rem] font-medium text-zinc-700 mx-0.5 align-baseline"
      >
        {match[1]}
      </span>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < tekst.length) {
    dele.push(tekst.slice(lastIndex));
  }
  return dele;
}

// ─────────── Toppen: MEST SANDSYNLIGE UDFALD-kort ───────────

function findMestSandsynligeUdfald(s: Sandsynligheder) {
  const fuld = s.fuld_medhold_til_klager ?? 0;
  const delvist = s.delvist_medhold_til_klager ?? 0;
  const afvisning = s.afvisning_af_klagen ?? 0;
  if (delvist >= fuld && delvist >= afvisning) {
    return {
      label: "DELVIST MEDHOLD",
      pct: delvist,
      anbefaling:
        "Blandet billede. Overvej et forligstilbud der afspejler det forventede delvise udfald.",
      farve: "border-amber-300 bg-amber-50 text-amber-900",
    };
  }
  if (afvisning >= fuld) {
    return {
      label: "AFVISNING AF KLAGEN",
      pct: afvisning,
      anbefaling:
        "Stærk position. Hold fast i argumentet, men vurder om et lille goodwill-tilbud kan undgå nævnsbehandling.",
      farve: "border-emerald-300 bg-emerald-50 text-emerald-900",
    };
  }
  return {
    label: "FULD MEDHOLD TIL KLAGER",
    pct: fuld,
    anbefaling:
      "Svag position. Overvej hurtigt forligstilbud nær klagers krav for at minimere yderligere omkostninger.",
    farve: "border-red-300 bg-red-50 text-red-900",
  };
}

function ProcentKort({
  label,
  vaerdi,
  bg,
  bjælke,
}: {
  label: string;
  vaerdi: number;
  bg: string;
  bjælke: string;
}) {
  return (
    <div className={`rounded-md border p-3 space-y-2 ${bg}`}>
      <p className="text-[0.65rem] uppercase tracking-wider opacity-75">
        {label}
      </p>
      <p className="text-2xl font-bold tabular-nums">{vaerdi}%</p>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/60">
        <div
          className={`h-full ${bjælke} transition-all`}
          style={{ width: `${vaerdi}%` }}
        />
      </div>
    </div>
  );
}

function TopDashboard({ s }: { s: Sandsynligheder }) {
  const top = findMestSandsynligeUdfald(s);
  return (
    <div className="space-y-3">
      <div className={`rounded-md border-l-4 p-4 ${top.farve}`}>
        <p className="text-[0.65rem] uppercase tracking-wider opacity-75">
          Mest sandsynlige udfald
        </p>
        <p className="text-xl font-bold mt-1">
          {top.label} — {top.pct}%
        </p>
        <p className="text-sm mt-2">
          <strong>Anbefalet strategi:</strong> {top.anbefaling}
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <ProcentKort
          label="Fuld medhold til klager"
          vaerdi={s.fuld_medhold_til_klager ?? 0}
          bg="border-red-200 bg-red-50 text-red-900"
          bjælke="bg-red-500"
        />
        <ProcentKort
          label="Delvist medhold til klager"
          vaerdi={s.delvist_medhold_til_klager ?? 0}
          bg="border-amber-200 bg-amber-50 text-amber-900"
          bjælke="bg-amber-500"
        />
        <ProcentKort
          label="Afvisning af klagen"
          vaerdi={s.afvisning_af_klagen ?? 0}
          bg="border-emerald-200 bg-emerald-50 text-emerald-900"
          bjælke="bg-emerald-500"
        />
      </div>
    </div>
  );
}

// ─────────── Klagepunkt-rendering med bold titel ───────────

function splitKlagepunkt(raw: string): { titel: string; rest: string } {
  let tekst = raw.trim();
  tekst = tekst.replace(
    /^(?:klagepunkt\s*\d+\s*[:.\-]|punkt\s*\d+\s*[:.\-]|sekundært\s+punkt\s+[a-zæøå]\s*[:.\-]|\d+\s*[:.\-])\s*/i,
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
    <li className="text-sm text-zinc-700 leading-relaxed">
      <strong className="font-semibold text-zinc-900">{titel}</strong>
      {rest && (
        <span className="ml-1">
          — {renderTekstMedBilagPiller(rest)}
        </span>
      )}
    </li>
  );
}

// ─────────── Sagskort til relevante referencer ───────────

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
          {harBeloeb && (
            <div>
              <p className="text-xs font-semibold text-zinc-700 uppercase tracking-wide mb-2">
                Beløb
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs text-zinc-500 mb-1">Klageren krævede</p>
                  <p className="text-lg font-semibold text-zinc-900">
                    {klagersKrav || "ukendt"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-zinc-500 mb-1">Nævnet tilkendte</p>
                  <p className="text-lg font-semibold text-zinc-900">
                    {tilkendt || "ukendt"}
                  </p>
                </div>
              </div>
            </div>
          )}

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

          {raaTekst && (
            <div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => sætVisRaaTekst((v) => !v)}
              >
                {visRaaTekst ? "Skjul rå tekst" : "Se rå tekst fra afgørelsen"}
              </Button>
              {visRaaTekst && (
                <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-200 bg-white p-3 text-xs text-zinc-700 font-sans leading-relaxed">
                  {raaTekst}
                  {(sag.indhold?.length ?? 0) > 2000 && "..."}
                </pre>
              )}
            </div>
          )}

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

// ─────────── Hoved-komponent ───────────

export function AnalyseResultat({
  data,
}: {
  data: FoerstevurderingsRespons;
}) {
  const a = data.analyse;
  const s = a.sandsynlighedsvurdering ?? {};
  const matchInfo = data.match_info ?? [];
  const sagsresume = data.sagsresume;

  return (
    <div className="space-y-6">
      {/* Top-dashboard */}
      <TopDashboard s={s} />

      {/* 1. Resumé — to-kolonne hvis sagsresumé findes */}
      {sagsresume && (sagsresume.emne || sagsresume.klagepunkter?.length) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">1. Resumé</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {sagsresume.emne && (
              <p className="text-sm text-zinc-700 leading-relaxed">
                {renderTekstMedBilagPiller(sagsresume.emne)}
              </p>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-md bg-white border border-zinc-200 p-3">
                <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
                  Klagepunkter
                </p>
                {sagsresume.klagepunkter && sagsresume.klagepunkter.length > 0 ? (
                  <ul className="list-disc pl-5 space-y-1 text-sm text-zinc-800">
                    {sagsresume.klagepunkter.map((k, i) => (
                      <li key={i}>{k}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-zinc-500 italic">
                    Ingen konkrete punkter udledt.
                  </p>
                )}
              </div>
              <div className="rounded-md bg-white border border-zinc-200 p-3">
                <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
                  Klagers krav
                </p>
                <p className="text-sm text-zinc-800 leading-relaxed">
                  {sagsresume.krav || "—"}
                </p>
              </div>
            </div>
            {sagsresume.forventet_udfald && (
              <div className="rounded-md border-l-4 border-emerald-400 bg-emerald-50 px-4 py-2 text-sm text-emerald-900">
                <p className="text-[0.65rem] uppercase tracking-wider opacity-75">
                  Forventet udfald
                </p>
                <p className="font-medium">{sagsresume.forventet_udfald}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 2. Tidsforhold */}
      {data.tidsforhold &&
        data.tidsforhold.har_problematisk_forsinkelse &&
        !data.tidsforhold.kunne_ikke_udledes && (
          <Card className="border-amber-200 bg-amber-50">
            <CardHeader>
              <CardTitle className="text-base font-semibold text-amber-900">
                2. Tidsforhold og rettidig kommunikation
              </CardTitle>
              <CardDescription className="text-xs text-amber-800">
                juriitech PAX har identificeret følgende relevante tidsforhold
                der bør indgå som forsvarsargument.
              </CardDescription>
            </CardHeader>
            <CardContent className="text-sm text-amber-900 space-y-2">
              {data.tidsforhold.samlet_vurdering && (
                <p>{renderTekstMedBilagPiller(data.tidsforhold.samlet_vurdering)}</p>
              )}
              {data.tidsforhold.konkrete_observationer &&
                data.tidsforhold.konkrete_observationer.length > 0 && (
                  <ul className="list-disc pl-5 space-y-1">
                    {data.tidsforhold.konkrete_observationer.map((o, i) => (
                      <li key={i}>{renderTekstMedBilagPiller(o)}</li>
                    ))}
                  </ul>
                )}
            </CardContent>
          </Card>
        )}

      {/* 3. Klagens kernepunkter */}
      {a.klagens_kernepunkter && a.klagens_kernepunkter.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              3. Klagens kernepunkter
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

      {/* 4. Yderligere klagepunkter */}
      {a.yderligere_klagepunkter_og_detaljer &&
        a.yderligere_klagepunkter_og_detaljer.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-semibold">
                4. Yderligere klagepunkter og detaljer
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

      {/* 5. Rejseselskabets stillingtagen */}
      {a.rejseselskabets_stillingtagen_indtil_nu && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              5. Rejseselskabets stillingtagen indtil nu
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-zinc-700 whitespace-pre-wrap leading-relaxed">
            {renderTekstMedBilagPiller(a.rejseselskabets_stillingtagen_indtil_nu)}
          </CardContent>
        </Card>
      )}

      {/* 6. Kort juridisk vurdering */}
      {a.kort_juridisk_vurdering && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              6. Kort juridisk vurdering
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-zinc-700 whitespace-pre-wrap leading-relaxed">
            {renderTekstMedBilagPiller(a.kort_juridisk_vurdering)}
          </CardContent>
        </Card>
      )}

      {/* Relevante referencer */}
      {data.relevante_sager && data.relevante_sager.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              Relevante tidligere afgørelser
            </CardTitle>
            <CardDescription className="text-xs">
              Tidligere afgørelser fra Pakkerejse-Ankenævnet som juriitech PAX
              har brugt som juridisk præcedens i vurderingen ovenfor. Klik på
              en sag for at se beløb, match-begrundelse og rå tekst-uddrag.
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

      {/* 7. Sandsynlighedsvurdering — inline format som Streamlit */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">
            7. Sandsynlighedsvurdering
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-zinc-700 leading-relaxed">
            <strong>Fuld medhold til klager:</strong>{" "}
            {s.fuld_medhold_til_klager ?? 0}%{" "}
            <strong className="ml-2">Delvist medhold til klager:</strong>{" "}
            {s.delvist_medhold_til_klager ?? 0}%{" "}
            <strong className="ml-2">Afvisning af klagen:</strong>{" "}
            {s.afvisning_af_klagen ?? 0}%
          </p>
          {s.begrundelse && (
            <p className="text-sm text-zinc-700 leading-relaxed">
              {renderTekstMedBilagPiller(s.begrundelse)}
            </p>
          )}
        </CardContent>
      </Card>

      {/* 8. Konklusion — separat sektion */}
      {a.konklusion_en_linje && (
        <Card className="border-emerald-200 bg-emerald-50">
          <CardHeader>
            <CardTitle className="text-base font-semibold text-emerald-900">
              8. Konklusion i én linje
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-emerald-900 leading-relaxed">
            {renderTekstMedBilagPiller(a.konklusion_en_linje)}
          </CardContent>
        </Card>
      )}

      {/* Verificeret klagepunkt-liste (debug-info) */}
      {data.klagepunkter && data.klagepunkter.length > 0 && (
        <details className="rounded-md bg-zinc-50 p-3 text-xs">
          <summary className="cursor-pointer text-zinc-600 hover:text-zinc-900">
            Verificeret klagepunkt-liste ({data.klagepunkter.length} punkter)
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
