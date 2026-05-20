// Udløber-skærm for brugere hvis prøveperiode er slut.
//
// Proxy-helper.ts redirecter automatisk hertil når brugerens HOME
// tenant er en prøve-tenant med trial_expires_at < NOW() og endnu
// ikke konverteret til betalende kunde.
//
// Siden er bevidst minimal: ingen navigation tilbage til appen, kun
// en kontakt-knap og en logout-knap. Brugeren skal kontakte juriitech
// for at konvertere prøven til et abonnement.
import { createClient } from "@/lib/supabase/server";
import { hentProeveStatusForBruger } from "@/lib/queries/trial-gate";
import { redirect } from "next/navigation";
import { logout } from "@/app/login/actions";

export const metadata = {
  title: "Prøveperioden er udløbet — juriitech PAX",
  robots: { index: false, follow: false },
};

export default async function ProeveUdloebetPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Hvis brugeren IKKE er logget ind, sende til login-siden i stedet.
  if (!user) redirect("/login");

  // Hvis brugeren ikke faktisk har en udløbet prøveperiode, send dem
  // tilbage til root. Det forhindrer at man kan se denne side ved
  // direkte at navigere til URL'en.
  const status = await hentProeveStatusForBruger(user.id);
  if (!status.expired) redirect("/");

  const udløbDato = status.expires_at
    ? new Date(status.expires_at).toLocaleDateString("da-DK", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;

  return (
    <main className="min-h-screen bg-gradient-to-b from-zinc-50 to-zinc-100 flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-lg space-y-8">
        <div className="text-center space-y-3">
          <div className="text-5xl">⏱️</div>
          <h1 className="text-3xl font-serif font-medium tracking-tight text-zinc-900">
            Prøveperioden er udløbet
          </h1>
          {udløbDato && (
            <p className="text-sm text-zinc-500">Udløb: {udløbDato}</p>
          )}
        </div>

        <div className="rounded-2xl border border-zinc-200 bg-white p-6 space-y-4 shadow-sm">
          <p className="text-sm leading-relaxed text-zinc-700">
            Tak fordi I har prøvet juriitech PAX. Jeres prøveperiode er nu
            slut, og adgangen til klage-analyse, præcedens-søgning og
            svarbrev-generering er pauseret.
          </p>
          <p className="text-sm leading-relaxed text-zinc-700">
            Vil I fortsætte med PAX som en del af jeres faste sagsbehandling?
            Skriv til os, så får I et tilbud tilpasset jeres sagsvolumen.
          </p>
          <p className="text-xs leading-relaxed text-zinc-500">
            Jeres data er stadig krypteret og opbevares i 30 dage efter
            udløb. Konverterer I til et abonnement i den periode, fortsætter
            adgangen uden tab af jeres prøvesager.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <a
            href="mailto:hej@juriitech.com?subject=Forts%C3%A6ttelse%20efter%20pr%C3%B8veperiode%20-%20juriitech%20PAX"
            className="inline-flex items-center justify-center gap-2 rounded-md bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-zinc-800 transition"
          >
            Kontakt juriitech
          </a>
          <form action={logout}>
            <button
              type="submit"
              className="inline-flex items-center justify-center gap-2 rounded-md border border-zinc-300 bg-white px-5 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 transition w-full sm:w-auto"
            >
              Log ud
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
