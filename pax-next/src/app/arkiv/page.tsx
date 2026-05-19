import Link from "next/link";
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
import { hentArkiv, type ArkivType } from "@/lib/queries/arkiv";
import { SletArkivKnap } from "@/components/slet-arkiv-knap";
import { LocaleProvider } from "@/lib/i18n/client";
import { lavT } from "@/lib/i18n/t";

const TYPE_FARVE: Record<ArkivType, string> = {
  analyse: "bg-blue-100 text-blue-800",
  svarbrev: "bg-emerald-100 text-emerald-800",
  tjekliste: "bg-amber-100 text-amber-800",
};

export default async function ArkivPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string }>;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const dbBruger = user ? await hentBrugerMedTenant(user.id) : null;
  const locale = dbBruger?.effektiv_sprog ?? "da";
  const t = lavT(locale);
  const datoLocale = locale === "no" ? "no-NO" : "da-DK";

  // Type-etiketter lokaliseres via t() — fallback til dansk hvis nøgle mangler.
  const typeTekst = (type: ArkivType): string => {
    return t(`arkiv.type_${type}`);
  };

  const params = await searchParams;
  const filter = (
    ["analyse", "svarbrev", "tjekliste"] as const
  ).includes(params.type as ArkivType)
    ? (params.type as ArkivType)
    : undefined;

  const indgange = dbBruger
    ? await hentArkiv(dbBruger.effektiv_tenant_id, 100, filter)
    : [];

  return (
    <LocaleProvider locale={locale}>
    <main className="flex flex-1 items-start justify-center bg-zinc-50 px-6 py-12">
      <div className="w-full max-w-3xl space-y-4">
        <div className="flex items-center justify-between">
          <Link
            href="/"
            className="text-sm text-zinc-500 hover:text-zinc-900 underline-offset-4 hover:underline"
          >
            ← {t("arkiv.tilbage_til_forsiden")}
          </Link>
          <Link
            href="/sag/ny"
            className={buttonVariants({ size: "sm" })}
          >
            {t("arkiv.ny_sag")}
          </Link>
        </div>

        <Card className="border-zinc-200 shadow-sm">
          <CardHeader className="space-y-2">
            <CardTitle className="text-2xl font-semibold tracking-tight">
              {t("arkiv.titel")}
            </CardTitle>
            <CardDescription className="text-zinc-600">
              {dbBruger ? (
                <>
                  {t("arkiv.tenant_meta", {
                    tenant: dbBruger.tenant_navn,
                    antal: indgange.length,
                  })}
                  {filter &&
                    t("arkiv.tenant_meta_filter", {
                      filter: typeTekst(filter),
                    })}
                </>
              ) : (
                t("arkiv.ikke_linket_tenant")
              )}
            </CardDescription>

            {/* Filter-piller */}
            <div className="flex flex-wrap gap-1.5 pt-2">
              <Link
                href="/arkiv"
                className={`text-xs rounded-full px-3 py-1 transition-colors ${
                  !filter
                    ? "bg-zinc-900 text-white"
                    : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"
                }`}
              >
                {t("arkiv.filter_alle")}
              </Link>
              {(["analyse", "svarbrev", "tjekliste"] as const).map((tp) => (
                <Link
                  key={tp}
                  href={`/arkiv?type=${tp}`}
                  className={`text-xs rounded-full px-3 py-1 transition-colors ${
                    filter === tp
                      ? "bg-zinc-900 text-white"
                      : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"
                  }`}
                >
                  {typeTekst(tp)}
                </Link>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            {indgange.length === 0 ? (
              <div className="rounded-md bg-zinc-50 border border-zinc-200 p-6 text-sm text-zinc-600 text-center">
                {filter
                  ? t("arkiv.tom_state_filter", {
                      type: typeTekst(filter).toLowerCase(),
                    })
                  : t("arkiv.tom_state")}
              </div>
            ) : (
              <ul className="divide-y divide-zinc-200">
                {indgange.map((i) => (
                  <li
                    key={i.id}
                    className="flex items-center justify-between gap-3 py-3"
                  >
                    <Link
                      href={`/arkiv/${i.id}`}
                      className="min-w-0 flex-1 group"
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-xs rounded-full px-2 py-0.5 ${
                            TYPE_FARVE[i.type as ArkivType] ??
                            "bg-zinc-100 text-zinc-700"
                          }`}
                        >
                          {typeTekst(i.type as ArkivType)}
                        </span>
                        <span className="font-medium text-sm truncate group-hover:underline underline-offset-4">
                          {i.titel}
                        </span>
                      </div>
                      <div className="text-xs text-zinc-500 mt-0.5">
                        {new Date(i.oprettet_dato).toLocaleString(datoLocale, {
                          dateStyle: "short",
                          timeStyle: "short",
                        })}
                        {i.klage_filnavn && (
                          <>
                            {" "}· {i.klage_filnavn}
                          </>
                        )}
                      </div>
                    </Link>
                    <SletArkivKnap id={i.id} titel={i.titel} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
    </LocaleProvider>
  );
}
