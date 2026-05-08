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

// Server Component — proxy.ts har allerede beskyttet ruten med auth.
export default async function SagerPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const dbBruger = user ? await hentBrugerMedTenant(user.id) : null;

  const sager = dbBruger ? await hentGemteSager(dbBruger.tenant_id) : [];

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
              Gemte sager
            </CardTitle>
            <CardDescription className="text-zinc-600">
              {dbBruger ? (
                <>
                  Tenant: <strong>{dbBruger.tenant_navn}</strong> ·{" "}
                  {sager.length} sag(er)
                </>
              ) : (
                "Din konto er ikke linket til en tenant"
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {sager.length === 0 ? (
              <div className="rounded-md bg-zinc-50 border border-zinc-200 p-6 text-sm text-zinc-600 text-center">
                Ingen gemte sager endnu. Upload en klage på{" "}
                <Link
                  href="/sag/ny"
                  className="underline underline-offset-2 hover:text-zinc-900"
                >
                  /sag/ny
                </Link>{" "}
                og tryk &quot;Gem som sag&quot; efter analyse.
              </div>
            ) : (
              <ul className="divide-y divide-zinc-200">
                {sager.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-center justify-between gap-3 py-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-sm truncate">
                        {s.titel}
                      </div>
                      <div className="text-xs text-zinc-500 mt-0.5">
                        Opdateret{" "}
                        {new Date(s.opdateret_dato).toLocaleString("da-DK", {
                          dateStyle: "short",
                          timeStyle: "short",
                        })}
                        {s.opdateret_dato !== s.oprettet_dato && (
                          <>
                            {" "}· Oprettet{" "}
                            {new Date(s.oprettet_dato).toLocaleDateString(
                              "da-DK",
                            )}
                          </>
                        )}
                      </div>
                    </div>
                    <SletSagKnap id={s.id} titel={s.titel} />
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
