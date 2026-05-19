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
import { hentGemteSager } from "@/lib/queries/gemte-sager";
import { SletSagKnap } from "@/components/slet-sag-knap";
import { LocaleProvider } from "@/lib/i18n/client";
import { lavT } from "@/lib/i18n/t";

// Server Component — proxy.ts har allerede beskyttet ruten med auth.
export default async function SagerPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const dbBruger = user ? await hentBrugerMedTenant(user.id) : null;
  const locale = dbBruger?.effektiv_sprog ?? "da";
  const t = lavT(locale);
  const datoLocale = locale === "no" ? "no-NO" : "da-DK";

  const sager = dbBruger
    ? await hentGemteSager(dbBruger.effektiv_tenant_id)
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
            ← {t("sager.tilbage_til_forsiden")}
          </Link>
          <Link
            href="/sag/ny"
            className={buttonVariants({ size: "sm" })}
          >
            {t("sager.ny_sag")}
          </Link>
        </div>

        <Card className="border-zinc-200 shadow-sm">
          <CardHeader className="space-y-2">
            <CardTitle className="text-2xl font-semibold tracking-tight">
              {t("sager.titel")}
            </CardTitle>
            <CardDescription className="text-zinc-600">
              {dbBruger ? (
                <>
                  {t("sager.tenant_meta", {
                    tenant: dbBruger.tenant_navn,
                    antal: sager.length,
                  })}
                </>
              ) : (
                t("sager.ikke_linket_tenant")
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {sager.length === 0 ? (
              <div className="rounded-md bg-zinc-50 border border-zinc-200 p-6 text-sm text-zinc-600 text-center">
                {t("sager.tom_state_prefix")}{" "}
                <Link
                  href="/sag/ny"
                  className="underline underline-offset-2 hover:text-zinc-900"
                >
                  {t("sager.tom_state_link")}
                </Link>{" "}
                {t("sager.tom_state_suffix")}
              </div>
            ) : (
              <ul className="divide-y divide-zinc-200">
                {sager.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-center justify-between gap-3 py-3"
                  >
                    <Link
                      href={`/sager/${s.id}`}
                      className="min-w-0 flex-1 group rounded-md -mx-2 px-2 py-1 hover:bg-zinc-50"
                    >
                      <div className="font-medium text-sm truncate group-hover:text-zinc-900 group-hover:underline underline-offset-2">
                        {s.titel}
                      </div>
                      <div className="text-xs text-zinc-500 mt-0.5">
                        {t("sager.opdateret", {
                          dato: new Date(s.opdateret_dato).toLocaleString(
                            datoLocale,
                            {
                              dateStyle: "short",
                              timeStyle: "short",
                            },
                          ),
                        })}
                        {s.opdateret_dato !== s.oprettet_dato && (
                          <>
                            {" "}·{" "}
                            {t("sager.oprettet", {
                              dato: new Date(
                                s.oprettet_dato,
                              ).toLocaleDateString(datoLocale),
                            })}
                          </>
                        )}
                      </div>
                    </Link>
                    <div className="flex items-center gap-2 shrink-0">
                      <Link
                        href={`/sager/${s.id}`}
                        className={buttonVariants({
                          variant: "outline",
                          size: "sm",
                        })}
                      >
                        {t("sager.aabn")}
                      </Link>
                      <SletSagKnap id={s.id} titel={s.titel} />
                    </div>
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
