"use client";

import { Card, CardContent } from "@/components/ui/card";
import { FileText } from "lucide-react";
import { useT } from "@/lib/i18n/client";

function formatStr(antalBytes: number): string {
  if (antalBytes < 1024) return `${antalBytes} B`;
  if (antalBytes < 1024 * 1024) return `${(antalBytes / 1024).toFixed(1)} kB`;
  return `${(antalBytes / 1024 / 1024).toFixed(1)} MB`;
}

// Sektion 9: Sagsakter til denne sag.
//
// Brugeren kan uploade yderligere filer (mails, screenshots,
// bookingdetaljer m.m.) der lægges til hovedsagen via onFilerTilfoejet.
// Bagefter kan der re-scannes med "Scan igen" øverst.
//
// 'filer'-prop'en er den fulde liste af sagens filer — den vises lige
// under upload-zonen så brugeren får øjeblikkelig feedback om at en ny
// fil faktisk landede i sagen (ellers er fil-listen kun synlig øverst
// på siden, langt fra hvor brugeren lige klikkede).
export function SagsakterSektion({
  onFilerTilfoejet,
  filer = [],
  disabled,
}: {
  onFilerTilfoejet: (filer: File[]) => void;
  filer?: File[];
  disabled?: boolean;
}) {
  const t = useT();
  function håndterFilValg(e: React.ChangeEvent<HTMLInputElement>) {
    const valgte = Array.from(e.target.files ?? []);
    onFilerTilfoejet(valgte);
    e.target.value = ""; // tillad samme fil at blive tilføjet igen senere
  }

  return (
    <Card>
      <CardContent className="space-y-5 pt-6">
        <div className="space-y-2">
          <label
            htmlFor="sagsakter-filer"
            className="block w-full cursor-pointer rounded-lg border-2 border-dashed border-zinc-300 bg-zinc-50 p-6 text-center hover:border-zinc-400 hover:bg-zinc-100 transition-colors"
          >
            <div className="text-sm text-zinc-600">
              <span className="font-medium text-zinc-900">
                {t("sagsakter.upload_overskrift")}
              </span>
              <span className="block mt-1 text-xs">
                {t("sagsakter.upload_beskrivelse")}
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

          {filer.length > 0 && (
            <div className="rounded-md bg-zinc-50 border border-zinc-200 p-4">
              <p className="text-sm font-semibold text-zinc-900 mb-3">
                {t("sagsakter.filer_i_sagen", { antal: filer.length })}
              </p>
              <ul className="divide-y divide-zinc-200 border-y border-zinc-200 bg-white rounded-sm">
                {filer.map((f, i) => (
                  <li
                    key={i}
                    className="flex items-center gap-3 px-3 py-2.5"
                  >
                    <FileText
                      aria-hidden
                      className="h-4 w-4 shrink-0 text-zinc-500"
                    />
                    <span className="flex-1 text-sm font-medium text-zinc-900 break-all">
                      {f.name}
                    </span>
                    <span className="shrink-0 text-xs text-zinc-500 tabular-nums">
                      {formatStr(f.size)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
