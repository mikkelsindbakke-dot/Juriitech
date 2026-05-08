import { ReactNode } from "react";

// Apple Health-inspireret pillar:
//   ●  N. Titel
//      Beskrivelse-tekst…
// Pastel afrundet kort med farvet dot øverst-venstre. Bruges som
// header-only (stand-alone) eller som container med children inde i
// pillaren (output-sektioner som analyse-resultat).

export type PillarFarve =
  | "lavender"
  | "rose"
  | "amber"
  | "blue"
  | "emerald"
  | "indigo"
  | "teal"
  | "slate"
  | "fuchsia"
  | "sky";

const farveMap: Record<PillarFarve, { bg: string; dot: string }> = {
  lavender: { bg: "bg-violet-100/70", dot: "bg-blue-500" },
  rose: { bg: "bg-rose-100/70", dot: "bg-rose-500" },
  amber: { bg: "bg-amber-100/60", dot: "bg-amber-500" },
  blue: { bg: "bg-blue-100/60", dot: "bg-blue-500" },
  emerald: { bg: "bg-emerald-100/60", dot: "bg-emerald-500" },
  indigo: { bg: "bg-indigo-100/60", dot: "bg-indigo-500" },
  teal: { bg: "bg-teal-100/60", dot: "bg-teal-500" },
  slate: { bg: "bg-slate-100/70", dot: "bg-slate-500" },
  fuchsia: { bg: "bg-fuchsia-100/60", dot: "bg-fuchsia-500" },
  sky: { bg: "bg-sky-100/60", dot: "bg-sky-500" },
};

export function Pillar({
  farve,
  nummer,
  titel,
  beskrivelse,
  children,
}: {
  farve: PillarFarve;
  nummer?: number;
  titel: string;
  beskrivelse?: ReactNode;
  children?: ReactNode;
}) {
  const styles = farveMap[farve];
  return (
    <section className={`${styles.bg} rounded-3xl px-8 py-7 sm:px-10 sm:py-8`}>
      <span
        className={`block w-2.5 h-2.5 rounded-full ${styles.dot} mb-4`}
        aria-hidden
      />
      <h2 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight text-zinc-900 leading-tight">
        {nummer !== undefined && `${nummer}. `}
        {titel}
      </h2>
      {beskrivelse && (
        <div className="mt-3 text-sm sm:text-base text-zinc-700 leading-relaxed max-w-3xl">
          {beskrivelse}
        </div>
      )}
      {children && <div className="mt-5">{children}</div>}
    </section>
  );
}
