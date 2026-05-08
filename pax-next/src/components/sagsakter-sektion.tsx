"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";

// Sektion 9: Sagsakter til denne sag.
//
// Lader brugeren tilføje yderligere kontekst (mailkorrespondancer, tekst-
// beskeder, bookingdetaljer, screenshots m.m.) som AI'en ikke automatisk
// har adgang til via de uploadede filer. Teksten medsendes alle AI-kald
// (analyse, svarbrev, tjekliste) som ekstra kontekst — så vurderingen
// tager højde for ny information.
//
// Bemærk: Streamlit-PAX bruger to felter — uploadede sagsakter-filer OG
// fri tekst. I Next.js v1 har vi kun fri tekst. Filer kan stadig
// uploades via hovedupload-zonen.
export function SagsakterSektion({
  vaerdi,
  onAendret,
  disabled,
}: {
  vaerdi: string;
  onAendret: (s: string) => void;
  disabled?: boolean;
}) {
  const [aaben, sætAaben] = useState(false);

  return (
    <Card>
      <CardContent className="pt-6">
        <button
          type="button"
          onClick={() => sætAaben((v) => !v)}
          className="w-full text-left text-sm font-medium text-zinc-700 hover:text-zinc-900 flex items-center gap-2 py-2"
        >
          <span className="text-zinc-400">{aaben ? "▾" : "▸"}</span>
          {aaben ? "Skjul sagsakter-feltet" : "Skriv yderligere noter (valgfri)"}
          {!aaben && vaerdi.trim() && (
            <span className="ml-auto text-xs text-emerald-700 font-normal">
              ✓ {vaerdi.trim().length} tegn skrevet
            </span>
          )}
        </button>
        {aaben && (
          <div className="space-y-2 pt-2">
            <textarea
              value={vaerdi}
              onChange={(e) => onAendret(e.target.value)}
              disabled={disabled}
              rows={8}
              placeholder="Eksempel: 28. maj 2025 kl. 16:50 ringer klager til vores kundeservice. Talte med Nichlas der…"
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            />
            <p className="text-xs text-zinc-500">
              {vaerdi.trim().length} tegn. Bruges som ekstra kontekst af AI&apos;en
              i analyse, svarbrev og tjekliste.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
