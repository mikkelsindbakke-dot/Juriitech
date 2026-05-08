import { buttonVariants } from "@/components/ui/button";
import { Button } from "@/components/ui/button";
import { UploadForm } from "@/components/upload-form";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import { logout } from "./login/actions";
import Link from "next/link";

// Forsiden ER ny-sag-flowet. Tidligere "logget ind som"-side er fjernet
// (irrelevant info — brugeren skal lande direkte i sit arbejde).
// Sekundære navigations-links (Gemte sager, Arkiv, Admin, Log ud) ligger
// diskret i top-rækken så de ikke konkurrerer med headlinen.
export default async function Home() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const dbBruger = user ? await hentBrugerMedTenant(user.id) : null;

  return (
    <main className="flex-1 bg-zinc-50 px-6 py-10">
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <nav className="flex items-center justify-end gap-1">
          <Link
            href="/sager"
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            Gemte sager
          </Link>
          <Link
            href="/arkiv"
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            Arkiv
          </Link>
          {dbBruger?.role === "admin" && (
            <Link
              href="/admin"
              className={buttonVariants({ variant: "ghost", size: "sm" })}
            >
              Admin
            </Link>
          )}
          <form action={logout}>
            <Button type="submit" variant="ghost" size="sm">
              Log ud
            </Button>
          </form>
        </nav>

        <header className="space-y-2">
          <h1 className="font-serif text-4xl sm:text-5xl font-bold tracking-tight text-zinc-900">
            Ny sag
          </h1>
          <p className="text-zinc-600 max-w-3xl">
            Upload klage og bilag (PDF, DOCX, PNG, JPG eller ZIP). juriitech
            PAX kører en grundig analyse, finder præcedens i Pakkerejse-
            Ankenævnets afgørelser og hjælper dig hele vejen til et
            færdigt svarbrev.
          </p>
        </header>

        <UploadForm />
      </div>
    </main>
  );
}
