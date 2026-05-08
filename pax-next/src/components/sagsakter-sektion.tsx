"use client";

import { Card, CardContent } from "@/components/ui/card";

// Sektion 9: Sagsakter til denne sag.
//
// To indgange til at give AI'en ekstra kontekst:
//   1. Upload yderligere filer (mails, screenshots, bookingdetaljer m.m.).
//      Filerne lægges til hovedsagen via onFilerTilfoejet — derefter kan
//      brugeren re-scanne med "Scan igen" øverst.
//   2. Skriv noter som fri tekst. Teksten medsendes alle AI-kald
//      (analyse, svarbrev, tjekliste) så vurderingen tager højde for
//      ny information.
export function SagsakterSektion({
  vaerdi,
  onAendret,
  onFilerTilfoejet,
  disabled,
}: {
  vaerdi: string;
  onAendret: (s: string) => void;
  onFilerTilfoejet: (filer: File[]) => void;
  disabled?: boolean;
}) {
  function håndterFilValg(e: React.ChangeEvent<HTMLInputElement>) {
    const filer = Array.from(e.target.files ?? []);
    onFilerTilfoejet(filer);
    e.target.value = ""; // tillad samme fil at blive tilføjet igen senere
  }

  return (
    <Card>
      <CardContent className="space-y-5 pt-6">
        {/* Upload-zone for ekstra sagsakter */}
        <div className="space-y-2">
          <label
            htmlFor="sagsakter-filer"
            className="block w-full cursor-pointer rounded-lg border-2 border-dashed border-zinc-300 bg-zinc-50 p-6 text-center hover:border-zinc-400 hover:bg-zinc-100 transition-colors"
          >
            <div className="text-sm text-zinc-600">
              <span className="font-medium text-zinc-900">
                Upload yderligere filer
              </span>
              <span className="block mt-1 text-xs">
                Mails, screenshots, bookingdetaljer m.m. — PDF, DOCX,
                PNG, JPG, ZIP. Filerne lægges til sagen og indgår i
                analysen næste gang du scanner.
              </span>
            </div>
            <input
              id="sagsakter-filer"
              type="file"
              multiple
              accept=".pdf,.docx,.png,.jpg,.jpeg,.zip"
              onChange={håndterFilValg}
              disabled={disabled}
              className="sr-only"
            />
          </label>
        </div>

        {/* Fri-tekst-felt */}
        <div className="space-y-2">
          <label
            htmlFor="sagsakter-tekst"
            className="text-sm font-medium text-zinc-700"
          >
            Eller skriv noter som fri tekst
          </label>
          <textarea
            id="sagsakter-tekst"
            value={vaerdi}
            onChange={(e) => onAendret(e.target.value)}
            disabled={disabled}
            rows={6}
            placeholder="Eksempel: 28. maj 2025 kl. 16:50 ringer klager til vores kundeservice. Talte med Nichlas der…"
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
          />
          <p className="text-xs text-zinc-500">
            {vaerdi.trim().length} tegn. Bruges som ekstra kontekst af AI&apos;en
            i analyse, svarbrev og tjekliste.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
