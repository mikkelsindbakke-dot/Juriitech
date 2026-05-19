"use client";

import { Tooltip } from "@base-ui/react/tooltip";
import { Info } from "lucide-react";
import type { ReactNode } from "react";

// Lille neutral info-ikon med hover-tooltip. Bruges til at gemme
// forklarende hjælpetekst der ellers ville fylde for meget under
// formularer — fx "Slået TIL: eksplicitte henvisninger til bilag…".
//
// API:
//   <InfoTooltip>Tooltip-tekst her</InfoTooltip>
//
// Tooltip åbner ved hover OG keyboard-focus (a11y), lukker ved blur eller
// Escape. Hjælpeteksten kan indeholde React-noder (for fed eller links).
export function InfoTooltip({ children }: { children: ReactNode }) {
  return (
    <Tooltip.Provider delay={150}>
      <Tooltip.Root>
        <Tooltip.Trigger
        render={(props) => (
          <button
            type="button"
            aria-label="Vis hjælpetekst"
            {...props}
            className="inline-flex h-4 w-4 items-center justify-center rounded-full text-zinc-400 hover:text-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 transition-colors align-middle"
          >
            <Info className="h-3.5 w-3.5" aria-hidden />
          </button>
        )}
      />
        <Tooltip.Portal>
          <Tooltip.Positioner side="top" sideOffset={6}>
            <Tooltip.Popup className="max-w-xs rounded-md bg-zinc-900 px-3 py-2 text-xs leading-relaxed text-white shadow-lg z-50">
              {children}
            </Tooltip.Popup>
          </Tooltip.Positioner>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
