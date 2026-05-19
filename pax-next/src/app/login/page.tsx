import { headers } from "next/headers";
import { LoginFormClient } from "./form-client";
import { normaliserLocale, type Locale } from "@/lib/i18n/config";
import { LocaleProvider } from "@/lib/i18n/client";

// Server-component wrapper: detekterer browser-locale fra Accept-Language
// (brugeren har endnu ikke et tenant her), og wrapper login-formularen
// i LocaleProvider så useT() returnerer korrekt sprog.
//
// Eksempler:
//   Accept-Language: nb-NO,nb;q=0.9 → 'no'
//   Accept-Language: en-US,en;q=0.9 → 'da' (default — engelsk ikke supporteret)
//   Ingen header                    → 'da'
function _detekterLocaleFraHeader(acceptLanguage: string | null): Locale {
  if (!acceptLanguage) return "da";
  // Tag det første sprog-tag (højest prioritet)
  const første = acceptLanguage.split(",")[0]?.trim().slice(0, 5);
  return normaliserLocale(første);
}

export default async function LoginPage() {
  const hdrs = await headers();
  const locale = _detekterLocaleFraHeader(hdrs.get("accept-language"));

  return (
    <LocaleProvider locale={locale}>
      <LoginFormClient />
    </LocaleProvider>
  );
}
