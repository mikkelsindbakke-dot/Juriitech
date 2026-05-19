// Side til at sætte initial adgangskode efter invitation, eller til
// at nulstille password efter "Glemt adgangskode?"-flow.
//
// Brugeren lander her via et email-link fra Supabase:
//   https://pax.juriitech.com/auth/set-password?token_hash=...&type=invite
//   https://pax.juriitech.com/auth/set-password?token_hash=...&type=recovery
//
// Supabase email-templates skal pege på /auth/set-password — ellers
// rammer brugeren middleware'ens redirect til /login og flowet brækker.
// Se rod-CLAUDE.md (Phase B4) for skabelon-konfiguration.
//
// Server Component: læser searchParams og delegerer til client-form'en.
// Token forbliver i URL'en så client kan kalde verifyOtp() — det er ok
// idet linket allerede har været i klar tekst i emailen, og vi rydder
// det fra URL'en efter succes.
//
// i18n: brugeren er endnu ikke logget ind, så locale detekteres fra
// Accept-Language-headeren (samme mønster som /login).
import Link from "next/link";
import { headers } from "next/headers";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PaxLogo } from "@/components/pax-logo";
import { SetPasswordForm } from "@/components/set-password-form";
import { normaliserLocale, type Locale } from "@/lib/i18n/config";
import { LocaleProvider } from "@/lib/i18n/client";
import { lavT } from "@/lib/i18n/t";

// Supabase EmailOtpType-værdier vi understøtter for set-password-flowet.
// Vi accepterer kun de typer der giver mening her — 'signup' og
// 'email_change' håndteres ikke (vi inviterer ikke via self-signup).
const TILLADTE_TYPER = ["invite", "recovery", "magiclink", "email"] as const;
type TilladtType = (typeof TILLADTE_TYPER)[number];

function erTilladtType(v: string): v is TilladtType {
  return (TILLADTE_TYPER as readonly string[]).includes(v);
}

// Browser-detection — samme mønster som /login.
function _detekterLocaleFraHeader(acceptLanguage: string | null): Locale {
  if (!acceptLanguage) return "da";
  const første = acceptLanguage.split(",")[0]?.trim().slice(0, 5);
  return normaliserLocale(første);
}

export default async function SetPasswordPage({
  searchParams,
}: {
  // Next.js 16: searchParams er async — skal afventes.
  searchParams: Promise<{ token_hash?: string; type?: string }>;
}) {
  const { token_hash, type } = await searchParams;
  const hdrs = await headers();
  const locale = _detekterLocaleFraHeader(hdrs.get("accept-language"));
  const t = lavT(locale);

  // Defensiv: vis nyttig fejl hvis link er ufuldstændigt eller manglende.
  if (!token_hash) {
    return (
      <LocaleProvider locale={locale}>
        <FejlSide
          titel={t("set_password.fejlside_mangler_token_titel")}
          besked={t("set_password.fejlside_mangler_token_besked")}
          tilbageTekst={t("set_password.fejlside_tilbage_til_login")}
        />
      </LocaleProvider>
    );
  }
  if (!type || !erTilladtType(type)) {
    return (
      <LocaleProvider locale={locale}>
        <FejlSide
          titel={t("set_password.fejlside_ukendt_type_titel")}
          besked={t("set_password.fejlside_ukendt_type_besked", { type: type ?? "" })}
          tilbageTekst={t("set_password.fejlside_tilbage_til_login")}
        />
      </LocaleProvider>
    );
  }

  const erInvite = type === "invite" || type === "magiclink";

  return (
    <LocaleProvider locale={locale}>
      <main className="flex flex-1 items-center justify-center bg-zinc-50 px-6 py-20">
        <div className="w-full max-w-md space-y-6">
          <div className="flex justify-center">
            <PaxLogo size="lg" />
          </div>
          <Card className="border-zinc-200 shadow-sm">
            <CardHeader className="space-y-2">
              <CardTitle className="text-2xl font-semibold tracking-tight">
                {erInvite
                  ? t("set_password.titel_invite")
                  : t("set_password.titel_recovery")}
              </CardTitle>
              <CardDescription className="text-sm text-zinc-600">
                {erInvite
                  ? t("set_password.beskrivelse_invite")
                  : t("set_password.beskrivelse_recovery")}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <SetPasswordForm
                tokenHash={token_hash}
                type={type}
                erInvite={erInvite}
              />
            </CardContent>
          </Card>
        </div>
      </main>
    </LocaleProvider>
  );
}

function FejlSide({
  titel,
  besked,
  tilbageTekst,
}: {
  titel: string;
  besked: string;
  tilbageTekst: string;
}) {
  return (
    <main className="flex flex-1 items-center justify-center bg-zinc-50 px-6 py-20">
      <div className="w-full max-w-md space-y-6">
        <div className="flex justify-center">
          <PaxLogo size="lg" />
        </div>
        <Card className="border-zinc-200 shadow-sm">
          <CardHeader className="space-y-2">
            <CardTitle className="text-xl font-semibold tracking-tight">
              {titel}
            </CardTitle>
            <CardDescription className="text-sm text-zinc-600">
              {besked}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              href="/login"
              className="inline-block text-sm text-blue-700 hover:text-blue-900 underline underline-offset-2"
            >
              {tilbageTekst}
            </Link>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
