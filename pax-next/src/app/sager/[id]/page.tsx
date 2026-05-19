// Detail-side for én gemt sag.
//
// Tenant-isolation: hentSagById filtrerer på tenant_id i SQL-laget,
// så cross-tenant adgang afvises før vi nogensinde læser rækken.
// Decryption sker server-side via pgcrypto i samme query — krypteret
// payload sendes ALDRIG til client.
//
// Status: MVP. Vi viser den gemte analyse (svarbrev/tjekliste indgår
// ikke i state_json fra Next.js-flowet endnu — de er stadig flyttet
// til arkivet via deres egne actions). Re-upload af filer for at
// genstarte AI-flow er IKKE understøttet — det kræver re-upload på
// forsiden.
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
import { hentSagById } from "@/lib/queries/gemte-sager";
import { GemtSagVisning } from "@/components/gemt-sag-visning";
import { LocaleProvider } from "@/lib/i18n/client";
import { lavT } from "@/lib/i18n/t";

export default async function GemtSagDetalje({
  params,
}: {
  // Next.js 16: params er Promise — skal afventes.
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

  const sag = await hentSagById(id, dbBruger.effektiv_tenant_id);
  if (!sag) notFound();

  const locale = dbBruger.effektiv_sprog ?? "da";
  const t = lavT(locale);
  const datoLocale = locale === "no" ? "no-NO" : "da-DK";

  const opdateretLabel = new Date(sag.opdateret_dato).toLocaleString(
    datoLocale,
    {
      dateStyle: "long",
      timeStyle: "short",
    },
  );
  const oprettetLabel = new Date(sag.oprettet_dato).toLocaleDateString(
    datoLocale,
  );

  return (
    <LocaleProvider locale={locale}>
    <main className="flex flex-1 items-start justify-center bg-zinc-50 px-6 py-12">
      <div className="w-full max-w-4xl space-y-4">
        <div className="flex items-center justify-between">
          <Link
            href="/sager"
            className="text-sm text-zinc-500 hover:text-zinc-900 underline-offset-4 hover:underline"
          >
            ← {t("sag.tilbage_til_gemte_sager")}
          </Link>
          <Link
            href="/sag/ny"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            {t("sag.ny_sag")}
          </Link>
        </div>

        <Card className="border-zinc-200 shadow-sm">
          <CardHeader className="space-y-2">
            <CardTitle className="text-2xl font-semibold tracking-tight">
              {sag.titel}
            </CardTitle>
            <CardDescription className="text-xs text-zinc-500">
              {t("sag.meta_id_opdateret", {
                id: sag.id,
                opdateret: opdateretLabel,
              })}
              {sag.opdateret_dato !== sag.oprettet_dato && (
                <> · {t("sag.meta_oprettet", { dato: oprettetLabel })}</>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <GemtSagVisning stateJson={sag.state_json} />
          </CardContent>
        </Card>
      </div>
    </main>
    </LocaleProvider>
  );
}
