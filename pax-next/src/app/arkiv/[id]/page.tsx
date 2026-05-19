import Link from "next/link";
import { notFound } from "next/navigation";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import { hentArkivById, type ArkivType } from "@/lib/queries/arkiv";
import { LocaleProvider } from "@/lib/i18n/client";
import { lavT } from "@/lib/i18n/t";

const TYPE_FARVE: Record<ArkivType, string> = {
  analyse: "bg-blue-100 text-blue-800",
  svarbrev: "bg-emerald-100 text-emerald-800",
  tjekliste: "bg-amber-100 text-amber-800",
};

export default async function ArkivDetalje({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: idStr } = await params;
  const id = Number(idStr);
  if (!Number.isFinite(id)) notFound();

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const dbBruger = user ? await hentBrugerMedTenant(user.id) : null;
  if (!dbBruger) notFound();

  const indgang = await hentArkivById(id, dbBruger.effektiv_tenant_id);
  if (!indgang) notFound();

  const locale = dbBruger.effektiv_sprog ?? "da";
  const t = lavT(locale);
  const datoLocale = locale === "no" ? "no-NO" : "da-DK";

  const typeKey = indgang.type as ArkivType;
  const typeFarve = TYPE_FARVE[typeKey] ?? "bg-zinc-100 text-zinc-700";
  // Hvis type ikke er kendt, vis raw value (fallback). Ellers oversæt.
  const typeTekst = TYPE_FARVE[typeKey]
    ? t(`arkiv.type_${typeKey}`)
    : indgang.type;

  return (
    <LocaleProvider locale={locale}>
    <main className="flex flex-1 items-start justify-center bg-zinc-50 px-6 py-12">
      <div className="w-full max-w-3xl space-y-4">
        <div className="flex items-center justify-between">
          <Link
            href="/arkiv"
            className="text-sm text-zinc-500 hover:text-zinc-900 underline-offset-4 hover:underline"
          >
            ← {t("arkiv.tilbage_til_arkivet")}
          </Link>
          <Link
            href="/sag/ny"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            {t("arkiv.ny_sag")}
          </Link>
        </div>

        <Card className="border-zinc-200 shadow-sm">
          <CardHeader className="space-y-3">
            <div className="flex items-center gap-2">
              <span
                className={`text-xs rounded-full px-2 py-0.5 ${typeFarve}`}
              >
                {typeTekst}
              </span>
              <span className="text-xs text-zinc-500">
                #{indgang.id} ·{" "}
                {new Date(indgang.oprettet_dato).toLocaleString(datoLocale, {
                  dateStyle: "long",
                  timeStyle: "short",
                })}
              </span>
            </div>
            <CardTitle className="text-2xl font-semibold tracking-tight">
              {indgang.titel}
            </CardTitle>
            {indgang.klage_filnavn && (
              <CardDescription className="text-xs">
                {t("arkiv.klage_label")}: <code>{indgang.klage_filnavn}</code>
              </CardDescription>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Indhold */}
            <div className="rounded-md bg-zinc-50 border border-zinc-200 p-4">
              <pre className="whitespace-pre-wrap text-sm text-zinc-800 font-sans leading-relaxed">
                {indgang.indhold}
              </pre>
            </div>

            {/* Metadata-felter (hvis udfyldt) */}
            {indgang.spoergsmaal && (
              <details className="text-sm">
                <summary className="cursor-pointer font-medium text-zinc-700 hover:text-zinc-900">
                  {t("arkiv.spoergsmaal_titel")}
                </summary>
                <p className="mt-2 text-zinc-700 whitespace-pre-wrap">
                  {indgang.spoergsmaal}
                </p>
              </details>
            )}
            {indgang.ekstra_instrukser && (
              <details className="text-sm">
                <summary className="cursor-pointer font-medium text-zinc-700 hover:text-zinc-900">
                  {t("arkiv.instrukser_titel")}
                </summary>
                <pre className="mt-2 whitespace-pre-wrap text-zinc-700 font-sans">
                  {indgang.ekstra_instrukser}
                </pre>
              </details>
            )}
            {indgang.sagsakter && (
              <details className="text-sm">
                <summary className="cursor-pointer font-medium text-zinc-700 hover:text-zinc-900">
                  {t("arkiv.sagsakter_titel", {
                    antal: indgang.sagsakter.length,
                  })}
                </summary>
                <pre className="mt-2 whitespace-pre-wrap text-zinc-700 font-sans max-h-60 overflow-auto rounded bg-zinc-50 p-2">
                  {indgang.sagsakter}
                </pre>
              </details>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
    </LocaleProvider>
  );
}
