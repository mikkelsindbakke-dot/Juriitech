import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import { ApiHealthButton } from "@/components/api-health-button";
import { logout } from "./login/actions";

// Server Component — kører server-side ved hver request.
// proxy.ts har allerede verificeret at brugeren er logget ind når
// vi når hertil; vi kan derfor antage at user findes.
export default async function Home() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Slå tenant op via supabase_user_id i vores users-tabel.
  // Returnerer null hvis brugeren er oprettet i Supabase Auth
  // men ikke endnu er linket via admin-UI'en.
  const dbBruger = user ? await hentBrugerMedTenant(user.id) : null;

  return (
    <main className="flex flex-1 items-center justify-center bg-zinc-50 px-6 py-20">
      <Card className="w-full max-w-xl border-zinc-200 shadow-sm">
        <CardHeader className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-3 w-3 rounded-full bg-amber-500" />
            <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Migrations-version · ikke i produktion
            </span>
          </div>
          <CardTitle className="text-3xl font-semibold tracking-tight">
            juriitech PAX
          </CardTitle>
          <CardDescription className="text-base text-zinc-600">
            Logget ind som <strong>{user?.email}</strong>
            {dbBruger && (
              <>
                {" — tenant: "}
                <strong>{dbBruger.tenant_navn}</strong>
                <span className="text-zinc-400 text-sm">
                  {" "}
                  ({dbBruger.tenant_slug})
                </span>
              </>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-zinc-700">
          {dbBruger ? (
            <div className="rounded-md bg-zinc-100 p-4 leading-relaxed space-y-3">
              <div>
                <p className="font-medium text-zinc-900 mb-1">Bruger-info</p>
                <ul className="space-y-1">
                  <li>
                    <span className="text-zinc-500">Email:</span>{" "}
                    {dbBruger.email}
                  </li>
                  <li>
                    <span className="text-zinc-500">Navn:</span>{" "}
                    {dbBruger.fulde_navn || "(ikke sat)"}
                  </li>
                  <li>
                    <span className="text-zinc-500">Rolle:</span>{" "}
                    {dbBruger.role}
                  </li>
                </ul>
              </div>
              <div>
                <p className="font-medium text-zinc-900 mb-1">Tenant</p>
                <ul className="space-y-1">
                  <li>
                    <span className="text-zinc-500">Navn:</span>{" "}
                    {dbBruger.tenant_navn}
                  </li>
                  <li>
                    <span className="text-zinc-500">Slug:</span>{" "}
                    {dbBruger.tenant_slug}
                  </li>
                  <li>
                    <span className="text-zinc-500">Tenant-id:</span>{" "}
                    {dbBruger.tenant_id}
                  </li>
                </ul>
              </div>
            </div>
          ) : (
            <div className="rounded-md bg-amber-50 border border-amber-200 p-4 text-sm text-amber-900">
              Du er logget ind på Supabase Auth, men din konto er ikke
              endnu linket til en tenant i <code>users</code>-tabellen.
              Bed en admin om at invitere dig.
            </div>
          )}
          <div className="space-y-2">
            <p className="font-medium text-zinc-900 text-sm">
              FastAPI-bro til Python-AI
            </p>
            <p className="text-xs text-zinc-500">
              Test at Next.js (port 3000) kan tale med FastAPI (port 8000)
              som wrapper den eksisterende ai_engine.py.
            </p>
            <ApiHealthButton />
          </div>

          <p className="text-zinc-500 italic text-xs">
            Den nuværende PAX kører fortsat på{" "}
            <a
              href="https://pax.juriitech.com"
              className="underline underline-offset-2 hover:text-zinc-900"
              target="_blank"
              rel="noopener noreferrer"
            >
              pax.juriitech.com
            </a>{" "}
            — kunder mærker intet før vi er klar.
          </p>
          <form action={logout}>
            <Button type="submit" variant="outline" size="sm">
              Log ud
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
