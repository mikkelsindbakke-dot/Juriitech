// juriitech PAX-logo som React-komponent.
//
// Bygget som ren HTML/CSS i stedet for et billede-asset:
//   • skarpt på alle DPI'er (retina-skærme, zoom)
//   • ingen ekstra netværks-kald
//   • let at vedligeholde — farver/spacing er centraliseret her
//   • samme styling som Streamlit-versionen (forside.py:641-695)
//
// Komponenter:
//   • "juriitech" — Space Grotesk bold, "j" i indigo (#6366F1, samme som
//     favicon), resten i sort
//   • "PAX" — fed sort tekst på amber-pille (#F5B53B) med lille trekant-
//     tail i bunden-højre, så det visuelt ligner en taleboble
//
// Størrelse styres via 'size'-prop ('sm' | 'md' | 'lg') så samme komponent
// kan bruges som lille nav-logo (sm) og som stort login/landing-logo (lg).

type PaxLogoSize = "sm" | "md" | "lg";

const STR: Record<
  PaxLogoSize,
  {
    wordmark: string;
    pax: string;
    paxPadding: string;
    paxRadius: string;
    tail: string;
    gap: string;
  }
> = {
  sm: {
    wordmark: "text-lg",
    pax: "text-[0.7rem]",
    paxPadding: "px-2 py-0.5",
    paxRadius: "rounded-[4px]",
    tail: "h-1.5 w-1.5 -bottom-[3px] right-2",
    gap: "gap-1",
  },
  md: {
    wordmark: "text-2xl",
    pax: "text-[0.78em]",
    paxPadding: "px-2 py-[3px]",
    paxRadius: "rounded-[5px]",
    tail: "h-2 w-2 -bottom-[5px] right-[10px]",
    gap: "gap-1.5",
  },
  lg: {
    wordmark: "text-4xl sm:text-5xl",
    pax: "text-[0.62em]",
    paxPadding: "px-2.5 py-1",
    paxRadius: "rounded-md",
    tail: "h-2.5 w-2.5 -bottom-[6px] right-3",
    gap: "gap-2",
  },
};

export function PaxLogo({
  size = "md",
  className = "",
}: {
  size?: PaxLogoSize;
  className?: string;
}) {
  const s = STR[size];
  return (
    <span
      className={`inline-flex items-center font-bold leading-none select-none tracking-[-0.035em] ${s.gap} ${s.wordmark} ${className}`}
      style={{ fontFamily: "var(--font-space-grotesk), system-ui, sans-serif" }}
      aria-label="juriitech PAX"
    >
      <span className="inline-flex items-baseline">
        <span style={{ color: "#6366F1" }}>j</span>
        <span style={{ color: "#0A0B0F" }}>uriitech</span>
      </span>
      <span
        className={`relative inline-block font-bold ${s.pax} ${s.paxPadding} ${s.paxRadius}`}
        style={{ background: "#F5B53B", color: "#0A0B0F" }}
      >
        PAX
        {/* Trekantet tail nederst-højre — visuelt en lille taleboble */}
        <span
          aria-hidden
          className={`absolute ${s.tail}`}
          style={{
            background: "#F5B53B",
            clipPath: "polygon(0 0, 100% 0, 50% 100%)",
          }}
        />
      </span>
    </span>
  );
}
