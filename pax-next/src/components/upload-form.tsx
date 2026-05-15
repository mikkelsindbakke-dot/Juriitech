"use client";

import { useState, useTransition, useEffect, useMemo } from "react";
import { Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pillar } from "@/components/ui/pillar";
import { toast } from "sonner";
import {
  AnalyseResultat,
  type FoerstevurderingsRespons,
} from "@/components/analyse-resultat";
import {
  ApiError,
  foerstevurderingSchema,
  kørAnalyseJob,
} from "@/lib/api-client";
import { useFejlBesked, useIsAdmin, VENLIG_FEJL } from "@/lib/bruger-rolle";
import { useT } from "@/lib/i18n/client";
import { SvarbrevSektion } from "@/components/svarbrev-sektion";
import { AnonymiserSektion } from "@/components/anonymiser-sektion";
import { TjeklisteSektion } from "@/components/tjekliste-sektion";
import { SagsakterSektion } from "@/components/sagsakter-sektion";
import {
  BilagTilSvarbrevSektion,
  bilagValgTilListe,
  type BilagValg,
} from "@/components/bilag-til-svarbrev-sektion";
import { udpak_zips_klient } from "@/lib/zip-udpakning";

function formatStr(antalBytes: number): string {
  if (antalBytes < 1024) return `${antalBytes} B`;
  if (antalBytes < 1024 * 1024) return `${(antalBytes / 1024).toFixed(1)} kB`;
  return `${(antalBytes / 1024 / 1024).toFixed(1)} MB`;
}

// Aktivitets-indikator: faseopdelt liste der viser hvad PAX arbejder
// på lige nu. Hver fase har en estimeret varighed der matcher den
// faktiske pipeline (parse → klagepunkter → tidsforhold → RAG →
// førstevurdering → resumé). Vi har ikke real-time signal fra backend,
// så timeren er et ærligt ESTIMAT — den sidste fase forbliver "aktiv"
// hvis backenden tager længere end forventet, og hele komponenten
// unmoountes når analysen er færdig (parent gater på analysePending).
//
// Renderes kun mens analysen kører.

// Varighedsestimater pr. fase. Labels/beskrivelser oversættes via t()
// inde i komponenten — kun durations holdes konstant.
const ANALYSE_FASE_DURATIONS_MS: ReadonlyArray<number> = [
  8000,
  15000,
  20000,
  5000,
  35000,
  60000, // bevidst lang så sidste fase persisterer ved længere kørsler
];

function formaterMmSs(sekunder: number) {
  const m = Math.floor(sekunder / 60);
  const s = sekunder % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function AnalyseProgress() {
  const t = useT();
  const [aktivIdx, sætAktivIdx] = useState(0);
  const [elapsedSek, sætElapsedSek] = useState(0);

  // Byg lokaliseret faseliste — labels/beskrivelser ud fra t() med
  // durations fra konstant-arrayet.
  const faser = useMemo(
    () =>
      ANALYSE_FASE_DURATIONS_MS.map((durationMs, i) => ({
        label: t(`analyse_progress.fase${i + 1}_label`),
        beskrivelse: t(`analyse_progress.fase${i + 1}_beskrivelse`),
        durationMs,
      })),
    [t],
  );

  // Avancer gennem faserne på cumulative tid. Bruger setTimeout-kæde
  // i stedet for én lang interval-loop så vi ikke skal regne tid
  // tilbage hver tick.
  useEffect(() => {
    const timeouts: ReturnType<typeof setTimeout>[] = [];
    let cumulativeMs = 0;
    for (let i = 0; i < ANALYSE_FASE_DURATIONS_MS.length - 1; i++) {
      cumulativeMs += ANALYSE_FASE_DURATIONS_MS[i];
      const tid = setTimeout(() => sætAktivIdx(i + 1), cumulativeMs);
      timeouts.push(tid);
    }
    return () => timeouts.forEach(clearTimeout);
  }, []);

  // Sekund-counter til den lille mm:ss-badge i hjørnet
  useEffect(() => {
    const id = setInterval(() => sætElapsedSek((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-5 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-indigo-900">
            {t("analyse_progress.titel")}
          </p>
          <p className="text-xs text-indigo-700 mt-0.5 max-w-md">
            {t("analyse_progress.undertekst")}
          </p>
        </div>
        <div
          className="text-xs font-mono tabular-nums text-indigo-700/80 bg-white/60 rounded-full px-2.5 py-0.5 border border-indigo-200/60"
          aria-label={t("analyse_progress.aria_forloebet_tid")}
        >
          {formaterMmSs(elapsedSek)}
        </div>
      </div>

      {/* Faseliste — vertikal med konnektor-linje mellem prikkerne.
          Brug 'role=list' så skærmlæsere ser det som en sekventiel
          liste over arbejdstrin. */}
      <ol className="relative space-y-3" aria-live="polite">
        {/* Vertikal forbindelseslinje gennem alle prikkene */}
        <div
          className="absolute left-[9px] top-2 bottom-2 w-px bg-indigo-200/70"
          aria-hidden
        />
        {faser.map((fase, i) => {
          const tilstand =
            i < aktivIdx ? "done" : i === aktivIdx ? "active" : "pending";
          return (
            <li
              key={i}
              className="relative flex items-start gap-3"
            >
              {/* Status-prik */}
              <div className="relative z-10 mt-0.5 shrink-0">
                {tilstand === "done" && (
                  <div className="h-[18px] w-[18px] rounded-full bg-emerald-500 flex items-center justify-center shadow-sm">
                    <Check
                      className="h-[11px] w-[11px] text-white"
                      strokeWidth={3}
                    />
                  </div>
                )}
                {tilstand === "active" && (
                  <div className="h-[18px] w-[18px] rounded-full bg-indigo-100 ring-2 ring-indigo-500 flex items-center justify-center">
                    <Loader2 className="h-[11px] w-[11px] text-indigo-600 animate-spin" />
                  </div>
                )}
                {tilstand === "pending" && (
                  <div className="h-[18px] w-[18px] rounded-full border-2 border-zinc-300 bg-white" />
                )}
              </div>

              {/* Tekst */}
              <div className="flex-1 min-w-0 pt-0.5">
                <p
                  className={`text-sm font-medium leading-tight ${
                    tilstand === "active"
                      ? "text-indigo-900"
                      : tilstand === "done"
                      ? "text-zinc-700"
                      : "text-zinc-400"
                  }`}
                >
                  {fase.label}
                </p>
                <p
                  className={`text-xs leading-snug mt-0.5 ${
                    tilstand === "active"
                      ? "text-indigo-700"
                      : tilstand === "done"
                      ? "text-zinc-500"
                      : "text-zinc-400"
                  }`}
                >
                  {fase.beskrivelse}
                </p>
              </div>
            </li>
          );
        })}
      </ol>

      {/* Subtil aktivitets-bjælke nederst — viser at noget hele tiden
          sker, selv hvis fase-indikatoren venter på næste fase. */}
      <div className="h-1 w-full overflow-hidden rounded-full bg-indigo-100">
        <div
          className="h-full w-full bg-gradient-to-r from-indigo-500 via-violet-500 via-sky-500 to-indigo-500 bg-[length:200%_100%]"
          style={{
            animation: "pax-pulse 1.8s ease-in-out infinite",
            backgroundSize: "200% 100%",
          }}
        />
      </div>
      <style>{`
        @keyframes pax-pulse {
          0%   { background-position:   0% 50%; opacity: 0.85; }
          50%  { background-position: 100% 50%; opacity: 1; }
          100% { background-position:   0% 50%; opacity: 0.85; }
        }
      `}</style>
    </div>
  );
}

type AnalyseFejl = { besked: string; detalje?: string; status?: number };

export function UploadForm() {
  const t = useT();
  const isAdmin = useIsAdmin();
  const formatFejl = useFejlBesked();
  const [analysePending, startAnalyseTransition] = useTransition();
  const [analyse, sætAnalyse] = useState<FoerstevurderingsRespons | null>(
    null,
  );
  const [valgteFiler, sætValgteFiler] = useState<File[]>([]);

  // Persistent fejl-state — vises som banner i stedet for at forsvinde
  // som toast. Brugeren skal vide hvad der gik galt og kunne prøve igen
  // uden at miste filerne.
  const [analyseFejl, sætAnalyseFejl] = useState<AnalyseFejl | null>(null);

  // Hvilken knap der trigger-scannede sagen — bruges til at vise
  // progress-UI'et lige under den knap brugeren faktisk klikkede på.
  // "initial" = øverste Scan-knap, "genscan" = knappen nederst i
  // sagsakter-sektionen (sektion 9). Uden dette ville rescan trigge
  // progress højt oppe på siden og brugeren ville tro intet sker.
  const [scanKilde, sætScanKilde] = useState<"initial" | "genscan">("initial");

  // Sektion 11: Bilag til svarbrevet (letter assignment + reorder).
  const [bilagStartBogstav, sætBilagStartBogstav] = useState("A");
  const [bilagValg, sætBilagValg] = useState<BilagValg[]>([]);

  // Advar brugeren hvis de prøver at lukke siden mens analysen kører —
  // ellers kan de tro de blev "smidt tilbage" til upload (i virkeligheden
  // bare en page-refresh der dræbte fetch'en).
  useEffect(() => {
    if (!analysePending) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = t("upload.beforeunload_advarsel");
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [analysePending, t]);

  // Klient-side ZIP-udpakning: hvis brugeren uploader en .zip, pakker
  // vi den ud i browseren og fanout'er filerne så Sagsakter-sektionen,
  // Anonymisér-sektionen osv. viser hver enkelt fil — ikke bare zippen
  // som ÉN entry. Media-filer (mp4/mp3 osv.) skippes med toast så
  // brugeren ved at de ikke indgår i analysen.
  async function ekspander_zips_og_meld(filer: File[]): Promise<File[]> {
    const r = await udpak_zips_klient(filer);
    for (const f of r.fejl) {
      toast.error(`${f.filnavn}: ${f.besked}`);
    }
    if (r.skipped_media.length > 0) {
      const liste = r.skipped_media.slice(0, 5).join(", ");
      const rest =
        r.skipped_media.length > 5
          ? ` (+${r.skipped_media.length - 5} flere)`
          : "";
      toast.info(
        `${r.skipped_media.length} medie-${r.skipped_media.length === 1 ? "fil" : "filer"} sprunget over: ${liste}${rest}. PAX analyserer ikke video/lyd.`,
      );
    }
    return r.filer;
  }

  function håndterFilValg(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = Array.from(e.target.files ?? []);
    e.target.value = ""; // tillad samme fil at blive valgt igen senere
    if (raw.length === 0) return;
    sætAnalyse(null);
    sætAnalyseFejl(null);
    sætBilagValg([]); // ny fil-set → reset bilag-valg
    void (async () => {
      const ekspanderet = await ekspander_zips_og_meld(raw);
      sætValgteFiler(ekspanderet);
    })();
  }

  // Tilføj flere filer (fra sagsakter-sektionen) uden at nulstille
  // den eksisterende sagsstand. Filerne lægges blot i hat-listen,
  // og brugeren kan re-scanne med "Scan igen".
  function tilfoejFiler(nyeFiler: File[]) {
    if (nyeFiler.length === 0) return;
    void (async () => {
      const ekspanderet = await ekspander_zips_og_meld(nyeFiler);
      if (ekspanderet.length === 0) return;
      sætValgteFiler((prev) => {
        const eksisterendeNavne = new Set(prev.map((f) => f.name));
        const tilfoejet = ekspanderet.filter(
          (f) => !eksisterendeNavne.has(f.name),
        );
        return [...prev, ...tilfoejet];
      });
      sætBilagValg([]); // bilag-listen skal regenereres med nye filer
    })();
  }

  function håndterAnalyse(kilde: "initial" | "genscan" = "initial") {
    if (valgteFiler.length === 0) {
      toast.error(t("upload.fejl_vaelg_fil_foerst"));
      return;
    }
    sætAnalyseFejl(null); // ryd evt. tidligere fejl
    sætScanKilde(kilde);
    startAnalyseTransition(async () => {
      const formData = new FormData();
      for (const fil of valgteFiler) formData.append("filer", fil);
      try {
        // kørAnalyseJob håndterer hele async-flowet:
        //   1. POST /api/jobs/foerstevurdering → får job_id
        //   2. Poll /api/jobs/[id] hver 3 sek
        //   3. Returnerer resultat når status === completed
        //   4. Kaster ApiError ved fail/timeout
        // Idempotent — samme input inden for 1 time genbruger job.
        const data = (await kørAnalyseJob(
          formData,
          foerstevurderingSchema,
          {
            onStatusChange: (status) => {
              // Kan hookes hvis vi vil vise "I kø..." vs "Analyserer..."
              console.debug("[foerstevurdering] status →", status);
            },
          },
        )) as FoerstevurderingsRespons;
        sætAnalyse(data);
        sætAnalyseFejl(null);
        toast.success(
          t("upload.toast_analyse_faerdig", {
            klagepunkter: data.metadata.antal_klagepunkter,
            matches: data.metadata.antal_relevante_sager,
          }),
        );
      } catch (e) {
        const fejl: AnalyseFejl =
          e instanceof ApiError
            ? {
                besked: e.message,
                detalje: e.detalje,
                status: e.status,
              }
            : {
                besked: t("upload.fejl_uventet_analyse"),
                detalje: e instanceof Error ? e.message : String(e),
              };
        console.error("[foerstevurdering]", fejl);
        sætAnalyseFejl(fejl);
        toast.error(formatFejl(e));
      }
    });
  }

  // Bygger bilag-listen der sendes til /api/svarbrev så Word-filen får
  // den korrekte bilag-oversigt nederst.
  const bilagListeTilDocx = bilagValgTilListe(bilagValg, bilagStartBogstav);

  // Tilbyd "Scan igen" hvis analyse allerede er kørt — så brugeren
  // kan re-køre efter at have tilføjet flere filer i sagsakter-sektionen.
  const harTidligereAnalyse = analyse !== null;

  return (
    <div className="space-y-6">
      {/* Fil-vælger */}
      <div className="space-y-3">
        <label
          htmlFor="filer-input"
          className="block w-full cursor-pointer rounded-lg border-2 border-dashed border-zinc-300 bg-zinc-50 p-8 text-center hover:border-zinc-400 hover:bg-zinc-100 transition-colors"
        >
          <div className="text-sm text-zinc-600">
            <span className="font-medium text-zinc-900">
              {t("upload.filvaelger_klik")}
            </span>
            <span className="block mt-1 text-xs">
              {t("upload.filvaelger_traek")}
            </span>
          </div>
          <input
            id="filer-input"
            type="file"
            multiple
            accept=".pdf,.docx,.png,.jpg,.jpeg,.zip"
            onChange={håndterFilValg}
            className="sr-only"
          />
        </label>

        {valgteFiler.length > 0 && (
          <div className="rounded-md bg-zinc-50 p-3 text-xs">
            <p className="font-medium text-zinc-900 mb-1">
              {valgteFiler.length === 1
                ? t("upload.filer_valgt_en")
                : t("upload.filer_valgt_flere", { antal: valgteFiler.length })}
            </p>
            <ul className="space-y-0.5 text-zinc-700">
              {valgteFiler.map((f, i) => (
                <li key={i}>
                  · {f.name}{" "}
                  <span className="text-zinc-500">({formatStr(f.size)})</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Én stor Scan-knap. Parse-preview er fjernet — brugeren skal
          ikke vælge mellem hurtig fil-tjek og AI-analyse, de vil bare
          scanne sagen og komme videre. */}
      <Button
        type="button"
        size="lg"
        onClick={() => håndterAnalyse("initial")}
        disabled={analysePending || valgteFiler.length === 0}
        className="w-full h-14 text-base bg-indigo-500 hover:bg-indigo-600 text-white"
      >
        {analysePending
          ? t("upload.knap_scanner")
          : harTidligereAnalyse
          ? t("upload.knap_scan_igen")
          : t("upload.knap_scan_filer")}
      </Button>

      {/* Progress-linje med trin der animerer mens analysen kører.
          Vises KUN her hvis brugeren klikkede på den øverste scan-knap —
          ellers står den nederst ved genscan-knappen i sektion 9. */}
      {analysePending && scanKilde === "initial" && <AnalyseProgress />}

      {/* Persistent fejl-banner — vises hvis API-kaldet fejlede.
          Forsvinder ikke som toast, og giver brugeren en retry-knap så
          filerne ikke skal genvælges. */}
      {analyseFejl && !analysePending && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-4 space-y-3">
          <div className="flex items-start gap-3">
            <span className="text-lg leading-none">⚠</span>
            <div className="flex-1 space-y-1">
              <p className="text-sm font-semibold text-amber-900">
                {t("upload.fejl_banner_titel")}
              </p>
              {isAdmin ? (
                <>
                  <p className="text-sm text-amber-800">{analyseFejl.besked}</p>
                  {analyseFejl.detalje && (
                    <details className="text-xs text-amber-700">
                      <summary className="cursor-pointer hover:text-amber-900">
                        {t("upload.fejl_tekniske_detaljer")}
                      </summary>
                      <pre className="mt-1 whitespace-pre-wrap font-mono">
                        {analyseFejl.detalje}
                      </pre>
                    </details>
                  )}
                  {analyseFejl.status && analyseFejl.status >= 500 && (
                    <p className="text-xs text-amber-700 italic">
                      {t("upload.fejl_5xx_forklaring")}
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-amber-800">{VENLIG_FEJL}</p>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => håndterAnalyse("initial")}
              disabled={valgteFiler.length === 0}
            >
              {t("upload.knap_proev_igen")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => sætAnalyseFejl(null)}
            >
              {t("upload.knap_luk")}
            </Button>
          </div>
        </div>
      )}

      {/* Info-besked: filer som ikke kunne læses (krypterede zip-entries,
          ikke-understøttede formater m.v.). Analysen fortsætter med de
          øvrige filer — denne boks er bare så brugeren ved hvad der blev
          sprunget over. Diskret zinc-farve, ikke rød/alarmagtig. */}
      {analyse &&
        analyse.ulaeselige_filer &&
        analyse.ulaeselige_filer.length > 0 && (
          <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-700">
            <p className="font-medium mb-1">
              {analyse.ulaeselige_filer.length === 1
                ? t("upload.ulaeselig_en_fil")
                : t("upload.ulaeselig_flere_filer", {
                    antal: analyse.ulaeselige_filer.length,
                  })}
            </p>
            <ul className="list-disc pl-5 space-y-0.5 text-xs text-zinc-600">
              {analyse.ulaeselige_filer.map((f) => (
                <li key={f.filnavn}>
                  <span className="font-medium">{f.filnavn}</span>
                  {f.aarsag ? ` — ${f.aarsag}` : null}
                </li>
              ))}
            </ul>
          </div>
        )}

      {/* Admin-only: advarsel om paragraf-hallucinations. Vises kun til
          admin (juriitech) så vi kan bemærke at AI'en har citeret en
          §-reference der ikke findes i pakkerejseloven. Brugere ser
          aldrig denne — de skal aldrig blive forvirrede over juridiske
          metavalideringer. */}
      {isAdmin &&
        analyse &&
        analyse.paragraf_advarsler &&
        analyse.paragraf_advarsler.length > 0 && (
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            <p className="font-medium mb-1">
              {t("upload.admin_paragraf_advarsel_titel")}
            </p>
            <p className="text-xs text-amber-800">
              {t("upload.admin_paragraf_advarsel_beskrivelse")}{" "}
              <span className="font-mono">
                {analyse.paragraf_advarsler.join(", ")}
              </span>
            </p>
          </div>
        )}

      {/* Analyse-resultat */}
      {analyse && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold tracking-tight border-t border-zinc-200 pt-4">
            {t("upload.foerstevurdering_titel")}
          </h2>
          <AnalyseResultat data={analyse} />
        </div>
      )}

      {/* Sektion 9-13 vises FØRST når analysen er kørt — ellers kan
          brugeren risikere at udfylde sagsakter, vælge bilag osv.
          før der er noget at re-analysere imod.

          Hver sektion får en farvet Apple Health-pillar som "header"
          (titel + beskrivelse) over selve form-indholdet. */}

      {/* Sektion 9: Sagsakter */}
      {analyse && (
        <div className="space-y-4">
          <Pillar
            farve="lavender"
            nummer={9}
            titel={t("upload.sektion9_titel")}
            beskrivelse={t("upload.sektion9_beskrivelse")}
          />
          <SagsakterSektion
            onFilerTilfoejet={tilfoejFiler}
            filer={valgteFiler}
            disabled={analysePending}
          />
          {/* Genscan-knap placeret HER så brugeren ikke skal scrolle op
              til hoved-Scan-knappen efter at have tilføjet sagsakter. */}
          <Button
            type="button"
            size="lg"
            onClick={() => håndterAnalyse("genscan")}
            disabled={analysePending || valgteFiler.length === 0}
            className="w-full h-14 text-base bg-indigo-500 hover:bg-indigo-600 text-white"
          >
            {analysePending && scanKilde === "genscan"
              ? t("upload.knap_scanner")
              : t("upload.knap_scan_igen_med_nye")}
          </Button>
          {/* Progress-UI lige under DEN her knap når det er rescan'en der
              kører — så brugeren får visuel feedback præcis hvor de
              klikkede i stedet for at progress-bjælken dukker op højt
              oppe på siden ved den oprindelige Scan-knap. */}
          {analysePending && scanKilde === "genscan" && <AnalyseProgress />}
        </div>
      )}

      {/* Anonymiser-sektion (10) */}
      {analyse && (
        <div className="space-y-4">
          <Pillar
            farve="rose"
            nummer={10}
            titel={t("upload.sektion10_titel")}
            beskrivelse={
              <>
                {t("upload.sektion10_beskrivelse_for")}
                <strong className="text-zinc-900">
                  {" "}
                  {t("upload.sektion10_beskrivelse_strong")}
                </strong>
                {t("upload.sektion10_beskrivelse_efter")}
                <br />
                <br />
                {t("upload.sektion10_beskrivelse_klager")}
              </>
            }
          />
          <AnonymiserSektion filer={valgteFiler} />
        </div>
      )}

      {/* Sektion 11: Bilag til svarbrevet */}
      {analyse && (
        <div className="space-y-4">
          <Pillar
            farve="amber"
            nummer={11}
            titel={t("upload.sektion11_titel")}
            beskrivelse={t("upload.sektion11_beskrivelse")}
          />
          <BilagTilSvarbrevSektion
            filer={valgteFiler.map((f) => ({ filnavn: f.name }))}
            startBogstav={bilagStartBogstav}
            onStartBogstavAendret={sætBilagStartBogstav}
            valg={bilagValg}
            onValgAendret={sætBilagValg}
          />
        </div>
      )}

      {/* Tjekliste-sektion (12) */}
      {analyse && (
        <div className="space-y-4">
          <Pillar
            farve="indigo"
            nummer={12}
            titel={t("upload.sektion12_titel")}
            beskrivelse={t("upload.sektion12_beskrivelse")}
          />
          <TjeklisteSektion filer={valgteFiler} />
        </div>
      )}

      {/* Svarbrev-sektion (13) */}
      {analyse && (
        <div className="space-y-4">
          <Pillar
            farve="emerald"
            nummer={13}
            titel={t("upload.sektion13_titel")}
            beskrivelse={t("upload.sektion13_beskrivelse")}
          />
          <SvarbrevSektion
            filer={valgteFiler}
            klagepunkter={analyse?.klagepunkter}
            tidsforhold={analyse?.tidsforhold}
            bilagListe={bilagListeTilDocx}
          />
        </div>
      )}

      {/* Sektion 14: Gem din sagsbehandling — FJERNET.
          Vi gemmer ikke længere klager pga. GDPR/datasikkerhed. */}
    </div>
  );
}
