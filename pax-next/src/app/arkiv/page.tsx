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

const typeEtiket: Record<ArkivType, { tekst: string; farve: string }> = {
  analyse: { tekst: "Analyse", farve: "bg-blue-100 text-blue-800" },
  svarbrev: { tekst: "Svarbrev", farve: "bg-emerald-100 text-emerald-800" },
  tjekliste: { tekst: "Tjekliste", farve: "bg-amber-100 text-amber-800" },
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

  const params = await searchParams;
  const filter = (
    ["analyse", "svarbrev", "tjekliste"] as const
  ).includes(params.type as ArkivType)
    ? (params.type as ArkivType)
    : undefined;

  const indgange = dbBruger
    ? await hentArkiv(dbBruger.tenant_id, 100, filter)
    : [];

  return (
    <main className="flex flex-1 items-start justify-center bg-zinc-50 px-6 py-12">
      <div className="w-full max-w-3xl space-y-4">
        <div className="flex items-center justify-between">
          <Link
            href="/"
            className="text-sm text-zinc-500 hover:text-zinc-900 underline-offset-4 hover:underline"
          >
            ← Tilbage til forsiden
          </Link>
          <Link
            href="/sag/ny"
            className={buttonVariants({ size: "sm" })}
          >
            Ny sag
          </Link>
        </div>

        <Card className="border-zinc-200 shadow-sm">
          <CardHeader className="space-y-2">
            <CardTitle className="text-2xl font-semibold tracking-tight">
              Arkiv
            </CardTitle>
            <CardDescription className="text-zinc-600">
              {dbBruger ? (
                <>
                  Tenant: <strong>{dbBruger.tenant_navn}</strong> ·{" "}
                  {indgange.length} indgang(e)
                  {filter && (
                    <>
                      {" "}· filter:{" "}
                      <strong>{typeEtiket[filter].tekst}</strong>
                    </>
                  )}
                </>
              ) : (
                "Din konto er ikke linket til en tenant"
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
                Alle
              </Link>
              {(["analyse", "svarbrev", "tjekliste"] as const).map((t) => (
                <Link
                  key={t}
                  href={`/arkiv?type=${t}`}
                  className={`text-xs rounded-full px-3 py-1 transition-colors ${
                    filter === t
                      ? "bg-zinc-900 text-white"
                      : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"
                  }`}
                >
                  {typeEtiket[t].tekst}
                </Link>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            {indgange.length === 0 ? (
              <div className="rounded-md bg-zinc-50 border border-zinc-200 p-6 text-sm text-zinc-600 text-center">
                {filter
                  ? `Ingen ${typeEtiket[filter].tekst.toLowerCase()}-indgange.`
                  : "Arkivet er tomt. Generer en analyse, et svarbrev eller en tjekliste."}
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
                            typeEtiket[i.type]?.farve ??
                            "bg-zinc-100 text-zinc-700"
                          }`}
                        >
                          {typeEtiket[i.type]?.tekst ?? i.type}
                        </span>
                        <span className="font-medium text-sm truncate group-hover:underline underline-offset-4">
                          {i.titel}
                        </span>
                      </div>
                      <div className="text-xs text-zinc-500 mt-0.5">
                        {new Date(i.oprettet_dato).toLocaleString("da-DK", {
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
  );
}
