"use client";

import { useState, useTransition } from "react";
import { Loader2, FileText, FileDown } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Pillar } from "@/components/ui/pillar";
import {
  analyseEksportSchema,
  ApiError,
  postJsonOgValider,
} from "@/lib/api-client";
import { useT } from "@/lib/i18n/client";

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

export type Begivenhed = {
  dato?: string;
  tidspunkt?: string | null;
  type?: string; // ankomst | klage_til_guide | tui_reaktion | klage_til_tui | afgang | andet
  aktoer?: string;
  beskrivelse?: string;
  betydning?: string; // neutral | positiv_for_tui | negativ_for_tui
};

export type Tidsforhold = {
  rejseperiode?: string;
  antal_naetter?: number;
  har_problematisk_forsinkelse?: boolean;
  kunne_ikke_udledes?: boolean;
  samlet_vurdering?: string;
  konkrete_observationer?: string[];
  begivenheder?: Begivenhed[];
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

export type UlaeseligFil = {
  filnavn: string;
  aarsag: string;
};

export type FoerstevurderingsRespons = {
  klagepunkter: string[];
  tidsforhold: Tidsforhold;
  analyse: Analyse;
  relevante_sager: RelevantSag[];
  match_info?: MatchInfo[];
  match_kvalitet?: "god" | "begrænset" | "ingen";
  sagsresume?: Sagsresume | null;
  ulaeselige_filer?: UlaeseligFil[];
  paragraf_advarsler?: string[];
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

// Renderer fri-tekst som afsnit, hvor leading-overskrifter/labels
// (markdown **bold**, "Tema:", "Klagepunkt:", "Afsnit:" osv.) gøres
// fed. Bruges fx i 'Rejseselskabets stillingtagen' og 'Kort juridisk
// vurdering' så afsnitsstrukturen visuelt matcher resten af analysen.
const LEADING_LABEL_RE = /^([A-ZÆØÅ][^:.\n]{2,60})[::]\s+/;

function renderTekstMedAfsnit(tekst: string): React.ReactNode {
  if (!tekst) return null;
  const afsnit = tekst.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean);
  return (
    <div className="space-y-3">
      {afsnit.map((afsnitTekst, idx) => {
        // 1) Markdown-style **fed**-prefix vinder
        const mdMatch = /^\*\*([^*]+?)\*\*[:\s—-]+/.exec(afsnitTekst);
        if (mdMatch) {
          const titel = mdMatch[1].trim();
          const rest = afsnitTekst.slice(mdMatch[0].length).trim();
          return (
            <p key={idx} className="text-sm sm:text-base text-zinc-800 leading-relaxed">
              <strong className="font-semibold text-zinc-900">{titel}</strong>
              {rest && <> — {renderTekstMedBilagPiller(rest)}</>}
            </p>
          );
        }
        // 2) Stand-alone overskrift-paragraf der ender på kolon —
        //    fx "På rejsemålet (29.-30. september 2025):" eller
        //    "Efter hjemkomst — første reklamationsrunde (21.-23. oktober):"
        //    Disse fanges IKKE af LEADING_LABEL_RE fordi de indeholder
        //    punktum-tegn i parentes-datoer. Vi detekterer dem som:
        //    kort (< 200 tegn), starter med stort bogstav, ender med ":".
        if (
          afsnitTekst.length <= 200 &&
          /^[A-ZÆØÅ]/.test(afsnitTekst) &&
          /[::]\s*$/.test(afsnitTekst) &&
          !afsnitTekst.includes("\n")
        ) {
          return (
            <p
              key={idx}
              className="text-sm sm:text-base font-semibold text-zinc-900 leading-relaxed"
            >
              {renderTekstMedBilagPiller(afsnitTekst)}
            </p>
          );
        }
        // 3) "Tema: …" / "Klagepunkt: …" / "Afsnit: …" leading-label
        const labelMatch = LEADING_LABEL_RE.exec(afsnitTekst);
        if (labelMatch && labelMatch[1].length <= 50) {
          const titel = labelMatch[1].trim();
          const rest = afsnitTekst.slice(labelMatch[0].length).trim();
          return (
            <p key={idx} className="text-sm sm:text-base text-zinc-800 leading-relaxed">
              <strong className="font-semibold text-zinc-900">{titel}</strong>
              {rest && <> — {renderTekstMedBilagPiller(rest)}</>}
            </p>
          );
        }
        return (
          <p key={idx} className="text-sm sm:text-base text-zinc-800 leading-relaxed">
            {renderTekstMedBilagPiller(afsnitTekst)}
          </p>
        );
      })}
    </div>
  );
}

// ─────────── Toppen: MEST SANDSYNLIGE UDFALD-kort ───────────

function findMestSandsynligeUdfald(s: Sandsynligheder) {
  const fuld = s.fuld_medhold_til_klager ?? 0;
  const delvist = s.delvist_medhold_til_klager ?? 0;
  const afvisning = s.afvisning_af_klagen ?? 0;
  if (delvist >= fuld && delvist >= afvisning) {
    return {
      labelNoegle: "resultat.udfald_delvist_medhold",
      pct: delvist,
      farve: "border-amber-300 bg-amber-50 text-amber-900",
    };
  }
  if (afvisning >= fuld) {
    return {
      labelNoegle: "resultat.udfald_afvisning",
      pct: afvisning,
      farve: "border-emerald-300 bg-emerald-50 text-emerald-900",
    };
  }
  return {
    labelNoegle: "resultat.udfald_fuld_medhold",
    pct: fuld,
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
  const t = useT();
  const top = findMestSandsynligeUdfald(s);
  return (
    <div className="space-y-3">
      <div className={`rounded-md border-l-4 p-4 ${top.farve}`}>
        <p className="text-[0.65rem] uppercase tracking-wider opacity-75">
          {t("resultat.mest_sandsynlige_udfald")}
        </p>
        <p className="text-xl font-bold mt-1">
          {t(top.labelNoegle)} — {top.pct}%
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <ProcentKort
          label={t("resultat.kort_fuld_medhold")}
          vaerdi={s.fuld_medhold_til_klager ?? 0}
          bg="border-red-200 bg-red-50 text-red-900"
          bjælke="bg-red-500"
        />
        <ProcentKort
          label={t("resultat.kort_delvist_medhold")}
          vaerdi={s.delvist_medhold_til_klager ?? 0}
          bg="border-amber-200 bg-amber-50 text-amber-900"
          bjælke="bg-amber-500"
        />
        <ProcentKort
          label={t("resultat.kort_afvisning")}
          vaerdi={s.afvisning_af_klagen ?? 0}
          bg="border-emerald-200 bg-emerald-50 text-emerald-900"
          bjælke="bg-emerald-500"
        />
      </div>
    </div>
  );
}

// ─────────── Klagepunkt-rendering med bold titel ───────────

export function splitKlagepunkt(raw: string): { titel: string; rest: string } {
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

// ─────────── Tidslinje for tidsforhold-pillaren ───────────
//
// Vertikal timeline der matcher Streamlit-PAX:
//   • venstre kolonne: dato (serif-bold), tidspunkt, fase-label (uppercase)
//   • midte: dot (rød = negativ for selskabet, grøn = positiv, grå = neutral)
//   • højre: kort med "Aktør: beskrivelse"
//
// Begivenheder efter "afgang"-typen dæmpes visuelt — det vigtige
// juridisk er hvad der skete PÅ destinationen.
function faseLabelNoegle(typ: string | undefined, efterHjemkomst: boolean): string {
  const lower = (typ ?? "").toLowerCase();
  if (lower === "ankomst") return "tidslinje.fase_ankomst";
  if (lower === "afgang") return "tidslinje.fase_hjemrejse";
  if (efterHjemkomst) return "tidslinje.fase_efter_hjemkomst";
  return "tidslinje.fase_paa_destination";
}

function dotFarverFraBetydning(b: string | undefined): {
  bg: string;
  ring: string;
} {
  switch ((b ?? "neutral").toLowerCase()) {
    case "negativ_for_tui":
      return { bg: "bg-red-600", ring: "ring-red-500/25" };
    case "positiv_for_tui":
      return { bg: "bg-emerald-600", ring: "ring-emerald-500/25" };
    default:
      return { bg: "bg-zinc-500", ring: "ring-zinc-500/20" };
  }
}

function Tidslinje({ begivenheder }: { begivenheder: Begivenhed[] }) {
  const t = useT();
  const afgangIdx = begivenheder.findIndex(
    (b) => (b.type ?? "").toLowerCase() === "afgang",
  );

  return (
    <div className="relative mt-3">
      {/* Vertikal linje gennem prikkene */}
      <div
        className="absolute left-[180px] top-3 bottom-3 w-[2px] bg-amber-900/15"
        aria-hidden
      />

      <ul className="space-y-3.5">
        {begivenheder.map((b, i) => {
          const efterHjem = afgangIdx >= 0 && i > afgangIdx;
          const { bg, ring } = dotFarverFraBetydning(b.betydning);
          const fase = t(faseLabelNoegle(b.type, efterHjem));

          return (
            <li
              key={i}
              className="relative flex items-start min-h-[28px]"
            >
              {/* Venstre: dato-kolonne */}
              <div className="w-[165px] shrink-0 text-right pr-5 pt-2">
                {b.dato ? (
                  <span
                    className={`block font-bold leading-tight whitespace-nowrap ${
                      efterHjem
                        ? "text-zinc-400 text-[0.85rem] font-semibold"
                        : "text-amber-900 text-[0.92rem]"
                    }`}
                  >
                    {b.dato}
                  </span>
                ) : (
                  <span className="block italic text-zinc-400 text-xs leading-tight">
                    {t("tidslinje.dato_ikke_verificeret")}
                  </span>
                )}
                {b.tidspunkt && (
                  <span
                    className={`block font-semibold text-[0.78rem] leading-tight mt-0.5 ${
                      efterHjem ? "text-zinc-400" : "text-amber-700"
                    }`}
                  >
                    {b.tidspunkt}
                  </span>
                )}
                <span
                  className={`block text-[0.7rem] font-semibold uppercase tracking-wide mt-1 ${
                    efterHjem
                      ? "text-zinc-400 opacity-65"
                      : "text-amber-700 opacity-80"
                  }`}
                >
                  {fase}
                </span>
              </div>

              {/* Dot på linjen */}
              <div
                className={`absolute left-[174px] top-3 w-3.5 h-3.5 rounded-full ring-4 ring-offset-0 border-[3px] border-amber-100 ${bg} ${ring} ${
                  efterHjem ? "scale-90 opacity-60" : ""
                }`}
                aria-hidden
              />

              {/* Højre: tekst-kort */}
              <div
                className={`flex-1 ml-[30px] rounded-lg px-3.5 py-2.5 text-[0.95rem] leading-relaxed border ${
                  efterHjem
                    ? "bg-white/35 border-amber-900/10 border-dashed text-zinc-500 text-[0.88rem] opacity-75"
                    : "bg-white/55 border-amber-900/10 text-zinc-800"
                }`}
              >
                {b.aktoer && (
                  <strong
                    className={`font-bold mr-1 ${
                      efterHjem ? "text-zinc-500" : "text-amber-900"
                    }`}
                  >
                    {b.aktoer}:
                  </strong>
                )}
                {b.beskrivelse
                  ? renderTekstMedBilagPiller(b.beskrivelse)
                  : "—"}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ─────────── Afgørelses-tekst i Pakkerejse-Ankenævnets stil ───────────
//
// Den scrapede tekst er ren tekst uden HTML-struktur. For at matche
// Nævnets webpræsentation parser vi de kanoniske afsnits-overskrifter
// (fx "Klagens indhold", "Indklagedes bemærkninger", "Nævnets
// bemærkninger og afgørelse") og renderer dem som tydelige sektion-
// overskrifter med almindelig brødtekst i serif-font.

const AFG_OVERSKRIFTER = [
  "Klagen drejer sig om",
  "Klagens indhold",
  "Klagerens påstand",
  "Klagers påstand",
  "Indklagedes bemærkninger",
  "Indklagedes påstand",
  "Indklagedes svar",
  "Sagens omstændigheder",
  "Sagsfremstilling",
  "Nævnets bemærkninger og afgørelse",
  "Nævnets bemærkninger",
  "Nævnets afgørelse",
  "Konklusion",
  "Begrundelse",
  "Sagsfremstilling og afgørelse",
];

function erOverskrift(linje: string): boolean {
  const trimmet = linje.trim().replace(/[.:]+$/, "");
  if (!trimmet || trimmet.length > 80) return false;
  return AFG_OVERSKRIFTER.some(
    (h) => trimmet.toLowerCase() === h.toLowerCase(),
  );
}

export type AfgBlok =
  | { type: "overskrift"; tekst: string }
  | { type: "afsnit"; tekst: string };

export function parseAfgoerelse(raaTekst: string): AfgBlok[] {
  const blokke: AfgBlok[] = [];
  let aktueltAfsnit: string[] = [];

  const flushAfsnit = () => {
    const sammen = aktueltAfsnit.join(" ").trim();
    if (sammen) blokke.push({ type: "afsnit", tekst: sammen });
    aktueltAfsnit = [];
  };

  // Split på blanke linjer for at få "naturlige" afsnit, men hold også
  // single-newlines som potentielle overskrift-kandidater.
  for (const raaLinje of raaTekst.split(/\n/)) {
    const linje = raaLinje.trim();
    if (!linje) {
      flushAfsnit();
      continue;
    }
    if (erOverskrift(linje)) {
      flushAfsnit();
      blokke.push({ type: "overskrift", tekst: linje.replace(/[.:]+$/, "") });
      continue;
    }
    aktueltAfsnit.push(linje);
  }
  flushAfsnit();
  return blokke;
}

// Heuristik: udtræk sagsnummer fra de første ~500 tegn af afgørelsen.
// Pakkerejse-Ankenævnet skriver typisk "Sag nr. ÅÅ-NNN" eller bare
// "ÅÅ-NNN" øverst på forsiden.
function udtraekSagsnummer(tekst: string, fallback: string): string {
  const top = tekst.slice(0, 500);
  const m =
    top.match(/sag\s*(?:nr\.?|nummer)?[\s.:]*([0-9]{2}[-/.][0-9]{2,4}[-/.0-9]*)/i) ||
    top.match(/\b([0-9]{2}-[0-9]{3,5})\b/);
  if (m && m[1]) return m[1].trim();
  return fallback;
}

// Heuristik: find første rimelig dato i de første ~800 tegn. Match
// både "12. juni 2025" og "12-06-2025"-formater.
function udtraekDato(tekst: string): string | null {
  const top = tekst.slice(0, 800);
  const m =
    top.match(
      /\b(\d{1,2}\.\s*(?:januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december)\s+\d{4})\b/i,
    ) || top.match(/\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b/);
  return m ? m[1].trim() : null;
}

function AfgoerelseFormateret({
  tekst,
  harMere,
  sagsnummerFallback,
}: {
  tekst: string;
  harMere: boolean;
  sagsnummerFallback: string;
}) {
  const t = useT();
  const blokke = parseAfgoerelse(tekst);
  const sagsnr = udtraekSagsnummer(tekst, sagsnummerFallback);
  const dato = udtraekDato(tekst);

  return (
    <article className="max-h-[36rem] overflow-auto rounded-md border border-zinc-200 bg-white">
      {/* Forside-header — matcher Pakkerejse-Ankenævnets PDF-layout:
          institutions-navn øverst, sagsnummer + dato i en kolonne under,
          tynd skille-linje før selve afgørelsesteksten. */}
      <header className="px-8 pt-7 pb-5 border-b border-zinc-300">
        <p className="font-serif text-base sm:text-lg font-semibold tracking-wide text-zinc-900">
          {t("praecedens.header_institution")}
        </p>
        <p className="text-[0.7rem] uppercase tracking-[0.15em] text-zinc-500 mt-0.5">
          {t("praecedens.header_undertekst")}
        </p>
        <div className="mt-4 flex flex-wrap gap-x-8 gap-y-1 text-sm font-serif text-zinc-800">
          <div>
            <span className="text-zinc-500 text-xs uppercase tracking-wider mr-1.5">
              {t("praecedens.label_sag_nr")}
            </span>
            <span className="font-medium">{sagsnr}</span>
          </div>
          {dato && (
            <div>
              <span className="text-zinc-500 text-xs uppercase tracking-wider mr-1.5">
                {t("praecedens.label_dato")}
              </span>
              <span className="font-medium">{dato}</span>
            </div>
          )}
        </div>
      </header>

      {/* Brødtekst — sektioner med sentence-case overskrifter (som
          den faktiske afgørelse, ikke uppercase). Justified body for
          klassisk juridisk-dokument-look. */}
      <div className="px-8 py-6 space-y-4 font-serif text-[0.95rem] text-zinc-900">
        {blokke.map((b, i) => {
          if (b.type === "overskrift") {
            return (
              <h4
                key={i}
                className="text-base font-semibold text-zinc-900 pt-3 leading-snug"
              >
                {b.tekst}
              </h4>
            );
          }
          return (
            <p key={i} className="leading-[1.7] text-justify hyphens-auto">
              {b.tekst}
            </p>
          );
        })}
        {harMere && (
          <p className="text-xs text-zinc-400 italic pt-4 mt-4 border-t border-zinc-200 not-italic">
            <span className="italic">{t("praecedens.resten_ikke_vist")}</span>
          </p>
        )}
      </div>
    </article>
  );
}

// ─────────── Sagskort til relevante referencer ───────────

function UdfaldsBadge({ udfald }: { udfald?: string }) {
  const t = useT();
  if (!udfald) return null;
  let label = udfald;
  let cls = "bg-zinc-100 text-zinc-700";
  if (udfald.includes("Fuld medhold")) {
    label = t("match.udfald_fuld_medhold");
    cls = "bg-red-100 text-red-800 border border-red-200";
  } else if (udfald.includes("Delvist")) {
    label = t("match.udfald_delvist_medhold");
    cls = "bg-amber-100 text-amber-800 border border-amber-200";
  } else if (udfald === "Afvist") {
    label = t("match.udfald_afvist");
    cls = "bg-emerald-100 text-emerald-800 border border-emerald-200";
  }
  return (
    <span className={`inline-block text-xs rounded-full px-2 py-0.5 ${cls}`}>
      {label}
    </span>
  );
}

function MatchProcent({ procent }: { procent: number }) {
  const t = useT();
  let farve = "text-zinc-500";
  if (procent >= 70) farve = "text-emerald-600";
  else if (procent >= 55) farve = "text-amber-600";
  return (
    <div className="text-right">
      <div className={`text-2xl font-bold ${farve}`}>{procent}%</div>
      <div className="text-xs text-zinc-500">{t("match.label_match")}</div>
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
  const t = useT();
  const [aaben, sætAaben] = useState(false);
  const [visRaaTekst, sætVisRaaTekst] = useState(false);

  const sim = sag.similarity ?? 0;
  const simPct = Math.round(sim * 100);

  const sagsnummer =
    info.sagsnummer ||
    (sag.filnavn ?? `${t("match.sag_prefix")} ${sag.sag_id ?? ""}`)
      .replace(/\.[^.]+$/, "")
      .replace(/_/g, " ");

  const titel = info.titel || "";
  const klagersKrav = info.klagers_krav || t("resultat.ukendt");
  const tilkendt = info.tilkendt_beloeb || t("resultat.ukendt");
  const arrangoer = info.rejsearrangoer || "";
  // Hvis backend ikke returnerer begrundelser overhovedet (fx fordi
  // opsummer_matches_til_visning fejlede helt og match_info var []),
  // viser vi en placeholder-bullet så sektionen ikke forsvinder fra UI'et.
  const begrundelser =
    info.match_begrundelse && info.match_begrundelse.length > 0
      ? info.match_begrundelse
      : [t("match.placeholder_ingen_begrundelse")];
  // De første ~3 sider. PDF'er pakkes uden form-feed-markører, så vi
  // bruger en char-baseret heuristik: 3500 tegn ≈ én A4-side med
  // juridisk pakkerejse-formatering. 10500 tegn ≈ 3 sider.
  const TRE_SIDER_TEGN = 10500;
  const raaTekst = (sag.indhold ?? "").slice(0, TRE_SIDER_TEGN);
  const harMere = (sag.indhold?.length ?? 0) > TRE_SIDER_TEGN;

  return (
    <div className="rounded-md border border-zinc-200 bg-white">
      <div className="flex items-start gap-3 p-4">
        <div className="flex-1 space-y-1">
          <p className="text-sm font-semibold text-zinc-900">
            {index}. {t("match.label_sagsnummer_prefix")} {sagsnummer}
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

      <button
        type="button"
        onClick={() => sætAaben((v) => !v)}
        className="w-full border-t border-zinc-100 px-4 py-2 text-left text-xs font-medium text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900"
      >
        {aaben ? t("match.knap_skjul_detaljer") : t("match.knap_se_hvorfor")}
      </button>

      {aaben && (
        <div className="space-y-4 border-t border-zinc-100 bg-zinc-50 px-4 py-4">
          {/* Beløb-sektion vises altid når kortet er åbent. Defaulter til
              'ukendt' hvis hverken AI eller regex-fallback fandt beløbene
              i den specifikke afgørelse. */}
          <div>
            <p className="text-xs font-semibold text-zinc-700 uppercase tracking-wide mb-2">
              {t("match.label_beloeb")}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs text-zinc-500 mb-1">
                  {t("match.label_klageren_kraevede")}
                </p>
                <p className="text-lg font-semibold text-zinc-900">
                  {klagersKrav}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500 mb-1">
                  {t("match.label_naevnet_tilkendte")}
                </p>
                <p className="text-lg font-semibold text-zinc-900">
                  {tilkendt}
                </p>
              </div>
            </div>
          </div>

          {/* Match-begrundelse vises altid — har minimum én placeholder-
              bullet hvis backend ikke kunne udlede konkrete begrundelser. */}
          <div>
            <p className="text-xs font-semibold text-zinc-700 uppercase tracking-wide mb-2">
              {t("match.label_hvorfor_match")}
            </p>
            <ul className="space-y-1 text-sm text-zinc-700 list-disc pl-5">
              {begrundelser.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          </div>

          {raaTekst && (
            <div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => sætVisRaaTekst((v) => !v)}
              >
                {visRaaTekst
                  ? t("match.knap_skjul_afgoerelse")
                  : t("match.knap_se_uddrag")}
              </Button>
              {visRaaTekst && (
                <div className="mt-3">
                  <AfgoerelseFormateret
                    tekst={raaTekst}
                    harMere={harMere}
                    sagsnummerFallback={sagsnummer}
                  />
                </div>
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
              {t("match.link_aabn_original")}
            </a>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────── Hoved-komponent ───────────

// ─────────── Eksport-knapper (DOCX / PDF) ───────────
//
// Streamlit-PAX lader brugeren downloade selve analysens tekst som
// Word eller PDF. Vi kalder /api/analyse-eksport med markdown-rendering
// af analyse-sektionerne (samme rekonstruktion som FastAPI's
// foerstevurdering bygger til sagsresumé-kaldet).

function base64TilBlob(b64: string, mime: string): Blob {
  const byteString = atob(b64);
  const arr = new Uint8Array(byteString.length);
  for (let i = 0; i < byteString.length; i++) {
    arr[i] = byteString.charCodeAt(i);
  }
  return new Blob([arr], { type: mime });
}

// Saml hele analysen til markdown. Holder rækkefølge og sektion-
// overskrifter ensartet med Streamlit-PAX (forside.py's
// analyse-archive-rendering) — så Word/PDF-eksport ligner det brugeren
// har set i UI'et.
type TFunc = (noegle: string, args?: Record<string, string | number>) => string;

function byggAnalyseMarkdown(
  data: FoerstevurderingsRespons,
  t: TFunc,
): string {
  const a = data.analyse;
  const s = a.sandsynlighedsvurdering ?? {};
  const dele: string[] = [];

  if (a.konklusion_en_linje) {
    dele.push(`## ${t("eksport.konklusion")}\n\n${a.konklusion_en_linje}`);
  }

  if (
    typeof s.fuld_medhold_til_klager === "number" ||
    typeof s.delvist_medhold_til_klager === "number" ||
    typeof s.afvisning_af_klagen === "number"
  ) {
    dele.push(
      `## ${t("eksport.sandsynlighedsvurdering")}\n\n` +
        `- ${t("eksport.linje_fuld_medhold")}: ${s.fuld_medhold_til_klager ?? 0}%\n` +
        `- ${t("eksport.linje_delvist_medhold")}: ${s.delvist_medhold_til_klager ?? 0}%\n` +
        `- ${t("eksport.linje_afvisning")}: ${s.afvisning_af_klagen ?? 0}%` +
        (s.begrundelse ? `\n\n${s.begrundelse}` : ""),
    );
  }

  if (data.sagsresume) {
    const r = data.sagsresume;
    const linjer: string[] = [`## ${t("eksport.resume")}`];
    if (r.emne) linjer.push(`\n${r.emne}`);
    if (r.klagepunkter && r.klagepunkter.length) {
      linjer.push(`\n**${t("eksport.klagepunkter")}:**`);
      for (const k of r.klagepunkter) linjer.push(`- ${k}`);
    }
    if (r.krav) linjer.push(`\n**${t("eksport.klagers_krav")}:** ${r.krav}`);
    if (r.tui_handtering)
      linjer.push(`\n**${t("eksport.selskabets_handtering")}:** ${r.tui_handtering}`);
    if (r.forventet_udfald)
      linjer.push(`\n**${t("eksport.forventet_udfald")}:** ${r.forventet_udfald}`);
    dele.push(linjer.join("\n"));
  }

  if (a.klagens_kernepunkter && a.klagens_kernepunkter.length) {
    dele.push(
      `## ${t("eksport.klagens_kernepunkter")}\n\n` +
        a.klagens_kernepunkter.map((p) => `- ${p}`).join("\n"),
    );
  }

  if (a.yderligere_klagepunkter_og_detaljer && a.yderligere_klagepunkter_og_detaljer.length) {
    dele.push(
      `## ${t("eksport.yderligere_klagepunkter")}\n\n` +
        a.yderligere_klagepunkter_og_detaljer.map((p) => `- ${p}`).join("\n"),
    );
  }

  if (a.rejseselskabets_stillingtagen_indtil_nu) {
    dele.push(
      `## ${t("eksport.stillingtagen")}\n\n` +
        a.rejseselskabets_stillingtagen_indtil_nu,
    );
  }

  if (a.kort_juridisk_vurdering) {
    dele.push(`## ${t("eksport.juridisk_vurdering")}\n\n${a.kort_juridisk_vurdering}`);
  }

  // Tidsforhold sidst — det er ofte vigtig kontekst men ikke kernen
  const tf = data.tidsforhold;
  if (tf && !tf.kunne_ikke_udledes && tf.samlet_vurdering) {
    const tfDele = [`## ${t("eksport.tidsforhold")}\n\n${tf.samlet_vurdering}`];
    if (tf.rejseperiode) {
      tfDele.push(
        `\n**${t("eksport.rejseperiode")}:** ${tf.rejseperiode}` +
          (tf.antal_naetter && tf.antal_naetter >= 1
            ? ` (${t("eksport.naetter", { antal: tf.antal_naetter })})`
            : ""),
      );
    }
    if (tf.konkrete_observationer && tf.konkrete_observationer.length) {
      tfDele.push(
        `\n**${t("eksport.konkrete_observationer")}:**\n` +
          tf.konkrete_observationer.map((o) => `- ${o}`).join("\n"),
      );
    }
    dele.push(tfDele.join("\n"));
  }

  return dele.join("\n\n");
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function EksportKnapper({ data }: { data: FoerstevurderingsRespons }) {
  const t = useT();
  const [docxPending, startDocx] = useTransition();
  const [pdfPending, startPdf] = useTransition();

  function eksportér(format: "docx" | "pdf") {
    const markdown = byggAnalyseMarkdown(data, t);
    if (!markdown.trim()) {
      toast.error(t("resultat.toast_intet_indhold"));
      return;
    }

    const runner = format === "docx" ? startDocx : startPdf;
    runner(async () => {
      try {
        const resp = await postJsonOgValider(
          "/api/analyse-eksport",
          analyseEksportSchema,
          { markdown, format },
          { retries: 2 },
        );
        const blob = base64TilBlob(resp.base64, resp.mime);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = resp.filnavn;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success(
          format === "docx"
            ? t("resultat.toast_analyse_word")
            : t("resultat.toast_analyse_pdf"),
        );
      } catch (e) {
        if (e instanceof ApiError) {
          toast.error(
            e.detalje ? `${e.message}: ${e.detalje.slice(0, 100)}` : e.message,
          );
        } else {
          toast.error(
            t("resultat.toast_uventet_fejl", {
              besked: e instanceof Error ? e.message : t("resultat.ukendt"),
            }),
          );
        }
      }
    });
  }

  return (
    <div className="flex flex-wrap gap-2 pt-2 border-t border-zinc-200">
      <Button
        variant="outline"
        size="sm"
        onClick={() => eksportér("docx")}
        disabled={docxPending || pdfPending}
      >
        {docxPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <FileText className="h-4 w-4" />
        )}
        {t("resultat.knap_download_word")}
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={() => eksportér("pdf")}
        disabled={docxPending || pdfPending}
      >
        {pdfPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <FileDown className="h-4 w-4" />
        )}
        {t("resultat.knap_download_pdf")}
      </Button>
    </div>
  );
}


export function AnalyseResultat({
  data,
}: {
  data: FoerstevurderingsRespons;
}) {
  const t = useT();
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
        <Pillar farve="sky" nummer={1} titel={t("resultat.pillar_resume")}>
          <div className="space-y-4">
            {sagsresume.emne && (
              <p className="text-sm sm:text-base text-zinc-800 leading-relaxed">
                {renderTekstMedBilagPiller(sagsresume.emne)}
              </p>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-2xl bg-white/70 border border-white p-4">
                <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2 font-medium">
                  {t("resultat.label_klagepunkter")}
                </p>
                {sagsresume.klagepunkter && sagsresume.klagepunkter.length > 0 ? (
                  <ul className="list-disc pl-5 space-y-1 text-sm text-zinc-800">
                    {sagsresume.klagepunkter.map((k, i) => (
                      <li key={i}>{k}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-zinc-500 italic">
                    {t("resultat.ingen_klagepunkter")}
                  </p>
                )}
              </div>
              <div className="rounded-2xl bg-white/70 border border-white p-4">
                <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2 font-medium">
                  {t("resultat.label_klagers_krav")}
                </p>
                <p className="text-sm text-zinc-800 leading-relaxed">
                  {sagsresume.krav || "—"}
                </p>
              </div>
            </div>
            <div className="rounded-xl border-l-4 border-amber-500 bg-white/70 px-4 py-3 text-sm text-zinc-900 space-y-2">
              <p className="text-[0.65rem] uppercase tracking-wider text-zinc-500">
                {t("resultat.label_sandsynlighedsvurdering")}
              </p>
              <p className="text-sm sm:text-base text-zinc-800 leading-relaxed">
                <strong>{t("resultat.label_fuld_medhold_kort")}</strong>{" "}
                {s.fuld_medhold_til_klager ?? 0}%{" "}
                <strong className="ml-2">{t("resultat.label_delvist_medhold_kort")}</strong>{" "}
                {s.delvist_medhold_til_klager ?? 0}%{" "}
                <strong className="ml-2">{t("resultat.label_afvisning_kort")}</strong>{" "}
                {s.afvisning_af_klagen ?? 0}%
              </p>
              {s.begrundelse && (
                <p className="text-sm text-zinc-800 leading-relaxed">
                  {renderTekstMedBilagPiller(s.begrundelse)}
                </p>
              )}
            </div>
          </div>
        </Pillar>
      )}

      {/* 2. Tidsforhold og rettidig kommunikation */}
      {(() => {
        const tf = data.tidsforhold;
        if (!tf || tf.kunne_ikke_udledes) return null;
        const begivenheder = tf.begivenheder ?? [];
        const observationer = tf.konkrete_observationer ?? [];
        const harIndhold =
          begivenheder.length > 0 ||
          observationer.length > 0 ||
          !!tf.samlet_vurdering;
        if (!harIndhold) return null;

        const introTekst = tf.har_problematisk_forsinkelse
          ? t("resultat.tidsforhold_intro_problematisk")
          : t("resultat.tidsforhold_intro_neutral");

        return (
          <Pillar
            farve="amber"
            nummer={2}
            titel={t("resultat.pillar_tidsforhold")}
            beskrivelse={introTekst}
          >
            <div className="space-y-4">
              {tf.samlet_vurdering && (
                <p className="text-sm sm:text-base text-zinc-800 leading-relaxed">
                  {renderTekstMedBilagPiller(tf.samlet_vurdering)}
                </p>
              )}

              {tf.rejseperiode && (
                <div className="inline-block rounded-full border border-amber-700/30 bg-white/60 px-4 py-1.5 text-sm">
                  <span className="font-semibold text-amber-900">
                    {t("resultat.tidsforhold_rejseperiode")}
                  </span>{" "}
                  <span className="text-amber-900">
                    {renderTekstMedBilagPiller(tf.rejseperiode)}
                    {tf.antal_naetter && tf.antal_naetter >= 1 && (
                      <> ({t("resultat.tidsforhold_naetter", { antal: tf.antal_naetter })})</>
                    )}
                  </span>
                </div>
              )}

              {begivenheder.length > 0 ? (
                <Tidslinje begivenheder={begivenheder} />
              ) : (
                observationer.length > 0 && (
                  <ul className="list-disc pl-5 space-y-1 text-sm text-zinc-800">
                    {observationer.map((o, i) => (
                      <li key={i}>{renderTekstMedBilagPiller(o)}</li>
                    ))}
                  </ul>
                )
              )}
            </div>
          </Pillar>
        );
      })()}

      {/* 3. Klagens kernepunkter */}
      {a.klagens_kernepunkter && a.klagens_kernepunkter.length > 0 && (
        <Pillar farve="rose" nummer={3} titel={t("resultat.pillar_klagens_kernepunkter")}>
          <ul className="space-y-2 list-disc pl-5">
            {a.klagens_kernepunkter.map((punkt, i) => (
              <KlagepunktItem key={i} punkt={punkt} />
            ))}
          </ul>
        </Pillar>
      )}

      {/* 4. Yderligere klagepunkter */}
      {a.yderligere_klagepunkter_og_detaljer &&
        a.yderligere_klagepunkter_og_detaljer.length > 0 && (
          <Pillar farve="lavender" nummer={4} titel={t("resultat.pillar_yderligere_klagepunkter")}>
            <ul className="space-y-2 list-disc pl-5">
              {a.yderligere_klagepunkter_og_detaljer.map((punkt, i) => (
                <KlagepunktItem key={i} punkt={punkt} />
              ))}
            </ul>
          </Pillar>
        )}

      {/* 5. Rejseselskabets stillingtagen */}
      {a.rejseselskabets_stillingtagen_indtil_nu && (
        <Pillar farve="blue" nummer={5} titel={t("resultat.pillar_stillingtagen")}>
          {renderTekstMedAfsnit(a.rejseselskabets_stillingtagen_indtil_nu)}
        </Pillar>
      )}

      {/* 6. Kort juridisk vurdering */}
      {a.kort_juridisk_vurdering && (
        <Pillar farve="emerald" nummer={6} titel={t("resultat.pillar_juridisk_vurdering")}>
          {renderTekstMedAfsnit(a.kort_juridisk_vurdering)}
        </Pillar>
      )}

      {/* 7. Relevante tidligere afgørelser */}
      {data.relevante_sager && data.relevante_sager.length > 0 && (
        <Pillar
          farve="slate"
          nummer={7}
          titel={t("resultat.pillar_relevante_afgoerelser")}
          beskrivelse={t("resultat.pillar_relevante_afgoerelser_beskrivelse")}
        >
          <div className="space-y-3">
            {data.match_kvalitet === "begrænset" && (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <p className="font-medium mb-0.5">
                  {t("resultat.match_begraenset_titel")}
                </p>
                <p className="text-amber-800">
                  {t("resultat.match_begraenset_beskrivelse")}
                </p>
              </div>
            )}
            {data.relevante_sager.map((sag, i) => (
              <RelevantSagKort
                key={i}
                index={i + 1}
                sag={sag}
                info={matchInfo[i] ?? {}}
              />
            ))}
          </div>
        </Pillar>
      )}

      {/* 8. Konklusion */}
      {a.konklusion_en_linje && (
        <Pillar farve="teal" nummer={8} titel={t("resultat.pillar_konklusion")}>
          <p className="text-sm sm:text-base text-zinc-900 leading-relaxed font-medium">
            {renderTekstMedBilagPiller(a.konklusion_en_linje)}
          </p>
        </Pillar>
      )}

      {/* Verificeret klagepunkt-liste og analyse-eksport-knapper
          FJERNET — vi vil ikke have download/listevisning af klagepunkter
          her; det hører til i svarbrev/tjekliste-flowet. */}
    </div>
  );
}
