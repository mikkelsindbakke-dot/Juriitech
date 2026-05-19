import { buttonVariants } from "@/components/ui/button";
import { Button } from "@/components/ui/button";
import { UploadForm } from "@/components/upload-form";
import { PaxLogo } from "@/components/pax-logo";
import { createClient } from "@/lib/supabase/server";
import { hentBrugerMedTenant } from "@/lib/queries/users";
import { BrugerRolleProvider } from "@/lib/bruger-rolle";
import { LocaleProvider } from "@/lib/i18n/client";
import { lavT } from "@/lib/i18n/t";
import { logout } from "./login/actions";
import Link from "next/link";

// Forsiden ER ny-sag-flowet. Tidligere "logget ind som"-side er fjernet
// (irrelevant info — brugeren skal lande direkte i sit arbejde).
// Sekundære navigations-links (Admin, Log ud) ligger diskret i top-rækken
// så de ikke konkurrerer med headlinen.
//
// "Gemte sager" og "Arkiv" er bevidst fjernet fra navigationen — vi
// gemmer ikke længere klager på siden af GDPR/datasikkerheds-grunde.
// De underliggende ruter (/sager, /arkiv) eksisterer stadig men er
// utilgængelige fra UI'et.
export default async function Home() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const dbBruger = user ? await hentBrugerMedTenant(user.id) : null;
  const locale = dbBruger?.effektiv_sprog ?? "da";
  const t = lavT(locale);
  // Norge bruger Pakkereisenemnda i stedet for Pakkerejse-Ankenævnet — vis
  // det rigtige navn i hero-paragrafen baseret på tenant. Begge varianter
  // (samt selve hero-paragraffen som indlejrer {klageorgan}) ligger i
  // common.json under forside.*.
  const klageorgan_kort = t("forside.klageorgan_genitiv");

  return (
    <LocaleProvider locale={locale}>
    <main className="flex-1 bg-zinc-50 px-6 py-10">
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <nav className="flex items-center justify-between gap-3 flex-wrap">
          <Link
            href="/"
            aria-label={t("forside.til_forsiden_aria")}
            className="hover:opacity-80 transition-opacity"
          >
            <PaxLogo size="md" />
          </Link>
          <div className="flex items-center gap-1">
          {dbBruger?.role === "admin" && (
            <Link
              href="/admin"
              className={buttonVariants({ variant: "ghost", size: "sm" })}
            >
              {t("nav.admin")}
            </Link>
          )}
          <form action={logout}>
            <Button type="submit" variant="ghost" size="sm">
              {t("nav.log_ud")}
            </Button>
          </form>
          </div>
        </nav>

        <header className="space-y-2">
          <h1 className="font-serif text-4xl sm:text-5xl font-bold tracking-tight text-zinc-900">
            {t("forside.ny_sag_overskrift")}
          </h1>
          <p className="text-zinc-600 max-w-3xl">
            {t("forside.hero_paragraf", { klageorgan: klageorgan_kort })}
          </p>
        </header>

        <BrugerRolleProvider isAdmin={dbBruger?.role === "admin"}>
          <UploadForm />
        </BrugerRolleProvider>
      </div>
    </main>
    </LocaleProvider>
  );
}
