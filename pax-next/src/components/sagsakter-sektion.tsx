"use client";

import { Card, CardContent } from "@/components/ui/card";

function formatStr(antalBytes: number): string {
  if (antalBytes < 1024) return `${antalBytes} B`;
  if (antalBytes < 1024 * 1024) return `${(antalBytes / 1024).toFixed(1)} kB`;
  return `${(antalBytes / 1024 / 1024).toFixed(1)} MB`;
}

// Sektion 9: Sagsakter til denne sag.
//
// To indgange til at give AI'en ekstra kontekst:
//   1. Upload yderligere filer (mails, screenshots, bookingdetaljer m.m.).
//      Filerne lægges til hovedsagen via onFilerTilfoejet — derefter kan
//      brugeren re-scanne med "Scan igen" øverst.
//   2. Skriv noter som fri tekst. Teksten medsendes alle AI-kald
//      (analyse, svarbrev, tjekliste) så vurderingen tager højde for
//      ny information.
//
// 'filer'-prop'en er den fulde liste af sagens filer — den vises lige
// under upload-zonen så brugeren får øjeblikkelig feedback om at en ny
// fil faktisk landede i sagen (ellers er fil-listen kun synlig øverst
// på siden, langt fra hvor brugeren lige klikkede).
export function SagsakterSektion({
  vaerdi,
  onAendret,
  onFilerTilfoejet,
  filer = [],
  disabled,
}: {
  vaerdi: string;
  onAendret: (s: string) => void;
  onFilerTilfoejet: (filer: File[]) => void;
  filer?: File[];
  disabled?: boolean;
}) {
  function håndterFilValg(e: React.ChangeEvent<HTMLInputElement>) {
    const valgte = Array.from(e.target.files ?? []);
    onFilerTilfoejet(valgte);
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

          {/* Filer i sagen — vises lige under upload-zonen for øjeblikkelig
              feedback. Listen er den FULDE sag (både hoved-upload + ekstra
              sagsakter), så brugeren altid kan se hvad der er i sagen. */}
          {filer.length > 0 && (
            <div className="rounded-md bg-zinc-50 border border-zinc-200 p-3 text-xs">
              <p className="font-medium text-zinc-900 mb-1.5">
                Filer i sagen ({filer.length})
              </p>
              <ul className="space-y-0.5 text-zinc-700">
                {filer.map((f, i) => (
                  <li key={i} className="flex items-baseline gap-1">
                    <span aria-hidden className="text-zinc-400">·</span>
                    <span className="text-zinc-800">{f.name}</span>
                    <span className="text-zinc-500">({formatStr(f.size)})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
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
